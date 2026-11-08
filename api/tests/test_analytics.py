"""The return series and the metrics over them, one rule per test, on hand-built data. No database."""

import math
import statistics
from dataclasses import replace
from datetime import date

import pytest

from tests.builders import BENCH, buy, closes, day, sell
from turtleweb.analytics import (
    Bin,
    DrawdownPeriod,
    PeriodReturn,
    Returns,
    benchmark_returns,
    cumulative,
    drawdown_periods,
    histogram,
    metrics,
    monthly,
    portfolio_returns,
    report,
    underwater,
    yearly,
)
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


def rounded[T: DrawdownPeriod | PeriodReturn](records: list[T], field: str) -> list[T]:
    """The records with one float field rounded to 9 places, so they compare with ==."""
    return [replace(x, **{field: round(getattr(x, field), 9)}) for x in records]


def daily(*values: float) -> Returns:
    """Consecutive days from day(0)."""
    return Returns([day(i) for i in range(len(values))], list(values))


def test_a_constant_return_compounds_and_has_no_risk() -> None:
    m = metrics(daily(0.01, 0.01, 0.01))
    assert m.cumulative_return == pytest.approx(1.01**3 - 1)
    assert m.cagr == pytest.approx(1.01**252 - 1)  # years = 3 returns / 252
    assert m.volatility == pytest.approx(0)
    assert (m.sharpe, m.sortino, m.calmar) == (None, None, None)
    assert (m.max_drawdown, m.longest_drawdown_days) == (0, 0)
    assert m.win_rate_days == 1


def test_a_single_loss_sets_the_drawdown_and_the_downside() -> None:
    r = daily(0.10, -0.20, 0.05)
    m = metrics(r)
    assert m.max_drawdown == pytest.approx(-0.20)
    assert m.sortino == pytest.approx((-0.05 / 3) / math.sqrt(0.04 / 3) * math.sqrt(252))
    assert m.sharpe == pytest.approx((-0.05 / 3) / statistics.stdev([0.10, -0.20, 0.05]) * math.sqrt(252))
    assert m.calmar == pytest.approx(m.cagr / 0.20)
    assert (m.best_day, m.worst_day) == (0.10, -0.20)
    assert m.win_rate_days == pytest.approx(2 / 3)
    assert underwater(r) == pytest.approx([0, -0.20, 1.1 * 0.8 * 1.05 / 1.1 - 1])
    assert rounded(drawdown_periods(r), "depth") == [DrawdownPeriod(day(1), day(1), day(2), -0.20, 2, ongoing=True)]


def test_a_recovery_to_the_exact_previous_peak_closes_the_drawdown() -> None:
    r = daily(0.25, -0.20, 0.25, 0.01)  # 1.25 -> 1.0 -> 1.25: back at the peak on day 2
    assert underwater(r)[2] == 0
    assert rounded(drawdown_periods(r), "depth") == [DrawdownPeriod(day(1), day(1), day(1), -0.20, 1, ongoing=False)]
    assert metrics(r).longest_drawdown_days == 1


def test_a_loss_on_day_one_is_a_drawdown() -> None:
    # the index starts at 1 before the first return, as quantstats' phantom baseline does
    r = daily(-0.10, 0.20)
    assert metrics(r).max_drawdown == pytest.approx(-0.10)
    assert drawdown_periods(r)[0].start == day(0)


def test_drawdown_periods_are_all_there_deepest_first() -> None:
    r = daily(-0.05, 0.10, -0.20, 0.30, -0.10, 0.20)
    assert [round(p.depth, 6) for p in drawdown_periods(r)] == [-0.20, -0.10, -0.05]


def test_cumulative_is_the_compounded_return_so_far() -> None:
    assert cumulative(daily(0.10, -0.10)) == pytest.approx([0.10, 1.1 * 0.9 - 1])


def test_monthly_and_yearly_returns_compound_and_flag_the_ends_as_partial() -> None:
    dates = [date(2026, 1, 30), date(2026, 2, 2), date(2026, 2, 3), date(2026, 3, 2)]
    r = Returns(dates, [0.10, 0.10, -0.10, 0.05])
    assert rounded(monthly(r), "value") == [
        PeriodReturn(2026, 1, 0.10, partial=True),
        PeriodReturn(2026, 2, round(1.1 * 0.9 - 1, 9), partial=False),
        PeriodReturn(2026, 3, 0.05, partial=True),
    ]
    assert rounded(yearly(r), "value") == [PeriodReturn(2026, None, round(1.1 * 1.1 * 0.9 * 1.05 - 1, 9), partial=True)]
    m = metrics(r)
    assert (m.best_month, m.worst_month) == pytest.approx((0.10, 1.1 * 0.9 - 1))
    assert m.win_rate_months == pytest.approx(2 / 3)


