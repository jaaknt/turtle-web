<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import PriceChart from '../components/PriceChart.vue'
import { useLoad } from '../useLoad'

const props = defineProps<{ symbol?: string }>()
const route = useRoute()
const router = useRouter()

// Raw/adjusted lives in the query string, so a view can be bookmarked.
const adjusted = computed(() => route.query.adjusted === 'true')
function setAdjusted(value: boolean): void {
  router.replace({ query: { ...route.query, adjusted: value ? 'true' : undefined } })
}

// About 5,600 symbols, fetched once into a native <datalist>: autocomplete with no search
// endpoint, no debounce and no request races.
const { data: symbols, error: symbolsError } = useLoad(() => api.symbols())

const typed = ref(props.symbol ?? '')
watch(() => props.symbol, (s) => (typed.value = s ?? ''))
function open(): void {
  const s = typed.value.trim().toUpperCase()
  if (!s) return
  if (s === props.symbol) reload() // same symbol: a retry, e.g. after a failed load
  // Named route + params, so the router encodes the symbol rather than parsing it as a path.
  else router.push({ name: 'chart', params: { symbol: s }, query: route.query })
}

const { data: chart, error, loading, reload } = useLoad(
  () => (props.symbol ? api.chart(props.symbol, adjusted.value) : null),
  [() => props.symbol, adjusted],
)

// The title follows the URL, not the last loaded chart, so a slow load never shows A's name under B.
const title = computed(() => {
  if (!props.symbol) return 'Chart'
  const name = chart.value?.symbol === props.symbol ? chart.value.name : null
  return name ? `${props.symbol} — ${name}` : props.symbol
})
</script>

<template>
  <h1>{{ title }}</h1>

  <form class="controls" @submit.prevent="open">
    <input
      v-model="typed"
      list="symbols"
      placeholder="Symbol, e.g. AAPL.US"
      autocomplete="off"
      spellcheck="false"
      aria-label="Symbol"
    />
    <datalist id="symbols">
      <option v-for="s in symbols ?? []" :key="s.symbol" :value="s.symbol">{{ s.name }}</option>
    </datalist>
    <button type="submit">Open</button>
    <span v-if="symbolsError" class="error" :title="symbolsError">Symbol list unavailable</span>
    <span class="toggle" role="group" aria-label="Prices">
      <button type="button" :aria-pressed="!adjusted" @click="setAdjusted(false)">Raw</button>
      <button type="button" :aria-pressed="adjusted" @click="setAdjusted(true)">Adjusted</button>
    </span>
  </form>

  <p v-if="!symbol" class="placeholder">Pick a symbol to see its chart.</p>
  <p v-else-if="error" class="error">{{ error }}</p>
  <p v-else-if="loading" class="placeholder">Loading…</p>
  <!-- Kept mounted across symbol changes (the chart instance is reused), dimmed while stale. -->
  <PriceChart v-if="chart" :data="chart" :class="{ stale: loading }" />
</template>

<style scoped>
.controls input {
  width: 16rem;
}
.toggle {
  margin-left: 1rem;
  display: inline-flex;
}
.toggle button[aria-pressed='true'] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--bg);
}
</style>
