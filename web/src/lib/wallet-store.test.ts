import { describe, expect, it } from "vitest"
import {
  addWallet,
  diffSnaps,
  makeSnap,
  pushSnap,
  readWallets,
  removeWallet,
  renameWallet,
  savedDiff,
  sevFromSnap,
  storageWorks,
  writeWallets,
} from "./wallet-store"
import type { Wallet } from "./wallet-store"

/* Signatures chosen by the tests (the coder implements to these):

   type Snap = { at: number; fps: Array<string> }               // fingerprints found by one scan
   type Wallet = { address: string; net: string; label: string; snaps: Array<Snap> }   // snaps: oldest first, at most 2
   type AddResult = { ok: true; list: Array<Wallet> } | { ok: false; error: "duplicate" | "full" | "empty" }

   readWallets(store: Pick<Storage, "getItem"> | undefined): Array<Wallet>      // key "rinng.wallets.v1"; [] on any trouble
   writeWallets(store: Pick<Storage, "setItem"> | undefined, list: ReadonlyArray<Wallet>): void   // never throws
   addWallet(list: ReadonlyArray<Wallet>, input: { address: string; net: string; label?: string }): AddResult
     // appends; address trimmed (case kept); duplicate = same address (case-insensitive) AND same net;
     // at most 20; label trimmed and cut to 24, blank/missing -> `${address.slice(0, 6)}…${address.slice(-4)}`
   renameWallet(list, address: string, net: string, label: string): Array<Wallet>   // same label rules; blank keeps the old
   removeWallet(list, address: string, net: string): Array<Wallet>                  // address match is case-insensitive
   pushSnap(wallet: Wallet, snap: Snap): Wallet                                     // keeps the last 2, newest last
   diffSnaps(prev: Snap | undefined, cur: Snap, sevOf: (fp: string) => "high" | "medium" | "low"):
     { newHigh: Array<string>; newOther: Array<string>; removed: Array<string> }    // no prev -> all empty
   storageWorks(store: Pick<Storage, "getItem" | "setItem" | "removeItem"> | undefined): boolean
*/

const KEY = "rinng.wallets.v1"
const A1 = "0xAbCd000000000000000000000000000000000001"
const A2 = "0x0000000000000000000000000000000000000002"

const memory = (initial?: string) => {
  const m = new Map<string, string>()
  if (initial !== undefined) m.set(KEY, initial)
  return {
    map: m,
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  }
}

const throwing = {
  getItem: (): string | null => {
    throw new Error("denied")
  },
  setItem: () => {
    throw new Error("denied")
  },
  removeItem: () => {
    throw new Error("denied")
  },
}

const wallet = (address: string, net = "eth", extra: Partial<Wallet> = {}): Wallet => ({
  address,
  net,
  label: "w",
  snaps: [],
  ...extra,
})

const added = (list: Array<Wallet>, input: Parameters<typeof addWallet>[1]) => {
  const r = addWallet(list, input)
  if (!r.ok) throw new Error(`expected ok, got ${r.error}`)
  return r.list
}

describe("addWallet", () => {
  it("adds a wallet with its label and no snapshots", () => {
    const list = added([], { address: A1, net: "eth", label: "Cold" })
    expect(list).toEqual([{ address: A1, net: "eth", label: "Cold", snaps: [] }])
  })

  it("defaults the label to the short address", () => {
    const list = added([], { address: A1, net: "eth" })
    expect(list[0].label).toBe("0xAbCd…0001")
    expect(added([], { address: A1, net: "eth", label: "   " })[0].label).toBe("0xAbCd…0001")
  })

  it("trims the label and cuts it to 24 characters", () => {
    expect(added([], { address: A1, net: "eth", label: "  Cold  " })[0].label).toBe("Cold")
    const long = "x".repeat(40)
    expect(added([], { address: A1, net: "eth", label: long })[0].label).toBe("x".repeat(24))
  })

  it("trims the address", () => {
    expect(added([], { address: `  ${A1}\n`, net: "eth" })[0].address).toBe(A1)
  })

  it("refuses a duplicate address and network, whatever the case", () => {
    const list = added([], { address: A1, net: "eth" })
    expect(addWallet(list, { address: A1, net: "eth" })).toEqual({ ok: false, error: "duplicate" })
    expect(addWallet(list, { address: A1.toLowerCase(), net: "eth" })).toEqual({
      ok: false,
      error: "duplicate",
    })
  })

  it("allows the same address on another network", () => {
    const list = added([], { address: A1, net: "eth" })
    expect(added(list, { address: A1, net: "base" })).toHaveLength(2)
  })

  it("refuses an empty address", () => {
    expect(addWallet([], { address: "  ", net: "eth" })).toEqual({ ok: false, error: "empty" })
  })

  it("stops at 20", () => {
    let list: Array<Wallet> = []
    for (let i = 10; i < 30; i++)
      list = added(list, { address: `0x${String(i).padStart(40, "0")}`, net: "eth" })
    expect(list).toHaveLength(20)
    expect(addWallet(list, { address: A2, net: "eth" })).toEqual({ ok: false, error: "full" })
  })

  it("does not change the list it was given", () => {
    const list = [wallet(A1)]
    addWallet(list, { address: A2, net: "eth" })
    expect(list).toHaveLength(1)
  })
})

