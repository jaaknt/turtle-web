<script setup lang="ts">
import { computed } from 'vue'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { api, type Transaction } from '../api/client'
import { day, money, num, pct, pnlClass } from '../format'
import { useLoad } from '../useLoad'

const { data: transactions, error, loading } = useLoad(() => api.transactions())

// Cash out for a buy, cash in for a sell: the P&L model's buy cost and sell proceeds.
function amount(t: Transaction): number {
  const gross = t.price * t.quantity
  return t.side === 'buy' ? gross + t.fee + t.tax : gross - t.fee - t.tax
}

// amount is a real field so the column sorts (DataTable sorts by field path, not by a function).
const rows = computed(() => transactions.value?.map((t) => ({ ...t, amount: amount(t) })) ?? null)
</script>

<template>
  <h1>Transactions</h1>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-else-if="loading && !transactions" class="placeholder">Loading…</p>

  <DataTable
    v-if="rows"
    :value="rows"
    sortField="transacted_at"
    :sortOrder="-1"
    size="small"
    stripedRows
    scrollable
  >
    <template #empty>No transactions yet.</template>
    <Column field="transacted_at" header="Date" sortable>
      <template #body="{ data }">{{ day(data.transacted_at) }}</template>
    </Column>
    <Column field="symbol" header="Symbol" sortable>
      <template #body="{ data }"><RouterLink :to="`/chart/${data.symbol}`">{{ data.symbol }}</RouterLink></template>
    </Column>
    <Column field="side" header="Side" sortable>
      <template #body="{ data }"><span :class="data.side === 'buy' ? 'pos' : 'neg'">{{ data.side }}</span></template>
    </Column>
    <Column field="quantity" header="Quantity" sortable bodyClass="num" headerClass="num">
      <template #body="{ data }">{{ num(data.quantity) }}</template>
    </Column>
    <Column field="price" header="Price" sortable bodyClass="num" headerClass="num">
      <template #body="{ data }">{{ money(data.price) }}</template>
    </Column>
    <Column field="fee" header="Fee" sortable bodyClass="num" headerClass="num">
      <template #body="{ data }">{{ money(data.fee) }}</template>
    </Column>
    <Column field="amount" header="Amount" sortable bodyClass="num" headerClass="num">
      <template #body="{ data }">{{ money(data.amount) }}</template>
    </Column>
    <Column field="signal_date" header="Signal date" sortable>
      <template #body="{ data }">{{ day(data.signal_date) }}</template>
    </Column>
    <Column field="ranking" header="Ranking" sortable bodyClass="num" headerClass="num">
      <template #body="{ data }">{{ data.ranking ?? '—' }}</template>
    </Column>
    <Column field="next_open" header="Next open" sortable bodyClass="num" headerClass="num">
      <template #body="{ data }">{{ money(data.next_open) }}</template>
    </Column>
    <Column field="slippage_pct" header="Slippage" sortable bodyClass="num" headerClass="num">
      <!-- Paying above the next open is a cost, so positive slippage is red. -->
      <template #body="{ data }"><span :class="pnlClass(data.slippage_pct == null ? null : -data.slippage_pct)">{{ pct(data.slippage_pct) }}</span></template>
    </Column>
  </DataTable>
</template>
