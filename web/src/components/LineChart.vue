<script setup lang="ts">
import { useTemplateRef, watch } from 'vue'
import { LineSeries, type ISeriesApi } from 'lightweight-charts'
import { useChart } from '../charts'

export interface LineSeriesSpec {
  name: string
  color: string
  points: { time: string; value: number }[] // time is 'YYYY-MM-DD'
}

const props = defineProps<{ series: LineSeriesSpec[] }>()
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
    const line = chart.addSeries(LineSeries, { color: s.color, title: s.name, lineWidth: 2 })
    line.setData(s.points)
    return line
  })
  chart.timeScale().fitContent()
}

watch(() => props.series, render)
</script>

<template><div ref="el" class="line-chart" /></template>

<style scoped>
.line-chart { height: 300px; }
</style>
