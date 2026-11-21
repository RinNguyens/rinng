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
import { cssColor } from "@/lib/chart-sync"
import { ago, num, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"

// 5m trading chart for the MakeMoney paper account (backend: src/rinng/makemoney_signals.py).
// Layers: EMA 21/50/200, daily VWAP, BOS/CHoCH structure, support/resistance, the rule-based
// long/short signals (with their SL/TP and whether TP or SL came first), RSI in its own pane,
// and the account's own orders: closed ones as green/red entry→exit segments, the open one with
// entry/SL/TP/liquidation lines and a profit/loss shaded area.

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
  source?: string
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
type Pt = { time: number; value: number }
type Signal = {
  time: number
  side: "long" | "short"
  entry: number
  stop: number
  take: number
  rsi: number
  atr: number
  reasons: Array<string>
  outcome: "win" | "loss" | "open"
  outcome_time: number | null
}
type Analysis = {
  candles: Array<Candle>
  ema21: Array<Pt>
  ema50: Array<Pt>
  ema200: Array<Pt>
  vwap: Array<Pt>
  rsi: Array<Pt>
  structure: Array<{
    time: number
    from: number
    price: number
    dir: "up" | "down"
    kind: "BOS" | "CHoCH"
  }>
  resistance: Array<number>
  support: Array<number>
  signals: Array<Signal>
  summary: {
    price: number
    bias: string
    rsi: number | null
    atr: number | null
    atr_pct: number | null
    ema21: number
    ema50: number
    ema200: number | null
    vwap: number
    h1_trend: number
    last_structure: {
      kind: string
      dir: string
      price: number
      time: number
    } | null
    last_signal: Signal | null
    signal_stats: {
      count: number
      wins: number
      losses: number
      hit_rate: number | null
    }
  }
}

const UP = "#26a69a"
const DOWN = "#ef5350"
const BAR = 300
const COL = {
  ema21: "#f59e0b",
  ema50: "#38bdf8",
  ema200: "#a78bfa",
  vwap: "#94a3b8",
}
const bar = (t: number) => (Math.floor(t / BAR) * BAR) as Time
type Layer = "ema" | "vwap" | "structure" | "levels" | "signals" | "orders"
const LAYERS: Array<[Layer, string]> = [
  ["signals", "Signals"],
  ["orders", "My orders"],
  ["ema", "EMA 21/50/200"],
  ["vwap", "VWAP"],
  ["structure", "BOS / CHoCH"],
  ["levels", "Support / resistance"],
]

export function TradeChart({
  symbols,
  positions,
  trades,
  autoSignal,
}: {
  symbols: Array<string>
  positions: Array<ChartPosition>
  trades: Array<ChartTrade>
  autoSignal: boolean
}) {
  const [symbol, setSymbol] = useState(symbols[0] ?? "BTC-USDT-PERP")
  const [data, setData] = useState<Analysis | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [on, setOn] = useState<Record<Layer, boolean>>({
    signals: true,
    orders: true,
    ema: true,
    vwap: false,
    structure: true,
    levels: true,
  })
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const base = useRef<{
    candles: ISeriesApi<"Candlestick">
    volume: ISeriesApi<"Histogram">
    pnl: ISeriesApi<"Baseline">
    rsi: ISeriesApi<"Line">
    markers: ISeriesMarkersPluginApi<Time>
  } | null>(null)
  const extra = useRef<{
    lines: Array<IPriceLine>
    series: Array<ISeriesApi<"Line">>
  }>({
    lines: [],
    series: [],
  })
  const fitted = useRef(false)

  useEffect(() => {
    if (!symbols.includes(symbol) && symbols.length) setSymbol(symbols[0])
  }, [symbols, symbol])

  // analysis, refreshed every 15s (the backend caches for 15s too)
  useEffect(() => {
    let alive = true
    fitted.current = false
    setData(null)
    const load = () =>
      fetch(`/api/makemoney/analysis?symbol=${encodeURIComponent(symbol)}`, {
        cache: "no-store",
      })
        .then((r) =>
          r.ok ? r.json() : Promise.reject(new Error(r.statusText))
        )
        .then((a: Analysis) => {
          if (alive) {
            setData(a)
            setErr(null)
          }
        })
        .catch((e: Error) => alive && setErr(e.message))
    load()
    const id = setInterval(load, 15_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbol])

  // chart shell, created once
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
    const pnl = c.addSeries(BaselineSeries, {
      lineVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    const candles = c.addSeries(CandlestickSeries, {
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
    const rsi = c.addSeries(
      LineSeries,
      {
        color: "#c084fc",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
      },
      1
    )
    for (const [lvl, col] of [
      [70, DOWN],
      [50, "#71717a"],
      [30, UP],
    ] as const)
      rsi.createPriceLine({
        price: lvl,
        color: col,
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: false,
        title: "",
      })
    c.panes()[1]?.setHeight(90)
    base.current = {
      candles,
      volume,
      pnl,
      rsi,
      markers: createSeriesMarkers(candles, []),
    }
    chart.current = c
    return () => {
      c.remove()
      chart.current = null
      base.current = null
      extra.current = { lines: [], series: [] }
    }
  }, [])

  const open = positions.find((p) => p.symbol === symbol)
  const closed = useMemo(
    () => trades.filter((t) => t.symbol === symbol),
    [trades, symbol]
  )

  // draw everything
  useEffect(() => {
    const c = chart.current
    const s = base.current
    if (!c || !s || !data?.candles.length) return
    const cs = data.candles
    s.candles.setData(cs.map((k) => ({ ...k, time: k.time as Time })))
    s.volume.setData(
      cs.map((k) => ({
        time: k.time as Time,
        value: k.volume,
        color:
          k.close >= k.open ? "rgba(38,166,154,0.35)" : "rgba(239,83,80,0.35)",
      }))
    )
    s.rsi.setData(
      data.rsi.map((p) => ({ time: p.time as Time, value: p.value }))
    )

    for (const l of extra.current.lines) s.candles.removePriceLine(l)
    for (const x of extra.current.series) c.removeSeries(x)
    extra.current = { lines: [], series: [] }
    const first = cs[0].time
    const lastT = cs[cs.length - 1].time
    const inView = (t: number) => t >= first && t <= lastT + BAR
    const seg = (
      pts: Array<Pt>,
      color: string,
      width: 1 | 2 | 3 = 1,
      style = LineStyle.Solid
    ) => {
      const x = c.addSeries(LineSeries, {
        color,
        lineWidth: width,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      x.setData(pts.map((p) => ({ time: p.time as Time, value: p.value })))
      extra.current.series.push(x)
      return x
    }
    const level = (
      p: number,
      color: string,
      title: string,
      style = LineStyle.Solid,
      axis = true
    ) =>
      extra.current.lines.push(
        s.candles.createPriceLine({
          price: p,
          color,
          lineWidth: 1,
          lineStyle: style,
          axisLabelVisible: axis,
          title,
        })
      )
    const marks: Array<SeriesMarker<Time>> = []

    if (on.ema) {
      seg(data.ema21, COL.ema21)
      seg(data.ema50, COL.ema50)
      seg(data.ema200, COL.ema200, 2)
    }
    if (on.vwap) seg(data.vwap, COL.vwap, 1, LineStyle.Dashed)

    if (on.structure) {
      for (const e of data.structure.slice(-14)) {
        if (!inView(e.from)) continue
        const col = e.dir === "up" ? UP : DOWN
        seg(
          [
            { time: e.from, value: e.price },
            { time: e.time, value: e.price },
          ],
          col,
          1,
          e.kind === "CHoCH" ? LineStyle.Dashed : LineStyle.Solid
        )
        marks.push({
          time: e.time as Time,
          position: e.dir === "up" ? "aboveBar" : "belowBar",
          shape: "square",
          size: 0,
          color: col,
          text: e.kind,
        })
      }
    }

    if (on.levels) {
      data.resistance.forEach((p, i) =>
        level(
          p,
          "rgba(239,83,80,0.55)",
          i ? "" : "R",
          LineStyle.Dotted,
          i === 0
        )
      )
      data.support.forEach((p, i) =>
        level(
          p,
          "rgba(38,166,154,0.55)",
          i ? "" : "S",
          LineStyle.Dotted,
          i === 0
        )
      )
    }

    if (on.signals) {
      const recent = new Set(data.signals.slice(-3))
      for (const g of data.signals) {
        if (!inView(g.time)) continue
        const long = g.side === "long"
        const end = g.outcome_time ?? lastT
        const span = Math.max(end, g.time + BAR)
        // projected trade for the latest signals: TP (green) / SL (red) until the outcome
        if (recent.has(g)) {
          seg(
            [
              { time: g.time, value: g.take },
              { time: span, value: g.take },
            ],
            "rgba(38,166,154,0.8)"
          )
          seg(
            [
              { time: g.time, value: g.stop },
              { time: span, value: g.stop },
            ],
            "rgba(239,83,80,0.8)"
          )
          seg(
            [
              { time: g.time, value: g.entry },
              { time: span, value: g.entry },
            ],
            "rgba(148,163,184,0.7)",
            1,
            LineStyle.Dotted
          )
        }
        marks.push({
          time: g.time as Time,
          position: long ? "belowBar" : "aboveBar",
          shape: long ? "arrowUp" : "arrowDown",
          color: long ? "#22c55e" : "#f43f5e",
          size: 2,
          text: `${long ? "LONG" : "SHORT"}${g.outcome === "win" ? " ✓" : g.outcome === "loss" ? " ✗" : " ●"}`,
        })
      }
    }

    // the account's orders
    s.pnl.setData([])
    if (on.orders) {
      const entryMark = (p: ChartPosition) =>
        marks.push({
          time: bar(p.opened),
          position: p.side === "long" ? "belowBar" : "aboveBar",
          shape: "circle",
          color: "#60a5fa",
          text: `#${p.id ?? "?"} ${p.side === "long" ? "BUY" : "SELL"} x${p.leverage}`,
        })
      for (const t of closed) {
        if (!inView(t.closed)) continue
        const col = t.pnl >= 0 ? UP : DOWN
        const a = Math.max(Number(bar(t.opened)), first)
        const b = Number(bar(t.closed))
        seg(
          b > a
            ? [
                { time: a, value: t.entry },
                { time: b, value: t.exit },
              ]
            : [{ time: b, value: t.exit }],
          col,
          2,
          LineStyle.Dashed
        )
        if (inView(t.opened)) entryMark(t)
        marks.push({
          time: bar(t.closed),
          position: "inBar",
          shape: "circle",
          color: col,
          text: `#${t.id ?? "?"} ${t.pnl >= 0 ? "+" : ""}${num(t.pnl, 2)}$`,
        })
      }
      if (open) {
        const long = open.side === "long"
        const risk = Math.abs(open.entry - open.stop) * open.qty
        const reward = Math.abs(open.take - open.entry) * open.qty
        level(
          open.entry,
          "#60a5fa",
          `#${open.id ?? "?"} ENTRY ${open.upnl >= 0 ? "+" : ""}${num(open.upnl, 2)}$`
        )
        level(open.take, UP, `TP +${num(reward, 2)}$`, LineStyle.Dashed)
        level(open.stop, DOWN, `SL -${num(risk, 2)}$`, LineStyle.Dashed)
        level(open.liq, "#f59e0b", "LIQ", LineStyle.Dotted)
        if (inView(open.opened)) entryMark(open)
        const g = "rgba(38,166,154,",
          r = "rgba(239,83,80,"
        const [top, bottom] = long ? [g, r] : [r, g]
        s.pnl.applyOptions({
          baseValue: { type: "price", price: open.entry },
          topFillColor1: `${top}0.28)`,
          topFillColor2: `${top}0.05)`,
          bottomFillColor1: `${bottom}0.05)`,
          bottomFillColor2: `${bottom}0.28)`,
        })
        const from = Number(bar(open.opened))
        s.pnl.setData(
          cs
            .filter((k) => k.time >= from)
            .map((k) => ({ time: k.time as Time, value: k.close }))
        )
      }
    }

    marks.sort((x, y) => Number(x.time) - Number(y.time))
    s.markers.setMarkers(marks)
    if (!fitted.current) {
      c.timeScale().setVisibleLogicalRange({
        from: cs.length - 220,
        to: cs.length + 6,
      })
      fitted.current = true
    }
  }, [data, open, closed, on])

  const sm = data?.summary
  const sig = sm?.last_signal
  const realized = closed.reduce((a, t) => a + t.pnl, 0)
  const wins = closed.filter((t) => t.pnl > 0).length
  const bull = sm?.bias.startsWith("bull")
  const bear = sm?.bias.startsWith("bear")

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">
          {symbols.map((s) => (
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
              {positions.some((p) => p.symbol === s) && (
                <span className="ml-1 inline-block size-1.5 rounded-full bg-sky-400 align-middle" />
              )}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">5m · Binance live</span>
        <div className="ml-auto flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs tabular-nums">
          {sm && <span>{price(sm.price)}</span>}
          {open && (
            <span>
              #{open.id} {open.side.toUpperCase()} uPnL{" "}
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
              : "no orders"}
          </span>
        </div>
      </div>

      {/* analysis read */}
      {sm && (
        <div className="grid gap-3 md:grid-cols-[1.1fr_1fr]">
          <div
            className={cn(
              "rounded-lg border p-3",
              sig?.outcome === "open" &&
                (sig.side === "long"
                  ? "border-emerald-500/60"
                  : "border-red-500/60")
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Latest signal
              </span>
              {sig ? (
                <>
                  <span
                    className={cn(
                      "rounded px-2 py-0.5 text-sm font-semibold",
                      sig.side === "long"
                        ? "bg-emerald-500/15 text-emerald-500"
                        : "bg-red-500/15 text-red-500"
                    )}
                  >
                    {sig.side === "long" ? "▲ LONG" : "▼ SHORT"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {ago(sig.time + BAR)}
                  </span>
                  <span
                    className={cn(
                      "ml-auto rounded px-1.5 py-0.5 text-xs",
                      sig.outcome === "win" &&
                        "bg-emerald-500/15 text-emerald-500",
                      sig.outcome === "loss" && "bg-red-500/15 text-red-500",
                      sig.outcome === "open" && "bg-sky-500/15 text-sky-400"
                    )}
                  >
                    {sig.outcome === "win"
                      ? "hit TP"
                      : sig.outcome === "loss"
                        ? "hit SL"
                        : "running"}
                  </span>
                </>
              ) : (
                <span className="text-sm text-muted-foreground">
                  none in the last 5 days
                </span>
              )}
            </div>
            {sig && (
              <>
                <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-xs tabular-nums">
                  <div>
                    <div className="text-muted-foreground">Entry</div>
                    {price(sig.entry)}
                  </div>
                  <div>
                    <div className="text-red-500">Stop</div>
                    {price(sig.stop)}
                  </div>
                  <div>
                    <div className="text-emerald-500">Target 2R</div>
                    {price(sig.take)}
                  </div>
                </div>
                <ul className="mt-2 grid gap-0.5 text-xs text-muted-foreground">
                  {sig.reasons.map((r) => (
                    <li key={r}>• {r}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              {autoSignal
                ? "Auto-trade is on: a new signal opens a simulated order at the next market price."
                : "Auto-trade is off: signals are only drawn."}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg border p-3 text-xs">
            <Stat label="Bias">
              <span
                className={cn(
                  "font-semibold",
                  bull && "text-emerald-500",
                  bear && "text-red-500"
                )}
              >
                {sm.bias}
              </span>
            </Stat>
            <Stat label="1h trend">
              <span className={tone(sm.h1_trend)}>
                {sm.h1_trend > 0 ? "up" : sm.h1_trend < 0 ? "down" : "flat"}
              </span>
            </Stat>
            <Stat label="RSI 14">
              <span
                className={cn(
                  sm.rsi != null && sm.rsi > 70 && "text-red-500",
                  sm.rsi != null && sm.rsi < 30 && "text-emerald-500"
                )}
              >
                {sm.rsi != null ? num(sm.rsi, 0) : "–"}
              </span>
            </Stat>
            <Stat label="ATR">
              {sm.atr != null
                ? `${price(sm.atr)} (${num(sm.atr_pct ?? 0, 2)}%)`
                : "–"}
            </Stat>
            <Stat label="vs EMA200">
              {sm.ema200 ? (
                <span className={tone(sm.price - sm.ema200)}>
                  {sm.price >= sm.ema200 ? "above" : "below"} {price(sm.ema200)}
                </span>
              ) : (
                "–"
              )}
            </Stat>
            <Stat label="VWAP">
              <span className={tone(sm.price - sm.vwap)}>
                {sm.price >= sm.vwap ? "above" : "below"} {price(sm.vwap)}
              </span>
            </Stat>
            <Stat label="Structure">
              {sm.last_structure ? (
                <span
                  className={
                    sm.last_structure.dir === "up"
                      ? "text-emerald-500"
                      : "text-red-500"
                  }
                >
                  {sm.last_structure.kind} {sm.last_structure.dir} @{" "}
                  {price(sm.last_structure.price)}
                </span>
              ) : (
                "–"
              )}
            </Stat>
            <Stat label="Nearest S / R">
              <span className="text-emerald-500">
                {data.support[0] ? price(data.support[0]) : "–"}
              </span>
              {" / "}
              <span className="text-red-500">
                {data.resistance[0] ? price(data.resistance[0]) : "–"}
              </span>
            </Stat>
            <Stat label="Signal record (5d)">
              {sm.signal_stats.count} signals · {sm.signal_stats.wins}✓{" "}
              {sm.signal_stats.losses}✗
            </Stat>
            <Stat label="Hit rate @2R">
              {sm.signal_stats.hit_rate != null ? (
                <span
                  className={
                    sm.signal_stats.hit_rate >= 34
                      ? "text-emerald-500"
                      : "text-red-500"
                  }
                >
                  {num(sm.signal_stats.hit_rate, 0)}%
                </span>
              ) : (
                "–"
              )}{" "}
              <span className="text-muted-foreground">(break-even ≈ 34%)</span>
            </Stat>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {LAYERS.map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setOn((o) => ({ ...o, [k]: !o[k] }))}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-xs",
              on[k]
                ? "border-foreground/50 bg-muted text-foreground"
                : "text-muted-foreground line-through"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="relative h-[520px] w-full">
        <div ref={host} className="absolute inset-0" />
        {!data && !err && (
          <div className="absolute inset-0 grid place-items-center text-sm text-muted-foreground">
            Loading analysis…
          </div>
        )}
        {err && (
          <div className="absolute inset-x-0 top-2 mx-auto w-fit rounded bg-destructive/15 px-2 py-1 text-xs text-destructive">
            {err}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <Legend color="#22c55e" label="▲ Long signal" />
        <Legend color="#f43f5e" label="▼ Short signal" />
        <span>✓ hit TP · ✗ hit SL · ● running</span>
        <Legend color={COL.ema21} label="EMA21" />
        <Legend color={COL.ema50} label="EMA50" />
        <Legend color={COL.ema200} label="EMA200" />
        <Legend color="#60a5fa" label="My order entry" />
        <Legend color={UP} label="Win / TP" dashed />
        <Legend color={DOWN} label="Loss / SL" dashed />
        <Legend color="#f59e0b" label="Liquidation" dashed />
        <Legend color="#c084fc" label="RSI (lower pane)" />
      </div>
    </div>
  )
}

function Stat({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-mono tabular-nums">{children}</span>
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
