// Everything Lightweight Charts needs beyond the series: the theme and the chart lifecycle.
// The library is touched only here and in src/components/.

import { onBeforeUnmount, onMounted, type ShallowRef } from 'vue'
import { ColorType, createChart, type ChartOptions, type DeepPartial, type IChartApi } from 'lightweight-charts'

/** Reads a CSS custom property from :root; the charts draw on a canvas, so they cannot inherit CSS. */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function chartTheme(): DeepPartial<ChartOptions> {
  return {
    layout: {
      background: { type: ColorType.Solid, color: cssVar('--bg') },
      textColor: cssVar('--muted'),
      panes: { separatorColor: cssVar('--border') }, // the default is near-white on a dark page
    },
    grid: { vertLines: { color: cssVar('--grid') }, horzLines: { color: cssVar('--grid') } },
    rightPriceScale: { borderColor: cssVar('--border') },
    timeScale: { borderColor: cssVar('--border') },
  }
}

/**
 * Creates a themed chart in `el` on mount and removes it on unmount.
 *
 * `init` adds the series once the chart exists; `onTheme` re-applies anything the component
 * colours itself (price lines, say) after the OS switches light/dark. The returned getter is
 * the only handle: keep chart and series objects in plain variables, NOT ref()/reactive() —
 * Vue's deep proxy over the chart instance breaks it and slows every redraw.
 */
export function useChart(
  el: Readonly<ShallowRef<HTMLDivElement | null>>,
  init: (chart: IChartApi) => void,
  onTheme?: () => void,
): () => IChartApi | undefined {
  let chart: IChartApi | undefined
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  const applyTheme = () => {
    chart?.applyOptions(chartTheme())
    onTheme?.()
  }

  onMounted(() => {
    chart = createChart(el.value!, { autoSize: true, ...chartTheme() })
    mq.addEventListener('change', applyTheme)
    init(chart)
  })
  onBeforeUnmount(() => {
    mq.removeEventListener('change', applyTheme)
    chart?.remove() // frees the canvas and ResizeObserver
    chart = undefined
  })
  return () => chart
}
