import { describe, expect, it } from "vitest"
import { ago, num, pct, price, tone } from "./format"

// Signatures under test:
//   num(v: number, d = 0): string
//   price(v: number | null | undefined): string
//   pct(v: number | null | undefined, d = 2): string
//   tone(v: number | null | undefined): string
//   ago(tSeconds: number, nowMs = Date.now()): string   // t is unix seconds, like the API

describe("num", () => {
  it("groups thousands and pads to the requested decimals", () => {
    expect(num(1234567)).toBe("1,234,567")
    expect(num(1.5, 2)).toBe("1.50")
    expect(num(0.126, 2)).toBe("0.13")
  })
})

describe("price", () => {
  it("uses 1, 2 and 5 decimals by magnitude", () => {
    expect(price(91204.14)).toBe("91,204.1")
    expect(price(1000)).toBe("1,000.0")
    expect(price(12.3456)).toBe("12.35")
    expect(price(1)).toBe("1.00")
    expect(price(0.5)).toBe("0.50000")
    expect(price(0.0001)).toBe("0.00010")
  })

  it("uses 4 significant digits under 0.0001", () => {
    expect(price(0.00001234)).toBe("0.00001234")
    expect(price(0.000056789)).toBe("0.00005679")
  })

  it("shows a dash for null and undefined", () => {
    expect(price(null)).toBe("—")
    expect(price(undefined)).toBe("—")
  })
})

describe("pct", () => {
  it("signs the value, using a real minus for negatives", () => {
    expect(pct(1.236)).toBe("+1.24%")
    expect(pct(-1.236)).toBe("−1.24%")
    expect(pct(0)).toBe("+0.00%")
    expect(pct(2.5, 1)).toBe("+2.5%")
  })

  it("shows a dash for null and undefined", () => {
    expect(pct(null)).toBe("—")
    expect(pct(undefined)).toBe("—")
  })
})

describe("tone", () => {
  it("maps sign to the up/down/muted classes", () => {
    expect(tone(1)).toBe("text-up")
    expect(tone(0)).toBe("text-up")
    expect(tone(-0.1)).toBe("text-down")
    expect(tone(null)).toBe("text-muted-foreground")
    expect(tone(undefined)).toBe("text-muted-foreground")
  })
})

describe("ago", () => {
  const now = 1_763_380_800_000
  const t = now / 1000

  it("shows seconds under a minute", () => {
    expect(ago(t - 14, now)).toBe("14s ago")
    expect(ago(t - 59, now)).toBe("59s ago")
  })

  it("never shows a negative or fractional age", () => {
    expect(ago(t, now)).toBe("0s ago")
    expect(ago(t + 5, now)).toBe("0s ago")
    expect(ago(t - 14.4, now)).toBe("14s ago")
  })

  it("shows minutes, hours and days after that", () => {
    expect(ago(t - 60, now)).toBe("1m ago")
    expect(ago(t - 5 * 60, now)).toBe("5m ago")
    expect(ago(t - 3 * 3600, now)).toBe("3h ago")
    expect(ago(t - 2 * 86400, now)).toBe("2d ago")
  })
})
