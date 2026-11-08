"""Transactions plus daily closes in, positions and daily P&L history out.

A pure function, no database: tests/test_ledger.py pins each rule with hand-built fixtures.

Conventions:
    - Cost basis includes fees and tax; sells use the average-cost method.
    - Market value is split-safe: a position is held in `units` of adjusted_close, fixed at each
      fill (units = quantity / f, f = adjusted_close / close on the fill date), so a split or a
      dividend adjustment never moves it.
    - `shares` follows the broker: a split while held rescales it, so a sell quoted in post-split
      shares matches. There is no split table, so splits are detected from the bars: on a split
      day f jumps by the split ratio (x2 for 2:1), while an ex-dividend day moves it a few percent.
    - Every comparison of share counts allows a float tolerance of 1e-9, so fractional shares
      (0.1 + 0.2 sold as 0.3) neither raise a false oversell nor leave a ghost position.
    - The benchmark is a shadow portfolio: every buy puts the same cash into the benchmark, and
      every sell takes out the same fraction of it.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

_EPSILON = 1e-9  # shares left after selling everything, as float arithmetic leaves them
_SPLIT_THRESHOLD = 0.25  # a day-over-day change in f beyond this is a split, not a dividend
_SPLIT_MAX_DENOMINATOR = 4  # "N for M" with M <= 4: 2, 3/2, 4/3, and reverse 1/10, 1/20, 1/50


class LedgerError(ValueError):
    """The fills and closes cannot be replayed: the message names the symbol and date."""


@dataclass(frozen=True)
class Fill:
    """One transaction."""

    date: date
    symbol: str
    side: str  # 'buy' | 'sell'
    quantity: float
    price: float
    fee: float
    tax: float


@dataclass(frozen=True)
class Close:
    """One symbol's raw and adjusted close on one day."""

    symbol: str
    date: date
    close: float
    adjusted_close: float


@dataclass(frozen=True)
class OpenPosition:
    """A position still held after the last day, valued at its latest close."""

    symbol: str
    shares: float  # in today's terms: rescaled by every split while held
    cost: float  # open cost basis, fees and tax included
    realized: float  # from partial sells so far
    market_value: float
    last_close: Close  # its date shows staleness; close is raw, comparable with fill prices
    first_buy: date


@dataclass(frozen=True)
class Point:
    """Portfolio totals at the end of one day."""

    date: date
    market_value: float
    cost_basis: float
    realized: float
    total_pnl: float
    benchmark_pnl: float


@dataclass(frozen=True)
class Ledger:
    """The result of replaying every fill."""

    positions: list[OpenPosition]  # open only, by symbol
    totals: Point | None  # the last day; realized includes fully closed positions. None without fills
    history: list[Point]  # one per calendar day from the first fill


@dataclass
class _Position:
    shares: float = 0.0  # as the broker counts them: rescaled by every split while held
    units: float = 0.0  # shares in adjusted_close terms: sum of quantity / f at each fill
    cost: float = 0.0  # open cost basis, average-cost method, fees and tax included
    realized: float = 0.0
    bench_units: float = 0.0  # shadow position in the benchmark
    bench_realized: float = 0.0
    first_buy: date | None = None


