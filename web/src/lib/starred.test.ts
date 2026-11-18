import { describe, expect, it } from "vitest"
import { readStarred, toggleStarred } from "./starred"

// Signatures under test (store = { getItem, setItem }):
//   readStarred(store): string[]
//   toggleStarred(store, symbol: string): string[]   // returns the new list, persisted
const KEY = "rinng.watchlist.v1"

function memory(initial?: string) {
  const data = new Map<string, string>()
  if (initial !== undefined) data.set(KEY, initial)
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
  }
}

const throwing = {
  getItem: () => {
    throw new Error("denied")
  },
  setItem: () => {
    throw new Error("denied")
  },
}

describe("readStarred", () => {
  it("is empty when nothing is stored", () => {
    expect(readStarred(memory())).toEqual([])
  })

  it("reads the stored symbols", () => {
    expect(readStarred(memory('["BTC-USDT-PERP","ETH-USDT-PERP"]'))).toEqual([
      "BTC-USDT-PERP",
      "ETH-USDT-PERP",
    ])
  })

  it("ignores malformed JSON and non-array values", () => {
    expect(readStarred(memory("{nope"))).toEqual([])
    expect(readStarred(memory('{"a":1}'))).toEqual([])
    expect(readStarred(memory('"BTC"'))).toEqual([])
  })

  it("keeps only string entries", () => {
    expect(readStarred(memory('["BTC-USDT-PERP",1,null,"ETH-USDT-PERP"]'))).toEqual([
      "BTC-USDT-PERP",
      "ETH-USDT-PERP",
    ])
  })

  it("survives a throwing store", () => {
    expect(readStarred(throwing)).toEqual([])
  })
})

describe("toggleStarred", () => {
  it("adds then removes a symbol, persisting each time", () => {
    const s = memory()
    expect(toggleStarred(s, "BTC-USDT-PERP")).toEqual(["BTC-USDT-PERP"])
    expect(JSON.parse(s.data.get(KEY)!)).toEqual(["BTC-USDT-PERP"])
    expect(toggleStarred(s, "ETH-USDT-PERP")).toEqual(["BTC-USDT-PERP", "ETH-USDT-PERP"])
    expect(toggleStarred(s, "BTC-USDT-PERP")).toEqual(["ETH-USDT-PERP"])
    expect(readStarred(s)).toEqual(["ETH-USDT-PERP"])
  })

  it("starts fresh over malformed stored data", () => {
    const s = memory("{nope")
    expect(toggleStarred(s, "BTC-USDT-PERP")).toEqual(["BTC-USDT-PERP"])
    expect(readStarred(s)).toEqual(["BTC-USDT-PERP"])
  })

  it("survives a throwing store without throwing", () => {
    expect(() => toggleStarred(throwing, "BTC-USDT-PERP")).not.toThrow()
    expect(toggleStarred(throwing, "BTC-USDT-PERP")).toEqual(["BTC-USDT-PERP"])
  })
})
