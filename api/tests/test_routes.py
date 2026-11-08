"""The endpoints against the seeded demo database, through TestClient."""

import re
from collections.abc import Iterator
from dataclasses import replace
from itertools import pairwise

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from turtleweb.main import create_app
from turtleweb.routes import SYMBOLS_TTL_SECONDS
from turtleweb.settings import Settings

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SPLIT_SYMBOL = "DEMOC.US"  # 5 shares bought, then a 2:1 split while held (db/seed_demo.py)


@pytest.fixture(scope="module")
def client(demo_engine: sa.Engine, demo_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(demo_settings)) as c:
        yield c


def test_openapi_lists_all_six_routes(client: TestClient) -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {"/api/healthz", "/api/portfolio", "/api/transactions", "/api/symbols", "/api/chart/{symbol}", "/api/signals"}


def test_positions_carry_the_company_sector(client: TestClient) -> None:
    sectors = {p["symbol"]: p["sector"] for p in client.get("/api/portfolio").json()["positions"]}
    assert sectors[SPLIT_SYMBOL] == "Industrials"
    assert sectors["DEMOF.US"] is None  # no turtle.company row: the LEFT JOIN keeps the position


def test_portfolio_totals_equal_the_sums_over_positions(client: TestClient) -> None:
    body = client.get("/api/portfolio").json()
    totals, positions = body["totals"], body["positions"]
    assert len(positions) == 8
    assert totals["market_value"] == pytest.approx(sum(p["market_value"] for p in positions))
    assert totals["cost_basis"] == pytest.approx(sum(p["cost_basis"] for p in positions))
    # not realized: the totals include fully closed positions, which have no row in positions
    assert body["history"][-1] == totals


def test_split_position_is_counted_in_post_split_shares(client: TestClient) -> None:
    (position,) = [p for p in client.get("/api/portfolio").json()["positions"] if p["symbol"] == SPLIT_SYMBOL]
    assert position["shares"] == pytest.approx(10)
    # only because the demo has no dividends: in general market_value is units x adjusted_close
    assert position["market_value"] == pytest.approx(position["shares"] * position["last_close"])
    assert position["avg_cost"] == pytest.approx(position["cost_basis"] / 10)


def test_total_pnl_has_no_discontinuity(client: TestClient) -> None:
    # a mishandled split would jump total P&L by half the split position's value (~7% of the book)
    history = client.get("/api/portfolio").json()["history"]
    for prev, curr in pairwise(history):
        assert abs(curr["total_pnl"] - prev["total_pnl"]) < 0.05 * curr["market_value"], curr["date"]


def test_history_carries_every_benchmark_in_the_configured_order(client: TestClient) -> None:
    body = client.get("/api/portfolio").json()
    assert body["benchmarks"] == ["BENCH.US", "BENCHQ.US"]
    history = body["history"]
    assert all(sorted(h["benchmark_pnl"]) == ["BENCH.US", "BENCHQ.US"] for h in history)
    assert history[-1]["benchmark_pnl"]["BENCH.US"] != history[-1]["benchmark_pnl"]["BENCHQ.US"]


def test_transactions_have_slippage_only_for_linked_buys(client: TestClient) -> None:
    rows = client.get("/api/transactions").json()
    assert len(rows) == 9
    for t in rows:
        if t["side"] == "buy" and t["next_open"] is not None:
            assert t["slippage_pct"] == pytest.approx(t["price"] / t["next_open"] - 1)
        else:
            assert t["slippage_pct"] is None
    assert sum(1 for t in rows if t["signal_id"] is None and t["side"] == "buy") == 1


def test_symbols_are_cached_for_an_hour(client: TestClient) -> None:
    response = client.get("/api/symbols")
    assert response.headers["cache-control"] == "max-age=3600"
    assert len(response.json()) == 10  # 8 demo tickers and 2 benchmarks


