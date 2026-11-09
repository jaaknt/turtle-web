<script setup lang="ts">
defineProps<{
  label: string
  value: string
  sub?: string // a second line: a percentage, a comparison
  tone?: '' | 'pos' | 'neg'
  subTone?: '' | 'pos' | 'neg' // defaults to tone
  lead?: boolean // the page's headline number: larger, two columns wide
}>()
</script>

<template>
  <div class="kpi" :class="{ lead }">
    <div class="kpi-label">{{ label }}</div>
    <div class="kpi-value" :class="tone">{{ value }}</div>
    <div v-if="sub" class="kpi-sub" :class="subTone ?? tone">{{ sub }}</div>
    <!-- Extra lines under the value, e.g. one comparison per benchmark. -->
    <slot />
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
.kpi-sub,
.kpi :slotted(.kpi-sub) {
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.lead {
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
}
.lead .kpi-label {
  font-size: 0.9rem;
}
.lead .kpi-value {
  font-size: 2rem;
  line-height: 1.2;
}
/* Two columns wide once the row has room for two; on a phone it takes the one column. */
@media (min-width: 600px) {
  .lead {
    grid-column: span 2;
  }
}
</style>
