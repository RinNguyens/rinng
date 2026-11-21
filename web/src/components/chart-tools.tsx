// Drawing tools over a lightweight-charts chart: a vertical toolbar (crosshair, trend line,
// horizontal price line, Fibonacci retracement, zone, date range, ruler, text, brush, magnet,
// eraser) and an SVG layer that keeps every drawing pinned to time/price while the chart
// scrolls and rescales. Drawings are saved per symbol + timeframe in localStorage.
// `autoFib` draws the retracement of the window's major swing with 0.618 highlighted.
import { useEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import type { IChartApi, ISeriesApi, Logical } from "lightweight-charts"
import { cn } from "@/lib/utils"

export type Candle = {
  time: number
  open: number
  high: number
  low: number
  close: number
}
type Pt = { t: number; p: number }
type Tool =
  | "cursor"
  | "trend"
  | "hline"
  | "fib"
  | "zone"
  | "range"
  | "ruler"
  | "text"
  | "brush"
type Drawing =
  | { id: number; kind: "trend" | "fib" | "zone" | "range"; a: Pt; b: Pt }
  | { id: number; kind: "hline"; a: Pt }
  | { id: number; kind: "text"; a: Pt; text: string }
  | { id: number; kind: "brush"; pts: Array<Pt> }

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.65, 0.786, 1]
const GOLD = "#f5b301"
const INK = "#60a5fa"
const fmt = (v: number) =>
  v.toLocaleString("en-US", {
    maximumFractionDigits: v >= 1000 ? 1 : v >= 1 ? 3 : 6,
  })

/* ---------------------------------------------------------- geometry */

// Time <-> logical index, extrapolating past both ends with the bar spacing.
function makeAxis(times: Array<number>) {
  const n = times.length
  const step = n > 1 ? times[n - 1] - times[n - 2] : 60
  const toLogical = (t: number) => {
    if (n === 0) return 0
    if (t <= times[0]) return (t - times[0]) / step
    if (t >= times[n - 1]) return n - 1 + (t - times[n - 1]) / step
    let lo = 0
    let hi = n - 1
    while (hi - lo > 1) {
      const m = (lo + hi) >> 1
      if (times[m] <= t) lo = m
      else hi = m
    }
    return lo + (t - times[lo]) / (times[hi] - times[lo] || 1)
  }
  const toTime = (l: number) => {
    if (n === 0) return 0
    if (l <= 0) return times[0] + l * step
    if (l >= n - 1) return times[n - 1] + (l - (n - 1)) * step
    const i = Math.floor(l)
    return times[i] + (l - i) * (times[i + 1] - times[i])
  }
  return { toLogical, toTime, step }
}

// The window's major swing: highest high and lowest low, in the order they happened.
export function majorSwing(candles: Array<Candle>) {
  if (candles.length < 2) return null
  let hi = 0
  let lo = 0
  candles.forEach((c, i) => {
    if (c.high > candles[hi].high) hi = i
    if (c.low < candles[lo].low) lo = i
  })
  const H = { t: candles[hi].time, p: candles[hi].high }
  const L = { t: candles[lo].time, p: candles[lo].low }
  // a = where the move started (level 1), b = where it ended (level 0)
  return lo > hi ? { a: H, b: L, down: true } : { a: L, b: H, down: false }
}

/* ---------------------------------------------------------- icons */

