"""Portfolio analytics: return series and the metrics over them (docs/specs/portfolio.md).

A pure module, like the ledger: no database, no FastAPI. Everything here is a function of the
ledger's history, so it is tested on hand-built ledgers.
"""

import math
import operator
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import accumulate, groupby, pairwise

from turtleweb.ledger import Ledger, Point

# quantstats' conventions throughout (risk-free rate 0, 252 periods a year, sample standard
# deviation), so these figures match turtle-backtest's reports; tests/test_analytics_oracle.py
# holds them to quantstats' own numbers.
PERIODS = 252
# A drawdown shallower than this is float noise: a recovery to the exact old peak can compute as
# peak * (1 - 2e-16), which would otherwise keep the drawdown open. quantstats compares with 0.
_DD_NOISE = 1e-12


@dataclass(frozen=True)
class Returns:
    """One daily return per date, as fractions."""

    dates: list[date]
    values: list[float]


def _series_days(ledger: Ledger) -> list[Point]:
    """History up to and including ledger.last_bar: a later day's prices are yesterday's."""
    return [p for p in ledger.history if p.date <= ledger.last_bar]


def portfolio_returns(ledger: Ledger) -> Returns:
    """Time-weighted daily returns of the holdings.

    r_t = (MV_t + S_t) / (MV_{t-1} + B_t) - 1: buys enter at the start of their day, sells leave at
    its end. So the first day runs from fill price (fees included) to close, a full sell from the
    previous close to the sell price, and a day with nothing held and nothing bought is 0.
    """
    days = _series_days(ledger)
    values: list[float] = []
    prev_value = 0.0
    for p in days:
        base = prev_value + p.bought
        values.append((p.market_value + p.sold) / base - 1.0 if base > 0 else 0.0)
        prev_value = p.market_value
    return Returns([p.date for p in days], values)


def benchmark_returns(ledger: Ledger, symbol: str) -> Returns:
    """Buy and hold of one benchmark over the portfolio's days: bought at the first day's close, so 0 that day."""
    days = _series_days(ledger)
    if not days:
        return Returns([], [])
    moves = [b.benchmark_close[symbol] / a.benchmark_close[symbol] - 1.0 for a, b in pairwise(days)]
    return Returns([p.date for p in days], [0.0, *moves])


@dataclass(frozen=True)
class Metrics:
    """The metrics table's column for one series. A ratio over a zero denominator is None."""

    cumulative_return: float
    cagr: float
    volatility: float | None  # None with fewer than 2 returns
    sharpe: float | None  # None with fewer than 2 returns, or none of them different
    sortino: float | None  # None without a down day
    calmar: float | None  # None without a drawdown
    max_drawdown: float  # ≤ 0
    longest_drawdown_days: int  # calendar days, as quantstats counts them; 0 without a drawdown
    best_day: float
    worst_day: float
    best_month: float
    worst_month: float
    win_rate_days: float | None  # of non-zero days; None when every day is 0
    win_rate_months: float | None
    beta: float | None  # vs the benchmark passed to metrics(); None without one
    correlation: float | None


@dataclass(frozen=True)
class PeriodReturn:
    """A month's or a year's compounded return."""

    year: int
    month: int | None  # None for a yearly return
    value: float
    partial: bool  # the series' first or last period, so it may not cover the whole of it


@dataclass(frozen=True)
class DrawdownPeriod:
    """One stretch under water, with quantstats' dates: end is the last day under water."""

    start: date
    valley: date
    end: date
    depth: float  # ≤ 0
    days: int  # calendar days from start to end, both included
    ongoing: bool  # still under water on the last day


@dataclass(frozen=True)
class Bin:
    """One histogram bar: count of values in [lower, upper)."""

    lower: float
    upper: float
    count: int


def _compound(values: list[float]) -> float:
    return math.prod(1.0 + v for v in values) - 1.0


def _growth(values: list[float]) -> list[float]:
    """I_t, the cumulative index, from 1 before the first return."""
    return list(accumulate((1.0 + v for v in values), operator.mul))


def cumulative(r: Returns) -> list[float]:
    """I_t - 1 per day, for the cumulative return chart."""
    return [i - 1.0 for i in _growth(r.values)]


def underwater(r: Returns) -> list[float]:
    """I_t / running peak - 1 per day, float noise as 0. The peak starts at 1, so a loss on day one is a drawdown."""
    growth = _growth(r.values)
    peaks = accumulate(growth, max, initial=1.0)
    next(peaks)  # the phantom baseline itself
    return [dd if (dd := i / peak - 1.0) < -_DD_NOISE else 0.0 for i, peak in zip(growth, peaks, strict=True)]


