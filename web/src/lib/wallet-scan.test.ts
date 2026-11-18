import { describe, expect, it } from "vitest"
import {
  combineScores,
  fingerprint,
  groupFindings,
  liveFps,
  money,
  parseWalletSearch,
  planJson,
  planMarkdown,
  pool,
  readRevoke,
  revokePlan,
  scanFailure,
  scanIsPartial,
  verifyState,
  worstGrade,
  writeRevoke,
} from "./wallet-scan"

/* Signatures chosen by the tests (the coder implements to these):

   type Grade = "A" | "B" | "C" | "D" | "F"
   type Severity = "high" | "medium" | "low"                      // from lib/scan
   type PlanItem = { fp: string; severity: Severity; usd?: number; unlimited: boolean }
   type PlanRow = PlanItem & { spender: string; label?: string; symbol?: string; kind: string }
   type RevokeMap = Record<string, { checkedAt: number }>

   fingerprint(net: string, f: { kind: string; token?: string; spender: string }): string
   revokePlan<T extends PlanItem>(items: ReadonlyArray<T>): Array<T>           // new array, input untouched
   readRevoke(store: Pick<Storage, "getItem"> | undefined, now: number): RevokeMap   // prunes > 90 days
   writeRevoke(store: Pick<Storage, "setItem"> | undefined, map: RevokeMap): void
   planMarkdown(items: ReadonlyArray<PlanRow>, net: string): string
   planJson(items: ReadonlyArray<PlanRow>, net: string): string                // JSON: { network, items }
   pool<T, R>(items: ReadonlyArray<T>, n: number, fn: (item: T, index: number) => Promise<R>): Promise<Array<R>>
   worstGrade(grades: ReadonlyArray<Grade>): Grade | null                      // null when empty
   groupFindings<T extends { spender: string; net: string }>(
     rows: ReadonlyArray<T>, by: "none" | "spender" | "network"
   ): Array<{ key: string; rows: Array<T> }>   // first-seen order; none -> one group key "" (no group for no rows);
                                               // spender key is the lowercased spender; network key is net
   money(n: number | undefined): string        // undefined/NaN -> "—", 0 -> "$0", (0,0.01) -> "<$0.01",
                                               // <1 -> 2 decimals, >=1 -> whole dollars with commas
   parseWalletSearch(raw: Record<string, unknown>): { address?: string; net?: string }
                                               // address: trimmed non-empty string; net: a NETWORKS key or "evm-all"
   verifyState(fp: string, checked: RevokeMap, live: ReadonlySet<string> | null): "verified" | "still-live" | "open"
                                               // live = fingerprints seen by the re-scan; null = not re-scanned yet
*/

const DAY = 86_400_000
const NOW = 1_800_000_000_000
const KEY = "rinng.revoke.v1"

const SPENDER = "0xAbCd000000000000000000000000000000000001"
const TOKEN = "0xDAC17F958D2ee523a2206206994597C13D831ec7"

const memory = (initial?: string) => {
  let value: string | null = initial ?? null
  return {
    getItem: (k: string) => (k === KEY ? value : null),
    setItem: (k: string, v: string) => {
      if (k === KEY) value = v
    },
    get value() {
      return value
    },
  }
}

const throwing = {
  getItem: (): string | null => {
    throw new Error("denied")
  },
  setItem: () => {
    throw new Error("denied")
  },
}

describe("fingerprint", () => {
  it("joins network, kind, token and spender, lowercased", () => {
    expect(fingerprint("eth", { kind: "erc20", token: TOKEN, spender: SPENDER })).toBe(
      `eth:erc20:${TOKEN.toLowerCase()}:${SPENDER.toLowerCase()}`
    )
  })

  it("is stable across case", () => {
    expect(fingerprint("eth", { kind: "erc20", token: TOKEN, spender: SPENDER })).toBe(
      fingerprint("eth", {
        kind: "erc20",
        token: TOKEN.toLowerCase(),
        spender: SPENDER.toUpperCase().replace("0X", "0x"),
      })
    )
  })

  it("uses a dash when there is no token and tells networks apart", () => {
    expect(fingerprint("base", { kind: "delegation", spender: SPENDER })).toBe(
      `base:delegation:-:${SPENDER.toLowerCase()}`
    )
    expect(fingerprint("eth", { kind: "nft", spender: SPENDER })).not.toBe(
      fingerprint("base", { kind: "nft", spender: SPENDER })
    )
  })
})

