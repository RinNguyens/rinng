// Live desk: one 5m chart carrying every overlay (structure, liquidity, profile, EMAs, projection,
// setups) with a smoothly moving running candle, next to the rule-based agents' read.
import { useEffect, useRef, useState } from "react"
import {
  CandlestickSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
} from "lightweight-charts"
import type {
  IChartApi,
  ISeriesApi,
  ISeriesMarkersPluginApi,
  Time,
} from "lightweight-charts"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import type { AgentVote, Desk, Scenario } from "@/lib/api"
import { cssColor } from "@/lib/chart-sync"
import { live, useBarClose, useLiveQuote, useLiveState } from "@/lib/live"
import type { LiveBar } from "@/lib/live"
import { RinngOverlay } from "@/lib/overlay"
import { cn } from "@/lib/utils"

const TF = "5m"
const BAR = 300 // seconds in one candle
const UP = "#26a69a"
const DOWN = "#ef5350"
const HISTORY = 132 // candles in view before the projection (11 hours)

const LAYERS: Array<{ id: string; label: string; color: string }> = [
  { id: "structure", label: "Structure", color: UP },
  { id: "liquidity", label: "Liquidity", color: "#ab47bc" },
  { id: "profile", label: "Profile", color: "#ff9800" },
  { id: "ema", label: "EMA", color: "#42a5f5" },
  { id: "projection", label: "Projection", color: "#90caf9" },
  { id: "setups", label: "Setups", color: "#e0e0e0" },
]
const STORE = "rinng.desk.layers"

const num = (v: number, d = 0) =>
  v.toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })
const price = (v: number | null | undefined) =>
  v == null ? "—" : num(v, v >= 1000 ? 1 : v >= 1 ? 2 : 5)
