"""Portfolio analytics: return series and the metrics over them (docs/specs/portfolio.md).

A pure module, like the ledger: no database, no FastAPI. Everything here is a function of the
ledger's history, so it is tested on hand-built ledgers.
"""

from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from turtleweb.ledger import Ledger, Point


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