describe("renameWallet", () => {
  it("renames the matching wallet only", () => {
    const out = renameWallet([wallet(A1, "eth"), wallet(A1, "base")], A1, "base", "Hot")
    expect(out.map((w) => w.label)).toEqual(["w", "Hot"])
  })

  it("trims, cuts to 24, and keeps the old label when blank", () => {
    expect(renameWallet([wallet(A1)], A1, "eth", "  Hot ")[0].label).toBe("Hot")
    expect(renameWallet([wallet(A1)], A1, "eth", "y".repeat(30))[0].label).toBe("y".repeat(24))
    expect(renameWallet([wallet(A1)], A1, "eth", "   ")[0].label).toBe("w")
  })

  it("matches the address case-insensitively and ignores unknown wallets", () => {
    expect(renameWallet([wallet(A1)], A1.toLowerCase(), "eth", "Hot")[0].label).toBe("Hot")
    expect(renameWallet([wallet(A1)], A2, "eth", "Hot")[0].label).toBe("w")
  })
})

describe("removeWallet", () => {
  it("removes by address and network", () => {
    const out = removeWallet([wallet(A1, "eth"), wallet(A1, "base"), wallet(A2)], A1, "eth")
    expect(out.map((w) => `${w.address}:${w.net}`)).toEqual([`${A1}:base`, `${A2}:eth`])
  })

  it("is case-insensitive and leaves the list alone for an unknown wallet", () => {
    expect(removeWallet([wallet(A1)], A1.toLowerCase(), "eth")).toEqual([])
    expect(removeWallet([wallet(A1)], A2, "eth")).toHaveLength(1)
  })
})

describe("pushSnap", () => {
  const snap = (at: number, fps: Array<string> = []) => ({ at, fps })

  it("appends the snapshot", () => {
    expect(pushSnap(wallet(A1), snap(1)).snaps).toEqual([snap(1)])
  })

  it("keeps the last two, newest last", () => {
    let w = wallet(A1)
    for (const at of [1, 2, 3, 4]) w = pushSnap(w, snap(at))
    expect(w.snaps.map((s) => s.at)).toEqual([3, 4])
  })

  it("does not change the wallet it was given", () => {
    const w = wallet(A1)
    pushSnap(w, snap(1))
    expect(w.snaps).toEqual([])
  })
})

describe("diffSnaps", () => {
  const sev = (fp: string) => (fp.startsWith("h") ? "high" : fp.startsWith("m") ? "medium" : "low")

  it("counts new high, new other and removed", () => {
    const prev = { at: 1, fps: ["h-old", "m-keep", "l-gone"] }
    const cur = { at: 2, fps: ["h-old", "m-keep", "h-new", "m-new", "l-new"] }
    expect(diffSnaps(prev, cur, sev)).toEqual({
      newHigh: ["h-new"],
      newOther: ["m-new", "l-new"],
      removed: ["l-gone"],
    })
  })

  it("is all empty when nothing changed", () => {
    const s = { at: 1, fps: ["h1", "l1"] }
    expect(diffSnaps(s, { at: 2, fps: ["l1", "h1"] }, sev)).toEqual({
      newHigh: [],
      newOther: [],
      removed: [],
    })
  })

  it("has nothing to compare against on the first scan", () => {
    expect(diffSnaps(undefined, { at: 1, fps: ["h1", "m1"] }, sev)).toEqual({
      newHigh: [],
      newOther: [],
      removed: [],
    })
  })

  it("reports everything as removed when the new scan is clean", () => {
    expect(diffSnaps({ at: 1, fps: ["h1", "m1"] }, { at: 2, fps: [] }, sev).removed).toEqual(["h1", "m1"])
  })
})