const odds = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`)

const reducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches

function loadLayers(): Record<string, boolean> {
  const on = Object.fromEntries(LAYERS.map((l) => [l.id, true]))
  try {
    return {
      ...on,
      ...(JSON.parse(localStorage.getItem(STORE) ?? "{}") as Record<
        string,
        boolean
      >),
    }
  } catch {
    return on
  }
}

type Handles = {
  chart: IChartApi
  candles: ISeriesApi<"Candlestick">
  overlay: RinngOverlay
  markers: ISeriesMarkersPluginApi<Time>
  lines: Map<string, ISeriesApi<"Line">>
}

export function LiveDesk({
  symbol,
  exchange,
}: {
  symbol: string
  exchange: string
}) {
  const key = `${exchange}:${symbol}`
  const [loaded, setLoaded] = useState<{ key: string; data: Desk } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rev, setRev] = useState(0)
  const [layers, setLayers] = useState(loadLayers)
  const state = useLiveState()
  const data = loaded?.key === key ? loaded.data : null

  useBarClose(symbol, exchange, TF, () => setRev((n) => n + 1))
  // Without the live feed nothing announces a candle close: ask again every minute.
  useEffect(() => {
    if (state !== "static" && state !== "offline") return
    const t = setInterval(() => setRev((n) => n + 1), 60_000)
    return () => clearInterval(t)
  }, [state])

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .desk({ symbol, exchange })
      .then(
        (d) => alive && setLoaded({ key: `${exchange}:${symbol}`, data: d })
      )
      .catch((e: Error) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [symbol, exchange, rev])

  const toggle = (id: string) =>
    setLayers((cur) => {
      const next = { ...cur, [id]: !cur[id] }
      try {
        localStorage.setItem(STORE, JSON.stringify(next))
      } catch {
        /* storage unavailable: the choice lasts for this page only */
      }
      return next
    })

  return (
    <Card size="sm" className="shrink-0 gap-0 overflow-hidden py-0">
      <div className="grid grid-cols-1 xl:grid-cols-3">
        <div className="flex h-[480px] min-w-0 flex-col xl:col-span-2 xl:h-[660px]">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-foreground/10 px-3 py-2">
            <span className="font-heading text-sm font-medium">Live desk</span>
            <Badge variant="outline" className="font-heading text-[10px]">
              5m
            </Badge>
            <LivePrice
              symbol={symbol}
              exchange={exchange}
              fallback={data?.candles.at(-1)?.close}
            />
            <CandleClock />
            <div className="ml-auto flex flex-wrap gap-1">
              {LAYERS.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  aria-pressed={layers[l.id]}
                  onClick={() => toggle(l.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] ring-1 transition-colors",
                    layers[l.id]
                      ? "bg-muted text-foreground ring-foreground/15"
                      : "text-muted-foreground ring-foreground/10 hover:text-foreground"
                  )}
                >
                  <i
                    className="inline-block size-1.5 rounded-full transition-opacity"
                    style={{
                      background: l.color,
                      opacity: layers[l.id] ? 1 : 0.3,
                    }}
                  />
                  {l.label}
                </button>
              ))}
            </div>
          </div>
          <DeskChart
            key={key}
            symbol={symbol}
            exchange={exchange}
            data={data}
            layers={layers}
            error={error}
          />
        </div>
        <div className="min-h-0 border-t border-foreground/10 xl:h-[660px] xl:overflow-y-auto xl:border-t-0 xl:border-l">
          {data ? (
            <AgentPanel data={data} />
          ) : (
            <div className="space-y-3 p-4">
              {error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : (
                Array.from({ length: 7 }, (_, i) => (
                  <Skeleton key={i} className="h-14 rounded-xl" />
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

// ----------------------------------------------------------------- header pieces

function LivePrice({
  symbol,
  exchange,
  fallback,
}: {
  symbol: string
  exchange: string
  fallback?: number
}) {
  const { tick } = useLiveQuote(symbol, exchange)
  const value = tick?.price ?? fallback
  const last = useRef<number | undefined>(undefined)
  const [dir, setDir] = useState(0)
  useEffect(() => {
    if (value == null) return
    if (last.current != null && value !== last.current)
      setDir(value > last.current ? 1 : -1)
    last.current = value
  }, [value])
  return (
    <span
      className={cn(
        "font-heading text-sm tabular-nums transition-colors duration-500",
        dir > 0 ? "text-up" : dir < 0 ? "text-down" : ""
      )}
    >
      {price(value)}
    </span>
  )
}

// Time left in the running 5m candle, with a bar that fills as the candle ages.
function CandleClock() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const into = (now / 1000) % BAR
  const left = Math.ceil(BAR - into)
  return (
    <span className="inline-flex items-center gap-2 font-heading text-[11px] text-muted-foreground tabular-nums">
      <span className="relative h-1 w-16 overflow-hidden rounded-full bg-muted">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-foreground/50 transition-[width] duration-1000 ease-linear"
          style={{ width: `${(into / BAR) * 100}%` }}
        />
      </span>
      closes in {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
    </span>
  )
}

// ----------------------------------------------------------------- chart

function DeskChart({
  symbol,
  exchange,
  data,
  layers,
  error,
}: {
  symbol: string
  exchange: string
  data: Desk | null
  layers: Record<string, boolean>
  error: string | null
}) {
  const host = useRef<HTMLDivElement>(null)
  const dot = useRef<HTMLSpanElement>(null)
  const handles = useRef<Handles | null>(null)
  // Closed candles currently drawn, the running candle and the price being shown for it.
  const closed = useRef<{ time: number; close: number }>({ time: 0, close: 0 })
  const running = useRef<LiveBar | null>(null)
  const shown = useRef<number | null>(null)
  const touched = useRef(false)
  const revealed = useRef(0)

  // The chart lives as long as the instrument: reloads update its series in place.
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
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
    })
    const overlay = new RinngOverlay([])
    overlay.coneMedian = true
    candles.attachPrimitive(overlay)
    handles.current = {
      chart,
      candles,
      overlay,
      markers: createSeriesMarkers(candles, []),
      lines: new Map(),
    }

    // Any manual pan/zoom stops the view from snapping back to "now" on the next candle.
    const touch = () => {
      touched.current = true
    }
    el.addEventListener("pointerdown", touch)
    el.addEventListener("wheel", touch, { passive: true })

    const place = () => {
      const d = dot.current
      const bar = running.current
      const t = bar?.time ?? closed.current.time
      const p = bar ? (shown.current ?? bar.close) : closed.current.close
      const x = t ? chart.timeScale().timeToCoordinate(t as Time) : null
      const y = candles.priceToCoordinate(p)
      if (!d) return
      if (x == null || y == null) {
        d.style.opacity = "0"
        return
      }
      d.style.opacity = "1"
      d.style.transform = `translate(${x}px, ${y}px)`
      d.dataset.dir = bar && p < bar.open ? "down" : "up"
      d.dataset.live = bar ? "1" : "0"
    }

    // Each frame the drawn close moves part of the way to the latest price: the candle glides.
    const calm = reducedMotion()
    let raf = 0
    const frame = () => {
      raf = requestAnimationFrame(frame)
      const bar = running.current
      if (!bar) return
      const from = shown.current ?? bar.close
      const gap = bar.close - from
      const step =
        calm || Math.abs(gap) < Math.abs(bar.close) * 1e-6 ? gap : gap * 0.18
      if (step === 0 && shown.current != null) return
      const at = from + step
      shown.current = at
      const up = at >= bar.open
      const color = up ? "rgba(38,166,154,0.7)" : "rgba(239,83,80,0.7)"
      try {
        candles.update({
          time: bar.time as Time,
          open: bar.open,
          high: Math.max(bar.high, at),
          low: Math.min(bar.low, at),
          close: at,
          color,
          wickColor: color,
        })
      } catch {
        /* older than the series' last point */
      }
      place()
    }
    raf = requestAnimationFrame(frame)

    const offLive = live.on((e) => {
      if (e.type === "status" || e.symbol !== symbol || e.exchange !== exchange)
        return
      const last = closed.current
      if (!last.time) return
      if (e.type === "bar" && e.tf === TF && e.bar.time > last.time) {
        running.current = { ...e.bar }
      } else if (e.type === "tick") {
        const start = Math.floor(Date.now() / 1000 / BAR) * BAR
        let bar = running.current
        if (!bar || bar.time < start) {
          if (start <= last.time) return
          // No candle event yet for this period: open one at the previous close.
          const open = bar?.close ?? last.close
          bar = {
            time: start,
            open,
            high: open,
            low: open,
            close: open,
            volume: 0,
          }
          shown.current = open
        }
        running.current = {
          ...bar,
          close: e.price,
          high: Math.max(bar.high, e.price),
          low: Math.min(bar.low, e.price),
        }
      }
    })
    chart.timeScale().subscribeVisibleLogicalRangeChange(place)
    const tick = setInterval(place, 250) // price-scale drags and resizes fire no event

    return () => {
      cancelAnimationFrame(raf)
      clearInterval(tick)
      offLive()
      el.removeEventListener("pointerdown", touch)
      el.removeEventListener("wheel", touch)
      handles.current = null
      chart.remove()
    }
  }, [symbol, exchange])

  useEffect(() => {
    const h = handles.current
    if (!h || !data) return
    const on = <T extends { layer?: string }>(items: Array<T> | undefined) =>
      (items ?? []).filter((i) => !i.layer || layers[i.layer])
    const times = data.candles.map((c) => c.time)
    const lastTime = times[times.length - 1]
    closed.current = {
      time: lastTime,
      close: data.candles[data.candles.length - 1].close,
    }
    if (running.current && running.current.time <= lastTime) {
      running.current = null
      shown.current = null
    }
    h.candles.setData(data.candles.map((c) => ({ ...c, time: c.time as Time })))
    h.overlay.setTimes(times)
    h.overlay.set({
      ...data,
      zones: on(data.zones),
      levels: on(data.levels),
      profiles: on(data.profiles),
      forecast: layers.projection ? data.forecast : undefined,
    })
    h.markers.setMarkers(
      on(data.markers).map((m) => ({ ...m, time: m.time as Time }))
    )
    for (const ln of data.lines ?? []) {
      let s = h.lines.get(ln.name)
      if (!s) {
        s = h.chart.addSeries(LineSeries, {
          color: ln.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        h.lines.set(ln.name, s)
      }
      s.setData(ln.data.map((d) => ({ ...d, time: d.time as Time })))
      s.applyOptions({ visible: !ln.layer || layers[ln.layer] })
    }
    if (!touched.current) {
      const n = times.length
      const ahead =
        data.forecast && layers.projection ? data.forecast.horizon + 6 : 10
      h.chart
        .timeScale()
        .setVisibleLogicalRange({ from: n - HISTORY, to: n + ahead })
    }
    // A new candle: the projection sweeps out again from the new origin.
    if (revealed.current !== lastTime && data.forecast && !reducedMotion()) {
      revealed.current = lastTime
      const t0 = performance.now()
      let raf = 0
      const sweep = (now: number) => {
        const k = Math.min(1, (now - t0) / 900)
        handles.current?.overlay.reveal(1 - (1 - k) ** 3)
        if (k < 1) raf = requestAnimationFrame(sweep)
      }
      raf = requestAnimationFrame(sweep)
      return () => {
        cancelAnimationFrame(raf)
        handles.current?.overlay.reveal(1)
      }
    }
    revealed.current = lastTime
    h.overlay.reveal(1)
  }, [data, layers])

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={host} className="absolute inset-0" />
      <span ref={dot} className="desk-dot" style={{ opacity: 0 }} aria-hidden />
      {!data && !error ? (
        <Skeleton className="absolute inset-3 rounded-xl" />
      ) : null}
      {error && !data ? (
        <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-destructive">
          {error}
        </div>
      ) : null}
    </div>
  )
}

// ----------------------------------------------------------------- agents

const STANCE = {
  buy: { label: "Buy", cls: "bg-up/15 text-up" },
  sell: { label: "Sell", cls: "bg-down/15 text-down" },
  wait: { label: "Wait", cls: "bg-muted text-muted-foreground" },
} as const

// Bar that grows from the centre: left = sell, right = buy.
function Lean({ score, className }: { score: number; className?: string }) {
  const w = Math.min(1, Math.abs(score)) * 50
  return (
    <div
      className={cn(
        "relative h-1.5 overflow-hidden rounded-full bg-muted",
        className
      )}
    >
      <span
        className={cn(
          "absolute inset-y-0 rounded-full transition-[width,left] duration-700 ease-out",
          score >= 0 ? "bg-up" : "bg-down"
        )}
        style={{ left: score >= 0 ? "50%" : `${50 - w}%`, width: `${w}%` }}
      />
      <span className="absolute inset-y-0 left-1/2 w-px bg-foreground/40" />
    </div>
  )
}

function AgentPanel({ data }: { data: Desk }) {
  const v = data.verdict
  const [open, setOpen] = useState<string | null>(null)
  const title =
    v.lean === "long"
      ? "Leaning long"
      : v.lean === "short"
        ? "Leaning short"
        : "No clear edge"
  const at = data.candles.at(-1)?.time
  return (
    <div className="space-y-4 p-4">
      <section className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            Agent consensus · 5m
          </span>
          <span className="font-heading text-[11px] text-muted-foreground">
            {at
              ? `candle ${new Date((at + BAR) * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
              : ""}
          </span>
        </div>
        <div className="flex items-end justify-between gap-3">
          <span
            className={cn(
              "font-heading text-2xl font-medium tracking-tight",
              v.lean === "long"
                ? "text-up"
                : v.lean === "short"
                  ? "text-down"
                  : ""
            )}
          >
            {title}
          </span>
          <span className="pb-1 font-heading text-sm text-muted-foreground tabular-nums">
            {v.score >= 0 ? "+" : "−"}
            {Math.round(Math.abs(v.score) * 100)}
          </span>
        </div>
        <Lean score={v.score} className="h-2" />
        <div className="flex justify-between font-heading text-[11px] text-muted-foreground">
          <span className="text-down">{v.sell} sell</span>
          <span>{v.wait} wait</span>
          <span className="text-up">{v.buy} buy</span>
        </div>
      </section>

      <section className="space-y-1.5">
        {data.agents.map((a, i) => (
          <AgentRow
            key={a.id}
            a={a}
            index={i}
            open={open === a.id}
            onToggle={() => setOpen(open === a.id ? null : a.id)}
          />
        ))}
      </section>

      <section className="space-y-2">
        <div className="text-xs text-muted-foreground">
          Setups if price gets there
        </div>
        {data.scenarios.map((s, i) => (
          <Setup key={s.side} s={s} total={v.total} index={i} />
        ))}
      </section>

      <p className="text-[11px] leading-snug text-muted-foreground">
        Rule-based readings of closed 5m candles, refreshed at every candle
        close. Touch odds come from the projection and are measured from the
        current price over the next {data.forecast?.horizon ?? 48} candles. Not
        trading advice.
      </p>
    </div>
  )
}

