// MakeMoney trade desk: a lean live chart that answers one question, "is my trade right?".
// Left: candles (the running one moves with every live tick), EMA21/50, the analog projection
// cone, the open order's entry / TP1 / TP / SL / liquidation and a profit-or-loss shaded area,
// and markers where orders were opened and closed. Right: the orders, in real time.
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
  IPriceLine,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  SeriesMarker,
  Time,
} from "lightweight-charts"
import { Card } from "@/components/ui/card"
import { CandleClock, LivePrice } from "@/components/live-desk"
import type {
  LivePosition,
  TradeProjection,
} from "@/components/makemoney/live-panels"
import { cssColor } from "@/lib/chart-sync"
import { ago, num, price, tone } from "@/lib/format"
import { useBarClose, useLiveQuote } from "@/lib/live"
import { cn } from "@/lib/utils"

type Candle = {
  time: number
  open: number
  high: number
  low: number
  close: number
}
type Pt = { time: number; value: number }
type Check = { label: string; ok: boolean; value: string }
type Analysis = {
  candles: Array<Candle & { volume: number }>
  ema21: Array<Pt>
  ema200: Array<Pt>
  vwap: Array<Pt>
  rsi: Array<Pt>
  ema50: Array<Pt>
  tf_sec?: number
  summary: {
    bias: string
    checklist: {
      long: Array<Check>
      short: Array<Check>
      ready: boolean
    } | null
  }
}
type Cone = Record<string, Array<Pt>>
type Proj = {
  orders: Partial<Record<string, (TradeProjection & { cone: Cone }) | null>>
  flat: Partial<
    Record<string, { cone: Cone; horizon_bars: number; bar_sec: number } | null>
  >
}
export type DeskTrade = {
  id?: number
  symbol: string
  side: "long" | "short"
  entry: number
  exit: number
  opened: number
  closed: number
  pnl: number
}
export type DeskLog = { t: number; msg: string }

export type Ind =
  | "ema21"
  | "ema50"
  | "ema200"
  | "vwap"
  | "bb"
  | "volume"
  | "rsi"
  | "macd"
  | "projection"
export const INDICATORS: Array<{ id: Ind; label: string; color: string }> = [
  { id: "ema21", label: "EMA 21", color: "#f59e0b" },
  { id: "ema50", label: "EMA 50", color: "#38bdf8" },
  { id: "ema200", label: "EMA 200", color: "#a78bfa" },
  { id: "vwap", label: "VWAP", color: "#94a3b8" },
  { id: "bb", label: "Bollinger", color: "#f472b6" },
  { id: "volume", label: "Volume", color: "#64748b" },
  { id: "rsi", label: "RSI", color: "#c084fc" },
  { id: "macd", label: "MACD", color: "#22d3ee" },
  { id: "projection", label: "Projection", color: "#60a5fa" },
]
const IND_KEY = "rinng.makemoney.indicators"
const IND_DEFAULT: Record<Ind, boolean> = {
  ema21: true,
  ema50: true,
  ema200: false,
  vwap: false,
  bb: false,
  volume: true,
  rsi: false,
  macd: false,
  projection: true,
}
function loadInd(): Record<Ind, boolean> {
  try {
    const raw = localStorage.getItem(IND_KEY)
    if (raw)
      return {
        ...IND_DEFAULT,
        ...(JSON.parse(raw) as Partial<Record<Ind, boolean>>),
      }
  } catch {
    /* no storage: defaults */
  }
  return IND_DEFAULT
}

function emaOf(v: Array<number>, n: number): Array<number | null> {
  const out: Array<number | null> = []
  const a = 2 / (n + 1)
  let e: number | null = null
  for (let i = 0; i < v.length; i++) {
    if (i < n - 1) out.push(null)
    else if (e == null) {
      e = v.slice(0, n).reduce((x, y) => x + y, 0) / n
      out.push(e)
    } else {
      e = a * v[i] + (1 - a) * e
      out.push(e)
    }
  }
  return out
}

function bollinger(c: Array<number>, n = 20, k = 2) {
  return c.map((_, i) => {
    if (i < n - 1) return null
    const w = c.slice(i - n + 1, i + 1)
    const m = w.reduce((x, y) => x + y, 0) / n
    const sd = Math.sqrt(w.reduce((x, y) => x + (y - m) ** 2, 0) / n)
    return { mid: m, up: m + k * sd, lo: m - k * sd }
  })
}