describe("readWallets / writeWallets", () => {
  it("round-trips under rinng.wallets.v1", () => {
    const store = memory()
    const list = [wallet(A1, "eth", { label: "Cold", snaps: [{ at: 1, fps: ["a"] }] }), wallet(A2, "tron")]
    writeWallets(store, list)
    expect(store.map.has(KEY)).toBe(true)
    expect(readWallets(store)).toEqual(list)
  })

  it("is empty for no store, no value, bad JSON or a non-array", () => {
    expect(readWallets(undefined)).toEqual([])
    expect(readWallets(memory())).toEqual([])
    expect(readWallets(memory("{nope"))).toEqual([])
    expect(readWallets(memory('{"address":"x"}'))).toEqual([])
    expect(readWallets(memory("null"))).toEqual([])
  })

  it("drops malformed entries and keeps good ones", () => {
    const good = wallet(A1, "eth", { label: "Cold" })
    const store = memory(
      JSON.stringify([
        good,
        { address: 5, net: "eth", label: "x", snaps: [] },
        { address: A2, label: "no net", snaps: [] },
        { address: A2, net: "eth" },
        null,
        "text",
      ])
    )
    const out = readWallets(store)
    expect(out[0]).toEqual(good)
    expect(out.every((w) => typeof w.address === "string" && typeof w.net === "string")).toBe(true)
    expect(out.find((w) => w.label === "no net")).toBeUndefined()
    expect(out.find((w) => w.address === 5 as unknown)).toBeUndefined()
  })

  it("repairs a missing or malformed snaps array to empty", () => {
    const out = readWallets(memory(JSON.stringify([{ address: A1, net: "eth", label: "L", snaps: "bad" }])))
    expect(out).toEqual([{ address: A1, net: "eth", label: "L", snaps: [] }])
  })

  it("survives a throwing store", () => {
    expect(readWallets(throwing)).toEqual([])
    expect(() => writeWallets(throwing, [wallet(A1)])).not.toThrow()
    expect(() => writeWallets(undefined, [])).not.toThrow()
  })
})

describe("storageWorks", () => {
  it("is true for a working store and leaves nothing behind", () => {
    const store = memory()
    expect(storageWorks(store)).toBe(true)
    expect(store.map.size).toBe(0)
  })

  it("is false when the store is missing or throws", () => {
    expect(storageWorks(undefined)).toBe(false)
    expect(storageWorks(throwing)).toBe(false)
  })

  it("is false when writes are silently dropped", () => {
    const dropped = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
    expect(storageWorks(dropped)).toBe(false)
  })
})

describe("snapshot summary fields", () => {
  const full = { at: 5, fps: ["a", "b"], score: 62, grade: "C" as const, usd: 4210, high: ["a"] }

  it("pushSnap keeps score, grade, usd and high", () => {
    expect(pushSnap(wallet(A1), full).snaps).toEqual([full])
  })

  it("readWallets keeps valid summary fields", () => {
    const store = memory(JSON.stringify([{ address: A1, net: "eth", label: "L", snaps: [full] }]))
    expect(readWallets(store)[0].snaps).toEqual([full])
  })

  it("readWallets drops malformed summary fields but keeps the snap and the wallet", () => {
    const bad = { at: 5, fps: ["a"], score: "62", grade: "Z", usd: null, high: [1] }
    const store = memory(JSON.stringify([{ address: A1, net: "eth", label: "L", snaps: [bad] }]))
    expect(readWallets(store)).toEqual([{ address: A1, net: "eth", label: "L", snaps: [{ at: 5, fps: ["a"] }] }])
  })

  it("sevFromSnap says high for fingerprints in high, else low", () => {
    const sev = sevFromSnap(full)
    expect(sev("a")).toBe("high")
    expect(sev("b")).toBe("low")
    expect(sevFromSnap({ at: 1, fps: ["a"] })("a")).toBe("low")
  })
})

describe("round 2: makeSnap", () => {
  const base = { at: 5, fps: ["a", "b"], high: ["a"], score: 70, grade: "C" as const, usd: 12, partial: false, pricesFailed: false }
  it("builds a snapshot from a complete scan", () => {
    expect(makeSnap(base)).toEqual({ at: 5, fps: ["a", "b"], score: 70, grade: "C", usd: 12, high: ["a"] })
  })
  it("makes no snapshot for a partial scan", () => {
    expect(makeSnap({ ...base, partial: true })).toBeUndefined()
  })
  it("leaves usd out when prices could not be loaded", () => {
    expect(makeSnap({ ...base, pricesFailed: true })?.usd).toBeUndefined()
  })
})

describe("round 2: savedDiff", () => {
  const w = (snaps: Array<{ at: number; fps: Array<string>; high?: Array<string> }>) => [
    { address: "0xAbC", net: "eth", label: "x", snaps },
  ]
  it("diffs the latest snapshot against the one before", () => {
    const d = savedDiff(w([{ at: 1, fps: ["a", "gone"] }, { at: 2, fps: ["a", "n1", "n2"], high: ["n1"] }]), "0xabc", "eth")
    expect(d).toEqual({ newHigh: ["n1"], newOther: ["n2"], removed: ["gone"] })
  })
  it("is null without two snapshots or an unknown wallet", () => {
    expect(savedDiff(w([{ at: 1, fps: [] }]), "0xabc", "eth")).toBeNull()
    expect(savedDiff(w([]), "0xabc", "eth")).toBeNull()
    expect(savedDiff(w([]), "0xother", "eth")).toBeNull()
  })
})