function AgentRow({
  a,
  index,
  open,
  onToggle,
}: {
  a: AgentVote
  index: number
  open: boolean
  onToggle: () => void
}) {
  const st = STANCE[a.stance]
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="desk-in block w-full rounded-xl bg-muted/40 p-2.5 text-left transition-colors hover:bg-muted/70"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm">{a.name}</span>
        <span className="font-heading text-[10px] text-muted-foreground tabular-nums">
          conf {Math.round(a.confidence * 100)}%
        </span>
        <span
          className={cn(
            "rounded-md px-1.5 py-0.5 font-heading text-[10px] font-medium",
            st.cls
          )}
        >
          {st.label}
        </span>
      </div>
      <Lean score={a.score} className="mt-2" />
      {open ? (
        <ul className="mt-2 space-y-1 text-xs leading-snug text-muted-foreground">
          {a.reasons.map((r) => (
            <li key={r} className="flex gap-1.5">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-foreground/30" />
              {r}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1.5 truncate text-xs text-muted-foreground">
          {a.reasons[0]}
        </p>
      )}
    </button>
  )
}

function Setup({
  s,
  total,
  index,
}: {
  s: Scenario
  total: number
  index: number
}) {
  const long = s.side === "long"
  return (
    <div
      className={cn(
        "desk-in space-y-2 rounded-xl p-2.5 ring-1",
        long ? "bg-up/5 ring-up/20" : "bg-down/5 ring-down/20"
      )}
      style={{ animationDelay: `${(index + 6) * 50}ms` }}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "font-heading text-sm font-medium",
            long ? "text-up" : "text-down"
          )}
        >
          {long ? "Long" : "Short"} setup
        </span>
        <span className="text-[11px] text-muted-foreground">
          {s.aligned ? "with the lean" : "against the lean"} · {s.favor}/{total}{" "}
          agents
        </span>
        <span className="ml-auto font-heading text-xs tabular-nums">
          R:R {s.rr == null ? "—" : num(s.rr, 1)}
        </span>
      </div>
      <div className="grid grid-cols-[1.6fr_1fr_1.2fr] gap-2 font-heading text-xs tabular-nums">
        <Cell
          k="Entry zone"
          v={`${price(s.zone[0])} – ${price(s.zone[1])}`}
          sub={s.zone_label}
        />
        <Cell
          k="Invalidation"
          v={price(s.stop)}
          sub={`touch ${odds(s.p_stop)}`}
        />
        <Cell
          k="Target"
          v={price(s.target)}
          sub={`${s.target_label} · touch ${odds(s.p_target)}`}
        />
      </div>
      <p className="text-xs leading-snug text-muted-foreground">
        {s.trigger}
        {s.p_entry != null
          ? ` (${odds(s.p_entry)} chance price gets there).`
          : "."}
      </p>
    </div>
  )
}

function Cell({ k, v, sub }: { k: string; v: string; sub: string }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <div className="font-sans text-[11px] text-muted-foreground">{k}</div>
      <div className="truncate">{v}</div>
      <div className="truncate font-sans text-[11px] text-muted-foreground">
        {sub}
      </div>
    </div>
  )
}
