// Under the SMC structure chart: every bearish event in the window, newest first, read from
// the lens output (red BOS/CHoCH breaks, bearish order blocks and FVGs, lower highs/lows),
// with how far the last close sits from each level.
import type { ChartData } from "@/lib/api"

const RED = "#ef5350"

type Ev = { t: number; kind: string; text: string; ref: number | null }

const day = (t: number) =>
  new Date(t * 1000).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "2-digit",
  })
const px = (v: number) =>
  v.toLocaleString("en-US", { maximumFractionDigits: v >= 100 ? 1 : 4 })

export function bearishEvents(data: ChartData): Array<Ev> {
  const out: Array<Ev> = []
  const byTime = new Map(data.candles.map((c) => [c.time, c]))
  for (const l of data.levels ?? []) {
    if (l.color !== RED || !l.label) continue
    const t = l.t1 ?? l.t0
    if (t == null) continue
    out.push({
      t,
      kind: `Bearish ${l.label}`,
      text:
        l.label === "CHoCH"
          ? `closed below ${px(l.price)}: trend turned down`
          : `closed below ${px(l.price)}: downtrend continues`,
      ref: l.price,
    })
  }
  for (const z of data.zones ?? []) {
    if (z.color !== RED || !z.label || z.t0 == null) continue
    const lo = Math.min(z.p0, z.p1)
    const hi = Math.max(z.p0, z.p1)
    out.push({
      t: z.t0,
      kind: `Bearish ${z.label}`,
      text: `supply ${px(lo)} – ${px(hi)}`,
      ref: lo,
    })
  }
  for (const m of data.markers ?? []) {
    if (m.text !== "LH" && m.text !== "LL") continue
    const c = byTime.get(m.time)
    const p = c ? (m.text === "LH" ? c.high : c.low) : null
    out.push({
      t: m.time,
      kind: m.text === "LH" ? "Lower high" : "Lower low",
      text: p == null ? "" : `at ${px(p)}`,
      ref: p,
    })
  }
  return out.sort((a, b) => b.t - a.t)
}

export function BearishEvents({ data }: { data: ChartData }) {
  const evs = bearishEvents(data)
  const last = data.candles[data.candles.length - 1]?.close
  return (
    <div className="max-h-36 shrink-0 overflow-y-auto border-t px-3 py-1.5 text-[11px]">
      <div className="mb-1 flex items-baseline gap-2">
        <span className="font-medium text-red-500">▼ Bearish events</span>
        <span className="text-muted-foreground">
          {evs.length} in window · newest first
        </span>
      </div>
      {evs.length === 0 ? (
        <p className="text-muted-foreground">
          No bearish event in this window.
        </p>
      ) : (
        <ul className="grid gap-0.5 font-mono">
          {evs.map((e, i) => {
            const d =
              e.ref != null && last ? ((last - e.ref) / e.ref) * 100 : null
            return (
              <li key={i} className="flex gap-2 text-muted-foreground">
                <span className="w-16 shrink-0">{day(e.t)}</span>
                <span className="w-28 shrink-0 text-red-500">{e.kind}</span>
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
