import { afterEach, describe, expect, it } from "vitest"
import {
  browserStore,
  exchangeFor,
  isResolved,
  needsWriteBack,
  parseSearch,
  readSavedInstrument,
  readSection,
  resolveInstrument,
  sectionFromPath,
  tabRedirect,
  writeSection,
} from "./terminal-nav"
import type { Instrument } from "./api"

const inst = (id: string, extra: Partial<Instrument> = {}): Instrument => ({
  id,
  kind: "perp",
  base: id.split("-")[0],
  quote: "USDT",
  name: id,
  ...extra,
})

const BTC = inst("BTC-USDT-PERP")
const ETH = inst("ETH-USDT-PERP")

const throwing = {
  getItem: () => {
    throw new Error("denied")
  },
  setItem: () => {
    throw new Error("denied")
  },
}

describe("parseSearch", () => {
  it("keeps a trimmed symbol and a known exchange", () => {
    expect(parseSearch({ symbol: "  ETH-USDT-PERP ", ex: "okx" })).toEqual({
      symbol: "ETH-USDT-PERP",
      ex: "okx",
    })
    expect(parseSearch({ ex: "binance" })).toEqual({ ex: "binance" })
    expect(parseSearch({ symbol: "BTC" })).toEqual({ symbol: "BTC" })
  })

  it("drops empty, non-string and unknown values", () => {
    expect(parseSearch({ symbol: "   " }).symbol).toBeUndefined()
    expect(parseSearch({ symbol: "" }).symbol).toBeUndefined()
    expect(parseSearch({ symbol: 123 }).symbol).toBeUndefined()
    expect(parseSearch({ symbol: null }).symbol).toBeUndefined()
    expect(parseSearch({ ex: "OKX" }).ex).toBeUndefined()
    expect(parseSearch({ ex: "kraken" }).ex).toBeUndefined()
    expect(parseSearch({ ex: 1 }).ex).toBeUndefined()
    expect(parseSearch({})).toEqual({})
  })

  it("drops unrelated keys", () => {
    const out = parseSearch({ symbol: "BTC", ex: "okx", seg: "x", junk: 1 })
    expect(Object.keys(out).sort()).toEqual(["ex", "symbol"])
  })
})

describe("sectionFromPath", () => {
  it("reads the section from nested paths", () => {
    expect(sectionFromPath("/terminal/coin")).toBe("coin")
    expect(sectionFromPath("/terminal/market")).toBe("market")
    expect(sectionFromPath("/terminal/wallet")).toBe("wallet")
    expect(sectionFromPath("/terminal/charts")).toBe("charts")
    expect(sectionFromPath("/terminal/charts/abc")).toBe("charts")
    expect(sectionFromPath("/terminal/coin/")).toBe("coin")
  })

  it("returns null for /terminal and unknown sections", () => {
    expect(sectionFromPath("/terminal")).toBeNull()
    expect(sectionFromPath("/terminal/")).toBeNull()
    expect(sectionFromPath("/terminal/foo")).toBeNull()
    expect(sectionFromPath("/terminalx/coin")).toBeNull()
    expect(sectionFromPath("/")).toBeNull()
    expect(sectionFromPath("/coin")).toBeNull()
  })
})

describe("readSection", () => {
  it("reads a saved section from the right key", () => {
    const keys: Array<string> = []
    const store = {
      getItem: (k: string) => {
        keys.push(k)
        return "wallet"
      },
    }
    expect(readSection(store)).toBe("wallet")
    expect(keys).toEqual(["rinng.section.v1"])
  })

  it("defaults to coin when storage is empty, junk or throws", () => {
    expect(readSection({ getItem: () => null })).toBe("coin")
    expect(readSection({ getItem: () => "junk" })).toBe("coin")
    expect(readSection({ getItem: () => "" })).toBe("coin")
    expect(readSection(throwing)).toBe("coin")
  })

  it("returns coin without a store", () => {
    expect(readSection(undefined)).toBe("coin")
    expect(readSection()).toBe("coin")
  })
})

describe("writeSection", () => {
  it("writes the section key", () => {
    const calls: Array<[string, string]> = []
    writeSection({ setItem: (k, v) => calls.push([k, v]) }, "charts")
    expect(calls).toEqual([["rinng.section.v1", "charts"]])
  })

  it("swallows storage write errors", () => {
    expect(() => writeSection(throwing, "market")).not.toThrow()
  })
})

describe("tabRedirect", () => {
  it("waits while workspaces are empty", () => {
    expect(tabRedirect("a", [])).toBeNull()
    expect(tabRedirect(undefined, [])).toBeNull()
  })

  it("keeps a known tab", () => {
    expect(tabRedirect("b", [{ id: "a" }, { id: "b" }])).toBeNull()
  })

  it("forwards a missing or unknown tab to the first workspace", () => {
    const list = [{ id: "a" }, { id: "b" }]
    expect(tabRedirect(undefined, list)).toBe("a")
    expect(tabRedirect("bogus", list)).toBe("a")
  })
})

describe("exchangeFor", () => {
  it("stays when the exchange lists the coin or listing is unknown", () => {
    expect(exchangeFor(inst("A", { binance: true, okx: true }), "okx")).toBe(
      "okx"
    )
    expect(exchangeFor(inst("A"), "binance")).toBe("binance")
    expect(exchangeFor(inst("A"), "okx")).toBe("okx")
  })

  it("switches to okx when binance is false", () => {
    expect(exchangeFor(inst("A", { binance: false, okx: true }), "binance")).toBe(
      "okx"
    )
  })

  it("switches to binance when okx is false", () => {
    expect(exchangeFor(inst("A", { binance: true, okx: false }), "okx")).toBe(
      "binance"
    )
  })

  it("keeps the okx quirk when neither listing is known to be true", () => {
    expect(exchangeFor(inst("A", { okx: false }), "okx")).toBe("okx")
  })
})

