"""Every daily_bars access in turtleweb.sql must be an index scan on pk_daily_bars.

The demo tables are tiny, so the planner would happily seq-scan them; sequential and bitmap
scans are disabled for the test, which then checks that the index *can* serve each access with
both a symbol and a date bound. On the live 20M-row table that is the plan the planner picks.
"""

import json
import re
from datetime import date, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from turtleweb import sql
from turtleweb.settings import Settings

START = date.today() - timedelta(days=400)
# A comparison on daily_bars' own date column; a bare substring would also match s.signal_date
DATE_BOUND = re.compile(r"\bdate\s*(?:[<>]=?|=)")


def _params(settings: Settings) -> dict[str, dict[str, Any]]:
    return {
        "TRANSACTIONS": {},
        "CLOSES": {"symbols": ["DEMOA.US", *settings.benchmark_symbols], "start": START},
        "BARS": {"symbol": "DEMOC.US", "start": START},
        "SIGNALS": {
            "strategy": settings.signal_strategy,
            "ranking_strategy": settings.signal_ranking_strategy,
            "days": 90,
            "min_ranking": 44,
        },
        "SYMBOLS": {},
    }


def _daily_bars_scans(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Every plan node that reads turtle.daily_bars, at any depth."""
    found = [node] if node.get("Relation Name") == "daily_bars" else []
    for child in node.get("Plans", []):
        found += _daily_bars_scans(child)
    return found


def _explain(engine: sa.Engine, name: str, params: dict[str, Any]) -> dict[str, Any]:
    statement: sa.TextClause = getattr(sql, name)
    with engine.connect() as conn:
        conn.execute(sa.text("SET LOCAL enable_seqscan = off"))
        conn.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
        raw = conn.execute(sa.text("EXPLAIN (ANALYZE, FORMAT JSON) " + statement.text), params).scalar_one()
    plan: dict[str, Any] = (raw if isinstance(raw, list) else json.loads(raw))[0]["Plan"]
    return plan


@pytest.mark.parametrize("name", ["TRANSACTIONS", "CLOSES", "BARS", "SIGNALS", "SYMBOLS"])
def test_daily_bars_is_read_through_its_primary_key(name: str, demo_engine: sa.Engine, demo_settings: Settings) -> None:
    plan = _explain(demo_engine, name, _params(demo_settings)[name])
    scans = _daily_bars_scans(plan)
    assert bool(scans) == (name != "TRANSACTIONS"), "a statement gained or lost its daily_bars access"
    for scan in scans:
        assert scan["Node Type"] in ("Index Scan", "Index Only Scan"), scan["Node Type"]
        assert scan["Index Name"] == "pk_daily_bars"
        if name == "SYMBOLS":
            continue  # the loose index scan probes symbols only, and its first min() has no bound at all
        cond = scan["Index Cond"]
        assert re.search(r"\bsymbol\s*=", cond), cond
        assert DATE_BOUND.search(cond), cond


def test_every_statement_returns_rows_on_the_demo_data(demo_engine: sa.Engine, demo_settings: Settings) -> None:
    params = _params(demo_settings)
    with demo_engine.connect() as conn:
        for name, p in params.items():
            assert conn.execute(getattr(sql, name), p).first() is not None, name
