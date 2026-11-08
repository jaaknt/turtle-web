<script setup lang="ts">
defineProps<{
  label: string
  value: string
  sub?: string // a second line: a percentage, a comparison
  tone?: '' | 'pos' | 'neg'
  subTone?: '' | 'pos' | 'neg' // defaults to tone
}>()
</script>

<template>
  <div class="kpi">
    <div class="kpi-label">{{ label }}</div>
    <div class="kpi-value" :class="tone">{{ value }}</div>
    <div v-if="sub" class="kpi-sub" :class="subTone ?? tone">{{ sub }}</div>
  </div>
</template>

<style scoped>
.kpi {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  min-width: 0;
}
.kpi-label {
  color: var(--muted);
  font-size: 0.8rem;
}
.kpi-value {
  font-size: 1.35rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.kpi-sub {
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
</style>
