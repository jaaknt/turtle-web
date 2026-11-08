<script setup lang="ts">
import { computed } from 'vue'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { api } from '../api/client'
import KpiTile from '../components/KpiTile.vue'
import LineChart, { type LineSeriesSpec } from '../components/LineChart.vue'
import PnlCaveats from '../components/PnlCaveats.vue'
import { money, num, pct, pnlClass } from '../format'
import { useLoad } from '../useLoad'

const { data: portfolio, error, loading } = useLoad(() => api.portfolio())

const totals = computed(() => portfolio.value?.totals ?? null)
const asOf = computed(() => totals.value?.date ?? null)
const unrealized = computed(() => (totals.value ? totals.value.market_value - totals.value.cost_basis : null))
const unrealizedPct = computed(() =>
  totals.value && totals.value.cost_basis !== 0 ? unrealized.value! / totals.value.cost_basis : null,
)
const vsBenchmark = computed(() => (totals.value ? totals.value.total_pnl - totals.value.benchmark_pnl : null))

function line(name: string, color: string, key: 'market_value' | 'cost_basis' | 'total_pnl' | 'benchmark_pnl'): LineSeriesSpec {
  return { name, color, points: (portfolio.value?.history ?? []).map((h) => ({ time: h.date, value: h[key] })) }
}
const valueSeries = computed(() => [line('Market value', '#3b82f6', 'market_value'), line('Cost basis', '#9ca3af', 'cost_basis')])
const pnlSeries = computed(() => [line('Total P&L', '#26a69a', 'total_pnl'), line('Benchmark P&L', '#f59e0b', 'benchmark_pnl')])
</script>

<template>
  <h1>Portfolio</h1>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-else-if="loading && !portfolio" class="placeholder">Loading…</p>
  <p v-else-if="portfolio && !totals" class="placeholder">No transactions yet: the portfolio starts with the first fill.</p>

  <template v-if="portfolio && totals">
    <section class="kpis">
      <KpiTile label="Market value" :value="money(totals.market_value)" />
      <KpiTile label="Cost basis" :value="money(totals.cost_basis)" />
      <KpiTile label="Unrealized P&L" :value="money(unrealized)" :sub="pct(unrealizedPct)" :tone="pnlClass(unrealized)" />
      <KpiTile label="Realized P&L" :value="money(totals.realized)" :tone="pnlClass(totals.realized)" />
      <KpiTile
        label="Total P&L"
        :value="money(totals.total_pnl)"
        :sub="`${money(vsBenchmark)} vs benchmark (${money(totals.benchmark_pnl)})`"
        :tone="pnlClass(totals.total_pnl)"
        :subTone="pnlClass(vsBenchmark)"
      />
      <KpiTile label="Open positions" :value="String(portfolio.positions.length)" />
      <KpiTile label="As of" :value="asOf ?? '—'" />
    </section>

    <h2>Open positions</h2>
    <DataTable
      :value="portfolio.positions"
      sortField="unrealized_pct"
      :sortOrder="-1"
      size="small"
      stripedRows
      scrollable
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
      <Column field="last_close" header="Last close" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">
          <span
            v-if="asOf && data.last_date < asOf"
            class="badge warn"
            :title="`No bar since ${data.last_date}; the price is forward-filled`"
          >{{ data.last_date }}</span>
          {{ money(data.last_close) }}
        </template>
      </Column>
      <Column field="market_value" header="Market value" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ money(data.market_value) }}</template>
      </Column>
      <Column field="cost_basis" header="Cost basis" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ money(data.cost_basis) }}</template>
      </Column>
      <Column field="unrealized" header="Unrealized" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }"><span :class="pnlClass(data.unrealized)">{{ money(data.unrealized) }}</span></template>
      </Column>
      <Column field="unrealized_pct" header="Unrealized %" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }"><span :class="pnlClass(data.unrealized_pct)">{{ pct(data.unrealized_pct) }}</span></template>
      </Column>
      <Column field="days_held" header="Days held" sortable bodyClass="num" headerClass="num" />
    </DataTable>

    <section class="charts">
      <div>
        <h2>Holdings value vs cost basis</h2>
        <LineChart :series="valueSeries" />
      </div>
      <div>
        <h2>P&amp;L vs benchmark</h2>
        <LineChart :series="pnlSeries" />
      </div>
    </section>

    <PnlCaveats />
  </template>
</template>

<style scoped>
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}
.charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}
</style>
