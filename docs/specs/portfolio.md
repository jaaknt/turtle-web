# Design: portfolio analytics page

> **Status:** Being implemented; Steps 1–7 are done. Each step is marked **Done** as it lands, as in
> [web.md](web.md). This page extends the dashboard that web.md describes; read its
> [P&L model](web.md#the-pl-model) first, because the return model below builds on it.

## Context

The Portfolio page answers "what do I hold and what is it worth". It does not answer "how good
is the strategy": how much it returned per unit of risk, how deep it fell, how its months are
distributed, and how all of that compares with SPY and QQQ. turtle-backtest answers those
questions for simulated portfolios with [quantstats](https://github.com/ranaroussi/quantstats).
This page answers them for the real Lightyear portfolio, at `/analytics`:

1. **Metrics table**: cumulative return, CAGR, volatility, Sharpe, Sortino, Calmar, max
   drawdown, longest drawdown, best and worst day and month, win rates, beta and correlation.
   One column for the portfolio and one per benchmark.
2. **Cumulative return** chart: portfolio vs each benchmark, in percent.
3. **Drawdown** ("underwater") chart: portfolio vs each benchmark.
4. **Monthly returns** heatmap: one row per year, one cell per month, and a year total.
5. **Distribution of returns**: a histogram of monthly returns, with daily returns as the
   alternative view while the history is short.
6. **Worst drawdowns** table: start, valley, recovery, depth and length of the five worst.

### Decisions

| Decision | Choice |
| --- | --- |
| Metric code | Written by hand in `api/turtleweb/analytics.py`: pure functions over a list of daily returns, standard library only (`math`, `statistics`) |
| quantstats | **Not** a runtime dependency. It is the test oracle: its numbers on a fixed series are committed as expected values ([Step 4](#step-4--validate-against-quantstats)) |
| Conventions | quantstats': risk-free rate 0, 252 periods a year, sample standard deviation. Where this spec and quantstats disagree, quantstats wins and this spec is corrected, so turtle-web and turtle-backtest reports agree |
| Return series | Daily **time-weighted** return, which removes the effect of money going in and out ([below](#the-return-model)) |
| Benchmarks | Buy and hold of each benchmark (default `SPY.US`, `QQQ.US`) over the same days, from its adjusted closes |
| Where the arithmetic runs | Backend only. The frontend formats and draws, as on every other page |
| Histogram | Bins computed by the backend; drawn by a small inline-SVG component. Lightweight Charts plots time series only |
| New dependencies | None, in either `api/` or `web/` |

Why not quantstats at runtime: it brings in pandas, numpy, scipy, matplotlib, seaborn and
yfinance (about 215 MB in turtle-backtest's virtualenv) for what amounts to a dozen formulas. It
is still at 0.0.x and has broken on pandas releases before; turtle-backtest pins `pandas<4`
partly for it. Its strength, HTML tear sheets and matplotlib plots, is what this frontend
replaces. The hard part, a correct return series for a portfolio with cash going in and out,
is something quantstats does not do for you either.

## The return model

Every metric on the page is a function of one daily return series. Getting that series right
is the whole difficulty; the metrics themselves are a few lines each.

**Why not `market_value.pct_change()`.** The ledger values holdings only; there is no cash
account (web.md's caveat "Not an equity curve"). A $1,000 buy raises market value by about
$1,000, which a naive percentage change reads as a gain. A sell reads as a loss. Every metric
computed from that series would be wrong, and nothing would look broken.

**Time-weighted return.** Buys enter at the start of their day and sells leave at its end:

```text
r_t = (MV_t + S_t) / (MV_{t-1} + B_t) − 1
```

- `MV_t`: market value at day `t`'s close, as the ledger computes it (`units × adjusted_close`).
- `B_t`: Σ buy cost on day `t` (`price × quantity + fee + tax`, the P&L model's buy cost).
- `S_t`: Σ sell proceeds on day `t` (`price × quantity − fee − tax`).

Consequences, each worth a test:

- **First day.** `MV_{t-1} = 0`, so `r = MV_t / B_t − 1`: from the fill price, fees included,
  to the close.
- **A full sell.** `MV_t = 0`, so `r = S_t / MV_{t-1} − 1`: from the previous close to the
  sell price, fees deducted. Putting sells at the end of the day keeps the denominator away
  from 0 here. Putting them at the start would divide by about zero.
- **A flat day** (nothing held, nothing traded): the denominator is 0. `r = 0`: idle cash earns
  nothing, the same assumption the ledger's shadow benchmarks make.
- **Splits** cancel, because `MV_t` uses adjusted closes.
- **One buy and no sells**: `∏(1 + r) − 1 = MV_T / B − 1 = total P&L / cost basis`. With more
  than one buy, the two differ, and that difference is the point: P&L measures dollars,
  time-weighted return measures the strategy regardless of how much money was in it.

**Which days.** The ledger's calendar, from the first fill up to and including the first
benchmark's last bar. A trailing day that is only in the calendar because of a fill imported
before that day's bars ([web.md, Step 5](web.md#step-5--the-ledger)) is left out. Its prices are
yesterday's, so its return would compare a fill price with a stale close. It joins the series
the next day, when its bars load and it becomes a benchmark day.

**Benchmark returns.** `r_t = adj_t / adj_{t-1} − 1` from each benchmark's forward-filled
adjusted close on the same days, and `0` on the first day: the benchmark is "bought" at the
first day's close. This is buy and hold, the comparison quantstats makes. It is not the
ledger's shadow portfolio, which matches your cash flows. On days the portfolio holds nothing,
the portfolio earns 0 while the benchmark keeps moving.

**What the page must say** (in its footer, next to web.md's caveats):

- Returns are time-weighted: they measure the holdings, not the account. There is still no
  cash, so they do not include cash drag.
- Annualised figures (CAGR, volatility, Sharpe, Sortino, Calmar) from under a year of data are
  unreliable. The page shows them, flagged, rather than hiding them.
- Day one is measured differently: the portfolio from fill price to close, each benchmark not at
  all (bought at that close). Over a short history this one day can move the comparison.
- Benchmarks are buy and hold from the first day's close, not the Portfolio page's shadow
  benchmarks, which follow the cash flows.

## Metric definitions

`r` is the daily return series, `n` its length, and `I_t = ∏_{s≤t}(1 + r_s)` the cumulative
index. Ratios whose denominator is 0 are `None`, rendered as "—". The right-hand column names
the quantstats function each one is checked against in [Step 4](#step-4--validate-against-quantstats).

| Metric | Definition | quantstats |
| --- | --- | --- |
| Cumulative return | `I_n − 1` | `stats.comp` |
| CAGR | `I_n^(252/n) − 1`: quantstats counts `years` as returns ÷ 252, not calendar days | `stats.cagr` |
| Volatility (annualised) | `stdev(r) · √252` | `stats.volatility` |
| Sharpe | `mean(r) / stdev(r) · √252` | `stats.sharpe` |
| Sortino | `mean(r) / √(Σ min(r, 0)² / n) · √252` | `stats.sortino` |
| Max drawdown | `min_t(I_t / max_{s≤t} I_s − 1)`, with a drawdown under `1e-12` read as 0 (float noise after an exact recovery; quantstats compares with 0) | `stats.max_drawdown` |
| Calmar | `CAGR / abs(max drawdown)` | `stats.calmar` |
| Longest drawdown | The longest drawdown period's `days` (below) | `stats.drawdown_details` |
| Best / worst day | `max(r)`, `min(r)` | `stats.best`, `stats.worst` |
| Best / worst month | Of the monthly returns below | `stats.best(aggregate="ME")`; not `"month"`, which merges the same month of different years |
| Win rate, days | Share of non-zero days with `r > 0` | `stats.win_rate` |
| Win rate, months | The same over monthly returns | `stats.win_rate(aggregate="ME")` |
| Beta vs first benchmark | `cov(r, b) / var(b)` | `stats.greeks` |
| Correlation vs first benchmark | Pearson `r` of the two daily series | `pandas.Series.corr` |
| Monthly return | `∏(1 + r)` over the month's days `− 1`; a month the history starts or ends in is flagged partial | `stats.monthly_returns` |
| Yearly return | The same over a year | `stats.yearly_returns` |
| Drawdown periods | Start (first day under water), valley, end (last day under water, or the last day while still under), depth, calendar days from start to end inclusive | `stats.drawdown_details` |

Beta and correlation are filled in for the portfolio column only.

## Step-by-step build

### Step 1 — Cash flows and benchmark prices in the ledger

**Done.** Implemented in `turtle-web` 2026-11-08.

`ledger.Point` gains what the return model needs and the ledger already has in hand:

```python
@dataclass(frozen=True)
class Point:
    ...  # date, market_value, cost_basis, realized, total_pnl, benchmark_pnl, as today
    bought: float  # Σ buy cost applied this day, fees and tax included
    sold: float  # Σ sell proceeds applied this day, net of fees and tax
    benchmark_close: dict[str, float]  # each benchmark's forward-filled adjusted close, configured order
```

- `_apply` returns the fill's cash as `(bought, sold)`, one of them 0, from amounts it already
  computes. The calendar loop adds the pairs up per day, so the buy/sell branch lives only in
  `_apply`.
- `_point` reads `benchmark_close` from `last`, which already holds every benchmark.
- `routes._point` builds `HistoryPoint` with `from_attributes`, which reads only the fields
  `HistoryPoint` declares. `/api/portfolio` does not change, and neither do its generated types.

Tests, in `tests/test_ledger.py`: a day with a buy and a sell has both amounts; `bought` summed
over history equals Σ buy cost; a weekend fill's cash lands on the trading day it is applied.

### Step 2 — The return series

**Done.** Implemented in `turtle-web` 2026-11-08.

`api/turtleweb/analytics.py`, a pure module like the ledger: no database, no FastAPI.

```python
@dataclass(frozen=True)
class Returns:
    dates: list[date]
    values: list[float]  # one daily return per date


def portfolio_returns(ledger: Ledger) -> Returns:
    """Time-weighted daily returns of the holdings, up to and including ledger.last_bar."""


def benchmark_returns(ledger: Ledger, symbol: str) -> Returns:
    """Buy and hold of one benchmark over the same days; 0 on the first day."""
```

`Ledger.last_bar` is the ledger's `last_bench_day`, so analytics never recomputes it from closes.
A sell within the ledger's share tolerance of the holding sells all of it (fraction exactly 1),
so a closed position is exactly 0 and a day with nothing held divides by exactly 0, which reads
as a 0 return.

Tests, each from [the return model](#the-return-model): the first-day return runs from fill
price to close; a full sell's return runs from the previous close to the sell price; a flat day
is 0; a split day is 0 at a flat price; with one buy, the compounded return equals total P&L
over cost basis; a trailing fill-only day is left out.

### Step 3 — The metrics

**Done.** Implemented in `turtle-web` 2026-11-08, with the definitions read from quantstats 0.0.86's
source (turtle-backtest's virtualenv), so Step 4 confirms them rather than discovers them.

Also in `analytics.py`, each a function of `Returns`, plus the aggregations:

```python
@dataclass(frozen=True)
class Metrics:
    cumulative_return: float
    cagr: float
    volatility: float | None  # None with fewer than 2 returns
    sharpe: float | None
    sortino: float | None  # None without a down day
    calmar: float | None  # None without a drawdown
    max_drawdown: float  # ≤ 0
    longest_drawdown_days: int  # calendar days; 0 without a drawdown
    best_day: float
    worst_day: float
    best_month: float
    worst_month: float
    win_rate_days: float | None  # of non-zero days; None when every day is 0 (quantstats says 0)
    win_rate_months: float | None
    beta: float | None  # vs the first benchmark; portfolio only
    correlation: float | None


def metrics(r: Returns, benchmark: Returns | None = None) -> Metrics: ...
def monthly(r: Returns) -> list[PeriodReturn]: ...  # year, month, value, partial
def yearly(r: Returns) -> list[PeriodReturn]: ...
def cumulative(r: Returns) -> list[float]: ...  # I_t − 1, for the chart
def underwater(r: Returns) -> list[float]: ...  # I_t / running peak − 1, for the chart
def drawdown_periods(r: Returns) -> list[DrawdownPeriod]: ...  # all of them, deepest first
def histogram(values: list[float], width: float) -> list[Bin]: ...  # lower, upper, count
```

Histogram bins have fixed widths, 2% for monthly and 0.5% for daily returns, with an edge at 0,
so a gain and a loss never share a bar: a loss lands below 0 however small it is. Fixed widths read better than a computed bin count, and
they keep bins comparable from one month to the next.

Unit tests use short hand-computed series: a constant return, a single loss, a recovery to the
exact previous peak (it closes the drawdown), a series that never draws down (Calmar `None`), a
series with no down day (Sortino `None`).

### Step 4 — Validate against quantstats

**Done.** Implemented in `turtle-web` 2026-11-08. Every metric, monthly and yearly return and
drawdown period matched quantstats 0.0.86 to `1e-9` on the first run, on the oracle and on the
demo database alike.

The hand-written metrics must give quantstats' numbers. That is checked twice: in CI on a
fixed synthetic series, and by hand on the live portfolio.

**4a. A committed oracle, checked in CI.** `api/scripts/make_analytics_oracle.py` builds a fixed,
seeded series of about 300 business days of synthetic returns, with a drawdown that recovers, one
that does not, and some zero days. It runs every quantstats function in the
[metric table](#metric-definitions) over that series and writes inputs and outputs to
`api/tests/analytics_oracle.json`. quantstats comes in only for that run, through uv's
throwaway environment, so it never enters `uv.lock`:

```bash
uv run --no-project --python 3.14 --with quantstats==0.0.86 python api/scripts/make_analytics_oracle.py
```

Pin the same quantstats version turtle-backtest uses; regenerate when either side upgrades it.
The JSON holds synthetic numbers only, never real data, per the README's rule. The series is
seeded, so regenerating writes byte-identical JSON unless quantstats' numbers change, and the
script refuses to write a series without three recovered drawdowns and an open one whose valley
comes before its end. The script
lives in `api/scripts/`, not `api/tests/`: mypy checks the tests, and quantstats is not installed
there.

`api/tests/test_analytics_oracle.py` loads the JSON, runs `analytics.metrics`, `monthly`,
`yearly` and `drawdown_periods` over the same inputs, and compares each value with
`pytest.approx(rel=1e-9)`. Every metric is one parametrized case, so a mismatch names the
metric.

Step 3 took the definitions in the [metric table](#metric-definitions) from quantstats 0.0.86's
source; the oracle confirms them. Two quantstats behaviours are deliberately not copied, so the
oracle series avoids them:

- `win_rate` returns 0, not "no value", when every day is 0.
- `drawdown_details` finds a period's start from the non-drawdown day before it, so a drawdown
  that begins on the first day can go unreported. The oracle series starts with a gain.

Any new difference goes into the metric table and a one-line comment in the code, so that the
next reader does not "fix" it back.

**4b. The real portfolio, checked by hand.** `api/scripts/compare_quantstats.py` builds the
ledger from the database the API is configured for (`TURTLE_WEB_*` variables or `api/.env`),
through the same loader as `/api/portfolio` (`db.fetch` and `db.replay`), and prints
every metric beside quantstats' value. It reuses the oracle script's quantstats calls. With
`--html`, it also writes quantstats' tear sheet, to compare the charts by eye with the page. Run
it from `api/`, with quantstats added to the project's environment for that run only:

```bash
uv run --with quantstats==0.0.86 python scripts/compare_quantstats.py --html /tmp/turtle-web-tearsheet.html
```

It exits non-zero if any metric differs by more than `1e-9` relative. A ratio left empty
(`None`) matches quantstats' NaN, 0 or ±inf. When the first day is a loss, a different longest
drawdown is reported as known, not as a failure: quantstats misses a drawdown that starts on
day one. Run it on the demo
database and on the VPS (from the deployed checkout) after any change to `analytics.py` or the
ledger. It is not part of CI: it needs a database, and the oracle already covers the formulas.
It reads the database directly rather than through `/api/analytics` so that it needs no running
API; Step 5's endpoint adds only serialisation on top.

What 4b catches that 4a cannot: an error in the return series itself (Steps 1 and 2). The
oracle checks the metrics on returns it is given. It cannot tell whether those returns were
derived correctly from your transactions. For that, also check one figure against the Portfolio
page by hand: while there has been only one buy, cumulative return equals total P&L divided by
cost basis.

### Step 5 — Endpoint and response models

**Done.** Implemented in `turtle-web` 2026-11-08. `analytics.report(ledger, benchmarks)` builds
the whole response as dataclasses, so the empty case and the portfolio-only beta are unit-tested
without the database; the route converts it to the `models.py` mirrors in one
`model_validate`. The portfolio's series key is `"portfolio"`.

`GET /api/analytics` in `routes.py`. It reuses `_transactions` and `_ledger`, so it costs the
same two queries as `/api/portfolio` and adds no SQL. A `LedgerError` returns 500, as it does
on `/api/portfolio`.

```python
class PeriodReturn(BaseModel):
    year: int
    month: int | None  # None for a yearly return
    value: float
    partial: bool  # the series' first or last period, so it may not cover the whole of it


class DrawdownPeriod(BaseModel):
    start: date
    valley: date
    end: date  # the last day under water
    depth: float  # ≤ 0
    days: int
    ongoing: bool  # still under water on the last day


class Bin(BaseModel):
    lower: float
    upper: float
    count: int


class SeriesAnalytics(BaseModel):
    symbol: str  # "portfolio", or a benchmark symbol
    metrics: Metrics  # a BaseModel mirror of analytics.Metrics
    monthly: list[PeriodReturn]
    yearly: list[PeriodReturn]


class CurvePoint(BaseModel):
    date: date
    cumulative: dict[str, float]  # by series symbol
    drawdown: dict[str, float]


class Analytics(BaseModel):
    start: date | None  # None before the first fill
    end: date | None
    trading_days: int  # the page flags annualised figures while this is under 252
    benchmarks: list[str]  # configured order, as on /api/portfolio
    series: list[SeriesAnalytics]  # the portfolio first, then each benchmark
    curve: list[CurvePoint]
    drawdowns: list[DrawdownPeriod]  # the portfolio's five worst: drawdown_periods(r)[:5]
    histogram_monthly: list[Bin]  # the portfolio's
    histogram_daily: list[Bin]
```

Route tests against the demo database: the portfolio comes first and the benchmarks follow in
configured order; `curve` has one point per series day; the demo's 2:1 split leaves no jump in
the cumulative curve; `start` is `None` and the lists are empty with no transactions.

### Step 6 — Frontend: route, types and charts

**Done.** Implemented in `turtle-web` 2026-11-08. `AnalyticsView.vue` is a placeholder (states
and the period) until Step 7. `BarChart`'s SVG stretches to its box, so its edge labels are HTML
under it: at most about eight, always 0 and both outer edges. With no bins it shows a sentence.

- `npm run gen:api` regenerates `openapi.json` and `src/api/schema.d.ts`; CI fails if this is
  forgotten.
- `api.analytics()` in `src/api/client.ts`.
- Route `/analytics` → `views/AnalyticsView.vue`, lazily loaded like the others, and an
  "Analytics" link after "Portfolio" in `App.vue`'s nav.
- `LineChart.vue` gains an optional `percent` prop, which sets a custom series `priceFormat`
  that formats through `format.ts`'s `pct`. Both new charts plot fractions.
- `components/MonthlyReturns.vue`: a plain `<table>`, one row per year, Jan–Dec and Year
  columns. Each cell's background is `--pos` or `--neg` mixed with `--bg` in proportion to
  `|value| / max |value|` (`color-mix()`), so it works in both themes. A partial month is shown
  in italics with a title saying so.
- `components/BarChart.vue`: an inline-SVG histogram over `Bin[]`. Bars are coloured
  `--pos`/`--neg` by the bin's side of 0, with the count on hover and percent labels at the
  edges. It is about 60 lines and needs no chart library.

### Step 7 — The page

**Done.** Implemented in `turtle-web` 2026-11-09. The Period tile shows the trading days, with
the dates as its sub line: the date range overflows a tile at 1366px. The monthly table takes the
full width (thirteen columns do not fit beside a chart), and the histogram sits beside the worst
drawdowns instead. The footer is `AnalyticsCaveats.vue`, with a fourth caveat: the benchmarks
are buy and hold, not the Portfolio page's shadow benchmarks. `ticker`, the series colours and
the `.kpis`, `.charts` and `.toggle` styles are now shared with the Portfolio and Chart pages.

`AnalyticsView.vue`, one `api.analytics()` call through `useLoad`, as on the Portfolio page:

- **KPI row** (`KpiTile`): cumulative return, CAGR, Sharpe, max drawdown, each with the first
  benchmark's value as the `sub` line. The period (`start` → `end`, `trading_days` days)
  completes the row.
- **Metrics table**: a PrimeVue `DataTable`, one row per metric and one column per series.
  Annualised rows carry a "< 1 year" badge (the `badge warn` class the Close column uses) while
  `trading_days < 252`.
- **Cumulative return** and **Drawdown**: two `LineChart`s with `percent`, side by side like
  the Portfolio page's pair, with the same benchmark colours.
- **Monthly returns**: `MonthlyReturns`, the portfolio's. A selector switches to a benchmark's.
- **Distribution of returns**: `BarChart` with a Monthly / Daily toggle. It defaults to daily
  while there are fewer than 12 full months (partial ones do not count), because a handful of monthly bars says little.
- **Worst drawdowns**: a `DataTable` over `drawdowns`; "ongoing" when `ongoing` is set.
- **Footer**: the [return model's caveats](#the-return-model), in a component next to
  `PnlCaveats.vue`, kept in step with this document as that one is with web.md.

Empty state before the first fill, as on the Portfolio page: a sentence, not a page of zeros.

### Step 8 — Documentation

- web.md: add the page to the list in its Context section and to Step 9's page list, with a
  link here; add `/api/analytics` to Step 6's endpoint list.
- README: the new page in the feature list, and the time-weighted vs P&L distinction in one
  sentence.

## Verification

1. CI is green: ruff, mypy, pytest with the oracle test, vue-tsc and the build.
2. `uv run pytest --cov` shows `analytics.py` at 100%, as `ledger.py` is.
3. `compare_quantstats.py` against the demo database reports no differences, and its tear sheet
   matches the page's charts by eye.
4. The same on the VPS, from the deployed checkout, against the live database.
5. While the live portfolio has a single buy and no sells, cumulative return on this page
   equals total P&L divided by cost basis on the Portfolio page.
6. The benchmark's cumulative return equals `adj_close(end) / adj_close(start) − 1` from a
   hand-run query on `daily_bars`.
7. The page at 1366 px shows no horizontal scroll, and both themes keep the heatmap and
   histogram readable.

## Later

Not part of this plan; each is a small addition once the series exists:

- **Money-weighted return (IRR)** from the same `bought` / `sold` flows: what the dollars
  earned, next to what the strategy earned.
- **Rolling Sharpe and rolling volatility** charts, once there is more than a year of data.
- **Trailing returns**: MTD, 3M, YTD, 1Y, since inception.
- **Skew, kurtosis, VaR / CVaR, profit factor**: one function each, and one oracle case each.
- **Attribution by sector**: contribution to return per GICS sector, from the positions' daily
  P&L.
