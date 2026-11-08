<script setup lang="ts">
import { computed } from 'vue'
import type { Bin } from '../api/client'
import { pctShort } from '../format'

// A histogram of returns: inline SVG, no chart library. Bins are contiguous and have an edge at 0.
// The SVG stretches to the box (preserveAspectRatio="none"), so the edge labels are HTML below it:
// SVG text would stretch with the bars.
const props = defineProps<{ bins: Bin[] }>()

const MAX_LABELS = 8

const maxCount = computed(() => Math.max(...props.bins.map((b) => b.count), 1))
const bars = computed(() =>
  props.bins.map((b, i) => ({
    x: i,
    h: (b.count / maxCount.value) * 100,
    cls: b.lower < 0 ? 'neg' : 'pos',
    title: `${pctShort(b.lower)} to ${pctShort(b.upper)}: ${b.count}`,
  })),
)
// At most about MAX_LABELS edges: both outer ones, which hug the sides, and every step-th edge
// counted from 0, so 0 is always labelled; an inner label too close to an outer one is dropped.
// The 0 edge is the first one not below 0, the same test that colours a bin.
const labels = computed(() => {
  const edges = [...props.bins.map((b) => b.lower), ...props.bins.slice(-1).map((b) => b.upper)]
  const step = Math.ceil(edges.length / MAX_LABELS)
  const zero = Math.max(edges.findIndex((e) => e >= 0), 0)
  const last = edges.length - 1
  const keep = (i: number) =>
    i === 0 || i === last || ((i - zero) % step === 0 && Math.min(i, last - i) > step / 2)
  return edges.flatMap((e, i) =>
    keep(i)
      ? [{ i, text: pctShort(e), left: `${(i / last) * 100}%`, shift: i === 0 ? '0' : i === last ? '-100%' : '-50%' }]
      : [],
  )
})
</script>

<template>
  <p v-if="!bins.length" class="placeholder">No returns yet.</p>
  <div v-else class="bar-chart">
    <svg :viewBox="`0 0 ${bins.length} 100`" preserveAspectRatio="none" role="img" aria-label="Histogram of returns">
      <rect v-for="b in bars" :key="b.x" :class="b.cls" :x="b.x + 0.06" :y="100 - b.h" width="0.88" :height="b.h">
        <title>{{ b.title }}</title>
      </rect>
    </svg>
    <div class="labels num">
      <span v-for="l in labels" :key="l.i" :style="{ left: l.left, transform: `translateX(${l.shift})` }">{{ l.text }}</span>
    </div>
  </div>
</template>

<style scoped>
.bar-chart svg {
  display: block;
  width: 100%;
  height: 200px;
  border-bottom: 1px solid var(--border);
}
rect.pos { fill: var(--pos); }
rect.neg { fill: var(--neg); }
rect:hover { opacity: 0.75; }
.labels {
  position: relative;
  height: 1.4rem;
  color: var(--muted);
  font-size: 0.75rem;
}
.labels span {
  position: absolute;
  top: 0.2rem;
  white-space: nowrap;
}
</style>