function macd(c: Array<number>) {
  const f = emaOf(c, 12)
  const sl = emaOf(c, 26)
  const line = c.map((_, i) => {
    const a = f[i]
    const b = sl[i]
    return a != null && b != null ? a - b : null
  })
  const start = line.findIndex((x) => x != null)
  const sig = start < 0 ? [] : emaOf(line.slice(start) as Array<number>, 9)
  return line.map((l, i) => {
    const sv = i >= start && start >= 0 ? sig[i - start] : null
    return l == null || sv == null
      ? null
      : { line: l, signal: sv, hist: l - sv }
  })
}

const UP = "#26a69a"
const DOWN = "#ef5350"
const usd = (v: number) => `${v < 0 ? "-" : ""}$${num(Math.abs(v), 2)}`
const coin = (s: string) => s.split("-")[0]

export function TradeDesk({
  symbols,
  positions,
  trades,
  log,
  tf,
}: {
  symbols: Array<string>
  positions: Array<LivePosition>
  trades: Array<DeskTrade>
  log: Array<DeskLog>
  tf: string
}) {
  const exchange = "binance"
  const [picked, setPicked] = useState(symbols[0])
  const symbol = symbols.includes(picked) ? picked : symbols[0]
  const [data, setData] = useState<Analysis | null>(null)
  const [proj, setProj] = useState<Proj | null>(null)
  const [rev, setRev] = useState(0)
  const [ind, setInd] = useState(loadInd)
  const toggle = (k: Ind) =>
    setInd((cur) => {
      const next = { ...cur, [k]: !cur[k] }
      try {
        localStorage.setItem(IND_KEY, JSON.stringify(next))
      } catch {
        /* the choice lasts for this page only */
      }
      return next
    })

  useBarClose(symbol, exchange, tf, () => setRev((n) => n + 1))
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`/api/makemoney/analysis?symbol=${encodeURIComponent(symbol)}`, {
        cache: "no-store",
      })
        .then((r) => r.json())
        .then((a: Analysis) => alive && setData(a))
        .catch(() => {})
    load()
    const id = setInterval(load, 20_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbol, rev])
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch("/api/makemoney/projection", { cache: "no-store" })
        .then((r) => r.json())
        .then((p: Proj) => alive && setProj(p))
        .catch(() => {})
    load()
    const id = setInterval(load, 30_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbol, positions.length])

  const pos = positions.find((p) => p.symbol === symbol) ?? null
  const odds = pos ? (proj?.orders[String(pos.id)] ?? null) : null
  const cone = pos ? odds?.cone : proj?.flat[symbol]?.cone
  const mine = useMemo(
    () => trades.filter((t) => t.symbol === symbol),
    [trades, symbol]
  )
  const { tick } = useLiveQuote(symbol, exchange)
  const live = tick?.price ?? data?.candles.at(-1)?.close

  return (
    <Card size="sm" className="gap-0 overflow-hidden py-0">
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px]">
        <div className="flex h-[520px] min-w-0 flex-col xl:h-[640px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-foreground/10 px-3 py-2">
            <span className="font-heading text-sm font-medium">Trade desk</span>
            {symbols.length > 1 ? (
              <div className="flex gap-1">
                {symbols.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setPicked(s)}
                    className={cn(
                      "rounded px-1.5 py-0.5 font-mono text-[11px]",
                      s === symbol
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    {coin(s)}
                  </button>
                ))}
              </div>
            ) : (
              <span className="font-mono text-xs">{coin(symbol)}</span>
            )}
            <span className="rounded border px-1 font-mono text-[10px] text-muted-foreground">
              {tf}
            </span>
            <LivePrice
              symbol={symbol}
              exchange={exchange}
              fallback={data?.candles.at(-1)?.close}
            />
            <CandleClock />
          </div>
          <div className="flex flex-wrap gap-1 border-b border-foreground/10 px-3 py-1.5">
            {INDICATORS.map((x) => (
              <button
                key={x.id}
                type="button"
                aria-pressed={ind[x.id]}
                onClick={() => toggle(x.id)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ring-1 transition-colors",
                  ind[x.id]
                    ? "bg-muted text-foreground ring-foreground/15"
                    : "text-muted-foreground ring-foreground/10 hover:text-foreground"
                )}
              >
                <i
                  className="inline-block size-1.5 rounded-full"
                  style={{ background: x.color, opacity: ind[x.id] ? 1 : 0.3 }}
                />
                {x.label}
              </button>
            ))}
          </div>
          <Chart
            key={symbol}
            data={data}
            tick={tick?.price ?? null}
            pos={pos}
            trades={mine}
            cone={ind.projection ? (cone ?? null) : null}
            ind={ind}
          />
        </div>
        <OrdersPanel
          symbol={symbol}
          pos={pos}
          live={live}
          odds={odds}
          checklist={data?.summary.checklist ?? null}
          bias={data?.summary.bias}
          trades={mine}
          log={log}
        />
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ chart */

