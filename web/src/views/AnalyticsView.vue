<script setup lang="ts">
import { computed, ref } from 'vue'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { api, type Analytics } from '../api/client'
import AnalyticsCaveats from '../components/AnalyticsCaveats.vue'
import BarChart from '../components/BarChart.vue'
import KpiTile from '../components/KpiTile.vue'
import LineChart, { type LineSeriesSpec } from '../components/LineChart.vue'
import LoadError from '../components/LoadError.vue'
import MonthlyReturns from '../components/MonthlyReturns.vue'
import { benchmarkColor, PORTFOLIO_COLOR } from '../charts'
import { day, days, pct, pnlClass, ratio, share, ticker } from '../format'
import { useLoad } from '../useLoad'

const { data: analytics, error, loading, reload } = useLoad(() => api.analytics())

type Series = Analytics['series'][number]
type MetricKey = keyof Series['metrics']
interface MetricRow {
  label: string
  key: MetricKey
  fmt: (v: number | null) => string
  signed?: boolean // coloured by sign
  annualised?: boolean // flagged "< 1 year" under YEAR trading days
}

const YEAR = 252 // trading days, as the API annualises: fewer make annualised figures unreliable

// The API sends the portfolio first, then each benchmark in configured order.
const series = computed(() => analytics.value?.series ?? [])
const portfolio = computed(() => series.value[0] ?? null)
const looks = computed(() =>
  series.value.map((s, i) => ({
    name: i === 0 ? 'Portfolio' : ticker(s.symbol),
    color: i === 0 ? PORTFOLIO_COLOR : benchmarkColor(i - 1),
  })),
)
const underAYear = computed(() => (analytics.value?.trading_days ?? 0) < YEAR)

// The metrics table, one row per metric and one column per series.
const METRICS: MetricRow[] = [
  { label: 'Cumulative return', key: 'cumulative_return', fmt: pct, signed: true },
  { label: 'CAGR', key: 'cagr', fmt: pct, signed: true, annualised: true },
  { label: 'Volatility', key: 'volatility', fmt: share, annualised: true },
  { label: 'Sharpe', key: 'sharpe', fmt: ratio, annualised: true },
  { label: 'Sortino', key: 'sortino', fmt: ratio, annualised: true },
  { label: 'Calmar', key: 'calmar', fmt: ratio, annualised: true },
  { label: 'Max drawdown', key: 'max_drawdown', fmt: pct, signed: true },
  { label: 'Longest drawdown', key: 'longest_drawdown_days', fmt: days },
  { label: 'Best day', key: 'best_day', fmt: pct, signed: true },
  { label: 'Worst day', key: 'worst_day', fmt: pct, signed: true },
  { label: 'Best month', key: 'best_month', fmt: pct, signed: true },
  { label: 'Worst month', key: 'worst_month', fmt: pct, signed: true },
  { label: 'Win rate, days', key: 'win_rate_days', fmt: share },
  { label: 'Win rate, months', key: 'win_rate_months', fmt: share },
  { label: 'Beta', key: 'beta', fmt: ratio },
  { label: 'Correlation', key: 'correlation', fmt: ratio },
]

// No series yet (the first response is loading): the formatter's dash.
function cell(s: Series | undefined, row: MetricRow): { text: string; tone: '' | 'pos' | 'neg' } {
  const v = s?.metrics[row.key] ?? null
  return { text: row.fmt(v), tone: row.signed ? pnlClass(v) : '' }
}
// Formatted once per response, not on every render: one cell per series, in series order.
const table = computed(() => METRICS.map((m) => ({ ...m, cells: series.value.map((s) => cell(s, m)) })))

// The KPI row: the cumulative return leads, then three more metrics, each with every benchmark's
// value under the portfolio's. Dashes until the first response.
const metric = (key: MetricKey): MetricRow => METRICS.find((m) => m.key === key)!
// 'SPY +8.90%': a benchmark's value under the portfolio's, by series index.
const vs = (i: number, m: MetricRow): string => `${looks.value[i]!.name} ${cell(series.value[i], m).text}`
const lead = computed(() => {
  const m = metric('cumulative_return')
  return {
    label: m.label,
    ...cell(series.value[0], m),
    benches: series.value.slice(1).map((s, i) => ({ symbol: s.symbol, text: vs(i + 1, m) })),
  }
})
const KPI_KEYS: MetricKey[] = ['cagr', 'sharpe', 'max_drawdown']
const kpis = computed(() =>
  KPI_KEYS.map(metric).map((m) => {
    const { text, tone } = cell(series.value[0], m)
    return { label: m.label, value: text, tone, benches: series.value.slice(1).map((s, i) => ({ symbol: s.symbol, text: vs(i + 1, m) })) }
  }),
)

function lines(field: 'cumulative' | 'drawdown'): LineSeriesSpec[] {
  const curve = analytics.value?.curve ?? []
  return series.value.map((s, i) => ({ ...looks.value[i]!, points: curve.map((p) => ({ time: p.date, value: p[field][s.symbol]! })) }))
}
const cumulativeSeries = computed(() => lines('cumulative'))
const drawdownSeries = computed(() => lines('drawdown'))

// Monthly returns of one series, by index: the portfolio's unless another is picked.
const monthlyOf = ref(0)
const monthlySeries = computed(() => series.value[monthlyOf.value] ?? portfolio.value)

