<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { api, type SignalRow } from '../api/client'
import LoadError from '../components/LoadError.vue'
import { day, median, money, pct, pnlClass } from '../format'
import { useLoad } from '../useLoad'

const DAY_CHOICES = [30, 90, 180] as const
const DEFAULT_DAYS = 90
const DEFAULT_MIN_RANKING = 44 // the gate is only meaningful on the qullamaggie scale

const route = useRoute()
const router = useRouter()

// Both filters live in the query string, so a filtered view can be bookmarked.
const days = computed(() => {
  const n = Number(route.query.days)
  return (DAY_CHOICES as readonly number[]).includes(n) ? n : DEFAULT_DAYS
})
const minRanking = computed(() => {
  const raw = route.query.min_ranking
  const n = Number(raw)
  return raw != null && raw !== '' && Number.isInteger(n) && n >= 0 && n <= 100 ? n : DEFAULT_MIN_RANKING
})

function setQuery(key: 'days' | 'min_ranking', value: number): void {
  router.replace({ query: { ...route.query, [key]: String(value) } })
}
function onMinRanking(e: Event): void {
  const input = e.target as HTMLInputElement
  const raw = input.value.trim()
  const n = Math.round(Number(raw))
  // Empty or junk means "back to the default", not 0 (Number('') is 0).
  const value = raw === '' || !Number.isFinite(n) ? DEFAULT_MIN_RANKING : Math.min(100, Math.max(0, n))
  // Write it back: when the clamped value equals the current one the query does not change,
  // nothing re-renders, and the box would keep showing what was typed (150 for a gate of 100).
  input.value = String(value)
  setQuery('min_ranking', value)
}

const { data: signals, error, loading, reload } = useLoad(() => api.signals(days.value, minRanking.value), [days, minRanking])

const summary = computed(() => {
  const rows = signals.value ?? []
  const changes = (bought: boolean) =>
    rows.filter((r) => r.bought === bought && r.change_pct != null).map((r) => r.change_pct!)
  return {
    count: rows.length,
    bought: rows.filter((r) => r.bought).length,
    medianBought: median(changes(true)),
    medianPassed: median(changes(false)),
  }
})

const rowClass = (r: SignalRow) => (r.bought ? 'bought' : undefined)
</script>

<template>
  <h1>Signals</h1>

  <form class="controls" @submit.prevent>
    <label>
      Last
      <select :value="days" @change="setQuery('days', Number(($event.target as HTMLSelectElement).value))">
        <option v-for="d in DAY_CHOICES" :key="d" :value="d">{{ d }} days</option>
      </select>
    </label>
    <label>
      Min ranking
      <input type="number" min="0" max="100" step="1" :value="minRanking" @change="onMinRanking" />
    </label>
    <span v-if="loading" class="placeholder">Loading…</span>
  </form>

  <LoadError v-if="error" what="the signals" :error="error" @retry="reload" />

  <template v-if="signals">
    <p class="summary" :class="{ stale: loading }">
      {{ summary.count }} signals, {{ summary.bought }} bought.
      Median change: bought <span :class="pnlClass(summary.medianBought)">{{ pct(summary.medianBought) }}</span>,
      not bought <span :class="pnlClass(summary.medianPassed)">{{ pct(summary.medianPassed) }}</span>.
    </p>

    <!-- No sortField: the API already orders by signal_date DESC, ranking DESC. -->
    <DataTable :value="signals" :rowClass="rowClass" size="small" stripedRows scrollable :class="{ stale: loading }">
      <template #empty>No signals in this window at this ranking.</template>
      <Column field="signal_date" header="Signal date" sortable />
      <Column field="symbol" header="Symbol" sortable>
        <template #body="{ data }"><RouterLink :to="`/chart/${data.symbol}`">{{ data.symbol }}</RouterLink></template>
      </Column>
      <Column field="name" header="Name" sortable />
      <Column field="ranking" header="Ranking" sortable bodyClass="num" headerClass="num" />
      <Column field="pct_vs_sma50" header="vs SMA50" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ pct(data.pct_vs_sma50) }}</template>
      </Column>
      <Column field="adr_pct" header="ADR" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ pct(data.adr_pct) }}</template>
      </Column>
      <Column field="entry_date" header="Entry date" sortable>
        <template #body="{ data }">
          <span v-if="data.entry_date == null" class="placeholder">pending</span>
          <template v-else>{{ day(data.entry_date) }}</template>
        </template>
      </Column>
      <Column field="entry_price" header="Entry price" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">
          <span v-if="data.entry_date == null" class="placeholder">pending</span>
          <template v-else>{{ money(data.entry_price) }}</template>
        </template>
      </Column>
      <Column field="curr_price" header="Current" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">{{ money(data.curr_price) }}</template>
      </Column>
      <Column field="change_pct" header="Change" sortable bodyClass="num" headerClass="num">
        <template #body="{ data }">
          <span v-if="data.entry_date == null" class="placeholder">pending</span>
          <span v-else :class="pnlClass(data.change_pct)">{{ pct(data.change_pct) }}</span>
        </template>
      </Column>
      <Column field="bought" header="Bought" sortable>
        <template #body="{ data }">{{ data.bought ? 'yes' : '' }}</template>
      </Column>
    </DataTable>
  </template>

  <footer class="page-footer">
    Change % is a total return from the next-day open, split- and dividend-adjusted. Prices shown are raw.
  </footer>
</template>

<style scoped>
.controls {
  gap: 1.25rem;
}
.controls input {
  width: 5rem;
}
.summary {
  font-variant-numeric: tabular-nums;
}
</style>
