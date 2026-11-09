<script setup lang="ts">
import { computed } from 'vue'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { api } from '../api/client'
import KpiTile from '../components/KpiTile.vue'
import LineChart, { type LineSeriesSpec } from '../components/LineChart.vue'
import LoadError from '../components/LoadError.vue'
import PnlCaveats from '../components/PnlCaveats.vue'
import { benchmarkColor, PORTFOLIO_COLOR } from '../charts'
import { money, num, pct, pnlClass, ticker } from '../format'
import { useLoad } from '../useLoad'

const { data: portfolio, error, loading, reload } = useLoad(() => api.portfolio())

const totals = computed(() => portfolio.value?.totals ?? null)
const asOf = computed(() => totals.value?.date ?? null)
const unrealized = computed(() => (totals.value ? totals.value.market_value - totals.value.cost_basis : null))
const unrealizedPct = computed(() =>
  totals.value && totals.value.cost_basis !== 0 ? unrealized.value! / totals.value.cost_basis : null,
)
// The configured order (SPY.US, QQQ.US), sent as its own list: object key order is not reliable
// (JavaScript moves integer-like keys first).
const benchmarks = computed(() => portfolio.value?.benchmarks ?? [])
const vsBenchmarks = computed(() => {
  const t = totals.value
  if (!t) return []
  return benchmarks.value.map((b) => {
    const pnl = t.benchmark_pnl[b]!
    // Read as a sentence, "$1,234.00 ahead of SPY": the size of the gap, its sign in the words.
    // Rounded to the cent first, so float noise never reads "$0.00 ahead of SPY" in green.
    const diff = Math.round((t.total_pnl - pnl) * 100) / 100
    const relation = diff > 0 ? 'ahead of' : diff < 0 ? 'behind' : 'level with'
    return { symbol: b, ticker: ticker(b), pnl, diff, gap: Math.abs(diff), relation }
  })
})

// "SPY", "SPY and QQQ", "SPY, QQQ and IWM"
const benchmarkList = computed(() => {
  const names = benchmarks.value.map(ticker)
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
})

type History = NonNullable<typeof portfolio.value>['history'][number]
function line(name: string, color: string, value: (h: History) => number): LineSeriesSpec {
  return { name, color, points: (portfolio.value?.history ?? []).map((h) => ({ time: h.date, value: value(h) })) }
}
const valueSeries = computed(() => [
  line('Market value', '#3b82f6', (h) => h.market_value),
  line('Cost basis', '#9ca3af', (h) => h.cost_basis),
])
const pnlSeries = computed(() => [
  line('Total P&L', PORTFOLIO_COLOR, (h) => h.total_pnl),
  ...benchmarks.value.map((b, i) =>
    line(`${ticker(b)} P&L`, benchmarkColor(i), (h) => h.benchmark_pnl[b]!),
  ),
])
</script>

<template>
  <h1>Portfolio</h1>
  <p v-if="asOf" class="page-meta">As of {{ asOf }}</p>
  <LoadError v-if="error" what="the portfolio" :error="error" @retry="reload" />
  <p v-else-if="portfolio && !totals" class="placeholder">No transactions yet: the portfolio starts with the first fill.</p>

  <!-- Before the first response the tiles show dashes, dimmed: money(undefined) is '—'. -->
  <section v-if="totals || (loading && !portfolio)" class="kpis" :class="{ stale: !totals }" :aria-busy="!totals">
    <KpiTile lead label="Total P&L" :value="money(totals?.total_pnl)" :tone="pnlClass(totals?.total_pnl)">
      <div v-for="b in vsBenchmarks" :key="b.symbol" class="kpi-sub">
        <span :class="pnlClass(b.diff)">{{ money(b.gap) }} {{ b.relation }} {{ b.ticker }}</span>
        <span class="placeholder"> ({{ b.ticker }} P&amp;L {{ money(b.pnl) }})</span>
      </div>
    </KpiTile>
    <KpiTile label="Market value" :value="money(totals?.market_value)" />
    <KpiTile label="Cost basis" :value="money(totals?.cost_basis)" />
    <KpiTile label="Unrealized P&L" :value="money(unrealized)" :sub="pct(unrealizedPct)" :tone="pnlClass(unrealized)" />
    <KpiTile label="Realized P&L" :value="money(totals?.realized)" :tone="pnlClass(totals?.realized)" />
  </section>

  <template v-if="portfolio && totals">
    <h2>Open positions ({{ portfolio.positions.length }})</h2>
    <DataTable
      :value="portfolio.positions"
      sortField="unrealized_pct"
      :sortOrder="-1"
      size="small"
      stripedRows
      scrollable
      class="positions"
    >
      <template #empty>No open positions.</template>
      <Column field="symbol" header="Symbol" sortable>
        <template #body="{ data }"><RouterLink :to="`/chart/${data.symbol}`">{{ data.symbol }}</RouterLink></template>
      </Column>
      <Column field="name" header="Name" sortable />
      <Column field="sector" header="Sector" sortable>
        <template #body="{ data }">{{ data.sector ?? '—' }}</template>
      </Column>
      <Column field="shares" header="Shares" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ num(data.shares) }}</template>
      </Column>
      <Column field="avg_cost" header="Avg cost" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ money(data.avg_cost) }}</template>
      </Column>
      <Column field="last_close" header="Close" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">
          <span
            v-if="asOf && data.last_date < asOf"
            class="badge warn"
            :title="`No bar since ${data.last_date}; the price is forward-filled`"
          >{{ data.last_date }}</span>
          {{ money(data.last_close) }}
        </template>
      </Column>
      <Column field="day_change_pct" header="Day %" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }"><span :class="pnlClass(data.day_change_pct)">{{ pct(data.day_change_pct) }}</span></template>
      </Column>
      <Column field="market_value" header="Value" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ money(data.market_value) }}</template>
      </Column>
      <Column field="cost_basis" header="Cost" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ money(data.cost_basis) }}</template>
      </Column>
      <Column field="unrealized" header="P&L" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }"><span :class="pnlClass(data.unrealized)">{{ money(data.unrealized) }}</span></template>
      </Column>
      <Column field="unrealized_pct" header="P&L %" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }"><span :class="pnlClass(data.unrealized_pct)">{{ pct(data.unrealized_pct) }}</span></template>
      </Column>
      <Column field="days_held" header="Days" sortable bodyClass="num" headerClass="num" />
    </DataTable>

    <section class="charts">
      <div>
        <h2>Holdings value vs cost basis</h2>
        <LineChart :series="valueSeries" />
      </div>
      <div>
        <h2>P&amp;L vs {{ benchmarkList }}</h2>
        <LineChart :series="pnlSeries" />
      </div>
    </section>

    <PnlCaveats />
  </template>
</template>

<style scoped>
/* The two charts side by side, stacked on a phone. */
.charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}
/* One-line headers: the short labels above keep the table within 1366px even with long sector names. */
.positions :deep(.p-datatable-thead > tr > th) {
  white-space: nowrap;
}
</style>