describe("revokePlan", () => {
  const item = (fp: string, severity: "high" | "medium" | "low", extra: { usd?: number; unlimited?: boolean } = {}) => ({
    fp,
    severity,
    unlimited: false,
    ...extra,
  })

  it("orders by severity first", () => {
    const out = revokePlan([item("l", "low", { usd: 9e6 }), item("h", "high"), item("m", "medium")])
    expect(out.map((i) => i.fp)).toEqual(["h", "m", "l"])
  })

  it("orders by USD at risk, biggest first, within a severity", () => {
    const out = revokePlan([
      item("small", "high", { usd: 10 }),
      item("big", "high", { usd: 5000 }),
      item("mid", "high", { usd: 400 }),
    ])
    expect(out.map((i) => i.fp)).toEqual(["big", "mid", "small"])
  })

  it("puts unpriced after priced", () => {
    const out = revokePlan([item("none", "high"), item("tiny", "high", { usd: 0.01 })])
    expect(out.map((i) => i.fp)).toEqual(["tiny", "none"])
  })

  it("breaks remaining ties with unlimited first, then keeps input order", () => {
    const out = revokePlan([
      item("a", "medium"),
      item("b", "medium", { unlimited: true }),
      item("c", "medium"),
    ])
    expect(out.map((i) => i.fp)).toEqual(["b", "a", "c"])
  })

  it("does not mutate its input and handles empty", () => {
    const input = [item("l", "low"), item("h", "high")]
    const copy = [...input]
    revokePlan(input)
    expect(input).toEqual(copy)
    expect(revokePlan([])).toEqual([])
  })
})

describe("readRevoke / writeRevoke", () => {
  it("round-trips what the user marked as revoked", () => {
    const store = memory()
    writeRevoke(store, { "eth:erc20:-:0xa": { checkedAt: NOW - DAY } })
    expect(readRevoke(store, NOW)).toEqual({ "eth:erc20:-:0xa": { checkedAt: NOW - DAY } })
  })

  it("stores under rinng.revoke.v1 as JSON", () => {
    const store = memory()
    writeRevoke(store, { x: { checkedAt: 5 } })
    expect(JSON.parse(store.value!)).toEqual({ x: { checkedAt: 5 } })
  })

  it("prunes entries older than 90 days", () => {
    const store = memory(
      JSON.stringify({
        old: { checkedAt: NOW - 91 * DAY },
        edge: { checkedAt: NOW - 90 * DAY },
        fresh: { checkedAt: NOW - DAY },
      })
    )
    const out = readRevoke(store, NOW)
    expect(Object.keys(out).sort()).toEqual(["edge", "fresh"])
  })

  it("is empty for no store, no value, bad JSON or the wrong shape", () => {
    expect(readRevoke(undefined, NOW)).toEqual({})
    expect(readRevoke(memory(), NOW)).toEqual({})
    expect(readRevoke(memory("{nope"), NOW)).toEqual({})
    expect(readRevoke(memory("[1,2]"), NOW)).toEqual({})
    expect(readRevoke(memory("null"), NOW)).toEqual({})
  })

  it("drops malformed entries and keeps good ones", () => {
    const store = memory(
      JSON.stringify({
        ok: { checkedAt: NOW },
        text: { checkedAt: "yesterday" },
        bare: 5,
        nul: null,
      })
    )
    expect(readRevoke(store, NOW)).toEqual({ ok: { checkedAt: NOW } })
  })

  it("survives a throwing store on read and write", () => {
    expect(readRevoke(throwing, NOW)).toEqual({})
    expect(() => writeRevoke(throwing, { a: { checkedAt: 1 } })).not.toThrow()
    expect(() => writeRevoke(undefined, {})).not.toThrow()
  })
})

