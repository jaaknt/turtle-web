<script setup lang="ts">
import { useTemplateRef, watch } from 'vue'
import { LineSeries, type ISeriesApi } from 'lightweight-charts'
import { useChart } from '../charts'
import { pct } from '../format'

export interface LineSeriesSpec {
  name: string
  color: string
  points: { time: string; value: number }[] // time is 'YYYY-MM-DD'
}

// percent: the values are fractions (0.05 is 5%), labelled through format.ts's pct.
const props = defineProps<{ series: LineSeriesSpec[]; percent?: boolean }>()
const PERCENT_FORMAT = { type: 'custom', formatter: pct, minMove: 0.0001 } as const
const el = useTemplateRef<HTMLDivElement>('el')

// Plain variable, not a ref: see useChart.
let lines: ISeriesApi<'Line'>[] = []

const getChart = useChart(el, () => render(props.series))

function render(series: LineSeriesSpec[]): void {
  const chart = getChart()
  if (!chart) return
  // Rebuild rather than diff: the series count can change, and there are only a few.
  for (const line of lines) chart.removeSeries(line)
  lines = series.map((s) => {
    const line = chart.addSeries(LineSeries, {
      color: s.color,
      title: s.name,
      lineWidth: 2,
      ...(props.percent && { priceFormat: PERCENT_FORMAT }),
    })
    line.setData(s.points)
    return line
  })
  chart.timeScale().fitContent()
}

watch([() => props.series, () => props.percent], () => render(props.series))
</script>

<template><div ref="el" class="line-chart" /></template>

<style scoped>
.line-chart { height: 300px; }
</style>
