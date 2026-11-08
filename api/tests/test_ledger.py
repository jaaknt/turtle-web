"""The ledger's rules, one per test, on hand-built fixtures. No database."""

import re
from datetime import date, timedelta

import pytest

from turtleweb.ledger import Close, Fill, LedgerError, build

BENCH = "BENCH.US"
D0 = date(2026, 1, 5)  # a Monday


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def closes(symbol: str, prices: list[float], adjusted: list[float] | None = None, start: int = 0) -> list[Close]:
    """One close per day from day(start); adjusted defaults to the raw price."""
    adjusted = adjusted or prices
    return [Close(symbol, day(start + i), c, a) for i, (c, a) in enumerate(zip(prices, adjusted, strict=True))]


def buy(n: int, symbol: str, quantity: float, price: float, fee: float = 0.0) -> Fill:
    return Fill(day(n), symbol, "buy", quantity, price, fee, 0.0)


def sell(n: int, symbol: str, quantity: float, price: float, fee: float = 0.0) -> Fill:
    return Fill(day(n), symbol, "sell", quantity, price, fee, 0.0)


def test_single_buy_at_a_flat_price_is_down_exactly_the_fee() -> None:
    ledger = build([buy(0, "A", 10, 100, fee=1)], closes("A", [100] * 3) + closes(BENCH, [50] * 3), [BENCH])
    (position,) = ledger.positions
    assert position.market_value - position.cost == pytest.approx(-1)
    assert position.realized == 0
    assert ledger.totals is not None
    assert ledger.totals.total_pnl == pytest.approx(-1)


def test_split_while_held_leaves_market_value_unchanged() -> None:
    # 2:1 split on day 2: raw close halves, adjusted is continuous (earlier adjusted = close / 2)
    raw = [100.0, 100.0, 50.0, 50.0]
    adj = [50.0, 50.0, 50.0, 50.0]
    ledger = build([buy(0, "A", 10, 100)], closes("A", raw, adj) + closes(BENCH, [10] * 4), [BENCH])
    values = [p.market_value for p in ledger.history]
    assert values == pytest.approx([1000.0] * 4)
    assert ledger.positions[0].last_close.close == 50  # raw price, comparable with fills, after the split
    assert ledger.positions[0].shares == 20  # as the broker counts them after the split


SPLIT_RAW = [100.0, 100.0, 50.0, 50.0]  # 2:1 split on day 2
SPLIT_ADJ = [50.0, 50.0, 50.0, 50.0]


def test_selling_every_post_split_share_closes_the_position() -> None:
    fills = [buy(0, "A", 10, 100), sell(3, "A", 20, 55)]
    ledger = build(fills, closes("A", SPLIT_RAW, SPLIT_ADJ) + closes(BENCH, [10] * 4), [BENCH])
    assert ledger.positions == []
    assert ledger.totals is not None
    assert ledger.totals.realized == pytest.approx(20 * 55 - 1000)


def test_selling_half_the_post_split_shares_keeps_half() -> None:
    fills = [buy(0, "A", 10, 100), sell(3, "A", 10, 55)]
    ledger = build(fills, closes("A", SPLIT_RAW, SPLIT_ADJ) + closes(BENCH, [10] * 4), [BENCH])
    (position,) = ledger.positions
    assert position.shares == pytest.approx(10)
    assert position.cost == pytest.approx(500)
    assert position.market_value == pytest.approx(500)


def test_reverse_split_rescales_shares_down() -> None:
    # 1:10 reverse split on day 1: raw close x10; adjusted continuous (earlier adjusted = close * 10)
    ledger = build([buy(0, "A", 100, 1)], closes("A", [1.0, 10.0], [10.0, 10.0]) + closes(BENCH, [10] * 2), [BENCH])
    assert ledger.positions[0].shares == pytest.approx(10)


def test_split_ratio_snaps_through_a_same_day_dividend() -> None:
    # 2:1 split with a 1% dividend going ex the same day: f goes 0.495 -> 1.0, a raw ratio of 2.02
    ledger = build([buy(0, "A", 10, 100)], closes("A", [100.0, 49.5], [49.5, 49.5]) + closes(BENCH, [10] * 2), [BENCH])
    assert ledger.positions[0].shares == 20


@pytest.mark.parametrize(("ratio", "expected"), [(3 / 2, 15.0), (1 / 20, 0.5), (1 / 50, 0.2)])
def test_common_split_ratios_are_recognised(ratio: float, expected: float) -> None:
    # raw close moves by 1 / ratio; adjusted is continuous
    ledger = build([buy(0, "A", 10, 100)], closes("A", [100.0, 100.0 / ratio], [100.0 / ratio] * 2) + closes(BENCH, [10] * 2), [BENCH])
    assert ledger.positions[0].shares == pytest.approx(expected)


