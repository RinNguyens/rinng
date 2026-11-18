export const num = (v: number, d = 0) =>
  v.toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  })

export const price = (v: number | null | undefined) => {
  if (v == null) return "—"
  if (v > 0 && v < 0.0001) return v.toFixed(Math.min(100, 3 - Math.floor(Math.log10(v))))
  return num(v, v >= 1000 ? 1 : v >= 1 ? 2 : 5)
}

export const pct = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}${num(Math.abs(v), d)}%`

export const tone = (v: number | null | undefined) =>
  v == null ? "text-muted-foreground" : v >= 0 ? "text-up" : "text-down"

/** `tSeconds` is unix seconds, like the API. */
export function ago(tSeconds: number, nowMs = Date.now()) {
  const s = Math.max(0, Math.round(nowMs / 1000 - tSeconds))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}
