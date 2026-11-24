import { useEffect, useRef } from "react"
import {
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts"
import type {
  IChartApi,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  SeriesMarker,
  Time,
} from "lightweight-charts"
import { cssColor } from "@/lib/chart-sync"
import { markText } from "@/lib/trusttrade"
import type { Decision } from "@/lib/trusttrade"

// One strategy on one coin: the daily fill price with its BUY/SELL decisions, and the share of
// equity held in the coin underneath. Clicking a day opens that day's evidence.

const UP = "#26a69a"
const DOWN = "#ef5350"

export function DecisionChart({
  rows,
  picked,
  onPick,
  height = 300,
}: {
  rows: Array<Decision>
  picked: string | null
  onPick: (day: string) => void
  height?: number
}) {
  const host = useRef<HTMLDivElement>(null)
  const parts = useRef<{
    chart: IChartApi
    price: ISeriesApi<"Line">
    exposure: ISeriesApi<"Histogram">
    markers: ISeriesMarkersPluginApi<Time>
  } | null>(null)
  const pick = useRef(onPick)
  pick.current = onPick

  useEffect(() => {
    const el = host.current
    if (!el) return
    const text = cssColor("--muted-foreground", "#a8a29e")
    const line = cssColor("--border", "#292524")
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: text,
        fontSize: 11,
        fontFamily: "'Geist Mono Variable', ui-monospace, monospace",
        attributionLogo: false,
        panes: { separatorColor: line },
      },
      grid: { vertLines: { color: line }, horzLines: { color: line } },
      timeScale: {
        borderColor: line,
        lockVisibleTimeRangeOnResize: true,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      rightPriceScale: { borderColor: line },
    })
    const price = chart.addSeries(LineSeries, {
      color: cssColor("--foreground", "#e7e5e4"),
      lineWidth: 2,
      priceLineVisible: false,
    })
    const exposure = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: {
          type: "custom",
          formatter: (v: number) => `${v.toFixed(0)}%`,
        },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1
    )
    chart.panes()[1]?.setHeight(70)
    const markers = createSeriesMarkers(price, [])
    chart.subscribeClick((p) => {
      if (typeof p.time === "string") pick.current(p.time)
    })
    parts.current = { chart, price, exposure, markers }
    return () => {
      parts.current = null
      chart.remove()
    }
  }, [])

  useEffect(() => {
    const x = parts.current
    if (!x) return
    x.price.setData(rows.map((r) => ({ time: r.day, value: r.price })))
    x.exposure.setData(
      rows.map((r) => ({
        time: r.day,
        value: 100 * r.exposure,
        color:
          r.day === picked ? "rgba(250,204,21,0.9)" : "rgba(16,185,129,0.45)",
      }))
    )
    const marks: Array<SeriesMarker<Time>> = []
    for (const r of rows) {
      if (r.action === "BUY" && r.pct > 0)
        marks.push({
          time: r.day,
          position: "belowBar",
          shape: "arrowUp",
          color: UP,
          text: markText(r),
        })
      else if (r.action === "SELL" && r.pct > 0)
        marks.push({
          time: r.day,
          position: "aboveBar",
          shape: "arrowDown",
          color: DOWN,
          text: markText(r),
        })
      if (r.day === picked)
        marks.push({
          time: r.day,
          position: "inBar",
          shape: "circle",
          color: "#facc15",
          size: 0.6,
        })
    }
    x.markers.setMarkers(marks)
  }, [rows, picked])

  useEffect(() => {
    parts.current?.chart.timeScale().fitContent()
  }, [rows])

  return (
    <div ref={host} style={{ height }} className="w-full cursor-crosshair" />
  )
}
