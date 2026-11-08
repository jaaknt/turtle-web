"""Pydantic response models: the API's contract, exported as OpenAPI for the frontend's types.

Every `*_pct` field is a fraction (0.05 is 5%), matching the indicators persisted in
turtle.signal.parameters; the frontend formats them.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class HistoryPoint(BaseModel):
    """Portfolio totals at the end of one day."""

    date: date
    market_value: float
    cost_basis: float
    realized: float
    total_pnl: float
    benchmark_pnl: dict[str, float]  # by benchmark symbol, in the configured order


class Position(BaseModel):
    """One open position, valued at its latest close."""

    symbol: str
    name: str | None
    sector: str | None  # from turtle.company; None when EODHD has no fundamentals for it
    shares: float  # as the broker counts them: rescaled by any split while held
    avg_cost: float  # cost basis / shares, fees and tax included
    last_close: float  # raw, comparable with fill prices
    last_date: date  # staleness is visible
    day_change_pct: float | None  # the stock's move on the latest trading day; see ledger.OpenPosition
    market_value: float
    cost_basis: float
    unrealized: float
    unrealized_pct: float | None  # None when the cost basis is 0
    realized: float  # from partial sells so far
    first_buy: date
    days_held: int  # first buy to the last ledger day


class Portfolio(BaseModel):
    """Totals, open positions and daily history; totals.realized includes fully closed positions."""

    benchmarks: list[str]  # benchmark_pnl's keys in the configured order; JSON key order is not to be relied on
    totals: HistoryPoint | None  # None before the first transaction
    positions: list[Position]
    history: list[HistoryPoint]


class Transaction(BaseModel):
    """One fill, with the signal it was bought off."""

    reference: str
    transacted_at: datetime
    symbol: str
    name: str | None
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fee: float
    tax: float
    currency: str
    signal_id: int | None
    signal_date: date | None
    ranking: int | None
    next_open: float | None
    slippage_pct: float | None  # price / next_open - 1, for linked buys once next_open is known


class Symbol(BaseModel):
    """A symbol with bars, for the chart page's search."""

    symbol: str
    name: str | None


class Bar(BaseModel):
    """One candle."""

    time: str  # 'YYYY-MM-DD', what Lightweight Charts expects; never a datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartFill(BaseModel):
    """One fill, drawn as a marker by time only."""

    time: str  # 'YYYY-MM-DD'
    side: Literal["buy", "sell"]
    quantity: float
    price: float  # raw, as traded


class ChartData(BaseModel):
    """One symbol's candles and fills."""

    symbol: str
    name: str | None
    adjusted: bool
    bars: list[Bar]
    fills: list[ChartFill]
    avg_cost: float | None  # the open position's, from the ledger; None when flat or adjusted


class SignalRow(BaseModel):
    """One gated signal, with its entry and current price."""

    id: int
    symbol: str
    name: str | None
    signal_date: date
    ranking: int
    next_open: float | None  # absent until the nightly re-scan after a bar after signal_date
    pct_vs_sma50: float | None
    adr_pct: float | None
    entry_date: date | None  # None until the bar after signal_date is loaded: render "pending"
    entry_price: float | None
    curr_price: float | None
    curr_date: date | None
    change_pct: float | None  # adjusted, so split-safe total return from entry
    bought: bool


class Metrics(BaseModel):
    """The metrics table's column for one series; see analytics.Metrics. A ratio over a zero denominator is None."""

    cumulative_return: float
    cagr: float
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float  # ≤ 0
    longest_drawdown_days: int  # calendar days
    best_day: float
    worst_day: float
    best_month: float
    worst_month: float
    win_rate_days: float | None  # of non-zero days
    win_rate_months: float | None
    beta: float | None  # vs the first benchmark; the portfolio's only
    correlation: float | None


class PeriodReturn(BaseModel):
    """A month's or a year's compounded return."""

    year: int
    month: int | None  # None for a yearly return
    value: float
    partial: bool  # the series' first or last period, so it may not cover the whole of it


class DrawdownPeriod(BaseModel):
    """One stretch under water."""

    start: date
    valley: date
    end: date  # the last day under water
    depth: float  # ≤ 0
    days: int  # calendar days from start to end, both included
    ongoing: bool  # still under water on the last day


class Bin(BaseModel):
    """One histogram bar: count of values in [lower, upper)."""

    lower: float
    upper: float
    count: int


class SeriesAnalytics(BaseModel):
    """One series' metrics and period returns."""

    symbol: str  # "portfolio" (analytics.PORTFOLIO), or a benchmark symbol
    metrics: Metrics
    monthly: list[PeriodReturn]
    yearly: list[PeriodReturn]


class CurvePoint(BaseModel):
    """Every series' cumulative return and drawdown at the end of one day."""

    date: date
    cumulative: dict[str, float]  # by series symbol
    drawdown: dict[str, float]  # ≤ 0


class Analytics(BaseModel):
    """The analytics page: time-weighted returns of the portfolio against each benchmark held; see analytics.Report."""

    start: date | None  # None before the first fill
    end: date | None
    trading_days: int  # the page flags annualised figures while this is under 252
    benchmarks: list[str]  # configured order, as on /api/portfolio
    series: list[SeriesAnalytics]  # the portfolio first, then each benchmark
    curve: list[CurvePoint]
    drawdowns: list[DrawdownPeriod]  # the portfolio's five worst
    histogram_monthly: list[Bin]  # the portfolio's
    histogram_daily: list[Bin]