function Chart({
  data,
  tick,
  pos,
  trades,
  cone,
  ind,
}: {
  data: Analysis | null
  tick: number | null
  pos: LivePosition | null
  trades: Array<DeskTrade>
  cone: Cone | null
  ind: Record<Ind, boolean>
}) {
  const host = useRef<HTMLDivElement>(null)
  const h = useRef<{
    chart: IChartApi
    candles: ISeriesApi<"Candlestick">
    pnl: ISeriesApi<"Baseline">
    studies: Array<ISeriesApi<"Line"> | ISeriesApi<"Histogram">>
    cone: Array<ISeriesApi<"Line">>
    markers: ISeriesMarkersPluginApi<Time>
    lines: Array<IPriceLine>
  } | null>(null)
  const last = useRef<Candle | null>(null)
  const fitted = useRef(false)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const text = cssColor("--muted-foreground", "#a8a29e")
    const grid = cssColor("--border", "#292524")
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: text,
        fontSize: 11,
        fontFamily: "'Geist Mono Variable', ui-monospace, monospace",
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: grid } },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: grid,
        rightOffset: 4,
      },
      rightPriceScale: { borderColor: grid },
      crosshair: { mode: 0 },
    })
    const quiet = {
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }
    const pnl = chart.addSeries(BaselineSeries, {
      ...quiet,
      lineVisible: false,
    })
    const coneLines = [
      { c: "rgba(96,165,250,0.25)", s: LineStyle.Dotted },
      { c: "rgba(96,165,250,0.5)", s: LineStyle.Dashed },
      { c: "rgba(96,165,250,0.9)", s: LineStyle.Dashed },
      { c: "rgba(96,165,250,0.5)", s: LineStyle.Dashed },
      { c: "rgba(96,165,250,0.25)", s: LineStyle.Dotted },
    ].map((x) =>
      chart.addSeries(LineSeries, {
        ...quiet,
        color: x.c,
        lineStyle: x.s,
        lineWidth: 1,
      })
    )
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
    })
    h.current = {
      chart,
      candles,
      pnl,
      studies: [],
      cone: coneLines,
      markers: createSeriesMarkers(candles, []),
      lines: [],
    }
    return () => {
      chart.remove()
      h.current = null
    }
  }, [])

  // candles, EMAs, projection, order lines and markers
  useEffect(() => {
    const x = h.current
    if (!x || !data?.candles.length) return
    const bar = data.tf_sec ?? 300
    const snap = (t: number) => (Math.floor(t / bar) * bar) as Time
    const cs = data.candles.slice(-300)
    x.candles.setData(cs.map((k) => ({ ...k, time: k.time as Time })))
    last.current = { ...cs[cs.length - 1] }
    const from = cs[0].time
    const tail = (s: Array<Pt>) =>
      s
        .filter((p) => p.time >= from)
        .map((p) => ({ time: p.time as Time, value: p.value }))
    // indicators: rebuilt from scratch so panes appear and disappear with their toggle
    for (const st of x.studies) x.chart.removeSeries(st)
    x.studies = []
    const quiet = {
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }
    const line = (
      pts: Array<{ time: Time; value: number }>,
      color: string,
      pane = 0,
      extra = {}
    ) => {
      const sr = x.chart.addSeries(
        LineSeries,
        { ...quiet, color, lineWidth: 1, ...extra },
        pane
      )
      sr.setData(pts)
      x.studies.push(sr)
      return sr
    }
    const closes = data.candles.map((k) => k.close)
    const at = (i: number) => data.candles[i].time
    const keep = (i: number) => at(i) >= from
    if (ind.ema21) line(tail(data.ema21), "#f59e0b")
    if (ind.ema50) line(tail(data.ema50), "#38bdf8")
    if (ind.ema200) line(tail(data.ema200), "#a78bfa", 0, { lineWidth: 2 })
    if (ind.vwap)
      line(tail(data.vwap), "#94a3b8", 0, { lineStyle: LineStyle.Dashed })
    if (ind.bb) {
      const b = bollinger(closes)
      const pick = (
        f: (v: { mid: number; up: number; lo: number }) => number
      ) =>
        b.flatMap((v, i) =>
          v && keep(i) ? [{ time: at(i) as Time, value: f(v) }] : []
        )
      line(
        pick((v) => v.up),
        "rgba(244,114,182,0.8)"
      )
      line(
        pick((v) => v.mid),
        "rgba(244,114,182,0.45)",
        0,
        { lineStyle: LineStyle.Dotted }
      )
      line(
        pick((v) => v.lo),
        "rgba(244,114,182,0.8)"
      )
    }
    if (ind.volume) {
      const v = x.chart.addSeries(HistogramSeries, {
        ...quiet,
        priceScaleId: "vol",
        priceFormat: { type: "volume" },
      })
      x.chart
        .priceScale("vol")
        .applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      v.setData(
        data.candles
          .filter((k) => k.time >= from)
          .map((k) => ({
            time: k.time as Time,
            value: k.volume,
            color:
              k.close >= k.open
                ? "rgba(38,166,154,0.35)"
                : "rgba(239,83,80,0.35)",
          }))
      )
      x.studies.push(v)
    }
    let pane = 1
    if (ind.rsi) {
      const rs = line(tail(data.rsi), "#c084fc", pane, {
        lastValueVisible: true,
      })
      for (const [lvl, col] of [
        [70, DOWN],
        [30, UP],
      ] as const)
        rs.createPriceLine({
          price: lvl,
          color: col,
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: false,
          title: "",
        })
      pane++
    }
    if (ind.macd) {
      const m = macd(closes)
      const rows = m.flatMap((v, i) =>
        v && keep(i) ? [{ t: at(i) as Time, ...v }] : []
      )
      const hist = x.chart.addSeries(HistogramSeries, { ...quiet }, pane)
      hist.setData(
        rows.map((v) => ({
          time: v.t,
          value: v.hist,
          color: v.hist >= 0 ? "rgba(38,166,154,0.6)" : "rgba(239,83,80,0.6)",
        }))
      )
      x.studies.push(hist)
      line(
        rows.map((v) => ({ time: v.t, value: v.line })),
        "#22d3ee",
        pane
      )
      line(
        rows.map((v) => ({ time: v.t, value: v.signal })),
        "#f59e0b",
        pane
      )
      pane++
    }
    const panes = x.chart.panes()
    for (let i = 1; i < panes.length; i++) panes[i].setHeight(90)
    const qs = ["0.1", "0.25", "0.5", "0.75", "0.9"]
    x.cone.forEach((s, i) =>
      s.setData(
        cone?.[qs[i]]
          ? cone[qs[i]].map((p) => ({ time: p.time as Time, value: p.value }))
          : []
      )
    )

    for (const l of x.lines) x.candles.removePriceLine(l)
    x.lines = []
    const add = (
      p: number,
      color: string,
      title: string,
      style: LineStyle,
      width: 1 | 2 = 1
    ) =>
      x.lines.push(
        x.candles.createPriceLine({
          price: p,
          color,
          lineWidth: width,
          lineStyle: style,
          axisLabelVisible: true,
          title,
        })
      )
    const marks: Array<SeriesMarker<Time>> = []
    for (const t of trades) {
      if (t.closed < from) continue
      if (t.opened >= from)
        marks.push({
          time: snap(t.opened),
          position: t.side === "long" ? "belowBar" : "aboveBar",
          shape: t.side === "long" ? "arrowUp" : "arrowDown",
          color: "#60a5fa",
          text: `#${t.id ?? ""} ${t.side === "long" ? "BUY" : "SELL"}`,
        })
      marks.push({
        time: snap(t.closed),
        position: "inBar",
        shape: "circle",
        color: t.pnl >= 0 ? UP : DOWN,
        text: `#${t.id ?? ""} ${t.pnl >= 0 ? "+" : ""}${num(t.pnl, 2)}$`,
      })
    }
    x.pnl.setData([])
    if (pos) {
      // $ result if the stop fills: negative normally, positive once the stop is in profit
      const atStop =
        (pos.side === "long" ? 1 : -1) * (pos.stop - pos.entry) * pos.qty
      const reward = Math.abs(pos.take - pos.entry) * pos.qty
      add(
        pos.entry,
        "#60a5fa",
        `#${pos.id ?? ""} ${pos.side.toUpperCase()}`,
        LineStyle.Solid,
        2
      )
      add(pos.take, "#22c55e", `TP +${usd(reward)}`, LineStyle.Dashed, 2)
      if (pos.tp1 != null && !pos.be)
        add(pos.tp1, "#86efac", "TP1", LineStyle.Dotted)
      add(
        pos.stop,
        "#ef4444",
        pos.be ? "SL BE" : `SL ${atStop >= 0 ? "+" : ""}${usd(atStop)}`,
        LineStyle.Dashed,
        2
      )
      add(pos.liq, "#f59e0b", "LIQ", LineStyle.Dotted)
      if (pos.opened >= from)
        marks.push({
          time: snap(pos.opened),
          position: pos.side === "long" ? "belowBar" : "aboveBar",
          shape: pos.side === "long" ? "arrowUp" : "arrowDown",
          color: "#60a5fa",
          size: 2,
          text: `#${pos.id ?? ""} ${pos.side === "long" ? "BUY" : "SELL"}`,
        })
      const g = "rgba(38,166,154,"
      const r = "rgba(239,83,80,"
      const [top, bottom] = pos.side === "long" ? [g, r] : [r, g]
      x.pnl.applyOptions({
        baseValue: { type: "price", price: pos.entry },
        topFillColor1: `${top}0.3)`,
        topFillColor2: `${top}0.05)`,
        bottomFillColor1: `${bottom}0.05)`,
        bottomFillColor2: `${bottom}0.3)`,
      })
      const start = Number(snap(pos.opened))
      x.pnl.setData(
        cs
          .filter((k) => k.time >= start)
          .map((k) => ({ time: k.time as Time, value: k.close }))
      )
    }
    marks.sort((a, b) => Number(a.time) - Number(b.time))
    x.markers.setMarkers(marks)
    if (!fitted.current) {
      x.chart
        .timeScale()
        .setVisibleLogicalRange({ from: cs.length - 140, to: cs.length + 30 })
      fitted.current = true
    }
  }, [data, pos, trades, cone, ind])

  // the running candle follows every live tick
  useEffect(() => {
    const x = h.current
    const k = last.current
    if (!x || !k || tick == null) return
    k.close = tick
    k.high = Math.max(k.high, tick)
    k.low = Math.min(k.low, tick)
    x.candles.update({ ...k, time: k.time as Time })
  }, [tick])

  return <div ref={host} className="min-h-0 flex-1" />
}

