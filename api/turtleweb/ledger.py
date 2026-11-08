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
    - Each benchmark is a shadow portfolio: every buy puts the same cash into it, and every sell
      takes out the same fraction of it. Several benchmarks run side by side, independently.
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
    # The stock's price move into the benchmark's last bar from the ledger day before it, in adjusted
    # closes (a split is not a drop). A price move, not the holding's: a fill that day changes the
    # value by more, and a position bought that day still shows the stock's move. Anchored on the
    # benchmark's last bar, so a fill imported before that day's bars does not zero the column.
    # 0 for a stale symbol, whose price is forward-filled; None when that bar is the first ledger day.
    day_change_pct: float | None
    first_buy: date


@dataclass(frozen=True)
class Point:
    """Portfolio totals at the end of one day."""

    date: date
    market_value: float
    cost_basis: float
    realized: float
    total_pnl: float
    benchmark_pnl: dict[str, float]  # by benchmark symbol, in the order given to build()
    # Cash flows for time-weighted returns (docs/specs/portfolio.md): there is no cash account, so
    # these are what moves market value without being a gain or a loss.
    bought: float  # buy cost applied this day, fees and tax included
    sold: float  # sell proceeds applied this day, net of fees and tax
    benchmark_close: dict[str, float]  # each benchmark's forward-filled adjusted close, same order


@dataclass(frozen=True)
class Ledger:
    """The result of replaying every fill."""

    positions: list[OpenPosition]  # open only, by symbol
    # The last day; realized includes fully closed positions. None without fills. Its bought and sold
    # are that day's cash flows, not running totals: sum them over history for those.
    totals: Point | None
    history: list[Point]  # one per calendar day from the first fill


@dataclass
class _Position:
    # Shadow position per benchmark: plain dicts holding every benchmark from the start (see
    # _new_position), so a benchmark that was never set up is a KeyError, not a silent 0.
    bench_units: dict[str, float]
    bench_realized: dict[str, float]
    shares: float = 0.0  # as the broker counts them: rescaled by every split while held
    units: float = 0.0  # shares in adjusted_close terms: sum of quantity / f at each fill
    cost: float = 0.0  # open cost basis, average-cost method, fees and tax included
    realized: float = 0.0
    first_buy: date | None = None


def _new_position(benchmarks: list[str]) -> _Position:
    return _Position(bench_units=dict.fromkeys(benchmarks, 0.0), bench_realized=dict.fromkeys(benchmarks, 0.0))


def build(fills: list[Fill], closes: list[Close], benchmarks: list[str]) -> Ledger:
    """Replay fills over the first benchmark's trading calendar.

    The calendar is the first benchmark's dates from the first fill on, plus any fill date after the
    benchmark's last bar: a fill imported before that day's bars are loaded must still count,
    valued at the previous close. Each day first takes in every close dated on or before it (so
    missing days forward-fill, and the CLOSES query's 7-day lookback seeds prices for a first fill
    on a day without a bar), rescaling held shares on a split, then applies every fill dated on or
    before it not yet applied (a fill dated on a weekend lands on the next trading day), then
    records a point.

    Args:
        fills: Every transaction, in any order; applied by date, stable within a day.
        closes: Daily closes for every traded symbol and every benchmark.
        benchmarks: Symbols the shadow portfolios buy, one each; the first one's dates form the
            calendar. A list, not one str, which would iterate as characters. A repeated symbol
            counts once: twice would buy that benchmark twice over.

    Returns:
        Ledger: Open positions as of the last day, totals, and one history point per day.

    Raises:
        LedgerError: A fill's symbol or a benchmark has no close by the day the fill is applied,
            or a sell exceeds the shares held. A ledger that silently drops a position is worse
            than a loud error naming the ticker.
    """
    benchmarks = list(dict.fromkeys(benchmarks))
    if not benchmarks:
        raise ValueError("at least one benchmark is required")
    if not fills:
        return Ledger(positions=[], totals=None, history=[])
    benchmark = benchmarks[0]

    fills = sorted(fills, key=lambda f: f.date)
    closes = sorted(closes, key=lambda c: c.date)
    bench_days = {c.date for c in closes if c.symbol == benchmark and c.date >= fills[0].date}
    last_bench_day = max(bench_days, default=date.min)
    calendar = sorted(bench_days | {f.date for f in fills if f.date > last_bench_day})

    last: dict[str, Close] = {}
    before_last_bar: dict[str, Close] = {}  # last as of the ledger day before the benchmark's last bar
    book: dict[str, _Position] = defaultdict(lambda: _new_position(benchmarks))
    history: list[Point] = []
    next_close = next_fill = 0
    for day in calendar:
        if day == last_bench_day:
            before_last_bar = dict(last)
        while next_close < len(closes) and closes[next_close].date <= day:
            c = closes[next_close]
            held = book.get(c.symbol)
            if held is not None and held.shares > _EPSILON and c.symbol in last:
                held.shares *= _split_ratio(last[c.symbol], c)
            last[c.symbol] = c
            next_close += 1
        bought = sold = 0.0
        while next_fill < len(fills) and fills[next_fill].date <= day:
            fill = fills[next_fill]
            b, s = _apply(fill, book[fill.symbol], last, benchmarks)
            bought, sold = bought + b, sold + s
            next_fill += 1
        history.append(_point(day, book, last, benchmarks, bought=bought, sold=sold))

    positions = [
        OpenPosition(
            symbol=symbol,
            shares=p.shares,
            cost=p.cost,
            realized=p.realized,
            market_value=p.units * last[symbol].adjusted_close,
            last_close=last[symbol],
            day_change_pct=_change(before_last_bar.get(symbol), last[symbol]),
            first_buy=p.first_buy,
        )
        for symbol, p in sorted(book.items())
        if p.shares > _EPSILON and p.first_buy is not None
    ]
    return Ledger(positions=positions, totals=history[-1], history=history)