def build(fills: list[Fill], closes: list[Close], benchmark: str) -> Ledger:
    """Replay fills over the benchmark's trading calendar.

    The calendar is the benchmark's dates from the first fill on, plus any fill date after the
    benchmark's last bar: a fill imported before that day's bars are loaded must still count,
    valued at the previous close. Each day first takes in every close dated on or before it (so
    missing days forward-fill, and the CLOSES query's 7-day lookback seeds prices for a first fill
    on a day without a bar), rescaling held shares on a split, then applies every fill dated on or
    before it not yet applied (a fill dated on a weekend lands on the next trading day), then
    records a point.

    Args:
        fills: Every transaction, in any order; applied by date, stable within a day.
        closes: Daily closes for every traded symbol and the benchmark.
        benchmark: Symbol whose dates form the calendar and which the shadow portfolio buys.

    Returns:
        Ledger: Open positions as of the last day, totals, and one history point per day.

    Raises:
        LedgerError: A fill's symbol or the benchmark has no close by the day the fill is applied,
            or a sell exceeds the shares held. A ledger that silently drops a position is worse
            than a loud error naming the ticker.
    """
    if not fills:
        return Ledger(positions=[], totals=None, history=[])

    fills = sorted(fills, key=lambda f: f.date)
    closes = sorted(closes, key=lambda c: c.date)
    bench_days = {c.date for c in closes if c.symbol == benchmark and c.date >= fills[0].date}
    last_bench_day = max(bench_days, default=date.min)
    calendar = sorted(bench_days | {f.date for f in fills if f.date > last_bench_day})

    last: dict[str, Close] = {}
    book: dict[str, _Position] = defaultdict(_Position)
    history: list[Point] = []
    next_close = next_fill = 0
    for day in calendar:
        while next_close < len(closes) and closes[next_close].date <= day:
            c = closes[next_close]
            held = book.get(c.symbol)
            if held is not None and held.shares > _EPSILON and c.symbol in last:
                held.shares *= _split_ratio(last[c.symbol], c)
            last[c.symbol] = c
            next_close += 1
        while next_fill < len(fills) and fills[next_fill].date <= day:
            _apply(fills[next_fill], book[fills[next_fill].symbol], last, benchmark)
            next_fill += 1
        history.append(_point(day, book, last, benchmark))

    positions = [
        OpenPosition(
            symbol=symbol,
            shares=p.shares,
            cost=p.cost,
            realized=p.realized,
            market_value=p.units * last[symbol].adjusted_close,
            last_close=last[symbol],
            first_buy=p.first_buy,
        )
        for symbol, p in sorted(book.items())
        if p.shares > _EPSILON and p.first_buy is not None
    ]
    return Ledger(positions=positions, totals=history[-1], history=history)


def _split_ratio(prev: Close, curr: Close) -> float:
    """Shares after per share before, between two consecutive closes of one symbol; 1 if no split.

    The raw ratio carries float noise and any same-day dividend, so it snaps to the nearest "N for
    M" split. A reverse split snaps through its inverse, so 1-for-20 stays 1/20.
    """
    ratio = (curr.adjusted_close / curr.close) / (prev.adjusted_close / prev.close)
    if abs(ratio - 1.0) <= _SPLIT_THRESHOLD:
        return 1.0
    if ratio >= 1.0:
        return float(Fraction(ratio).limit_denominator(_SPLIT_MAX_DENOMINATOR))
    return float(1 / Fraction(1 / ratio).limit_denominator(_SPLIT_MAX_DENOMINATOR))


def _apply(fill: Fill, p: _Position, last: dict[str, Close], benchmark: str) -> None:
    for symbol in (fill.symbol, benchmark):
        if symbol not in last:
            raise LedgerError(f"no close for {symbol} on or before {fill.date} (fill of {fill.symbol})")
    c = last[fill.symbol]
    f = c.adjusted_close / c.close
    b = last[benchmark].adjusted_close

    if fill.side == "buy":
        amount = fill.quantity * fill.price + fill.fee + fill.tax
        p.shares += fill.quantity
        p.units += fill.quantity / f
        p.cost += amount
        p.bench_units += amount / b
        if p.first_buy is None:
            p.first_buy = fill.date
    elif fill.side == "sell":
        if fill.quantity > p.shares + _EPSILON:
            raise LedgerError(f"sell of {fill.quantity} {fill.symbol} on {fill.date} exceeds the {p.shares} held")
        frac = fill.quantity / p.shares
        cost_out = p.cost * frac
        p.realized += (fill.quantity * fill.price - fill.fee - fill.tax) - cost_out
        p.bench_realized += p.bench_units * frac * b - cost_out
        keep = 1.0 - frac
        p.shares *= keep
        p.units *= keep
        p.cost *= keep
        p.bench_units *= keep
        if p.shares <= _EPSILON:
            p.first_buy = None  # a later buy opens a new holding period
    else:
        raise LedgerError(f"unknown side {fill.side!r} for {fill.symbol} on {fill.date}")


def _point(day: date, book: dict[str, _Position], last: dict[str, Close], benchmark: str) -> Point:
    b = last[benchmark].adjusted_close
    market_value = sum(p.units * last[s].adjusted_close for s, p in book.items() if p.units)
    cost_basis = sum(p.cost for p in book.values())
    realized = sum(p.realized for p in book.values())
    bench_value = sum(p.bench_units for p in book.values()) * b
    bench_realized = sum(p.bench_realized for p in book.values())
    return Point(
        date=day,
        market_value=market_value,
        cost_basis=cost_basis,
        realized=realized,
        total_pnl=market_value - cost_basis + realized,
        benchmark_pnl=bench_value - cost_basis + bench_realized,
    )