def test_beta_and_correlation_against_a_benchmark() -> None:
    bench = daily(0.01, -0.02, 0.03, 0.00)
    m = metrics(daily(0.02, -0.04, 0.06, 0.00), bench)  # twice the benchmark every day
    assert (m.beta, m.correlation) == pytest.approx((2.0, 1.0))
    assert metrics(daily(0.01, 0.02)).beta is None  # no benchmark
    assert metrics(daily(0.01, 0.02), daily(0.01, 0.01)).beta is None  # a flat benchmark has no variance


def test_one_return_has_no_volatility_and_no_returns_raise() -> None:
    m = metrics(daily(0.05))
    assert (m.volatility, m.sharpe) == (None, None)
    with pytest.raises(ValueError, match="at least one return"):
        metrics(daily())


def test_a_series_of_zero_days_has_no_win_rate() -> None:
    assert metrics(daily(0.0, 0.0)).win_rate_days is None


def test_histogram_bins_have_an_edge_at_zero_and_keep_empty_bins() -> None:
    bins = histogram([-0.01, 0.0, 0.004, 0.06], 0.02)
    assert [Bin(round(b.lower, 6), round(b.upper, 6), b.count) for b in bins] == [
        Bin(-0.02, 0.0, 1),
        Bin(0.0, 0.02, 2),
        Bin(0.02, 0.04, 0),
        Bin(0.04, 0.06, 0),
        Bin(0.06, 0.08, 1),  # 0.06 / 0.02 is 2.9999999999999996 in floats: it still lands on its own edge
    ]
    assert histogram([], 0.02) == []


def test_a_recovery_short_of_the_peak_by_float_noise_closes_the_drawdown() -> None:
    # 1.1 -> 1.023 -> back to 1.1, which computes as 1.1 * (1 - 2e-16)
    r = daily(0.10, -0.07, 1.1 / (1.1 * 0.93) - 1, 0.01)
    assert underwater(r)[2] == 0
    assert [(p.start, p.end) for p in drawdown_periods(r)] == [(day(1), day(1))]


def test_a_benchmark_on_other_dates_is_rejected() -> None:
    with pytest.raises(ValueError, match="same dates"):
        metrics(daily(0.01, 0.02), daily(0.01))


def test_a_tiny_loss_lands_below_zero_and_a_bad_width_is_rejected() -> None:
    assert [(round(b.lower, 6), b.count) for b in histogram([-1e-12, 0.0], 0.02)] == [(-0.02, 1), (0.0, 1)]
    assert [round(b.lower, 6) for b in histogram([-0.02, -0.03], 0.02)] == [-0.04, -0.02]  # -0.02 is on its own edge
    with pytest.raises(ValueError, match="positive"):
        histogram([0.01], 0)


def test_the_report_puts_the_portfolio_first_with_beta_against_the_first_benchmark() -> None:
    data = closes("A", [100, 110, 99]) + closes(BENCH, [10, 11, 10]) + closes("QQQ.US", [20, 21, 22])
    rep = report(build([buy(0, "A", 10, 100)], data, [BENCH, "QQQ.US"]), [BENCH, "QQQ.US"])
    assert [s.symbol for s in rep.series] == ["portfolio", BENCH, "QQQ.US"]
    assert rep.series[0].metrics.beta is not None
    assert all(s.metrics.beta is None and s.metrics.correlation is None for s in rep.series[1:])
    assert (rep.start, rep.end, rep.trading_days) == (day(0), day(2), 3)
    assert [p.date for p in rep.curve] == [day(0), day(1), day(2)]
    assert rep.curve[-1].cumulative == pytest.approx({"portfolio": -0.01, BENCH: 0.0, "QQQ.US": 0.10})
    assert rep.curve[-1].drawdown["portfolio"] == pytest.approx(-0.10)
    assert [round(d.depth, 6) for d in rep.drawdowns] == [-0.10]
    assert sum(b.count for b in rep.histogram_daily) == 3


def test_the_report_before_the_first_fill_is_empty() -> None:
    rep = report(build([], closes(BENCH, [10]), [BENCH]), [BENCH])
    assert (rep.start, rep.end, rep.trading_days, rep.benchmarks) == (None, None, 0, [BENCH])
    assert [len(x) for x in (rep.series, rep.curve, rep.drawdowns, rep.histogram_monthly, rep.histogram_daily)] == [0] * 5


def test_a_benchmark_cannot_take_the_portfolio_s_name() -> None:
    with pytest.raises(ValueError, match="cannot be a benchmark"):
        report(build([], closes("portfolio", [10]), ["portfolio"]), ["portfolio"])