describe("planMarkdown / planJson", () => {
  const rows = [
    {
      fp: "eth:erc20:0xt:0xs1",
      severity: "high" as const,
      usd: 4210,
      unlimited: true,
      spender: "0x1111111111111111111111111111111111111111",
      label: "Shady Router",
      symbol: "USDT",
      kind: "erc20",
    },
    {
      fp: "eth:nft:-:0xs2",
      severity: "low" as const,
      unlimited: false,
      spender: "0x2222222222222222222222222222222222222222",
      kind: "nft",
    },
  ]

  it("markdown lists every item numbered with spender, severity and dollars", () => {
    const md = planMarkdown(rows, "eth")
    expect(md).toContain("eth")
    expect(md).toMatch(/^1\. .*0x1111111111111111111111111111111111111111/m)
    expect(md).toMatch(/^2\. .*0x2222222222222222222222222222222222222222/m)
    expect(md).toContain("Shady Router")
    expect(md).toContain("USDT")
    expect(md).toContain("$4,210")
    expect(md.toLowerCase()).toContain("high")
    expect(md.toLowerCase()).toContain("unlimited")
  })

  it("markdown for an empty plan says there is nothing to revoke instead of an empty list", () => {
    const md = planMarkdown([], "eth")
    expect(md).not.toMatch(/^1\. /m)
    expect(md.toLowerCase()).toContain("nothing")
  })

  it("json carries the network and every row", () => {
    const parsed = JSON.parse(planJson(rows, "base"))
    expect(parsed.network).toBe("base")
    expect(parsed.items).toHaveLength(2)
    expect(parsed.items[0]).toMatchObject({ fp: rows[0].fp, severity: "high", usd: 4210, unlimited: true })
    expect(parsed.items[1].spender).toBe(rows[1].spender)
  })

  it("json is an empty list for an empty plan", () => {
    expect(JSON.parse(planJson([], "eth"))).toEqual({ network: "eth", items: [] })
  })
})

describe("pool", () => {
  const deferred = <T>() => {
    let resolve!: (v: T) => void
    let reject!: (e: unknown) => void
    const promise = new Promise<T>((res, rej) => {
      resolve = res
      reject = rej
    })
    return { promise, resolve, reject }
  }
  const tick = () => new Promise<void>((r) => setImmediate(r))

  it("never runs more than n at once", async () => {
    const gates = [0, 1, 2, 3, 4].map(() => deferred<number>())
    let running = 0
    let peak = 0
    const done = pool([0, 1, 2, 3, 4], 2, async (i) => {
      running++
      peak = Math.max(peak, running)
      const v = await gates[i].promise
      running--
      return v
    })
    await tick()
    expect(running).toBe(2)
    for (const [i, g] of gates.entries()) {
      g.resolve(i * 10)
      await tick()
    }
    await done
    expect(peak).toBe(2)
  })

  it("starts the next item as soon as a slot frees", async () => {
    const gates = [deferred<void>(), deferred<void>(), deferred<void>()]
    const started: Array<number> = []
    const done = pool([0, 1, 2], 2, async (i) => {
      started.push(i)
      await gates[i].promise
    })
    await tick()
    expect(started).toEqual([0, 1])
    gates[1].resolve()
    await tick()
    expect(started).toEqual([0, 1, 2])
    gates[0].resolve()
    gates[2].resolve()
    await done
  })

  it("returns results in input order even when they finish out of order", async () => {
    const gates = [deferred<string>(), deferred<string>(), deferred<string>()]
    const done = pool(["a", "b", "c"], 3, (_s, i) => gates[i].promise)
    gates[2].resolve("third")
    gates[0].resolve("first")
    gates[1].resolve("second")
    expect(await done).toEqual(["first", "second", "third"])
  })

  it("passes the item and its index", async () => {
    expect(await pool(["x", "y"], 2, async (s, i) => `${s}${i}`)).toEqual(["x0", "y1"])
  })

  it("handles an empty list and treats n below 1 as 1", async () => {
    expect(await pool([], 2, async () => 1)).toEqual([])
    let running = 0
    let peak = 0
    const out = await pool([1, 2, 3], 0, async (x) => {
      running++
      peak = Math.max(peak, running)
      await tick()
      running--
      return x
    })
    expect(out).toEqual([1, 2, 3])
    expect(peak).toBe(1)
  })

  it("rejects with the error of a failing item", async () => {
    await expect(
      pool([1, 2, 3], 2, async (x) => {
        if (x === 2) throw new Error("rpc down")
        return x
      })
    ).rejects.toThrow("rpc down")
  })
})

