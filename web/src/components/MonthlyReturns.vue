<script setup lang="ts">
import { computed } from 'vue'
import type { PeriodReturn } from '../api/client'
import { pct, pnlClass } from '../format'

// One series' returns as a year-by-month grid; the shade of a cell grows with |value|.
const props = defineProps<{ monthly: PeriodReturn[]; yearly: PeriodReturn[] }>()

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Twelve month cells (null before the first and after the last month), then the year's total.
const rows = computed(() => {
  // One scale for months and years alike, so a year's cell reads against its months.
  const scale = Math.max(...[...props.monthly, ...props.yearly].map((p) => Math.abs(p.value)), 1e-12)
  const shade = (p: PeriodReturn | null): Record<string, string> => {
    const tone = pnlClass(p?.value)
    if (!p || !tone) return {}
    const share = Math.round((Math.abs(p.value) / scale) * 60) // at most 60%: text stays readable
    return { background: `color-mix(in srgb, var(--${tone}) ${share}%, var(--bg))` }
  }
  const byMonth = new Map(props.monthly.map((m) => [`${m.year}-${m.month}`, m]))
  return props.yearly.map((y) => ({
    year: y.year,
    cells: [...MONTHS.map((_, i) => byMonth.get(`${y.year}-${i + 1}`) ?? null), y].map((p) => ({ p, style: shade(p) })),
  }))
})
</script>

<template>
  <div class="monthly-wrap">
    <table class="monthly">
      <thead>
        <tr>
          <th>Year</th>
          <th v-for="m in MONTHS" :key="m" class="num">{{ m }}</th>
          <th class="num">Year</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.year">
          <th>{{ row.year }}</th>
          <td
            v-for="(c, i) in row.cells"
            :key="i"
            class="num"
            :class="{ partial: c.p?.partial, total: i === MONTHS.length }"
            :style="c.style"
            :title="c.p?.partial ? 'Partial: the series starts or ends inside this period' : undefined"
          >
            {{ c.p ? pct(c.p.value) : '' }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.monthly-wrap { overflow-x: auto; }
/* As wide as the charts above and below it; on a narrow screen it keeps its content width and scrolls. */
.monthly {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}
/* The twelve months and the year total share the width evenly; the year label keeps the rest. */
.monthly .num { width: 7.5%; }
/* Tight cells: thirteen columns of signed percentages fit beside another column. */
.monthly th,
.monthly td {
  border: 1px solid var(--border);
  padding: 0.3rem 0.35rem;
  white-space: nowrap;
}
.monthly th { color: var(--muted); font-weight: 500; }
.monthly .total { font-weight: 600; }
.monthly .partial { font-style: italic; }
</style>
