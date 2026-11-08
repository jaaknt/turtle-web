<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, type ChartData } from '../api/client'
import PriceChart from '../components/PriceChart.vue'

// Minimal wiring so Step 8's chart can be checked; Step 9 adds the symbol picker and raw/adjusted toggle.
const props = defineProps<{ symbol?: string }>()
const route = useRoute()
const adjusted = computed(() => route.query.adjusted === 'true')

const chart = ref<ChartData | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)
let request = 0

// The title follows the URL, not the last loaded chart, so a slow load never shows A's name under B.
const title = computed(() => {
  if (!props.symbol) return 'Chart'
  const name = chart.value?.symbol === props.symbol ? chart.value.name : null
  return name ? `${props.symbol} — ${name}` : props.symbol
})

watch(
  [() => props.symbol, adjusted],
  async ([symbol, adj]) => {
    const mine = ++request // a slower earlier response must not overwrite a newer one
    error.value = null
    if (!symbol) {
      chart.value = null
      loading.value = false
      return
    }
    loading.value = true
    try {
      const data = await api.chart(symbol, adj)
      if (mine === request) chart.value = data
    } catch (e) {
      if (mine === request) {
        chart.value = null
        error.value = e instanceof Error ? e.message : String(e)
      }
    } finally {
      if (mine === request) loading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <h1>{{ title }}</h1>
  <p v-if="!symbol" class="placeholder">Open /chart/SYMBOL; the symbol picker comes in Step 9.</p>
  <p v-else-if="error" class="error">{{ error }}</p>
  <p v-else-if="loading" class="placeholder">Loading…</p>
  <!-- Kept mounted across symbol changes (the chart instance is reused), dimmed while stale. -->
  <PriceChart v-if="chart" :data="chart" :class="{ stale: loading }" />
</template>

<style scoped>
.stale { opacity: 0.4; }
</style>
