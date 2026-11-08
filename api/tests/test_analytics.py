"""The return series, one rule per test, on hand-built ledgers. No database."""

import math

import pytest

from tests.builders import BENCH, buy, closes, day, sell
from turtleweb.analytics import benchmark_returns, portfolio_returns
from turtleweb.ledger import build


def test_first_day_runs_from_the_fill_price_with_fees_to_the_close() -> None:
    ledger = build([buy(0, "A", 10, 100, fee=1)], closes("A", [101]) + closes(BENCH, [10]), [BENCH])
    assert portfolio_returns(ledger).values == pytest.approx([1010 / 1001 - 1])


def test_a_later_buy_is_not_a_gain() -> None:
    # day 1: price flat, a second buy doubles market value; the return is 0, not +100%
    fills = [buy(0, "A", 10, 100), buy(1, "A", 10, 100)]
    ledger = build(fills, closes("A", [100, 100]) + closes(BENCH, [10, 10]), [BENCH])
    assert portfolio_returns(ledger).values == pytest.approx([0, 0])


def test_a_full_sell_runs_from_the_previous_close_to_the_sell_price() -> None:
    fills = [buy(0, "A", 10, 100), sell(1, "A", 10, 105, fee=1)]
    ledger = build(fills, closes("A", [100, 104]) + closes(BENCH, [10, 10]), [BENCH])
    assert portfolio_returns(ledger).values == pytest.approx([0, 1049 / 1000 - 1])


def test_a_day_with_nothing_held_is_zero() -> None:
    fills = [buy(0, "A", 10, 100), sell(1, "A", 10, 100)]
    ledger = build(fills, closes("A", [100, 100, 120]) + closes(BENCH, [10] * 3), [BENCH])
    assert portfolio_returns(ledger).values[2] == 0


def test_a_split_at_a_flat_price_is_zero() -> None:
    raw, adj = [100.0, 100.0, 50.0], [50.0, 50.0, 50.0]  # 2:1 split on day 2
    ledger = build([buy(0, "A", 10, 100)], closes("A", raw, adj) + closes(BENCH, [10] * 3), [BENCH])
    assert portfolio_returns(ledger).values == pytest.approx([0, 0, 0])


def test_with_one_buy_the_compounded_return_is_total_pnl_over_cost() -> None:
    ledger = build([buy(0, "A", 10, 100, fee=2)], closes("A", [101, 97, 104, 110]) + closes(BENCH, [10] * 4), [BENCH])
    assert ledger.totals is not None
    compounded = math.prod(1 + r for r in portfolio_returns(ledger).values) - 1
    assert compounded == pytest.approx(ledger.totals.total_pnl / ledger.totals.cost_basis)


def test_a_fill_only_last_day_is_left_out() -> None:
    # day 2 is in the calendar only for its fill, imported before that day's bars
    fills = [buy(0, "A", 10, 100), buy(2, "A", 5, 110)]
    ledger = build(fills, closes("A", [100, 110]) + closes(BENCH, [10, 11]), [BENCH])
    assert ledger.history[-1].date == day(2)
    assert portfolio_returns(ledger).dates == [day(0), day(1)]
    assert benchmark_returns(ledger, BENCH).dates == [day(0), day(1)]


def test_a_benchmark_is_bought_at_the_first_close_and_held() -> None:
    # adjusted closes, forward-filled: QQQ has no bar on day 1
    data = closes("A", [100] * 3) + closes(BENCH, [10, 11, 12], [5, 5.5, 6.6]) + closes("QQQ.US", [20]) + closes("QQQ.US", [30], start=2)
    ledger = build([buy(0, "A", 10, 100)], data, [BENCH, "QQQ.US"])
    bench = benchmark_returns(ledger, BENCH)
    assert bench.values == pytest.approx([0, 0.10, 0.20])
    assert benchmark_returns(ledger, "QQQ.US").values == pytest.approx([0, 0, 0.50])
    assert bench.dates == portfolio_returns(ledger).dates


def test_no_fills_is_an_empty_series() -> None:
    ledger = build([], closes(BENCH, [10]), [BENCH])
    assert portfolio_returns(ledger).values == []
    assert benchmark_returns(ledger, BENCH).values == []