describe("readSavedInstrument", () => {
  it("parses a saved instrument", () => {
    const keys: Array<string> = []
    const store = {
      getItem: (k: string) => {
        keys.push(k)
        return JSON.stringify(ETH)
      },
    }
    expect(readSavedInstrument(store)).toEqual(ETH)
    expect(keys).toEqual(["rinng.instrument.v1"])
  })

  it("returns null for missing, bad JSON, no id, or throwing storage", () => {
    expect(readSavedInstrument({ getItem: () => null })).toBeNull()
    expect(readSavedInstrument({ getItem: () => "{nope" })).toBeNull()
    expect(readSavedInstrument({ getItem: () => "junk" })).toBeNull()
    expect(
      readSavedInstrument({ getItem: () => JSON.stringify({ name: "x" }) })
    ).toBeNull()
    expect(
      readSavedInstrument({ getItem: () => JSON.stringify({ id: 5 }) })
    ).toBeNull()
    expect(readSavedInstrument({ getItem: () => "null" })).toBeNull()
    expect(readSavedInstrument(throwing)).toBeNull()
    expect(readSavedInstrument(undefined)).toBeNull()
  })
})

describe("resolveInstrument", () => {
  it("no symbol → saved, else first watchlist coin", () => {
    expect(resolveInstrument(undefined, [BTC, ETH], ETH)).toBe(ETH)
    expect(resolveInstrument(undefined, [BTC, ETH], null)).toBe(BTC)
  })

  it("returns undefined with no symbol, no saved coin and an empty watchlist", () => {
    expect(resolveInstrument(undefined, [], null)).toBeUndefined()
  })

  it("matches the watchlist by id", () => {
    expect(resolveInstrument("ETH-USDT-PERP", [BTC, ETH], null)).toBe(ETH)
  })

  it("matches the saved coin by id", () => {
    const sol = inst("SOL-USDT-PERP")
    expect(resolveInstrument("SOL-USDT-PERP", [BTC, ETH], sol)).toBe(sol)
  })

  it("returns undefined for an unknown symbol", () => {
    expect(resolveInstrument("NOPE", [BTC, ETH], ETH)).toBeUndefined()
    expect(resolveInstrument("btc", [BTC], null)).toBeUndefined()
    expect(resolveInstrument("NOPE", [], null)).toBeUndefined()
  })
})

describe("isResolved", () => {
  it("false with no current coin", () => {
    expect(isResolved(undefined, null)).toBe(false)
    expect(isResolved("BTC-USDT-PERP", null)).toBe(false)
  })

  it("true when the URL has no symbol", () => {
    expect(isResolved(undefined, { key: undefined, inst: BTC })).toBe(true)
    expect(isResolved(undefined, { key: "ETH-USDT-PERP", inst: BTC })).toBe(
      true
    )
  })

  it("true for the requested key (alias) or the canonical id", () => {
    const cur = { key: "btc", inst: BTC }
    expect(isResolved("btc", cur)).toBe(true)
    expect(isResolved("BTC-USDT-PERP", cur)).toBe(true)
  })

  it("false for a different symbol (Back button)", () => {
    expect(isResolved("BTC-USDT-PERP", { key: "ETH-USDT-PERP", inst: ETH })).toBe(
      false
    )
    expect(isResolved("eth", { key: "BTC-USDT-PERP", inst: BTC })).toBe(false)
  })
})

// Review round 1, S2: reading the global throws when the browser blocks site data.
describe("browserStore", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
  afterEach(() => {
    if (original) Object.defineProperty(globalThis, "localStorage", original)
    else delete (globalThis as { localStorage?: unknown }).localStorage
  })

  it("returns undefined when there is no localStorage", () => {
    delete (globalThis as { localStorage?: unknown }).localStorage
    expect(browserStore()).toBeUndefined()
  })

  it("returns undefined when reading localStorage throws", () => {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get() {
        throw new Error("SecurityError")
      },
    })
    expect(browserStore()).toBeUndefined()
  })

  it("returns the store when it is readable", () => {
    const store = { getItem: () => null, setItem: () => {} }
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: store })
    expect(browserStore()).toBe(store)
  })

  it("lets writeSection run without a store", () => {
    expect(() => writeSection(undefined, "coin")).not.toThrow()
  })
})

// Review round 1, S1: a failed lookup must not rewrite the URL the user asked for.
describe("needsWriteBack", () => {
  it("writes the canonical id and exchange for an alias or a missing exchange", () => {
    expect(needsWriteBack({ symbol: "btc" }, { key: "btc", inst: BTC }, "binance")).toBe(true)
    expect(needsWriteBack({}, { key: undefined, inst: BTC }, "binance")).toBe(true)
  })

  it("does nothing when the URL already matches", () => {
    expect(
      needsWriteBack({ symbol: "BTC-USDT-PERP", ex: "binance" }, { key: "BTC-USDT-PERP", inst: BTC }, "binance")
    ).toBe(false)
  })

  it("does nothing while the coin is unresolved or the URL moved on (Back)", () => {
    expect(needsWriteBack({ symbol: "btc" }, null, "binance")).toBe(false)
    expect(needsWriteBack({ symbol: "BTC-USDT-PERP" }, { key: "ETH-USDT-PERP", inst: ETH }, "binance")).toBe(false)
  })

  it("keeps the URL when the lookup failed and a fallback coin is shown", () => {
    expect(
      needsWriteBack({ symbol: "PEPE-USDT-PERP" }, { key: "PEPE-USDT-PERP", inst: BTC, error: "offline" }, "binance")
    ).toBe(false)
  })
})