describe("worstGrade", () => {
  it("picks the worst of several", () => {
    expect(worstGrade(["A", "C", "B"])).toBe("C")
    expect(worstGrade(["A", "F", "D"])).toBe("F")
    expect(worstGrade(["B", "B"])).toBe("B")
  })

  it("is null when nothing was graded", () => {
    expect(worstGrade([])).toBeNull()
  })
})

describe("groupFindings", () => {
  const rows = [
    { id: 1, spender: "0xAA", net: "eth" },
    { id: 2, spender: "0xbb", net: "base" },
    { id: 3, spender: "0xaa", net: "base" },
  ]

  it("none gives one group with every row in order", () => {
    expect(groupFindings(rows, "none")).toEqual([{ key: "", rows }])
  })

  it("none gives no group for no rows", () => {
    expect(groupFindings([], "none")).toEqual([])
    expect(groupFindings([], "spender")).toEqual([])
  })

  it("groups by spender, case-insensitive, in first-seen order", () => {
    const out = groupFindings(rows, "spender")
    expect(out.map((g) => g.key)).toEqual(["0xaa", "0xbb"])
    expect(out[0].rows.map((r) => r.id)).toEqual([1, 3])
  })

  it("groups by network in first-seen order", () => {
    const out = groupFindings(rows, "network")
    expect(out.map((g) => g.key)).toEqual(["eth", "base"])
    expect(out[1].rows.map((r) => r.id)).toEqual([2, 3])
  })
})

describe("money", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(money(4210)).toBe("$4,210")
    expect(money(4210.6)).toBe("$4,211")
    expect(money(1_250_000)).toBe("$1,250,000")
    expect(money(1)).toBe("$1")
  })

  it("keeps cents under a dollar", () => {
    expect(money(0.42)).toBe("$0.42")
    expect(money(0.5)).toBe("$0.50")
  })

  it("handles zero and dust", () => {
    expect(money(0)).toBe("$0")
    expect(money(0.001)).toBe("<$0.01")
  })

  it("shows a dash when there is no price", () => {
    expect(money(undefined)).toBe("—")
    expect(money(Number.NaN)).toBe("—")
  })
})

describe("parseWalletSearch", () => {
  it("keeps a trimmed address and a known network", () => {
    expect(parseWalletSearch({ address: `  ${SPENDER} `, net: "base" })).toEqual({
      address: SPENDER,
      net: "base",
    })
  })

  it("accepts evm-all and non-EVM networks", () => {
    expect(parseWalletSearch({ net: "evm-all" })).toEqual({ net: "evm-all" })
    expect(parseWalletSearch({ net: "bitcoin" })).toEqual({ net: "bitcoin" })
  })

  it("drops empty, non-string and unknown values", () => {
    expect(parseWalletSearch({ address: "   " }).address).toBeUndefined()
    expect(parseWalletSearch({ address: 5 }).address).toBeUndefined()
    expect(parseWalletSearch({ address: null }).address).toBeUndefined()
    expect(parseWalletSearch({ net: "dogechain" }).net).toBeUndefined()
    expect(parseWalletSearch({ net: "ETH" }).net).toBeUndefined()
    expect(parseWalletSearch({ net: 1 }).net).toBeUndefined()
    expect(parseWalletSearch({})).toEqual({})
  })

  it("drops unrelated keys (labels and notes never ride in the URL)", () => {
    expect(parseWalletSearch({ address: SPENDER, label: "mine", note: "x", junk: 1 })).toEqual({
      address: SPENDER,
    })
  })
})