def test_symbol_cache_reloads_after_an_hour(client: TestClient) -> None:
    client.get("/api/symbols")
    state = client.app.state  # type: ignore[attr-defined]
    state.symbols = replace(state.symbols, symbols=[], names={}, loaded_at=state.symbols.loaded_at - SYMBOLS_TTL_SECONDS - 1)
    assert len(client.get("/api/symbols").json()) == 10


def test_chart_bars_are_dates_and_the_split_shows_in_raw_candles(client: TestClient) -> None:
    response = client.get(f"/api/chart/{SPLIT_SYMBOL}")
    body = response.json()
    assert "cache-control" not in response.headers  # fills change on a statement import
    assert response.headers["content-encoding"] == "gzip"
    assert ISO_DATE.match(body["bars"][0]["time"])
    assert body["name"] == "Cobalt Demo Industries"
    assert [f["side"] for f in body["fills"]] == ["buy"]
    assert body["avg_cost"] == pytest.approx(934.5 / 10)  # from the ledger: split-aware, fees included
    closes = [b["close"] for b in body["bars"]]
    assert max(a / b for a, b in pairwise(closes)) > 1.8  # the raw 2:1 drop


def test_adjusted_chart_is_continuous_and_has_no_cost_line(client: TestClient) -> None:
    body = client.get(f"/api/chart/{SPLIT_SYMBOL}", params={"adjusted": True}).json()
    closes = [b["close"] for b in body["bars"]]
    assert max(a / b for a, b in pairwise(closes)) < 1.2
    assert body["avg_cost"] is None


def test_adjusted_volume_keeps_dollar_volume(client: TestClient) -> None:
    raw = client.get(f"/api/chart/{SPLIT_SYMBOL}").json()["bars"]
    adj = client.get(f"/api/chart/{SPLIT_SYMBOL}", params={"adjusted": True}).json()["bars"]
    for r, a in zip(raw, adj, strict=True):
        assert a["volume"] * a["close"] == pytest.approx(r["volume"] * r["close"]), r["time"]


def test_unknown_chart_symbol_is_404(client: TestClient) -> None:
    assert client.get("/api/chart/NOPE.US").status_code == 404


def test_signals_gate_includes_the_boundary(client: TestClient) -> None:
    at_44 = client.get("/api/signals", params={"min_ranking": 44}).json()
    at_45 = client.get("/api/signals", params={"min_ranking": 45}).json()
    assert any(s["ranking"] == 44 for s in at_44)
    assert not any(s["ranking"] == 44 for s in at_45)
    assert all(s["ranking"] >= 44 for s in at_44)
    assert len(at_44) == len(at_45) + 1


def test_last_day_signal_is_pending(client: TestClient) -> None:
    rows = client.get("/api/signals", params={"min_ranking": 0}).json()
    latest = max(rows, key=lambda s: s["signal_date"])
    assert latest["entry_price"] is None
    assert latest["next_open"] is None
    assert latest["change_pct"] is None
    assert any(s["bought"] for s in rows)


@pytest.mark.parametrize("params", [{"days": 0}, {"days": 367}, {"min_ranking": -1}, {"min_ranking": 101}])
def test_signals_reject_out_of_range_parameters(client: TestClient, params: dict[str, int]) -> None:
    assert client.get("/api/signals", params=params).status_code == 422


def test_ledger_error_is_a_500_naming_the_ticker(demo_engine: sa.Engine, demo_settings: Settings) -> None:
    settings = demo_settings.model_copy(update={"benchmark_symbols": ["BENCH.US", "MISSING.US"]})
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        response = c.get("/api/portfolio")
    assert response.status_code == 500
    assert "MISSING.US" in response.json()["detail"]


def test_chart_survives_a_ledger_error_without_its_cost_line(demo_engine: sa.Engine, demo_settings: Settings) -> None:
    settings = demo_settings.model_copy(update={"benchmark_symbols": ["MISSING.US"]})
    with TestClient(create_app(settings)) as c:
        response = c.get(f"/api/chart/{SPLIT_SYMBOL}")
    assert response.status_code == 200
    body = response.json()
    assert body["fills"]
    assert body["avg_cost"] is None