const I = ({ children }: { children: ReactNode }) => (
  <svg
    viewBox="0 0 24 24"
    className="size-[18px]"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.6}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
)
const ICONS: Record<Tool | "magnet" | "erase" | "auto", ReactNode> = {
  cursor: (
    <I>
      <path d="M12 3v7M12 14v7M3 12h7M14 12h7" />
    </I>
  ),
  trend: (
    <I>
      <path d="M6 18 18 6" />
      <circle cx="5" cy="19" r="2" />
      <circle cx="19" cy="5" r="2" />
    </I>
  ),
  hline: (
    <I>
      <path d="M3 17h18" />
      <circle cx="5" cy="17" r="2" />
      <path d="M11 9V5l-1 1M14 5h2.5v2H14v2h2.5M19 5h2v4h-2M19 7h2" />
    </I>
  ),
  fib: (
    <I>
      <path d="M3 5h18M3 10h18M3 14h18M3 19h18" />
      <circle cx="7" cy="5" r="1.6" />
      <circle cx="17" cy="19" r="1.6" />
    </I>
  ),
  zone: (
    <I>
      <rect x="4" y="6" width="16" height="12" rx="1" />
    </I>
  ),
  range: (
    <I>
      <path d="M4 4v16M20 4v16M7 12h10M14 9l3 3-3 3" />
    </I>
  ),
  ruler: (
    <I>
      <path d="M4 16 16 4l4 4L8 20z" />
      <path d="m8 12 2 2M11 9l2 2M14 6l2 2" />
    </I>
  ),
  text: (
    <I>
      <path d="M5 6V4h14v2M12 4v16M9 20h6" />
    </I>
  ),
  brush: (
    <I>
      <path d="M14 6l4 4-7 7H7v-4z" />
      <path d="M4 20c2 0 3-1 3-3" />
    </I>
  ),
  magnet: (
    <I>
      <path d="M6 4v8a6 6 0 0 0 12 0V4h-4v8a2 2 0 0 1-4 0V4z" />
      <path d="M6 8h4M14 8h4" />
    </I>
  ),
  erase: (
    <I>
      <path d="m7 21-4-4L14 6l6 6-9 9z" />
      <path d="M21 21H7M9 11l6 6" />
    </I>
  ),
  auto: (
    <I>
      <path d="M3 6h18M3 12h18M3 18h18" />
      <path d="M17 9.5l1-1 1 1" />
    </I>
  ),
}
const TOOLS: Array<[Tool, string]> = [
  ["cursor", "Crosshair"],
  ["trend", "Trend line"],
  ["hline", "Horizontal line (price)"],
  ["fib", "Fibonacci retracement"],
  ["zone", "Zone"],
  ["range", "Date & price range"],
  ["ruler", "Ruler (measure)"],
  ["text", "Text"],
  ["brush", "Brush"],
]

/* ---------------------------------------------------------- component */

