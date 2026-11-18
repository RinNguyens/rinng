import { describe, expect, it } from "vitest"
import {
  annualized,
  countdown,
  crowding,
  filterRows,
  fundingExtremes,
  movers,
  parseMarketSearch,
  priceMoves,
  segmentRows,
  sortRows,
} from "./market"
import type { MarketRow } from "./api"

// Signatures under test:
//   type MarketSeg = "all" | "watch" | "top"
//   type MarketSort = "price" | "chg_24h" | "volume_24h" | "funding_rate_pct"
//                   | "oi_value" | "oi_chg_24h" | "ls_ratio" | "base"
//   parseMarketSearch(raw: Record<string, unknown>): { seg?: MarketSeg; sort?: MarketSort; dir?: "asc" | "desc" }
//   sortRows(rows, key: MarketSort, dir: "asc" | "desc"): MarketRow[]            // new array
//   segmentRows(rows, seg: MarketSeg, starred: string[]): MarketRow[]
//   filterRows(rows, query: string): MarketRow[]
//   movers(rows, n = 5): { up: MarketRow[]; down: MarketRow[] }                  // up: chg desc, down: chg asc
//   fundingExtremes(rows, n = 5): { high: MarketRow[]; low: MarketRow[] }        // by funding_rate_pct desc / asc
//   crowding(rows, n = 5): { long: MarketRow[]; short: MarketRow[] }             // collected rows with ls_ratio only
//   annualized(ratePct: number): number                                          // x 3 fundings/day x 365
//   countdown(nextSec: number, nowMs: number): string                            // "3h", "42m", "30s", "0s" when past

const row = (base: string, extra: Partial<MarketRow> = {}): MarketRow => ({
  symbol: `${base}-USDT-PERP`,
  base,
  name: base,
  price: 1,
  chg_24h: 0,
  volume_24h: 1,
  funding_rate_pct: 0.01,
  next_funding: 0,
  oi_value: null,
  oi_chg_24h: null,
  ls_ratio: null,
  collected: false,
  ...extra,
})

const bases = (rows: MarketRow[]) => rows.map((r) => r.base)

describe("parseMarketSearch", () => {
  it("keeps known seg, sort and dir", () => {
    expect(parseMarketSearch({ seg: "watch", sort: "chg_24h", dir: "asc" })).toEqual({
      seg: "watch",
      sort: "chg_24h",
      dir: "asc",
    })
    for (const seg of ["all", "watch", "top"]) expect(parseMarketSearch({ seg }).seg).toBe(seg)
    for (const sort of [
      "price",
      "chg_24h",
      "volume_24h",
      "funding_rate_pct",
      "oi_value",
      "oi_chg_24h",
      "ls_ratio",
      "base",
    ])
      expect(parseMarketSearch({ sort }).sort).toBe(sort)
  })

  it("drops unknown values", () => {
    expect(parseMarketSearch({ seg: "gainers", sort: "mcap", dir: "up" })).toEqual({})
    expect(parseMarketSearch({ seg: "ALL", dir: "DESC" })).toEqual({})
    expect(parseMarketSearch({ seg: 1, sort: null, dir: ["asc"] })).toEqual({})
    expect(parseMarketSearch({})).toEqual({})
  })

  it("drops unrelated keys", () => {
    expect(parseMarketSearch({ seg: "top", foo: "bar" })).toEqual({ seg: "top" })
  })
})

describe("sortRows", () => {
  const rows = [row("B", { price: 2 }), row("A", { price: 3 }), row("C", { price: 1 })]

  it("sorts numbers in both directions without mutating the input", () => {
    expect(bases(sortRows(rows, "price", "desc"))).toEqual(["A", "B", "C"])
    expect(bases(sortRows(rows, "price", "asc"))).toEqual(["C", "B", "A"])
    expect(bases(rows)).toEqual(["B", "A", "C"])
  })

  it("sorts by base alphabetically", () => {
    expect(bases(sortRows(rows, "base", "asc"))).toEqual(["A", "B", "C"])
    expect(bases(sortRows(rows, "base", "desc"))).toEqual(["C", "B", "A"])
  })

  it("puts tier-B nulls last in both directions", () => {
    const r = [
      row("N1"),
      row("LOW", { oi_value: 1, collected: true }),
      row("HIGH", { oi_value: 9, collected: true }),
      row("N2"),
    ]
    expect(bases(sortRows(r, "oi_value", "desc")).slice(0, 2)).toEqual(["HIGH", "LOW"])
    expect(bases(sortRows(r, "oi_value", "asc")).slice(0, 2)).toEqual(["LOW", "HIGH"])
    for (const dir of ["asc", "desc"] as const) {
      expect(bases(sortRows(r, "oi_value", dir)).slice(2).sort()).toEqual(["N1", "N2"])
    }
  })

  it("keeps a zero ahead of nulls", () => {
    const r = [row("N"), row("Z", { ls_ratio: 0, collected: true })]
    expect(bases(sortRows(r, "ls_ratio", "asc"))).toEqual(["Z", "N"])
    expect(bases(sortRows(r, "ls_ratio", "desc"))).toEqual(["Z", "N"])
  })
})

