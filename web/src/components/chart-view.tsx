import { useEffect, useRef, useState } from "react"
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts"
import type { SeriesMarker, Time } from "lightweight-charts"
import type { ChartData, ProjectionStats } from "@/lib/api"
import { api } from "@/lib/api"
import { RinngOverlay } from "@/lib/overlay"
import { cssColor } from "@/lib/chart-sync"
import type { SyncGroup } from "@/lib/chart-sync"
import type { PanelCfg } from "@/lib/workspaces"
import { live, useBarClose } from "@/lib/live"
import { Skeleton } from "@/components/ui/skeleton"

type Props = {
  cfg: PanelCfg
  symbol: string
  exchange: string
  sync?: SyncGroup
  onStatus?: (s: { source?: string; error?: string; loading: boolean }) => void
  onData?: (d: ChartData) => void
  hideStrip?: boolean
}

export function ChartView({
  cfg,
  symbol,
  exchange,
  sync,
  onStatus,
  onData,
  hideStrip,
}: Props) {
  const host = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<ChartData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const status = useRef(onStatus)
  status.current = onStatus
  const dataCb = useRef(onData)
  dataCb.current = onData
  // Bumped when a candle of this chart's timeframe closes: the lens is recomputed server-side.
  const [reload, setReload] = useState(0)
  // Visible time range kept across reloads so a candle close does not reset zoom/scroll.
  const view = useRef<{ from: Time; to: Time } | null>(null)
  useBarClose(symbol, exchange, cfg.tf, () => setReload((n) => n + 1))

  useEffect(() => {
    let alive = true
    setError(null)
    if (reload === 0) status.current?.({ loading: true })
    api
      .chart({
        lens: cfg.lens,
        tf: cfg.tf,
        days: cfg.days,
        period: cfg.period,
        zigzag: cfg.zigzag ?? "auto",
        symbol,
        exchange,
      })
      .then((d) => {
        if (!alive) return
        setData(d)
        dataCb.current?.(d)
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
  }, [
    cfg.lens,
    cfg.tf,
    cfg.days,
    cfg.period,
    cfg.zigzag,
    symbol,
    exchange,
    reload,
  ])

  // A new lens/timeframe/instrument starts from the default view.
  useEffect(() => {
    view.current = null
  }, [cfg.lens, cfg.tf, cfg.days, cfg.period, cfg.zigzag, symbol, exchange])

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
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: line,
        rightOffset: 8,
      },
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
        data.markers.map((m) => ({ ...m, time: m.time as Time })) as Array<
          SeriesMarker<Time>
        >
      )
    }
    for (const ln of data.lines ?? []) {
      const s = chart.addSeries(
        LineSeries,
        {
          color: ln.color,
          lineWidth: ln.pane === 0 && ln.name !== "median" ? 1 : 2,
          lineStyle: ln.name === "median" ? 2 : 0,
          priceLineVisible: false,
          lastValueVisible: ln.pane !== 0,
          title: ln.name === "median" ? "" : ln.name,
        },
        ln.pane
      )
      s.setData(ln.data.map((d) => ({ ...d, time: d.time as Time })))
      for (const guide of (data.guides ?? []).filter(
        (x) => x.pane === ln.pane
      )) {
        for (const v of guide.values) {
          s.createPriceLine({
            price: v,
            color: text,
            lineStyle: 2,
            lineWidth: 1,
          })
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
        h.pane
      )
      s.setData(h.data.map((d) => ({ ...d, time: d.time as Time })))
    }
    const panes = chart.panes()
    if (panes.length > 1) {
      panes[0].setStretchFactor(3)
      for (const p of panes.slice(1)) p.setStretchFactor(1)
    }
    if (view.current) {
      try {
        chart.timeScale().setVisibleRange(view.current)
      } catch {
        chart.timeScale().fitContent()
      }
    } else if (data.forecast) {
      // Projection: recent history (3× the horizon) plus the whole cone.
      const h = data.forecast.horizon
      const n = data.candles.length
      chart
        .timeScale()
        .setVisibleLogicalRange({ from: n - 3 * h, to: n + h + 4 })
    } else {
      chart.timeScale().fitContent()
    }
    // Running candle from /ws/live, drawn translucent until it closes and the lens reloads.
    const lastClosed = times[times.length - 1] ?? 0
    const offLive = live.on((e) => {
      if (
        e.type !== "bar" ||
        e.tf !== cfg.tf ||
        e.symbol !== symbol ||
        e.exchange !== exchange
      )
        return
      if (e.bar.time <= lastClosed) return
      const up = e.bar.close >= e.bar.open
      const color = up ? "rgba(38,166,154,0.55)" : "rgba(239,83,80,0.55)"
      try {
        candles.update({
          ...e.bar,
          time: e.bar.time as Time,
          color,
          wickColor: color,
        })
      } catch {
        /* older than the series' last point */
      }
    })
    const off = sync?.add(cfg.id, {
      tf: cfg.tf,
      chart,
      candles,
      times,
      closes: data.candles.map((c) => c.close),
      follow: !data.forecast,
    })
    return () => {
      const r = chart.timeScale().getVisibleRange()
      if (r) view.current = r
      offLive()
      off?.()
      chart.remove()
    }
  }, [data, sync, cfg.id, cfg.tf, symbol, exchange])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {data?.stats && !hideStrip ? <ProjectionStrip data={data} /> : null}
      {data?.legend?.length ? (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 px-3 pt-1.5 pb-1 text-[11px] text-muted-foreground">
          {data.legend.map(([color, label]) => (
            <span key={label} className="inline-flex items-center gap-1.5">
              {color ? (
                <i
                  className="inline-block size-2 rounded-full"
                  style={{ background: color }}
                />
              ) : null}
              {label}
            </span>
          ))}
        </div>
      ) : null}
      <div className="relative min-h-0 flex-1">
        <div ref={host} className="absolute inset-0" />
        {!data && !error ? (
          <Skeleton className="absolute inset-3 rounded-xl" />
        ) : null}
        {error ? (
          <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-destructive">
            {error}
          </div>
        ) : null}
      </div>
    </div>
  )
}

const pct = (v: number) => `${(v * 100).toFixed(0)}%`

// How the same projection method did on this market's own history (walk-forward, no lookahead).
function ProjectionStrip({ data }: { data: ChartData }) {
  const s = data.stats as ProjectionStats
  const f = data.forecast
  const skill = s.skill * 100
  return (
    <div className="mx-3 mt-1.5 grid gap-x-4 gap-y-0.5 rounded-lg bg-muted/50 px-2.5 py-1.5 font-heading text-[11px] text-muted-foreground sm:grid-cols-[auto_1fr]">
      <span className="text-foreground">
        Backtest · {s.origins} past projections
      </span>
      <span>
        80% band held {pct(s.coverage["80"])} · 50% band {pct(s.coverage["50"])}{" "}
        · median direction right{" "}
        {s.direction_hit == null ? "—" : pct(s.direction_hit)} · skill vs.
        no-context baseline {skill >= 0 ? "+" : "−"}
        {Math.abs(skill).toFixed(1)}%
      </span>
      {f ? (
        <>
          <span className="text-foreground">Next {f.horizon} candles</span>
          <span>
            80% range {Math.round(f.end.q10).toLocaleString("en-US")} –{" "}
            {Math.round(f.end.q90).toLocaleString("en-US")} · median{" "}
            {Math.round(f.end.q50).toLocaleString("en-US")} · from {f.analogs}{" "}
            closest of {f.pool} past setups
          </span>
        </>
      ) : null}
    </div>
  )
}