export function ChartTools({
  chart,
  series,
  candles,
  storageKey,
  autoFib,
  fibBars,
}: {
  chart: IChartApi
  series: ISeriesApi<"Candlestick">
  candles: Array<Candle>
  storageKey: string
  autoFib?: boolean
  // auto Fibonacci over the last N candles only (default: the whole window)
  fibBars?: number
}) {
  const times = useMemo(() => candles.map((c) => c.time), [candles])
  const axis = useMemo(() => makeAxis(times), [times])
  const svg = useRef<SVGSVGElement>(null)
  const [tool, setTool] = useState<Tool>("cursor")
  const [magnet, setMagnet] = useState(true)
  const [showAuto, setShowAuto] = useState(autoFib ?? false)
  const [drawings, setDrawings] = useState<Array<Drawing>>(() =>
    load(storageKey)
  )
  const [draft, setDraft] = useState<Drawing | null>(null)
  const [ruler, setRuler] = useState<{ a: Pt; b: Pt } | null>(null)
  const [, setFrame] = useState(0)

  useEffect(() => setDrawings(load(storageKey)), [storageKey])
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(drawings))
    } catch {
      /* no storage */
    }
  }, [storageKey, drawings])
  useEffect(() => setShowAuto(autoFib ?? false), [autoFib])

  // Re-project on every scroll, zoom, rescale or resize.
  useEffect(() => {
    let raf = 0
    const bump = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => setFrame((n) => n + 1))
    }
    const ts = chart.timeScale()
    ts.subscribeVisibleLogicalRangeChange(bump)
    chart.subscribeCrosshairMove(bump)
    const iv = setInterval(bump, 400) // price-scale autoscale has no event
    return () => {
      ts.unsubscribeVisibleLogicalRangeChange(bump)
      chart.unsubscribeCrosshairMove(bump)
      clearInterval(iv)
      cancelAnimationFrame(raf)
    }
  }, [chart])

  // Crosshair tool lets the chart pan/zoom; every other tool captures the mouse.
  useEffect(() => {
    const drawing = tool !== "cursor"
    chart.applyOptions({
      handleScroll: !drawing,
      handleScale: !drawing,
    })
  }, [chart, tool])

  const x = (t: number) =>
    chart.timeScale().logicalToCoordinate(axis.toLogical(t) as Logical) ?? -1e4
  const y = (p: number) => series.priceToCoordinate(p) ?? -1e4

  const toPt = (e: React.PointerEvent): Pt | null => {
    const r = svg.current?.getBoundingClientRect()
    if (!r) return null
    const px = e.clientX - r.left
    const py = e.clientY - r.top
    const l = chart.timeScale().coordinateToLogical(px)
    const p = series.coordinateToPrice(py)
    if (l == null || p == null) return null
    let t = axis.toTime(l)
    let price: number = p
    if (magnet && times.length) {
      const i = Math.round(l)
      const c = candles[Math.min(candles.length - 1, Math.max(0, i))]
      if (i >= 0 && i < candles.length) {
        t = c.time
        const opts = [c.open, c.high, c.low, c.close]
        const near = opts.reduce((b, v) =>
          Math.abs(y(v) - py) < Math.abs(y(b) - py) ? v : b
        )
        if (Math.abs(y(near) - py) < 30) price = near
      }
    }
    return { t, p: price }
  }

  const nextId = () => Date.now() + Math.random()

  const onDown = (e: React.PointerEvent) => {
    if (tool === "cursor") return
    const pt = toPt(e)
    if (!pt) return
    ;(e.target as Element).setPointerCapture(e.pointerId)
    if (tool === "hline") {
      setDrawings((d) => [...d, { id: nextId(), kind: "hline", a: pt }])
      setTool("cursor")
    } else if (tool === "text") {
      const text = window.prompt("Text")
      if (text) {
        setDrawings((d) => [...d, { id: nextId(), kind: "text", a: pt, text }])
      }
      setTool("cursor")
    } else if (tool === "brush") {
      setDraft({ id: nextId(), kind: "brush", pts: [pt] })
    } else if (tool === "ruler") {
      setRuler({ a: pt, b: pt })
    } else {
      setDraft({ id: nextId(), kind: tool, a: pt, b: pt })
    }
  }
  const onMove = (e: React.PointerEvent) => {
    if (!draft && !ruler) return
    const pt = toPt(e)
    if (!pt) return
    if (ruler) setRuler({ a: ruler.a, b: pt })
    if (draft?.kind === "brush") setDraft({ ...draft, pts: [...draft.pts, pt] })
    else if (draft && "b" in draft) setDraft({ ...draft, b: pt })
  }
  const onUp = () => {
    if (draft) {
      const tiny =
        "b" in draft &&
        Math.abs(x(draft.a.t) - x(draft.b.t)) < 3 &&
        Math.abs(y(draft.a.p) - y(draft.b.p)) < 3
      if (!tiny) setDrawings((d) => [...d, draft])
      setDraft(null)
      setTool("cursor")
    }
  }

  const swing = useMemo(
    () => majorSwing(fibBars ? candles.slice(-fibBars) : candles),
    [candles, fibBars]
  )
  const el = svg.current
  const W = el?.clientWidth ?? 0
  const plotW = W - (chart.priceScale("right").width() || 0)

  const renderOne = (d: Drawing, ghost = false) => {
    const k = String(d.id)
    const o = ghost ? 0.7 : 1
    switch (d.kind) {
      case "trend":
        return (
          <g key={k} opacity={o}>
            <line
              x1={x(d.a.t)}
              y1={y(d.a.p)}
              x2={x(d.b.t)}
              y2={y(d.b.p)}
              stroke={INK}
              strokeWidth={1.5}
            />
            <circle cx={x(d.a.t)} cy={y(d.a.p)} r={3} fill={INK} />
            <circle cx={x(d.b.t)} cy={y(d.b.p)} r={3} fill={INK} />
          </g>
        )
      case "hline":
        return (
          <g key={k}>
            <line
              x1={0}
              x2={plotW}
              y1={y(d.a.p)}
              y2={y(d.a.p)}
              stroke={INK}
              strokeWidth={1}
            />
            <Tag x={plotW - 4} y={y(d.a.p)} color={INK} anchor="end">
              {fmt(d.a.p)}
            </Tag>
          </g>
        )
      case "fib":
        return (
          <Fib
            key={k}
            x0={Math.min(x(d.a.t), x(d.b.t))}
            x1={Math.max(x(d.a.t), x(d.b.t), plotW)}
            a={d.a.p}
            b={d.b.p}
            y={y}
            from={[x(d.a.t), y(d.a.p)]}
            to={[x(d.b.t), y(d.b.p)]}
          />
        )
      case "zone":
        return (
          <rect
            key={k}
            x={Math.min(x(d.a.t), x(d.b.t))}
            y={Math.min(y(d.a.p), y(d.b.p))}
            width={Math.abs(x(d.a.t) - x(d.b.t))}
            height={Math.abs(y(d.a.p) - y(d.b.p))}
            fill="rgba(96,165,250,0.12)"
            stroke={INK}
            opacity={o}
          />
        )
      case "range":
        return <Measure key={k} a={d.a} b={d.b} x={x} y={y} step={axis.step} />
      case "text":
        return (
          <text
            key={k}
            x={x(d.a.t)}
            y={y(d.a.p)}
            fill="currentColor"
            fontSize={12}
            className="text-foreground"
          >
            {d.text}
          </text>
        )
      case "brush":
        return (
          <polyline
            key={k}
            points={d.pts.map((p) => `${x(p.t)},${y(p.p)}`).join(" ")}
            fill="none"
            stroke={GOLD}
            strokeWidth={2}
            strokeLinejoin="round"
          />
        )
    }
  }

  return (
    <>
      <svg
        ref={svg}
        className={cn(
          "absolute inset-0 z-10 h-full w-full overflow-hidden",
          tool === "cursor" ? "pointer-events-none" : "cursor-crosshair"
        )}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
      >
        {showAuto && swing && W > 0 ? (
          <Fib
            auto
            x0={x(swing.a.t)}
            x1={plotW}
            a={swing.a.p}
            b={swing.b.p}
            y={y}
            from={[x(swing.a.t), y(swing.a.p)]}
            to={[x(swing.b.t), y(swing.b.p)]}
          />
        ) : null}
        {drawings.map((d) => renderOne(d))}
        {draft ? renderOne(draft, true) : null}
        {ruler ? (
          <Measure a={ruler.a} b={ruler.b} x={x} y={y} step={axis.step} />
        ) : null}
      </svg>

      <div className="absolute top-2 left-2 z-20 flex flex-col gap-0.5 rounded-lg border bg-background/85 p-1 shadow-sm backdrop-blur">
        {TOOLS.map(([t, label]) => (
          <Btn
            key={t}
            label={label}
            active={tool === t}
            onClick={() => {
              setRuler(null)
              setTool(t)
            }}
          >
            {ICONS[t]}
          </Btn>
        ))}
        <div className="my-0.5 h-px bg-border" />
        <Btn
          label="Auto Fibonacci (major swing, 0.618)"
          active={showAuto}
          onClick={() => setShowAuto((v) => !v)}
        >
          {ICONS.auto}
        </Btn>
        <Btn
          label={magnet ? "Magnet on (snap to OHLC)" : "Magnet off"}
          active={magnet}
          onClick={() => setMagnet((v) => !v)}
        >
          {ICONS.magnet}
        </Btn>
        <Btn
          label="Remove all drawings"
          onClick={() => {
            setRuler(null)
            if (drawings.length && window.confirm("Remove all drawings?"))
              setDrawings([])
          }}
        >
          {ICONS.erase}
        </Btn>
      </div>
    </>
  )
}

