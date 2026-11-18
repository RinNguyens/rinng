import type { MarketRow } from "./api"

export type MarketSeg = "all" | "watch" | "top"
export type MarketSort =
  | "price"
  | "chg_24h"
  | "volume_24h"
  | "funding_rate_pct"
  | "oi_value"
  | "oi_chg_24h"
  | "ls_ratio"
  | "base"
export type MarketDir = "asc" | "desc"
export type MarketSearch = { seg?: MarketSeg; sort?: MarketSort; dir?: MarketDir }

const SEGS: Array<MarketSeg> = ["all", "watch", "top"]
const SORTS: Array<MarketSort> = [
  "price",
  "chg_24h",
  "volume_24h",
  "funding_rate_pct",
  "oi_value",
  "oi_chg_24h",
  "ls_ratio",
  "base",
]
const DIRS: Array<MarketDir> = ["asc", "desc"]

const pick = <T extends string>(allowed: Array<T>, v: unknown) =>
  allowed.find((a) => a === v)

export function parseMarketSearch(raw: Record<string, unknown>): MarketSearch {
  const out: MarketSearch = {}
  const seg = pick(SEGS, raw.seg)
  const sort = pick(SORTS, raw.sort)
  const dir = pick(DIRS, raw.dir)
  if (seg) out.seg = seg
  if (sort) out.sort = sort
  if (dir) out.dir = dir
  return out
}

export function sortRows(rows: Array<MarketRow>, key: MarketSort, dir: MarketDir) {
  const sign = dir === "asc" ? 1 : -1
  return [...rows].sort((a, b) => {
    const x = a[key]
    const y = b[key]
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1
    return (typeof x === "string" ? x.localeCompare(String(y)) : Number(x) - Number(y)) * sign
  })
}

const byVolume = (rows: Array<MarketRow>) => sortRows(rows, "volume_24h", "desc")

export function segmentRows(rows: Array<MarketRow>, seg: MarketSeg, starred: Array<string>) {
  if (seg === "watch") return rows.filter((r) => starred.includes(r.symbol))
  if (seg === "top") return byVolume(rows).slice(0, 50)
  return rows
}

export function filterRows(rows: Array<MarketRow>, query: string) {
  const q = query.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((r) =>
    [r.base, r.name, r.symbol].some((s) => s.toLowerCase().includes(q)),
  )
}

export function movers(rows: Array<MarketRow>, n = 5) {
  return {
    up: sortRows(rows, "chg_24h", "desc").slice(0, n),
    down: sortRows(rows, "chg_24h", "asc").slice(0, n),
  }
}

export function fundingExtremes(rows: Array<MarketRow>, n = 5) {
  return {
    high: sortRows(rows, "funding_rate_pct", "desc").slice(0, n),
    low: sortRows(rows, "funding_rate_pct", "asc").slice(0, n),
  }
}

export function crowding(rows: Array<MarketRow>, n = 5) {
  // A coin sits on the side its ratio leans to (above 1 long, below 1 short), never on both.
  const known = rows.filter((r) => r.collected && r.ls_ratio != null)
  return {
    long: sortRows(known.filter((r) => r.ls_ratio! > 1), "ls_ratio", "desc").slice(0, n),
    short: sortRows(known.filter((r) => r.ls_ratio! < 1), "ls_ratio", "asc").slice(0, n),
  }
}

/** Funding rate in percent per 8h, as a yearly percent (3 fundings a day). */
export const annualized = (ratePct: number) => ratePct * 3 * 365

export function countdown(nextSec: number, nowMs: number) {
  const s = Math.max(0, Math.floor(nextSec - nowMs / 1000))
  if (s >= 3600) return `${Math.floor(s / 3600)}h`
  if (s >= 60) return `${Math.floor(s / 60)}m`
  return `${s}s`
}

/** Symbols whose price moved between two snapshots, for the brief row flash. */
export function priceMoves(prev: Array<MarketRow>, next: Array<MarketRow>) {
  const before = new Map(prev.map((r) => [r.symbol, r.price]))
  const moved: Record<string, "up" | "down"> = {}
  for (const r of next) {
    const p = before.get(r.symbol)
    if (p != null && p !== r.price) moved[r.symbol] = r.price > p ? "up" : "down"
  }
  return moved
}
