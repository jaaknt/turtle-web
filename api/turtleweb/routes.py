"""The /api/* endpoints.

Every endpoint is a plain `def`, never `async def`: the engine is sync, and FastAPI runs `def`
endpoints in a threadpool, whereas an `async def` calling a sync engine would block the event loop.
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query, Request, Response

from turtleweb import ledger, sql
from turtleweb.models import Bar, ChartData, ChartFill, HistoryPoint, Portfolio, Position, SignalRow, Symbol, Transaction
from turtleweb.settings import Settings

log = logging.getLogger(__name__)
router = APIRouter()

CACHE_FOR_AN_HOUR = "max-age=3600"  # the symbol list changes once a night
SYMBOLS_TTL_SECONDS = 3600  # matches the max-age above
LOOKBACK_DAYS = 7  # closes before the first fill, so a fill on a day without a bar has a price
CHART_YEARS = 3


def _engine(request: Request) -> sa.Engine:
    engine: sa.Engine = request.app.state.engine
    return engine


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _rows(request: Request, statement: sa.TextClause, **params: Any) -> list[sa.RowMapping]:
    with _engine(request).connect() as conn:
        return list(conn.execute(statement, params).mappings())


def _transactions(request: Request) -> list[sa.RowMapping]:
    return _rows(request, sql.TRANSACTIONS)


def _ledger(request: Request, transactions: list[sa.RowMapping]) -> ledger.Ledger:
    """Replay every transaction over the closes it needs."""
    fills = [
        ledger.Fill(t["transacted_at"].date(), t["symbol"], t["side"], t["quantity"], t["price"], t["fee"], t["tax"]) for t in transactions
    ]
    benchmarks = _settings(request).benchmark_symbols
    if not fills:
        return ledger.build([], [], benchmarks)
    symbols = sorted({f.symbol for f in fills} | set(benchmarks))
    start = min(f.date for f in fills) - timedelta(days=LOOKBACK_DAYS)
    rows = _rows(request, sql.CLOSES, symbols=symbols, start=start)
    closes = [ledger.Close(r["symbol"], r["date"], r["close"], r["adjusted_close"]) for r in rows]
    return ledger.build(fills, closes, benchmarks)


@dataclass(frozen=True)
class SymbolCache:
    """Every symbol with bars, and when it was loaded."""

    loaded_at: float  # time.monotonic()
    symbols: list[Symbol]
    names: dict[str, str | None]


def _symbols(request: Request) -> SymbolCache:
    """The symbol list, reloaded once it is older than an hour, so a ticker the nightly load adds
    shows up without a restart.

    Two concurrent requests may both reload it, which is harmless.
    """
    cache: SymbolCache | None = request.app.state.symbols
    if cache is None or time.monotonic() - cache.loaded_at > SYMBOLS_TTL_SECONDS:
        symbols = [Symbol(symbol=r["symbol"], name=r["name"]) for r in _rows(request, sql.SYMBOLS)]
        cache = SymbolCache(time.monotonic(), symbols, {s.symbol: s.name for s in symbols})
        request.app.state.symbols = cache
    return cache


def _point(p: ledger.Point) -> HistoryPoint:
    return HistoryPoint.model_validate(p, from_attributes=True)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the process is up, without querying the database.

    Postgres on the VPS can refuse connections after a reboot; a health check that queried would
    turn that into a restart loop instead of a single failed request.
    """
    return {"status": "ok"}


@router.get("/portfolio", response_model=Portfolio)
def portfolio(request: Request) -> Portfolio:
    """Open positions, totals and daily P&L history against each shadow benchmark.

    Args:
        request: The incoming request, carrying the engine and settings.
    """
    transactions = _transactions(request)
    names = {t["symbol"]: t["name"] for t in transactions}
    sectors = {t["symbol"]: t["sector"] for t in transactions}
    result = _ledger(request, transactions)
    benchmarks = _settings(request).benchmark_symbols
    if result.totals is None:
        return Portfolio(benchmarks=benchmarks, totals=None, positions=[], history=[])
    as_of = result.totals.date
    positions = [
        Position(
            symbol=p.symbol,
            name=names.get(p.symbol),
            sector=sectors.get(p.symbol),
            shares=p.shares,
            avg_cost=p.cost / p.shares,
            last_close=p.last_close.close,
            last_date=p.last_close.date,
            day_change_pct=p.day_change_pct,
            market_value=p.market_value,
            cost_basis=p.cost,
            unrealized=p.market_value - p.cost,
            unrealized_pct=p.market_value / p.cost - 1.0 if p.cost else None,
            realized=p.realized,
            first_buy=p.first_buy,
            days_held=(as_of - p.first_buy).days,
        )
        for p in result.positions
    ]
    return Portfolio(
        benchmarks=benchmarks,
        totals=_point(result.totals),
        positions=positions,
        history=[_point(p) for p in result.history],
    )