function load(key: string): Array<Drawing> {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as Array<Drawing>) : []
  } catch {
    return []
  }
}

function Btn({
  children,
  label,
  active,
  onClick,
}: {
  children: ReactNode
  label: string
  active?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        active && "bg-muted text-foreground"
      )}
    >
      {children}
    </button>
  )
}

function Tag({
  x,
  y,
  color,
  children,
  anchor = "start",
}: {
  x: number
  y: number
  color: string
  children: ReactNode
  anchor?: "start" | "end"
}) {
  return (
    <text
      x={x}
      y={y - 4}
      fill={color}
      fontSize={11}
      textAnchor={anchor}
      fontFamily="'Geist Mono Variable', ui-monospace, monospace"
    >
      {children}
    </text>
  )
}

// Level r sits at b + (a - b) * r: 1 where the move started, 0 where it ended.
function Fib({
  x0,
  x1,
  a,
  b,
  y,
  from,
  to,
  auto,
}: {
  x0: number
  x1: number
  a: number
  b: number
  y: (p: number) => number
  from: [number, number]
  to: [number, number]
  auto?: boolean
}) {
  const at = (r: number) => b + (a - b) * r
  const yGp = [y(at(0.618)), y(at(0.65))]
  return (
    <g>
      <rect
        x={x0}
        width={Math.max(0, x1 - x0)}
        y={Math.min(...yGp)}
        height={Math.abs(yGp[0] - yGp[1])}
        fill="rgba(245,179,1,0.18)"
      />
      <line
        x1={from[0]}
        y1={from[1]}
        x2={to[0]}
        y2={to[1]}
        stroke="currentColor"
        className="text-muted-foreground"
        strokeDasharray="4 4"
      />
      {FIB_LEVELS.map((r) => {
        const key618 = r === 0.618
        const yy = y(at(r))
        const color = key618
          ? GOLD
          : r === 0.65
            ? "rgba(245,179,1,0.6)"
            : "#94a3b8"
        return (
          <g key={r}>
            <line
              x1={x0}
              x2={x1}
              y1={yy}
              y2={yy}
              stroke={color}
              strokeWidth={key618 ? 2.5 : 1}
              strokeDasharray={key618 || r === 0 || r === 1 ? undefined : "2 3"}
            />
            {r === 0.65 ? null : (
              <Tag x={Math.max(x0, 44) + 4} y={yy} color={color}>
                {key618 ? "★ 0.618" : r} · {fmt(at(r))}
              </Tag>
            )}
          </g>
        )
      })}
      {auto ? (
        <Tag x={Math.max(x0, 44) + 4} y={y(at(1)) - 14} color="#94a3b8">
          Auto Fib · major swing
        </Tag>
      ) : null}
    </g>
  )
}

