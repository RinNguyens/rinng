import { useEffect, useRef, useState } from "react"
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts"
import type { SeriesMarker, Time } from "lightweight-charts"
import type { ChartData } from "@/lib/api"
import { api } from "@/lib/api"
import { RinngOverlay } from "@/lib/overlay"
import { cssColor } from "@/lib/chart-sync"
import type { SyncGroup } from "@/lib/chart-sync"
import type { PanelCfg } from "@/lib/workspaces"
import { Skeleton } from "@/components/ui/skeleton"

type Props = {
  cfg: PanelCfg
  symbol: string
  exchange: string
  sync?: SyncGroup
  onStatus?: (s: { source?: string; error?: string; loading: boolean }) => void
}

export function ChartView({ cfg, symbol, exchange, sync, onStatus }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<ChartData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const status = useRef(onStatus)
  status.current = onStatus

  useEffect(() => {
    let alive = true
    setError(null)
    status.current?.({ loading: true })
    api
      .chart({ lens: cfg.lens, tf: cfg.tf, days: cfg.days, period: cfg.period, symbol, exchange })
      .then((d) => {
        if (!alive) return
        setData(d)
        status.current?.({ loading: false, source: d.source })
      })
      .catch((e: Error) => {
        if (!alive) return
        setError(e.message)
        status.current?.({ loading: false, error: e.message })
      })
    return () => {
      alive = false
    }
  }, [cfg.lens, cfg.tf, cfg.days, cfg.period, symbol, exchange])

  useEffect(() => {
    const el = host.current
    if (!el || !data) return
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
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: line, rightOffset: 8 },
      rightPriceScale: { borderColor: line },
      crosshair: { mode: 0 },
    })
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    })
    candles.setData(data.candles.map((c) => ({ ...c, time: c.time as Time })))
    const times = data.candles.map((c) => c.time)
    const overlay = new RinngOverlay(times)
    candles.attachPrimitive(overlay)
    overlay.set(data)
    if (data.markers?.length) {
      createSeriesMarkers(
        candles,
        data.markers.map((m) => ({ ...m, time: m.time as Time })) as Array<SeriesMarker<Time>>,
      )
    }
    for (const ln of data.lines ?? []) {
      const s = chart.addSeries(
        LineSeries,
        {
          color: ln.color,
          lineWidth: ln.pane === 0 ? 1 : 2,
          priceLineVisible: false,
          lastValueVisible: ln.pane !== 0,
          title: ln.name,
        },
        ln.pane,
      )
      s.setData(ln.data.map((d) => ({ ...d, time: d.time as Time })))
      for (const guide of (data.guides ?? []).filter((x) => x.pane === ln.pane)) {
        for (const v of guide.values) {
          s.createPriceLine({ price: v, color: text, lineStyle: 2, lineWidth: 1 })
        }
      }
    }
    for (const h of data.histos ?? []) {
      const fmt = h.precision
        ? {
            priceFormat: {
              type: "price" as const,
              precision: h.precision,
              minMove: 10 ** -h.precision,
            },
          }
        : {}
      const s = chart.addSeries(
        HistogramSeries,
        { priceLineVisible: false, title: h.name, ...fmt },
        h.pane,
      )
      s.setData(h.data.map((d) => ({ ...d, time: d.time as Time })))
    }
    const panes = chart.panes()
    if (panes.length > 1) {
      panes[0].setStretchFactor(3)
      for (const p of panes.slice(1)) p.setStretchFactor(1)
    }
    chart.timeScale().fitContent()
    const off = sync?.add(cfg.id, {
      tf: cfg.tf,
      chart,
      candles,
      times,
      closes: data.candles.map((c) => c.close),
    })
    return () => {
      off?.()
      chart.remove()
    }
  }, [data, sync, cfg.id, cfg.tf])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {data?.legend?.length ? (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 px-3 pt-1.5 pb-1 text-[11px] text-muted-foreground">
          {data.legend.map(([color, label]) => (
            <span key={label} className="inline-flex items-center gap-1.5">
              {color ? (
                <i className="inline-block size-2 rounded-full" style={{ background: color }} />
              ) : null}
              {label}
            </span>
          ))}
        </div>
      ) : null}
      <div className="relative min-h-0 flex-1">
        <div ref={host} className="absolute inset-0" />
        {!data && !error ? <Skeleton className="absolute inset-3 rounded-xl" /> : null}
        {error ? (
          <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-destructive">
            {error}
          </div>
        ) : null}
      </div>
    </div>
  )
}
