import { describe, expect, it } from "vitest"
import { averageEquity, grid, heat, markText, toReturn } from "./trusttrade"
import type { RunSummary } from "./trusttrade"

const run = (
  name: string,
  days: number,
  cr: Record<string, number>
): RunSummary => ({
  name,
  start: "2026-09-22",
  end: "2026-11-20",
  days,
  symbols: ["BTC-USDT-PERP"],
  blind: false,
  analyst_models: ["claude-haiku-5-5"],
  trader_model: "claude-haiku-5-5",
  n_agents: 3,
  allocation: "partial",
  variants: [],
  baselines: [],
  cost_usd: 1,
  calls: 10,
  average: Object.fromEntries(
    Object.entries(cr).map(([k, v]) => [
      k,
      { cr_pct: v, mdd_pct: Math.abs(v), sharpe: 0 },
    ])
  ),
})

describe("averageEquity", () => {
  it("averages each strategy day by day across symbols", () => {
    const a = { days: ["d1", "d2"], series: { x: [100, 110], y: [100, 90] } }
    const b = { days: ["d1", "d2"], series: { x: [100, 130], y: [100, 100] } }
    expect(averageEquity([a, b])).toEqual({
      days: ["d1", "d2"],
      series: { x: [100, 120], y: [100, 95] },
    })
  })

  it("leaves out curves of a different length and empty input", () => {
    const a = { days: ["d1", "d2"], series: { x: [100, 110] } }
    const short = { days: ["d1"], series: { x: [100] } }
    expect(averageEquity([a, short]).series.x).toEqual([100, 110])
    expect(averageEquity([])).toEqual({ days: [], series: {} })
  })
})

describe("grid", () => {
  it("keeps strategies present in some run and means only the runs that count", () => {
    const runs = [
      run("smoke", 2, { trusttrade: 50 }),
      run("a", 60, { trusttrade: 2, buy_hold: -10 }),
      run("b", 60, { trusttrade: 4 }),
    ]
    const rows = grid(runs, "cr_pct", (r) => r.days >= 30)
    expect(rows.map((r) => r.strategy)).toEqual(["trusttrade", "buy_hold"])
    expect(rows[0].mean).toBe(3)
    expect(rows[0].cells).toEqual({ smoke: 50, a: 2, b: 4 })
    expect(rows[1].cells.b).toBeNull()
    expect(rows[1].mean).toBe(-10)
  })
})

describe("helpers", () => {
  it("turns equity into percent return", () => {
    expect(toReturn([10000, 10500, 9000], 10000)).toEqual([0, 5, -10])
  })
  it("labels trades and skips holds", () => {
    expect(markText({ action: "BUY", pct: 50 })).toBe("B50")
    expect(markText({ action: "SELL", pct: 100 })).toBe("S100")
    expect(markText({ action: "HOLD", pct: 0 })).toBe("")
  })
  it("colours gains green, losses red, missing transparent", () => {
    expect(heat(5)).toMatch(/^rgba\(16,185,129/)
    expect(heat(-5)).toMatch(/^rgba\(239,83,80/)
    expect(heat(null)).toBe("transparent")
  })
})