describe("verifyState", () => {
  const fp = "eth:erc20:0xt:0xs"
  const checked = { [fp]: { checkedAt: NOW } }

  it("is open when the user has not marked it revoked", () => {
    expect(verifyState(fp, {}, new Set())).toBe("open")
    expect(verifyState(fp, {}, new Set([fp]))).toBe("open")
  })

  it("is verified when marked revoked and the re-scan no longer sees it", () => {
    expect(verifyState(fp, checked, new Set(["other"]))).toBe("verified")
    expect(verifyState(fp, checked, new Set())).toBe("verified")
  })

  it("is still-live when marked revoked but the re-scan still finds it", () => {
    expect(verifyState(fp, checked, new Set([fp]))).toBe("still-live")
  })

  it("stays open until a re-scan has happened", () => {
    expect(verifyState(fp, checked, null)).toBe("open")
  })
})

const sc = (score: number, grade: "A" | "B" | "C" | "D" | "F", usdAtRisk = 0, provisional = false) => ({
  score,
  grade,
  items: [],
  provisional,
  usdAtRisk,
})
const ok = (complete = true) => ({ status: "done" as const, outcome: { result: { complete } } })
const bad = { status: "error" as const }

describe("round 2: combineScores", () => {
  it("returns null for no scores instead of reducing an empty array", () => {
    expect(combineScores([])).toBeNull()
  })
  it("takes the worst score and grade, sums dollars, and can be forced provisional", () => {
    const c = combineScores([sc(90, "A", 5), sc(40, "D", 7)])
    expect(c).toMatchObject({ score: 40, grade: "D", usdAtRisk: 12, provisional: false })
    expect(combineScores([sc(90, "A")], { provisional: true })?.provisional).toBe(true)
  })
})

describe("round 2: partial scans", () => {
  it("is partial when a network errored or a result is incomplete", () => {
    expect(scanIsPartial([ok(), ok()])).toBe(false)
    expect(scanIsPartial([ok(), bad])).toBe(true)
    expect(scanIsPartial([ok(), ok(false)])).toBe(true)
  })
  it("is partial when a non-EVM report is incomplete", () => {
    const report = (complete: boolean) => ({ status: "done" as const, outcome: { report: { complete } } })
    expect(scanIsPartial([report(true)])).toBe(false)
    expect(scanIsPartial([ok(), report(false)])).toBe(true)
  })
  it("a partial scan gives no live set, so nothing is verified", () => {
    const checked = { "a": { checkedAt: 1 } }
    expect(verifyState("a", checked, liveFps([], true))).toBe("open")
    expect(verifyState("a", checked, liveFps([], false))).toBe("verified")
    expect(verifyState("a", checked, liveFps([{ fp: "a" }], false))).toBe("still-live")
  })
  it("says so when no network could be read, and passes a single failure through", () => {
    expect(scanFailure([{ ...bad, error: "x" }, { ...bad, error: "y" }])).toMatch(/^Could not read any network/)
    expect(scanFailure([{ ...bad, error: "rpc down" }])).toBe("rpc down")
    expect(scanFailure([ok(), bad])).toBeUndefined()
  })
})

describe("round 2: planMarkdown escaping", () => {
  const row = (symbol: string, label?: string) => ({
    fp: "f",
    severity: "high" as const,
    unlimited: false,
    spender: "0xabc",
    symbol,
    label,
    kind: "erc20",
  })
  it("escapes Markdown characters in symbols and labels", () => {
    const md = planMarkdown([row("[FREE](http://evil.example)", "*bold*")], "eth")
    expect(md).not.toContain("[FREE](")
    expect(md).toContain("\\[FREE\\]\\(http://evil.example\\)")
    expect(md).toContain("\\*bold\\*")
  })
  it("strips newlines so a symbol cannot start a new line", () => {
    const md = planMarkdown([row("A\n# Heading\r\n- x")], "eth")
    expect(md.split("\n")).toHaveLength(4)
  })
})

describe("round 2: parseWalletSearch hl", () => {
  it("keeps only hl=new", () => {
    expect(parseWalletSearch({ address: "0xabc", hl: "new" })).toEqual({ address: "0xabc", hl: "new" })
    expect(parseWalletSearch({ hl: "other" }).hl).toBeUndefined()
    expect(parseWalletSearch({ hl: 1 }).hl).toBeUndefined()
  })
})