def test_ex_dividend_day_keeps_shares_and_counts_the_dividend_as_reinvested() -> None:
    # Ex-dividend on day 1: the raw close drops by the $2 dividend, f moves 2%, well under the
    # split threshold. Dividends are not imported as transactions, so market value is total
    # return (units x adjusted_close), the same basis as the benchmark's adjusted close.
    ledger = build([buy(0, "A", 10, 100)], closes("A", [100.0, 98.0], [98.0, 98.0]) + closes(BENCH, [10] * 2), [BENCH])
    assert ledger.positions[0].shares == 10
    assert ledger.positions[0].market_value == pytest.approx(1000)  # not 10 x 98 = 980
    assert ledger.history[-1].market_value == pytest.approx(1000)


def test_average_cost_sell_with_fees() -> None:
    fills = [buy(0, "A", 10, 100, fee=1), buy(1, "A", 10, 120, fee=1), sell(2, "A", 10, 130, fee=1)]
    ledger = build(fills, closes("A", [100, 120, 130]) + closes(BENCH, [10] * 3), [BENCH])
    (position,) = ledger.positions
    # cost 1,001 + 1,201 = 2,202; selling half takes out 1,101; proceeds 1,300 - 1 = 1,299
    assert position.realized == pytest.approx(1299 - 1101)
    assert position.cost == pytest.approx(1101)
    assert position.shares == pytest.approx(10)


def test_benchmark_identical_to_the_stock_tracks_total_pnl_every_day() -> None:
    # No fees: the shadow portfolio pays none, so any fee would open a gap (next test)
    prices = [100.0, 105.0, 98.0, 110.0, 120.0]
    fills = [buy(0, "A", 10, 100), buy(1, "A", 5, 105), sell(3, "A", 8, 110)]
    ledger = build(fills, closes("A", prices) + closes(BENCH, prices), [BENCH])
    for point in ledger.history:
        assert point.benchmark_pnl[BENCH] == pytest.approx(point.total_pnl), point.date


def test_benchmark_leads_by_the_fees_and_tax_paid_at_flat_prices() -> None:
    # The shadow portfolio invests the whole buy amount, fee and tax included, and pays neither on
    # either side. At flat prices that cash earns nothing, so the gap is exactly what was paid so far.
    fills = [
        Fill(day(0), "A", "buy", 10, 100, 1.0, 0.5),
        Fill(day(1), "A", "buy", 5, 100, 1.0, 0.0),
        Fill(day(2), "A", "sell", 8, 100, 1.0, 0.25),
    ]
    ledger = build(fills, closes("A", [100] * 3) + closes(BENCH, [100] * 3), [BENCH])
    assert [p.benchmark_pnl[BENCH] - p.total_pnl for p in ledger.history] == pytest.approx([1.5, 2.5, 3.75])


def test_missing_bar_mid_window_uses_the_previous_close() -> None:
    a = closes("A", [100, 110]) + closes("A", [130], start=3)  # no bar on day 2
    ledger = build([buy(0, "A", 10, 100)], a + closes(BENCH, [10] * 4), [BENCH])
    assert [p.market_value for p in ledger.history] == pytest.approx([1000, 1100, 1100, 1300])


def test_first_fill_on_a_day_without_a_bar_uses_the_lookback_close() -> None:
    a = closes("A", [90], start=-2)  # the 7-day lookback; no bar on the fill date itself
    ledger = build([buy(0, "A", 10, 100)], a + closes(BENCH, [10] * 3, start=-2), [BENCH])
    assert ledger.history[0].date == day(0)
    assert ledger.history[0].market_value == pytest.approx(900)


def test_fill_after_the_last_bar_still_counts() -> None:
    # bought before that day's bars were loaded: valued at the previous close, not dropped
    ledger = build(
        [buy(0, "A", 10, 100), buy(3, "B", 5, 20)], closes("A", [100] * 3) + closes("B", [21] * 3) + closes(BENCH, [10] * 3), [BENCH]
    )
    assert [p.symbol for p in ledger.positions] == ["A", "B"]
    assert ledger.history[-1].date == day(3)
    assert ledger.history[-1].market_value == pytest.approx(1000 + 5 * 21)


def test_fill_with_no_close_on_or_before_its_date_raises_naming_the_symbol() -> None:
    with pytest.raises(ValueError, match=re.escape("ZZZ.US")):
        build([buy(0, "ZZZ.US", 10, 100)], closes(BENCH, [10] * 3), [BENCH])


def test_missing_benchmark_bars_raise_naming_the_benchmark() -> None:
    with pytest.raises(ValueError, match=BENCH):
        build([buy(0, "A", 10, 100)], closes("A", [100] * 3), [BENCH])


