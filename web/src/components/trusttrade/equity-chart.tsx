import { useEffect, useRef } from "react"
import { LineSeries, LineStyle, createChart } from "lightweight-charts"
import type { IChartApi, ISeriesApi } from "lightweight-charts"
import { cssColor } from "@/lib/chart-sync"
import { style, toReturn } from "@/lib/trusttrade"
import type { Equity } from "@/lib/trusttrade"

// Cumulative return (%) of every strategy over one run window, one line each.

export function EquityChart({
  equity,
  start,
  shown,
  height = 320,
}: {
  equity: Equity
  start: number
  shown: Set<string>
  height?: number
}) {
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const lines = useRef(new Map<string, ISeriesApi<"Line">>())

  useEffect(() => {
    const el = host.current
    if (!el) return
    const text = cssColor("--muted-foreground", "#a8a29e")
    const line = cssColor("--border", "#292524")
    const c = createChart(el, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: text,
        fontSize: 11,
        fontFamily: "'Geist Mono Variable', ui-monospace, monospace",
        attributionLogo: false,
      },
      grid: { vertLines: { color: line }, horzLines: { color: line } },
      timeScale: {
        borderColor: line,
        lockVisibleTimeRangeOnResize: true,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      rightPriceScale: { borderColor: line },
      localization: {
        priceFormatter: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`,
      },
    })
    chart.current = c
    const map = lines.current
    return () => {
      map.clear()
      chart.current = null
      c.remove()
    }
  }, [])

  useEffect(() => {
    const c = chart.current
    if (!c) return
    for (const s of lines.current.values()) c.removeSeries(s)
    lines.current.clear()
    // draw the highlighted LLM variants last so they sit on top of the baselines
    const names = Object.keys(equity.series).sort(
      (a, b) => style(a).width - style(b).width || (style(a).dashed ? -1 : 1)
    )
    for (const name of names) {
      const st = style(name)
      const s = c.addSeries(LineSeries, {
        color: st.color,
        lineWidth: st.width,
        lineStyle: st.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerRadius: 3,
        title: "",
      })
      const ret = toReturn(equity.series[name], start)
      s.setData(equity.days.map((d, i) => ({ time: d, value: ret[i] })))
      lines.current.set(name, s)
    }
    c.timeScale().fitContent()
  }, [equity, start])

  useEffect(() => {
    for (const [name, s] of lines.current)
      s.applyOptions({ visible: shown.has(name) })
  }, [shown, equity])

  return <div ref={host} style={{ height }} className="w-full" />
}
