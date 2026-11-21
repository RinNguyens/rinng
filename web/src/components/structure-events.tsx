// Under the SMC structure chart: every bullish and bearish event in the window, newest first,
// read from the lens output (BOS/CHoCH breaks, order blocks / FVGs / breakers, higher or
// lower highs and lows), with how far the last close sits from each level.
import { useState } from "react"
import type { ChartData } from "@/lib/api"
import { cn } from "@/lib/utils"

const RED = "#ef5350"
const GREEN = "#26a69a"

type Side = "bull" | "bear"
type Ev = {
  t: number
  side: Side
  kind: string
  text: string
  ref: number | null
}

const day = (t: number) =>
  new Date(t * 1000).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "2-digit",
  })
const px = (v: number) =>
  v.toLocaleString("en-US", { maximumFractionDigits: v >= 100 ? 1 : 4 })

// premium/discount bands are background, not events
const BANDS = new Set(["premium", "discount", "equilibrium"])

const sideOf = (color: string): Side | null =>
  color === RED ? "bear" : color === GREEN ? "bull" : null

const SWINGS: Record<string, [Side, string, "high" | "low"]> = {
  HH: ["bull", "Higher high", "high"],
  HL: ["bull", "Higher low", "low"],
  LH: ["bear", "Lower high", "high"],
  LL: ["bear", "Lower low", "low"],
}

export function structureEvents(data: ChartData): Array<Ev> {
  const out: Array<Ev> = []
  const byTime = new Map(data.candles.map((c) => [c.time, c]))
  for (const l of data.levels ?? []) {
    const side = sideOf(l.color)
    const t = l.t1 ?? l.t0
    if (!side || !l.label || t == null) continue
    const bull = side === "bull"
    out.push({
      t,
      side,
      kind: `${bull ? "Bullish" : "Bearish"} ${l.label}`,
      text: `closed ${bull ? "above" : "below"} ${px(l.price)}: ${
        l.label === "CHoCH"
          ? `trend turned ${bull ? "up" : "down"}`
          : `${bull ? "uptrend" : "downtrend"} continues`
      }`,
      ref: l.price,
    })
  }
  for (const z of data.zones ?? []) {
    const side = sideOf(z.color)
    if (!side || !z.label || z.t0 == null || BANDS.has(z.label)) continue
    const lo = Math.min(z.p0, z.p1)
    const hi = Math.max(z.p0, z.p1)
    out.push({
      t: z.t0,
      side,
      kind: `${side === "bull" ? "Bullish" : "Bearish"} ${z.label}`,
      text: `${side === "bull" ? "demand" : "supply"} ${px(lo)} – ${px(hi)}`,
      ref: side === "bull" ? hi : lo,
    })
  }
  for (const m of data.markers ?? []) {
    const s = SWINGS[m.text] as (typeof SWINGS)[string] | undefined
    if (!s) continue
    const c = byTime.get(m.time)
    const p = c ? c[s[2]] : null
    out.push({
      t: m.time,
      side: s[0],
      kind: s[1],
      text: p == null ? "" : `at ${px(p)}`,
      ref: p,
    })
  }
  return out.sort((a, b) => b.t - a.t)
}

const OPEN_KEY = "rinng.structure-events.open"

const FILTERS: Array<[Side | "all", string]> = [
  ["all", "All"],
  ["bull", "▲ Bullish"],
  ["bear", "▼ Bearish"],
]

export function StructureEvents({ data }: { data: ChartData }) {
  const [show, setShow] = useState<Side | "all">("all")
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(OPEN_KEY) !== "0"
    } catch {
      return true
    }
  })
  const toggle = () =>
    setOpen((v) => {
      try {
        localStorage.setItem(OPEN_KEY, v ? "0" : "1")
      } catch {
        /* no storage */
      }
      return !v
    })
  const all = structureEvents(data)
  const evs = show === "all" ? all : all.filter((e) => e.side === show)
  const n = (s: Side) => all.filter((e) => e.side === s).length
  const last = data.candles[data.candles.length - 1]?.close
  return (
    <div className="max-h-[35%] min-h-10 shrink-0 overflow-y-auto border-t px-3 py-1.5 text-[11px]">
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="mr-1 inline-flex items-center gap-1 font-medium hover:text-foreground"
        >
          <span
            className={cn(
              "inline-block text-muted-foreground transition-transform",
              open && "rotate-90"
            )}
          >
            ▸
          </span>
          Structure events
        </button>
        {FILTERS.map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => {
              setShow(k)
              if (!open) toggle()
            }}
            className={cn(
              "rounded px-1.5 py-0.5 text-muted-foreground hover:bg-muted",
              show === k && "bg-muted text-foreground",
              k === "bull" && "text-emerald-500",
              k === "bear" && "text-red-500"
            )}
          >
            {label} {k === "all" ? all.length : n(k)}
          </button>
        ))}
        {open ? (
          <span className="ml-auto text-muted-foreground">newest first</span>
        ) : null}
      </div>
      {!open ? null : evs.length === 0 ? (
        <p className="text-muted-foreground">No event in this window.</p>
      ) : (
        <ul className="grid gap-0.5 font-mono">
          {evs.map((e, i) => {
            const d =
              e.ref != null && last ? ((last - e.ref) / e.ref) * 100 : null
            const bull = e.side === "bull"
            return (
              <li key={i} className="flex gap-2 text-muted-foreground">
                <span className="w-16 shrink-0">{day(e.t)}</span>
                <span
                  className={cn(
                    "w-32 shrink-0",
                    bull ? "text-emerald-500" : "text-red-500"
                  )}
                >
                  {bull ? "▲" : "▼"} {e.kind}
                </span>
                <span className="min-w-0 flex-1 truncate text-foreground/80">
                  {e.text}
                </span>
                {d == null ? null : (
                  <span className="shrink-0">
                    now {d >= 0 ? "+" : ""}
                    {d.toFixed(1)}%
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
