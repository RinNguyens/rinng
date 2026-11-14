// Syncs the crosshair (all charts in a tab) and the visible time range (only charts on the
// same timeframe) between open charts.
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from "lightweight-charts"

type Entry = {
  tf: string
  chart: IChartApi
  candles: ISeriesApi<"Candlestick">
  times: Array<number>
  closes: Array<number>
  // false: the chart leads but never follows other charts' time range (projection keeps its
  // future cone in view).
  follow?: boolean
}

export class SyncGroup {
  enabled = true
  private entries = new Map<string, Entry>()
  private busy = false

  add(id: string, e: Entry) {
    this.entries.set(id, e)
    const onMove = (p: MouseEventParams<Time>) => this.crosshair(id, p)
    const onRange = (r: { from: Time; to: Time } | null) => this.range(id, r)
    e.chart.subscribeCrosshairMove(onMove)
    e.chart.timeScale().subscribeVisibleTimeRangeChange(onRange)
    return () => {
      this.entries.delete(id)
    }
  }

  private crosshair(src: string, p: MouseEventParams<Time>) {
    if (!this.enabled || this.busy) return
    this.busy = true
    for (const [id, e] of this.entries) {
      if (id === src) continue
      if (p.time === undefined) {
        e.chart.clearCrosshairPosition()
        continue
      }
      const i = barAt(e.times, p.time as number)
      if (i >= 0) e.chart.setCrosshairPosition(e.closes[i], e.times[i] as Time, e.candles)
    }
    this.busy = false
  }

  private range(src: string, r: { from: Time; to: Time } | null) {
    const me = this.entries.get(src)
    if (!this.enabled || this.busy || !r || !me) return
    this.busy = true
    for (const [id, e] of this.entries) {
      if (id === src || e.tf !== me.tf || !e.times.length || e.follow === false) continue
      try {
        e.chart.timeScale().setVisibleRange(r)
      } catch {
        /* outside the other chart's data range */
      }
    }
    this.busy = false
  }
}

// The candle containing time t (largest open time <= t).
function barAt(ts: Array<number>, t: number) {
  if (!ts.length || t < ts[0]) return -1
  let lo = 0
  let hi = ts.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (ts[mid] <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}

// Resolve a theme CSS variable (oklch...) to rgb so Lightweight Charts can use it.
export function cssColor(name: string, fallback: string) {
  if (typeof document === "undefined") return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!raw) return fallback
  const c = document.createElement("canvas")
  c.width = c.height = 1
  const ctx = c.getContext("2d")
  if (!ctx) return fallback
  ctx.fillStyle = fallback
  ctx.fillStyle = raw
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  return `rgba(${r},${g},${b},${(a / 255).toFixed(3)})`
}
