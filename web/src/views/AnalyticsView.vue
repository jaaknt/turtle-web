<script setup lang="ts">
// docs/specs/portfolio.md, Step 7 fills this page in: KPIs, metrics, charts and drawdowns.
import { api } from '../api/client'
import { day } from '../format'
import { useLoad } from '../useLoad'

const { data: analytics, error, loading } = useLoad(() => api.analytics())
</script>

<template>
  <h1>Analytics</h1>
  <p v-if="error" class="error">{{ error }}</p>
  <p v-else-if="loading && !analytics" class="placeholder">Loading…</p>
  <p v-else-if="analytics && !analytics.start" class="placeholder">No transactions yet: the analytics start with the first fill.</p>
  <p v-else-if="analytics" class="placeholder">
    {{ day(analytics.start) }} → {{ day(analytics.end) }}, {{ analytics.trading_days }} trading days.
  </p>
</template>
