"""The read-only connection pool, and loading the ledger through it."""

from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from turtleweb import ledger, sql
from turtleweb.settings import Settings

LOOKBACK_DAYS = 7  # closes before the first fill, so a fill on a day without a bar has a price


def make_engine(s: Settings) -> sa.Engine:
    """Build the read-only connection pool.

    The connect options repeat the turtle_web role's settings, so the demo database (where you
    connect as postgres) is read-only too. create_engine connects lazily: nothing here touches
    the database until the first query.

    Args:
        s: Settings holding the connection parameters.

    Returns:
        sa.Engine: A small pool; the dashboard has one user.
    """
    url = sa.URL.create(
        "postgresql+psycopg", username=s.db_user, password=s.db_password, host=s.db_host, port=s.db_port, database=s.db_name
    )
    return sa.create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=10000 -c jit=off"},
    )


def fetch(engine: sa.Engine, statement: sa.TextClause, **params: Any) -> list[sa.RowMapping]:
    """Run one statement from turtleweb.sql and return its rows."""
    with engine.connect() as conn:
        return list(conn.execute(statement, params).mappings())


def replay(engine: sa.Engine, transactions: list[sa.RowMapping], benchmarks: list[str]) -> ledger.Ledger:
    """Replay every transaction (TRANSACTIONS rows) over the closes it needs."""
    fills = [
        ledger.Fill(t["transacted_at"].date(), t["symbol"], t["side"], t["quantity"], t["price"], t["fee"], t["tax"]) for t in transactions
    ]
    if not fills:
        return ledger.build([], [], benchmarks)
    symbols = sorted({f.symbol for f in fills} | set(benchmarks))
    start = min(f.date for f in fills) - timedelta(days=LOOKBACK_DAYS)
    rows = fetch(engine, sql.CLOSES, symbols=symbols, start=start)
    closes = [ledger.Close(r["symbol"], r["date"], r["close"], r["adjusted_close"]) for r in rows]
    return ledger.build(fills, closes, benchmarks)