def _change(before: Close | None, now: Close) -> float | None:
    """now vs before as a fraction, in adjusted closes (CLOSES returns none at 0); None without a before."""
    if before is None:
        return None
    return now.adjusted_close / before.adjusted_close - 1.0


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


def _apply(fill: Fill, p: _Position, last: dict[str, Close], benchmarks: list[str]) -> tuple[float, float]:
    """Apply one fill to its position; return its cash as (bought, sold), one of them 0."""
    for symbol in (fill.symbol, *benchmarks):
        if symbol not in last:
            raise LedgerError(f"no close for {symbol} on or before {fill.date} (fill of {fill.symbol})")
    c = last[fill.symbol]
    f = c.adjusted_close / c.close

    if fill.side == "buy":
        amount = fill.quantity * fill.price + fill.fee + fill.tax
        p.shares += fill.quantity
        p.units += fill.quantity / f
        p.cost += amount
        for bm in benchmarks:
            p.bench_units[bm] += amount / last[bm].adjusted_close
        if p.first_buy is None:
            p.first_buy = fill.date
        return amount, 0.0
    if fill.side == "sell":
        if p.shares <= _EPSILON or fill.quantity > p.shares + _EPSILON:
            raise LedgerError(f"sell of {fill.quantity} {fill.symbol} on {fill.date} exceeds the {p.shares} held")
        frac = fill.quantity / p.shares
        cost_out = p.cost * frac
        proceeds = fill.quantity * fill.price - fill.fee - fill.tax
        p.realized += proceeds - cost_out
        for bm in benchmarks:
            p.bench_realized[bm] += p.bench_units[bm] * frac * last[bm].adjusted_close - cost_out
        keep = 1.0 - frac
        p.shares *= keep
        p.units *= keep
        p.cost *= keep
        for bm in benchmarks:
            p.bench_units[bm] *= keep
        if p.shares <= _EPSILON:
            p.first_buy = None  # a later buy opens a new holding period
        return 0.0, proceeds
    raise LedgerError(f"unknown side {fill.side!r} for {fill.symbol} on {fill.date}")


def _point(day: date, book: dict[str, _Position], last: dict[str, Close], benchmarks: list[str], *, bought: float, sold: float) -> Point:
    market_value = cost_basis = realized = 0.0
    bench_units = dict.fromkeys(benchmarks, 0.0)
    bench_realized = dict.fromkeys(benchmarks, 0.0)
    for s, p in book.items():  # one pass over the book, whatever the number of benchmarks
        if p.units:
            market_value += p.units * last[s].adjusted_close
        cost_basis += p.cost
        realized += p.realized
        for bm in benchmarks:
            bench_units[bm] += p.bench_units[bm]
            bench_realized[bm] += p.bench_realized[bm]
    benchmark_close = {bm: last[bm].adjusted_close for bm in benchmarks}
    return Point(
        date=day,
        market_value=market_value,
        cost_basis=cost_basis,
        realized=realized,
        total_pnl=market_value - cost_basis + realized,
        benchmark_pnl={bm: bench_units[bm] * benchmark_close[bm] - cost_basis + bench_realized[bm] for bm in benchmarks},
        bought=bought,
        sold=sold,
        benchmark_close=benchmark_close,
    )