// A handful of monthly bars says little: daily until there are 12 full months, unless one is picked.
const picked = ref<'monthly' | 'daily' | null>(null)
const fullMonths = computed(() => portfolio.value?.monthly.filter((m) => !m.partial).length ?? 0)
const distribution = computed(() => picked.value ?? (fullMonths.value < 12 ? 'daily' : 'monthly'))
const bins = computed(() => analytics.value?.[distribution.value === 'monthly' ? 'histogram_monthly' : 'histogram_daily'] ?? [])
</script>

<template>
  <h1>Analytics</h1>
  <p v-if="analytics && portfolio" class="page-meta">
    {{ analytics.trading_days }} trading days, {{ day(analytics.start) }} → {{ day(analytics.end) }}
  </p>
  <LoadError v-if="error" what="the analytics" :error="error" @retry="reload" />
  <p v-else-if="analytics && !analytics.start" class="placeholder">No transactions yet: the analytics start with the first fill.</p>

  <section v-if="portfolio || (loading && !analytics)" class="kpis" :class="{ stale: !portfolio }" :aria-busy="!portfolio">
    <KpiTile lead :label="lead.label" :value="lead.text" :tone="lead.tone">
      <div v-for="b in lead.benches" :key="b.symbol" class="kpi-sub placeholder">{{ b.text }}</div>
    </KpiTile>
    <KpiTile v-for="k in kpis" :key="k.label" :label="k.label" :value="k.value" :tone="k.tone">
      <div v-for="b in k.benches" :key="b.symbol" class="kpi-sub">{{ b.text }}</div>
    </KpiTile>
  </section>

  <template v-if="analytics && portfolio">

    <!-- Two columns, like a quantstats tear sheet: the charts on the left, the numbers on the right. -->
    <div class="tearsheet">
      <div class="plots">
        <h2>Cumulative return</h2>
        <LineChart :series="cumulativeSeries" percent />

        <h2>Drawdown</h2>
        <LineChart :series="drawdownSeries" percent />

        <h2>Monthly returns</h2>
        <div class="controls">
          <span class="toggle" role="group" aria-label="Series">
            <button v-for="(s, i) in series" :key="s.symbol" type="button" :aria-pressed="monthlySeries === s" @click="monthlyOf = i">
              {{ looks[i]!.name }}
            </button>
          </span>
        </div>
        <MonthlyReturns v-if="monthlySeries" :monthly="monthlySeries.monthly" :yearly="monthlySeries.yearly" />

        <h2>Distribution of portfolio returns</h2>
        <div class="controls">
          <span class="toggle" role="group" aria-label="Period">
            <button type="button" :aria-pressed="distribution === 'monthly'" @click="picked = 'monthly'">Monthly</button>
            <button type="button" :aria-pressed="distribution === 'daily'" @click="picked = 'daily'">Daily</button>
          </span>
        </div>
        <BarChart :bins="bins" />
      </div>

      <div class="numbers">
        <h2>Metrics</h2>
        <DataTable :value="table" dataKey="key" size="small" stripedRows scrollable>
          <Column header="Metric">
            <template #body="{ data }">
              {{ data.label }}
              <span v-if="data.annualised && underAYear" class="badge warn" title="Annualised from under a year of data">&lt; 1 year</span>
            </template>
          </Column>
          <Column v-for="(s, i) in series" :key="s.symbol" :header="looks[i]!.name" bodyClass="num" headerClass="num">
            <template #body="{ data }">
              <span :class="data.cells[i].tone">{{ data.cells[i].text }}</span>
            </template>
          </Column>
        </DataTable>

        <h2>Worst portfolio drawdowns</h2>
        <DataTable :value="analytics.drawdowns" dataKey="start" size="small" stripedRows scrollable>
          <template #empty>No drawdowns.</template>
          <Column field="start" header="Start">
            <template #body="{ data }">{{ day(data.start) }}</template>
          </Column>
          <Column field="valley" header="Valley">
            <template #body="{ data }">{{ day(data.valley) }}</template>
          </Column>
          <Column field="end" header="End">
            <template #body="{ data }">{{ data.ongoing ? 'ongoing' : day(data.end) }}</template>
          </Column>
          <Column field="depth" header="Depth" bodyClass="num" headerClass="num">
            <template #body="{ data }"><span class="neg">{{ pct(data.depth) }}</span></template>
          </Column>
          <Column field="days" header="Calendar days" bodyClass="num" headerClass="num" />
        </DataTable>
      </div>
    </div>

    <AnalyticsCaveats />
  </template>
</template>

<style scoped>
/* Charts beside a numbers column as wide as its tables. They wrap, charts first, once the charts
   would get under 560px: no breakpoint. */
.tearsheet {
  display: flex;
  flex-wrap: wrap;
  gap: 2rem;
  align-items: flex-start;
}
.plots {
  flex: 1 1 560px;
  min-width: 0;
}
.numbers {
  flex: 0 1 max-content;
  min-width: 0; /* when narrower than its tables, they scroll within the column */
}
.tearsheet h2:first-child {
  margin-top: 0;
}
.numbers :deep(.p-datatable-thead > tr > th) {
  white-space: nowrap;
}
</style>