def test_weekend_fill_lands_on_the_next_trading_day_without_a_weekend_point() -> None:
    # day(5) is a Saturday: an after-hours fill whose UTC date rolled over
    weekdays = [0, 1, 2, 3, 4, 7, 8]
    a = [Close("A", day(n), 100, 100) for n in weekdays]
    bench = [Close(BENCH, day(n), 10, 10) for n in weekdays]
    ledger = build([buy(0, "A", 10, 100), buy(5, "A", 5, 100)], a + bench, [BENCH])
    assert [p.date for p in ledger.history] == [day(n) for n in weekdays]
    assert ledger.history[4].market_value == pytest.approx(1000)  # Friday: not yet
    assert ledger.history[5].market_value == pytest.approx(1500)  # Monday: applied


def test_fractional_shares_sold_in_full_leave_no_ghost_position() -> None:
    fills = [buy(0, "A", 0.1, 100), buy(0, "A", 0.2, 100), sell(1, "A", 0.3, 100)]
    ledger = build(fills, closes("A", [100] * 2) + closes(BENCH, [10] * 2), [BENCH])
    assert ledger.positions == []


def test_selling_more_than_held_raises() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        build([buy(0, "A", 10, 100), sell(1, "A", 11, 100)], closes("A", [100] * 2) + closes(BENCH, [10] * 2), [BENCH])


def test_fully_closed_position_leaves_positions_but_stays_in_totals() -> None:
    ledger = build([buy(0, "A", 10, 100), sell(1, "A", 10, 120)], closes("A", [100, 120]) + closes(BENCH, [10] * 2), [BENCH])
    assert ledger.positions == []
    assert ledger.totals is not None
    assert ledger.totals.realized == pytest.approx(200)
    assert ledger.totals.market_value == pytest.approx(0)
    assert ledger.totals.cost_basis == pytest.approx(0)


def test_no_fills_is_an_empty_ledger() -> None:
    ledger = build([], closes(BENCH, [10] * 3), [BENCH])
    assert ledger.positions == []
    assert ledger.history == []
    assert ledger.totals is None


def test_each_benchmark_is_its_own_shadow_portfolio() -> None:
    # A at 100 -> 120 -> 120; BENCH doubles on day 1, QQQ halves. Buy 1000 of A on day 0, sell half
    # on day 2: each shadow buys 1000 of its benchmark and sells the same half.
    fills = [buy(0, "A", 10, 100), sell(2, "A", 5, 120)]
    a = closes("A", [100, 120, 120])
    bench = closes(BENCH, [10, 20, 20])
    qqq = closes("QQQ.US", [10, 5, 5])
    ledger = build(fills, a + bench + qqq, [BENCH, "QQQ.US"])
    assert list(ledger.history[-1].benchmark_pnl) == [BENCH, "QQQ.US"]
    assert [p.benchmark_pnl[BENCH] for p in ledger.history] == pytest.approx([0, 1000, 1000])
    assert [p.benchmark_pnl["QQQ.US"] for p in ledger.history] == pytest.approx([0, -500, -500])
    assert ledger.history[-1].total_pnl == pytest.approx(200)


def test_the_first_benchmark_sets_the_calendar() -> None:
    # QQQ has a bar on day 3 that BENCH lacks: no point for day 3, as with any traded symbol's extra bar
    ledger = build([buy(0, "A", 10, 100)], closes("A", [100] * 4) + closes(BENCH, [10] * 3) + closes("QQQ.US", [10] * 4), [BENCH, "QQQ.US"])
    assert [p.date for p in ledger.history] == [day(0), day(1), day(2)]


def test_missing_second_benchmark_bars_raise_naming_it() -> None:
    with pytest.raises(ValueError, match=re.escape("QQQ.US")):
        build([buy(0, "A", 10, 100)], closes("A", [100] * 3) + closes(BENCH, [10] * 3), [BENCH, "QQQ.US"])


def test_a_repeated_benchmark_counts_once() -> None:
    fills = [buy(0, "A", 10, 100)]
    data = closes("A", [100, 100]) + closes(BENCH, [10, 20])
    once = build(fills, data, [BENCH]).history[-1].benchmark_pnl
    assert build(fills, data, [BENCH, BENCH]).history[-1].benchmark_pnl == pytest.approx(once) == {BENCH: 1000}


def test_no_benchmark_raises() -> None:
    with pytest.raises(ValueError, match="at least one benchmark"):
        build([buy(0, "A", 10, 100)], closes("A", [100] * 3), [])


def test_unknown_fill_side_raises_naming_it() -> None:
    fill = Fill(day(0), "A", "short", 10, 100, 0.0, 0.0)
    with pytest.raises(LedgerError, match="unknown side 'short' for A"):
        build([fill], closes("A", [100] * 3) + closes(BENCH, [10] * 3), [BENCH])