/* ------------------------------------------------------------------ orders panel */

function OrdersPanel({
  symbol,
  pos,
  live,
  odds,
  checklist,
  bias,
  trades,
  log,
}: {
  symbol: string
  pos: LivePosition | null
  live: number | undefined
  odds: TradeProjection | null
  checklist: { long: Array<Check>; short: Array<Check>; ready: boolean } | null
  bias?: string
  trades: Array<DeskTrade>
  log: Array<DeskLog>
}) {
  const feed = log
    .filter(
      (l) =>
        /^(OPEN|CLOSE|TP1|SIGNAL|STOP|FUNDING|TRAINING)/.test(l.msg) &&
        l.msg.includes(symbol.split("-")[0])
    )
    .slice(0, 8)
  return (
    <div className="flex min-h-0 flex-col border-t border-foreground/10 xl:h-[640px] xl:border-t-0 xl:border-l">
      <div className="flex items-center gap-2 border-b border-foreground/10 px-3 py-2">
        <span className="font-heading text-sm font-medium">Orders</span>
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
        </span>
        <span className="text-xs text-muted-foreground">realtime</span>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {pos ? (
          <OpenOrder pos={pos} live={live} odds={odds} />
        ) : (
          <Waiting checklist={checklist} bias={bias} />
        )}

        <div>
          <div className="mb-1 text-xs text-muted-foreground">
            Recent orders
          </div>
          {trades.length === 0 ? (
            <p className="text-xs text-muted-foreground">None closed yet.</p>
          ) : (
            <ul className="grid gap-1 text-xs">
              {trades.slice(0, 6).map((t) => (
                <li
                  key={`${t.id}-${t.closed}`}
                  className="flex items-center gap-2 font-mono tabular-nums"
                >
                  <span className="text-muted-foreground">#{t.id}</span>
                  <span
                    className={
                      t.side === "long" ? "text-emerald-500" : "text-red-500"
                    }
                  >
                    {t.side === "long" ? "BUY" : "SELL"}
                  </span>
                  <span className="text-muted-foreground">{ago(t.closed)}</span>
                  <span className={cn("ml-auto font-semibold", tone(t.pnl))}>
                    {t.pnl >= 0 ? "+" : ""}
                    {num(t.pnl, 2)}$
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-1 text-xs text-muted-foreground">Activity</div>
          {feed.length === 0 ? (
            <p className="text-xs text-muted-foreground">Nothing yet.</p>
          ) : (
            <ul className="grid gap-1.5 text-[11px] leading-snug">
              {feed.map((l) => (
                <li
                  key={`${l.t}-${l.msg.slice(0, 20)}`}
                  className="grid grid-cols-[3.5rem_1fr] gap-1.5"
                >
                  <span className="text-muted-foreground">{ago(l.t)}</span>
                  <span className="line-clamp-2">{l.msg.split(" — ")[0]}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function OpenOrder({
  pos,
  live,
  odds,
}: {
  pos: LivePosition
  live: number | undefined
  odds: TradeProjection | null
}) {
  const long = pos.side === "long"
  const now = live ?? pos.mark ?? pos.entry
  const sgn = long ? 1 : -1
  const upnl = sgn * (now - pos.entry) * pos.qty
  const atStop = sgn * (pos.stop - pos.entry) * pos.qty
  const risk = Math.abs(atStop)
  const reward = Math.abs(pos.take - pos.entry) * pos.qty
  const r = risk ? upnl / risk : 0
  const roe = pos.margin ? (upnl / pos.margin) * 100 : 0
  const at = (x: number) =>
    Math.min(100, Math.max(0, ((x - pos.stop) / (pos.take - pos.stop)) * 100))
  const toTp = (Math.abs(pos.take - now) / now) * 100
  const toSl = (Math.abs(now - pos.stop) / now) * 100
  const left = pos.deadline ? pos.deadline - Date.now() / 1000 : null
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        upnl >= 0 ? "border-emerald-500/40" : "border-red-500/40"
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">
          #{pos.id}
        </span>
        <span
          className={cn(
            "rounded px-1.5 text-xs font-semibold",
            long
              ? "bg-emerald-500/15 text-emerald-500"
              : "bg-red-500/15 text-red-500"
          )}
        >
          {long ? "LONG" : "SHORT"} x{pos.leverage}
        </span>
        <span className="text-[11px] text-muted-foreground">
          {ago(pos.opened)}
        </span>
        {pos.be && <span className="text-[11px] text-sky-400">stop at BE</span>}
      </div>
      <div
        className={cn(
          "mt-2 font-mono text-2xl font-semibold tabular-nums",
          tone(upnl)
        )}
      >
        {upnl >= 0 ? "+" : "-"}${num(Math.abs(upnl), 2)}
      </div>
      <div className="font-mono text-xs text-muted-foreground tabular-nums">
        {r >= 0 ? "+" : ""}
        {num(r, 2)}R · ROE {num(roe, 1)}% · {price(pos.entry)} → {price(now)}
      </div>

      <div className="relative mt-4 mb-5 h-2 rounded-full bg-gradient-to-r from-red-500/60 via-muted to-emerald-500/60">
        <div
          className="absolute top-0 h-2 w-0.5 bg-sky-400"
          style={{ left: `${at(pos.entry)}%` }}
        />
        {pos.tp1 != null && !pos.be && (
          <div
            className="absolute top-0 h-2 w-0.5 bg-emerald-300"
            style={{ left: `${at(pos.tp1)}%` }}
          />
        )}
        <div
          className="absolute -top-1 size-4 -translate-x-1/2 rounded-full border-2 border-background bg-foreground transition-[left] duration-500"
          style={{ left: `${at(now)}%` }}
        />
        <span className="absolute top-3 left-0 text-[10px] text-red-500">
          SL {price(pos.stop)}
        </span>
        <span className="absolute top-3 right-0 text-[10px] text-emerald-500">
          TP {price(pos.take)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums">
        <span>
          to TP <b className="text-emerald-500">{num(toTp, 2)}%</b> · +
          {usd(reward)}
        </span>
        <span>
          to SL <b className="text-red-500">{num(toSl, 2)}%</b> ·{" "}
          {pos.be ? "BE" : `${atStop >= 0 ? "+" : ""}${usd(atStop)}`}
        </span>
        <span className="text-muted-foreground">liq {price(pos.liq)}</span>
        <span className="text-muted-foreground">
          {left != null
            ? left > 0
              ? `${num(left / 3600, 1)}h to time stop`
              : "time stop"
            : ""}
        </span>
      </div>

      {odds && (
        <div className="mt-3 border-t border-foreground/10 pt-2">
          <div className="mb-1 flex items-baseline justify-between text-[11px]">
            <span className="text-muted-foreground">
              Projection {num((odds.horizon_bars * odds.bar_sec) / 3600, 1)}h
            </span>
            <span className={cn("font-mono font-semibold", tone(odds.ev_usd))}>
              EV {odds.ev_usd >= 0 ? "+" : "-"}${num(Math.abs(odds.ev_usd), 2)}
            </span>
          </div>
          <div className="flex h-2 overflow-hidden rounded-full">
            <div
              className="bg-emerald-500"
              style={{ width: `${odds.p_tp_first * 100}%` }}
            />
            <div
              className="bg-muted-foreground/40"
              style={{ width: `${odds.p_neither * 100}%` }}
            />
            <div
              className="bg-red-500"
              style={{ width: `${odds.p_sl_first * 100}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between font-mono text-[11px] tabular-nums">
            <span className="text-emerald-500">
              TP first {num(odds.p_tp_first * 100, 0)}%
            </span>
            {odds.p_tp1_before_sl != null && (
              <span className="text-muted-foreground">
                TP1 {num(odds.p_tp1_before_sl * 100, 0)}%
              </span>
            )}
            <span className="text-red-500">
              SL first {num(odds.p_sl_first * 100, 0)}%
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function Waiting({
  checklist,
  bias,
}: {
  checklist: { long: Array<Check>; short: Array<Check>; ready: boolean } | null
  bias?: string
}) {
  return (
    <div className="rounded-lg border border-dashed p-3">
      <div className="text-sm font-medium">No open order</div>
      <div className="text-xs text-muted-foreground">
        Waiting for the next signal{bias ? ` · market ${bias}` : ""}
      </div>
      {checklist?.ready && (
        <div className="mt-2 grid gap-1.5">
          {(["long", "short"] as const).map((side) => {
            const items = checklist[side]
            const met = items.filter((c) => c.ok).length
            const missing = items.filter((c) => !c.ok).map((c) => c.label)
            return (
              <div key={side} className="text-xs">
                <div className="flex justify-between">
                  <span
                    className={
                      side === "long" ? "text-emerald-500" : "text-red-500"
                    }
                  >
                    {side === "long" ? "▲ Long" : "▼ Short"}
                  </span>
                  <span className="font-mono">
                    {met}/{items.length}
                  </span>
                </div>
                <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={
                      side === "long" ? "h-1 bg-emerald-500" : "h-1 bg-red-500"
                    }
                    style={{
                      width: `${(met / Math.max(items.length, 1)) * 100}%`,
                    }}
                  />
                </div>
                {missing.length > 0 && (
                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                    needs: {missing.join(", ")}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