function Measure({
  a,
  b,
  x,
  y,
  step,
}: {
  a: Pt
  b: Pt
  x: (t: number) => number
  y: (p: number) => number
  step: number
}) {
  const up = b.p >= a.p
  const color = up ? "#26a69a" : "#ef5350"
  const pct = ((b.p - a.p) / a.p) * 100
  const bars = Math.round((b.t - a.t) / step)
  const secs = Math.abs(b.t - a.t)
  const span =
    secs >= 86400
      ? `${(secs / 86400).toFixed(1)}d`
      : `${(secs / 3600).toFixed(1)}h`
  const X = [x(a.t), x(b.t)]
  const Y = [y(a.p), y(b.p)]
  return (
    <g>
      <rect
        x={Math.min(...X)}
        y={Math.min(...Y)}
        width={Math.abs(X[0] - X[1])}
        height={Math.abs(Y[0] - Y[1])}
        fill={up ? "rgba(38,166,154,0.15)" : "rgba(239,83,80,0.15)"}
        stroke={color}
      />
      <line x1={X[0]} y1={Y[0]} x2={X[1]} y2={Y[1]} stroke={color} />
      <Tag
        x={(X[0] + X[1]) / 2}
        y={Math.min(...Y) - 2}
        color={color}
        anchor="start"
      >
        {pct >= 0 ? "+" : ""}
        {pct.toFixed(2)}% · {fmt(b.p - a.p)} · {bars} bars · {span}
      </Tag>
    </g>
  )
}
