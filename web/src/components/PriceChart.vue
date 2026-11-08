<script setup lang="ts">
import { useTemplateRef, watch } from 'vue'
import {
  CandlestickSeries, HistogramSeries, LineStyle, createSeriesMarkers,
  type IPriceLine, type ISeriesApi, type ISeriesMarkersPluginApi, type SeriesMarker, type Time,
} from 'lightweight-charts'
import type { ChartData } from '../api/client'
import { cssVar, useChart } from '../charts'
import { num } from '../format'

const props = defineProps<{ data: ChartData }>()
const el = useTemplateRef<HTMLDivElement>('el')

const UP = '#26a69a'
const DOWN = '#ef5350'

// Plain variables, not refs: see useChart.
let candles: ISeriesApi<'Candlestick'> | undefined
let volume: ISeriesApi<'Histogram'> | undefined
let markers: ISeriesMarkersPluginApi<Time> | undefined
let costLine: IPriceLine | undefined

const getChart = useChart(
  el,
  (chart) => {
    candles = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, wickUpColor: UP, wickDownColor: DOWN, borderVisible: false,
    })
    volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } }, 1) // 3rd arg = paneIndex
    chart.panes()[1]?.setStretchFactor(0.25) // volume gets a fifth of the height, not half
    markers = createSeriesMarkers(candles, [])
    render(props.data)
  },
  () => drawCostLine(props.data.avg_cost), // its colour comes from the theme
)

function drawCostLine(avgCost: number | null): void {
  if (!candles) return
  if (costLine) candles.removePriceLine(costLine)
  costLine = avgCost == null ? undefined : candles.createPriceLine({
    price: avgCost, title: 'avg cost', lineStyle: LineStyle.Dashed, color: cssVar('--muted'),
  })
}

function fillMarker(f: ChartData['fills'][number], adjusted: boolean): SeriesMarker<Time> {
  // Fill prices are raw; on adjusted candles a price label would contradict the scale, so drop it.
  const label = adjusted ? num(f.quantity) : `${num(f.quantity)}@${num(f.price)}`
  return f.side === 'buy'
    ? { time: f.time, position: 'belowBar', shape: 'arrowUp', color: UP, text: `B ${label}` }
    : { time: f.time, position: 'aboveBar', shape: 'arrowDown', color: DOWN, text: `S ${label}` }
}

function render(d: ChartData): void {
  const chart = getChart()
  if (!chart || !candles || !volume || !markers) return
  candles.setData(d.bars)
  volume.setData(
    d.bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? `${UP}80` : `${DOWN}80` })),
  )
  // The API returns every fill but only CHART_YEARS of bars, and the library snaps a marker
  // outside the bars onto the nearest candle, so keep only fills within the bars' range.
  // 'YYYY-MM-DD' strings compare correctly as text.
  const first = d.bars[0]?.time
  const last = d.bars[d.bars.length - 1]?.time
  const fills = first && last ? d.fills.filter((f) => f.time >= first && f.time <= last) : []
  markers.setMarkers(fills.map((f) => fillMarker(f, d.adjusted)))
  drawCostLine(d.avg_cost)
  chart.timeScale().fitContent()
}

watch(() => props.data, render) // /chart/A -> /chart/B reuses this instance
</script>

<template><div ref="el" class="price-chart" /></template>

<style scoped>
.price-chart { height: 520px; }
</style>