@router.get("/transactions", response_model=list[Transaction])
def transactions(request: Request) -> list[Transaction]:
    """Every fill, oldest first, with its signal and the slippage against the signal's next open.

    Args:
        request: The incoming request, carrying the engine.
    """
    result = []
    for t in _transactions(request):
        next_open = t["next_open"]
        slippage = t["price"] / next_open - 1.0 if t["side"] == "buy" and next_open else None
        result.append(Transaction(**t, slippage_pct=slippage))
    return result


@router.get("/symbols", response_model=list[Symbol])
def symbols(request: Request, response: Response) -> list[Symbol]:
    """Every symbol with bars, for the chart page's search.

    Args:
        request: The incoming request, carrying the engine and the symbol cache.
        response: Used to set Cache-Control.
    """
    response.headers["Cache-Control"] = CACHE_FOR_AN_HOUR
    return _symbols(request).symbols


@router.get("/chart/{symbol}", response_model=ChartData)
def chart(request: Request, symbol: str, start: date | None = None, adjusted: bool = False) -> ChartData:
    """One symbol's daily candles, its fills, and the open position's average cost.

    Not cached: its fills and avg_cost change as soon as a statement is imported.

    Args:
        request: The incoming request, carrying the engine and settings.
        symbol: Ticker code, such as AAPL.US.
        start: First bar date; defaults to three years back.
        adjusted: Scale O/H/L/C by adjusted_close / close per bar, and volume by its inverse, so a
            split shows in neither. The fills and the average-cost line stay raw, so avg_cost is
            None on adjusted candles.
    """
    start = start or date.today() - timedelta(days=365 * CHART_YEARS)
    rows = _rows(request, sql.BARS, symbol=symbol, start=start)
    if not rows:
        raise HTTPException(status_code=404, detail=f"no bars for {symbol} since {start}")

    bars = []
    for r in rows:
        k = r["adjusted_close"] / r["close"] if adjusted else 1.0
        bars.append(
            Bar(
                time=r["date"].isoformat(),
                open=r["open"] * k,
                high=r["high"] * k,
                low=r["low"] * k,
                close=r["close"] * k,
                volume=(r["volume"] or 0) / k,
            )
        )

    transactions = _transactions(request)
    fills = [
        ChartFill(time=t["transacted_at"].date().isoformat(), side=t["side"], quantity=t["quantity"], price=t["price"])
        for t in transactions
        if t["symbol"] == symbol
    ]

    # From the ledger, so it is split-aware and equals the positions page's avg_cost. The ledger
    # replays every ticker, so an error in another one only drops this line; /portfolio reports it.
    avg_cost = None
    if fills and not adjusted:
        try:
            held = [p for p in _ledger(request, transactions).positions if p.symbol == symbol]
        except ledger.LedgerError as exc:
            log.warning("chart %s without avg_cost: %s", symbol, exc)
            held = []
        avg_cost = held[0].cost / held[0].shares if held else None

    name = _symbols(request).names.get(symbol)
    return ChartData(symbol=symbol, name=name, adjusted=adjusted, bars=bars, fills=fills, avg_cost=avg_cost)


@router.get("/signals", response_model=list[SignalRow])
def signals(
    request: Request,
    days: Annotated[int, Query(ge=1, le=366)] = 90,
    min_ranking: Annotated[int, Query(ge=0, le=100)] = 44,
) -> list[SignalRow]:
    """Signals of the configured strategy from the last `days` days, gated at `min_ranking`.

    Validated at the edge, so a bad URL is a 422 and never a slow query.

    Args:
        request: The incoming request, carrying the engine and settings.
        days: How far back to look, in calendar days.
        min_ranking: The gate; kept when ranking >= min_ranking, so a signal scoring exactly the
            gate is included.
    """
    s = _settings(request)
    rows = _rows(
        request,
        sql.SIGNALS,
        strategy=s.signal_strategy,
        ranking_strategy=s.signal_ranking_strategy,
        days=days,
        min_ranking=min_ranking,
    )
    return [SignalRow(**r) for r in rows]