describe("segmentRows", () => {
  const many = Array.from({ length: 60 }, (_, i) => row(`C${i}`, { volume_24h: i }))

  it("all returns every row", () => {
    expect(segmentRows(many, "all", [])).toHaveLength(60)
  })

  it("watch returns only starred symbols", () => {
    const out = segmentRows(many, "watch", ["C3-USDT-PERP", "C7-USDT-PERP", "GONE-USDT-PERP"])
    expect(bases(out).sort()).toEqual(["C3", "C7"])
    expect(segmentRows(many, "watch", [])).toEqual([])
  })

  it("top keeps the 50 rows with the highest volume", () => {
    const out = segmentRows(many, "top", [])
    expect(out).toHaveLength(50)
    expect(Math.min(...out.map((r) => r.volume_24h))).toBe(10)
    expect(bases(out)).not.toContain("C9")
  })

  it("top returns everything when there are fewer than 50", () => {
    expect(segmentRows(many.slice(0, 5), "top", [])).toHaveLength(5)
  })
})

describe("filterRows", () => {
  const rows = [
    row("BTC", { name: "Bitcoin" }),
    row("ETH", { name: "Ethereum" }),
    row("WIF", { name: "dogwifhat" }),
  ]

  it("matches base, name and symbol case-insensitively", () => {
    expect(bases(filterRows(rows, "btc"))).toEqual(["BTC"])
    expect(bases(filterRows(rows, "ETHEREUM"))).toEqual(["ETH"])
    expect(bases(filterRows(rows, "wif-usdt"))).toEqual(["WIF"])
    expect(bases(filterRows(rows, "  hat "))).toEqual(["WIF"])
  })

  it("returns all rows for an empty query and none for no match", () => {
    expect(filterRows(rows, "")).toHaveLength(3)
    expect(filterRows(rows, "   ")).toHaveLength(3)
    expect(filterRows(rows, "zzz")).toEqual([])
  })
})

describe("movers", () => {
  const rows = Array.from({ length: 12 }, (_, i) => row(`C${i}`, { chg_24h: i - 6 }))

  it("returns 5 up and 5 down, biggest move first", () => {
    const { up, down } = movers(rows)
    expect(up.map((r) => r.chg_24h)).toEqual([5, 4, 3, 2, 1])
    expect(down.map((r) => r.chg_24h)).toEqual([-6, -5, -4, -3, -2])
  })

  it("honours n and handles fewer rows than n", () => {
    expect(movers(rows, 2).up).toHaveLength(2)
    expect(movers(rows.slice(0, 3)).up.length).toBeLessThanOrEqual(3)
    expect(movers([])).toEqual({ up: [], down: [] })
  })
})

describe("fundingExtremes", () => {
  const rows = [-0.3, -0.1, 0, 0.05, 0.2, 0.4].map((f, i) =>
    row(`F${i}`, { funding_rate_pct: f }),
  )

  it("returns the highest and lowest funding, most extreme first", () => {
    const { high, low } = fundingExtremes(rows, 2)
    expect(high.map((r) => r.funding_rate_pct)).toEqual([0.4, 0.2])
    expect(low.map((r) => r.funding_rate_pct)).toEqual([-0.3, -0.1])
  })

  it("defaults to 5 per side", () => {
    expect(fundingExtremes(rows).high).toHaveLength(5)
  })
})

describe("crowding", () => {
  const rows = [
    row("NONE"),
    row("L1", { ls_ratio: 3.4, collected: true }),
    row("L2", { ls_ratio: 1.5, collected: true }),
    row("S1", { ls_ratio: 0.6, collected: true }),
    row("S2", { ls_ratio: 0.9, collected: true }),
  ]

  it("ranks long-heavy and short-heavy among collected rows only", () => {
    const { long, short } = crowding(rows, 2)
    expect(bases(long)).toEqual(["L1", "L2"])
    expect(bases(short)).toEqual(["S1", "S2"])
  })

  it("lists a coin only on the side its ratio leans to", () => {
    const allLong = [
      row("A", { ls_ratio: 3.3, collected: true }),
      row("B", { ls_ratio: 1.76, collected: true }),
      row("EVEN", { ls_ratio: 1, collected: true }),
    ]
    const { long, short } = crowding(allLong)
    expect(bases(long)).toEqual(["A", "B"])
    expect(short).toEqual([])
  })

  it("never includes rows without an L/S ratio", () => {
    const { long, short } = crowding([row("NONE"), row("X")])
    expect(long).toEqual([])
    expect(short).toEqual([])
  })
})

describe("annualized", () => {
  it("is rate x 3 fundings a day x 365", () => {
    expect(annualized(0.01)).toBeCloseTo(10.95, 6)
    expect(annualized(-0.02)).toBeCloseTo(-21.9, 6)
    expect(annualized(0)).toBe(0)
  })
})

describe("countdown", () => {
  const nowMs = 1_763_380_800_000
  const nowSec = nowMs / 1000

  it("shows hours, minutes or seconds, whichever is the largest unit", () => {
    expect(countdown(nowSec + 3 * 3600 + 1800, nowMs)).toBe("3h")
    expect(countdown(nowSec + 42 * 60 + 10, nowMs)).toBe("42m")
    expect(countdown(nowSec + 30, nowMs)).toBe("30s")
  })

  it("is 0s when the time has passed", () => {
    expect(countdown(nowSec, nowMs)).toBe("0s")
    expect(countdown(nowSec - 100, nowMs)).toBe("0s")
  })
})

describe("priceMoves", () => {
  it("marks only symbols whose price changed, up or down", () => {
    const prev = [row("A", { price: 1 }), row("B", { price: 2 }), row("C", { price: 3 })]
    const next = [row("A", { price: 1 }), row("B", { price: 2.5 }), row("C", { price: 2 }), row("D", { price: 9 })]
    expect(priceMoves(prev, next)).toEqual({ "B-USDT-PERP": "up", "C-USDT-PERP": "down" })
  })
})