def drawdown_periods(r: Returns) -> list[DrawdownPeriod]:
    """Every stretch under water, deepest first."""
    periods = []
    for under, group in groupby(zip(r.dates, underwater(r), strict=True), key=lambda d: d[1] < 0):
        if under:
            run = list(group)
            (start, _), (end, _) = run[0], run[-1]
            valley, depth = min(run, key=lambda d: d[1])
            periods.append(DrawdownPeriod(start, valley, end, depth, (end - start).days + 1, ongoing=end == r.dates[-1]))
    return sorted(periods, key=lambda p: p.depth)


def _periods(r: Returns, key: Callable[[date], tuple[int, int | None]]) -> list[PeriodReturn]:
    groups = [
        (y, m, _compound([v for _, v in days])) for (y, m), days in groupby(zip(r.dates, r.values, strict=True), key=lambda d: key(d[0]))
    ]
    last = len(groups) - 1
    return [PeriodReturn(year, month, value, partial=i in (0, last)) for i, (year, month, value) in enumerate(groups)]


def monthly(r: Returns) -> list[PeriodReturn]:
    """Each calendar month's compounded return; the first and the last month are flagged partial."""
    return _periods(r, lambda d: (d.year, d.month))


def yearly(r: Returns) -> list[PeriodReturn]:
    """Each calendar year's compounded return; the first and the last year are flagged partial."""
    return _periods(r, lambda d: (d.year, None))


def histogram(values: list[float], width: float) -> list[Bin]:
    """Fixed-width bins with an edge at 0, from the lowest value's bin to the highest's, gaps included."""
    if width <= 0:
        raise ValueError(f"histogram width must be positive, not {width}")
    if not values:
        return []
    counts = Counter(_slot(v, width) for v in values)
    return [Bin(k * width, (k + 1) * width, counts[k]) for k in range(min(counts), max(counts) + 1)]


def _slot(v: float, width: float) -> int:
    """The bin index of v: k for [k * width, (k + 1) * width).

    Rounding to 9 places keeps a value on an edge in its own bin despite float division (0.06 / 0.02
    is 2.9999999999999996). A loss always lands below 0, however small it is.
    """
    if v < 0:
        return -max(1, math.ceil(round(-v / width, 9)))
    return math.floor(round(v / width, 9))


def _win_rate(values: list[float]) -> float | None:
    non_zero = [v for v in values if v != 0]
    return sum(v > 0 for v in non_zero) / len(non_zero) if non_zero else None


def metrics(r: Returns, benchmark: Returns | None = None) -> Metrics:
    """Every figure in the metrics table for one non-empty series, as quantstats computes it."""
    values = r.values
    if not values:
        raise ValueError("metrics need at least one return")
    if benchmark is not None and benchmark.dates != r.dates:
        raise ValueError("the benchmark's returns must be on the same dates as the series'")
    n = len(values)
    total = _compound(values)
    cagr = (1.0 + total) ** (PERIODS / n) - 1.0  # quantstats: years = number of returns / 252
    stdev = statistics.stdev(values) if n > 1 else None
    mean = statistics.fmean(values)
    downside = math.sqrt(sum(v * v for v in values if v < 0) / n)
    drawdowns = drawdown_periods(r)
    max_dd = min((p.depth for p in drawdowns), default=0.0)
    months = [m.value for m in monthly(r)]
    beta = correlation = None
    if benchmark is not None and n > 1 and (var_b := statistics.variance(benchmark.values)) > 0:
        beta = statistics.covariance(values, benchmark.values) / var_b
        correlation = statistics.correlation(values, benchmark.values) if stdev else None
    return Metrics(
        cumulative_return=total,
        cagr=cagr,
        volatility=stdev * math.sqrt(PERIODS) if stdev is not None else None,
        sharpe=mean / stdev * math.sqrt(PERIODS) if stdev else None,
        sortino=mean / downside * math.sqrt(PERIODS) if downside > 0 else None,
        calmar=cagr / abs(max_dd) if max_dd < 0 else None,
        max_drawdown=max_dd,
        longest_drawdown_days=max((p.days for p in drawdowns), default=0),
        best_day=max(values),
        worst_day=min(values),
        best_month=max(months),
        worst_month=min(months),
        win_rate_days=_win_rate(values),
        win_rate_months=_win_rate(months),
        beta=beta,
        correlation=correlation,
    )
