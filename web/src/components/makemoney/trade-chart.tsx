import { useEffect, useMemo, useRef, useState } from "react"
import {
  BaselineSeries,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts"
import type {
  IChartApi,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  IPriceLine,
  SeriesMarker,
  Time,
} from "lightweight-charts"
import { cssColor } from "@/lib/chart-sync"
import { num, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"

// 5m trading chart for the MakeMoney paper account: live Binance candles with every trade
// drawn on it. Closed trades are entry→exit segments coloured by result; an open position
// shows entry / SL / TP / liquidation lines and a shaded profit (green) / loss (red) area.

export type ChartPosition = {
  id?: number
  symbol: string
  side: "long" | "short"
  qty: number
  entry: number
  leverage: number
  stop: number
  take: number
  liq: number
  opened: number
  mark?: number
  upnl: number
}
export type ChartTrade = ChartPosition & {
  exit: number
  closed: number
  pnl: number
  exit_reason: string
}

type Candle = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

const UP = "#26a69a"
const DOWN = "#ef5350"
const BAR = 300
const bar = (t: number) => (Math.floor(t / BAR) * BAR) as Time

export function TradeChart({
  symbols,
  positions,
  trades,
}: {
  symbols: Array<string>
  positions: Array<ChartPosition>
  trades: Array<ChartTrade>
}) {
  const [symbol, setSymbol] = useState(symbols[0] ?? "BTC-USDT-PERP")
  const [candles, setCandles] = useState<Array<Candle>>([])
  const [err, setErr] = useState<string | null>(null)
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const series = useRef<{
    candles: ISeriesApi<"Candlestick">
    volume: ISeriesApi<"Histogram">
    pnl: ISeriesApi<"Baseline">
    markers: ISeriesMarkersPluginApi<Time>
  } | null>(null)
  const overlays = useRef<{
    lines: Array<IPriceLine>
    segs: Array<ISeriesApi<"Line">>
  }>({
    lines: [],
    segs: [],
  })
  const fitted = useRef(false)

  useEffect(() => {
    if (!symbols.includes(symbol) && symbols.length) setSymbol(symbols[0])
  }, [symbols, symbol])

  // live candles, refreshed every 10s
  useEffect(() => {
    let alive = true
    fitted.current = false
    setCandles([])
    const load = () =>
      fetch(
        `/api/makemoney/candles?symbol=${encodeURIComponent(symbol)}&limit=288`,
        {
          cache: "no-store",
        }
      )
        .then((r) =>
          r.ok ? r.json() : Promise.reject(new Error(r.statusText))
        )
        .then((c: Array<Candle>) => {
          if (alive) {
            setCandles(c)
            setErr(null)
          }
        })
        .catch((e: Error) => alive && setErr(e.message))
    load()
    const id = setInterval(load, 10_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbol])

  // the chart itself, created once
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
        timeVisible: true,
        secondsVisible: false,
        borderColor: line,
        rightOffset: 6,
      },
      rightPriceScale: { borderColor: line },
      crosshair: { mode: 0 },
    })
    const pnl = c.addSeries(BaselineSeries, {
      lineVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      topFillColor1: "rgba(38,166,154,0.28)",
      topFillColor2: "rgba(38,166,154,0.05)",
      bottomFillColor1: "rgba(239,83,80,0.05)",
      bottomFillColor2: "rgba(239,83,80,0.28)",
    })
    const cs = c.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
    })
    const volume = c.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    })
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })
    series.current = {
      candles: cs,
      volume,
      pnl,
      markers: createSeriesMarkers(cs, []),
    }
    chart.current = c
    return () => {
      c.remove()
      chart.current = null
      series.current = null
      overlays.current = { lines: [], segs: [] }
    }
  }, [])

  const open = positions.find((p) => p.symbol === symbol)
  const closed = useMemo(
    () => trades.filter((t) => t.symbol === symbol),
    [trades, symbol]
  )

  // candles + every trade overlay
  useEffect(() => {
    const c = chart.current
    const s = series.current
    if (!c || !s || !candles.length) return
    s.candles.setData(candles.map((k) => ({ ...k, time: k.time as Time })))
    s.volume.setData(
      candles.map((k) => ({
        time: k.time as Time,
        value: k.volume,
        color:
          k.close >= k.open ? "rgba(38,166,154,0.35)" : "rgba(239,83,80,0.35)",
      }))
    )
    const first = candles[0].time
    const last = candles[candles.length - 1].time
    const inView = (t: number) => t >= first && t <= last + BAR

    // clear previous overlays
    for (const l of overlays.current.lines) s.candles.removePriceLine(l)
    for (const seg of overlays.current.segs) c.removeSeries(seg)
    overlays.current = { lines: [], segs: [] }

    const marks: Array<SeriesMarker<Time>> = []
    const entryMark = (p: ChartPosition) =>
      marks.push({
        time: bar(p.opened),
        position: p.side === "long" ? "belowBar" : "aboveBar",
        shape: p.side === "long" ? "arrowUp" : "arrowDown",
        color: p.side === "long" ? UP : DOWN,
        text: `${p.id ? `#${p.id} ` : ""}${p.side === "long" ? "LONG" : "SHORT"} x${p.leverage}`,
      })

    // closed trades: entry → exit segment, green for profit, red for loss
    for (const t of closed) {
      if (!inView(t.closed)) continue
      const win = t.pnl >= 0
      const col = win ? UP : DOWN
      const seg = c.addSeries(LineSeries, {
        color: col,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      const a = Math.max(Number(bar(t.opened)), first)
      const b = Number(bar(t.closed))
      seg.setData(
        b > a
          ? [
              { time: a as Time, value: t.entry },
              { time: b as Time, value: t.exit },
            ]
          : [{ time: b as Time, value: t.exit }]
      )
      overlays.current.segs.push(seg)
      if (inView(t.opened)) entryMark(t)
      marks.push({
        time: bar(t.closed),
        position: "inBar",
        shape: "circle",
        color: col,
        text: `${t.id ? `#${t.id} ` : ""}${win ? "+" : ""}${num(t.pnl, 2)}$`,
      })
    }

    // open position: levels + live profit/loss area against the entry
    if (open) {
      const long = open.side === "long"
      const risk = Math.abs(open.entry - open.stop) * open.qty
      const reward = Math.abs(open.take - open.entry) * open.qty
      const add = (
        p: number,
        color: string,
        title: string,
        style = LineStyle.Solid
      ) =>
        overlays.current.lines.push(
          s.candles.createPriceLine({
            price: p,
            color,
            lineWidth: 1,
            lineStyle: style,
            axisLabelVisible: true,
            title,
          })
        )
      add(
        open.entry,
        "#60a5fa",
        `ENTRY ${open.upnl >= 0 ? "+" : ""}${num(open.upnl, 2)}$`
      )
      add(open.take, UP, `TP +${num(reward, 2)}$`, LineStyle.Dashed)
      add(open.stop, DOWN, `SL -${num(risk, 2)}$`, LineStyle.Dashed)
      add(open.liq, "#f59e0b", "LIQ", LineStyle.Dotted)
      if (inView(open.opened)) entryMark(open)
      // shade green where the position is in profit, red where it is losing
      s.pnl.applyOptions({
        baseValue: { type: "price", price: open.entry },
        ...(long
          ? {
              topFillColor1: "rgba(38,166,154,0.28)",
              topFillColor2: "rgba(38,166,154,0.05)",
              bottomFillColor1: "rgba(239,83,80,0.05)",
              bottomFillColor2: "rgba(239,83,80,0.28)",
            }
          : {
              topFillColor1: "rgba(239,83,80,0.28)",
              topFillColor2: "rgba(239,83,80,0.05)",
              bottomFillColor1: "rgba(38,166,154,0.05)",
              bottomFillColor2: "rgba(38,166,154,0.28)",
            }),
      })
      const from = Number(bar(open.opened))
      s.pnl.setData(
        candles
          .filter((k) => k.time >= from)
          .map((k) => ({ time: k.time as Time, value: k.close }))
      )
    } else {
      s.pnl.setData([])
    }

    marks.sort((x, y) => Number(x.time) - Number(y.time))
    s.markers.setMarkers(marks)
    if (!fitted.current) {
      c.timeScale().fitContent()
      fitted.current = true
    }
  }, [candles, open, closed])

  const realized = closed.reduce((a, t) => a + t.pnl, 0)
  const wins = closed.filter((t) => t.pnl > 0).length
  const last = candles[candles.length - 1]

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">
          {symbols.map((s) => {
            const has = positions.some((p) => p.symbol === s)
            return (
              <button
                key={s}
                type="button"
                onClick={() => setSymbol(s)}
                className={cn(
                  "rounded-md border px-2.5 py-1 font-mono text-xs",
                  s === symbol
                    ? "border-foreground bg-muted"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {s.split("-")[0]}
                {has && (
                  <span className="ml-1 inline-block size-1.5 rounded-full bg-sky-400 align-middle" />
                )}
              </button>
            )
          })}
        </div>
        <span className="text-xs text-muted-foreground">5m · Binance live</span>
        <div className="ml-auto flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs tabular-nums">
          {last && <span>{price(last.close)}</span>}
          {open && (
            <span>
              {open.side.toUpperCase()} uPnL{" "}
              <b className={tone(open.upnl)}>
                {open.upnl >= 0 ? "+" : ""}
                {num(open.upnl, 2)}$
              </b>
            </span>
          )}
          <span>
            Realized{" "}
            <b className={tone(realized)}>
              {realized >= 0 ? "+" : ""}
              {num(realized, 2)}$
            </b>
          </span>
          <span className="text-muted-foreground">
            {closed.length
              ? `${wins}W / ${closed.length - wins}L`
              : "no trades"}
          </span>
        </div>
      </div>
      <div className="relative h-[420px] w-full">
        <div ref={host} className="absolute inset-0" />
        {err && (
          <div className="absolute inset-x-0 top-2 mx-auto w-fit rounded bg-destructive/15 px-2 py-1 text-xs text-destructive">
            {err}
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <Legend color="#60a5fa" label="Entry" />
        <Legend color={UP} label="Take-profit / winning trade" dashed />
        <Legend color={DOWN} label="Stop-loss / losing trade" dashed />
        <Legend color="#f59e0b" label="Liquidation" dashed />
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-sm bg-[rgba(38,166,154,0.4)]" />/
          <span className="h-2.5 w-4 rounded-sm bg-[rgba(239,83,80,0.4)]" />{" "}
          open position in profit / loss
        </span>
      </div>
    </div>
  )
}

function Legend({
  color,
  label,
  dashed,
}: {
  color: string
  label: string
  dashed?: boolean
}) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="w-4 border-t-2"
        style={{ borderColor: color, borderStyle: dashed ? "dashed" : "solid" }}
      />
      {label}
    </span>
  )
}
