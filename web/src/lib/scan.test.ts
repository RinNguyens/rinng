import { describe, expect, it } from "vitest"
import {
  PERMIT2,
  UNLIMITED,
  classify,
  codeKind,
  exposure,
  logsInChunks,
  scanWallet,
  sortFindings,
} from "./scan"
import type { Raw, ScanClient } from "./scan"

const OWNER = "0x1111111111111111111111111111111111111111"
const TOKEN = "0x2222222222222222222222222222222222222222"
const NFT = "0x3333333333333333333333333333333333333333"
const CONTRACT = "0x4444444444444444444444444444444444444444"
const EOA = "0x5555555555555555555555555555555555555555"
const NOW = 1_800_000_000
const DAY = 86_400

const raw = (r: Partial<Raw>): Raw => ({
  kind: "erc20",
  spender: CONTRACT,
  spenderIsContract: true,
  ...r,
})

describe("classify", () => {
  it("flags any EIP-7702 delegation as high", () => {
    expect(
      classify(raw({ kind: "delegation", spender: CONTRACT }), NOW)?.severity
    ).toBe("high")
  })

  it("flags ERC-20 allowances to an EOA as high, whatever the amount", () => {
    expect(
      classify(raw({ spender: EOA, spenderIsContract: false, amount: 1n }), NOW)
        ?.severity
    ).toBe("high")
  })

  it("flags unlimited ERC-20 allowances to a contract as medium, limited ones as low", () => {
    expect(classify(raw({ amount: UNLIMITED }), NOW)?.severity).toBe("medium")
    expect(classify(raw({ amount: 10n ** 18n }), NOW)?.severity).toBe("low")
  })

  it("drops allowances that are already zero", () => {
    expect(classify(raw({ amount: 0n }), NOW)).toBeNull()
  })

  it("treats the Permit2 router itself as low: the risk sits in Permit2 allowances", () => {
    expect(
      classify(raw({ spender: PERMIT2, amount: UNLIMITED }), NOW)?.severity
    ).toBe("low")
  })

  it("flags NFT operator approvals: EOA high, contract medium, revoked dropped", () => {
    expect(
      classify(
        raw({
          kind: "nft",
          spender: EOA,
          spenderIsContract: false,
          approved: true,
        }),
        NOW
      )?.severity
    ).toBe("high")
    expect(classify(raw({ kind: "nft", approved: true }), NOW)?.severity).toBe(
      "medium"
    )
    expect(classify(raw({ kind: "nft", approved: false }), NOW)).toBeNull()
  })

  it("rates Permit2 allowances by spender, size and expiry; expired ones are dropped", () => {
    const p = (r: Partial<Raw>) =>
      classify(
        raw({ kind: "permit2", amount: 100n, expiration: NOW + DAY, ...r }),
        NOW
      )
    expect(p({})?.severity).toBe("low")
    expect(p({ amount: 2n ** 160n - 1n })?.severity).toBe("medium")
    expect(p({ expiration: NOW + 60 * DAY })?.severity).toBe("medium")
    expect(p({ spender: EOA, spenderIsContract: false })?.severity).toBe("high")
    expect(p({ expiration: NOW - 1 })).toBeNull()
    expect(p({ amount: 0n })).toBeNull()
  })

  it("sorts high before medium before low", () => {
    const f = [
      classify(raw({ amount: 1n }), NOW)!,
      classify(raw({ kind: "delegation" }), NOW)!,
      classify(raw({ amount: UNLIMITED }), NOW)!,
    ]
    expect(sortFindings(f).map((x) => x.severity)).toEqual([
      "high",
      "medium",
      "low",
    ])
  })
})

describe("logsInChunks", () => {
  it("halves the range when the RPC refuses it and still covers every block exactly once", async () => {
    const seen: Array<[bigint, bigint]> = []
    const fetch = async (from: bigint, to: bigint) => {
      if (to - from + 1n > 1000n) throw new Error("block range too large")
      seen.push([from, to])
      return [Number(from)]
    }
    const { items, errors, covered } = await logsInChunks(
      fetch,
      0n,
      9_999n,
      8_000n
    )
    expect(errors).toEqual([])
    expect(covered).toBe(10_000n)
    expect(items.length).toBe(seen.length)
    expect(seen.reduce((s, [a, b]) => s + (b - a + 1n), 0n)).toBe(10_000n)
    seen.sort((a, b) => (a[0] < b[0] ? -1 : 1))
    seen.forEach(([a], i) => i > 0 && expect(a).toBe(seen[i - 1][1] + 1n))
  })

  it("records a range it cannot read instead of failing the whole scan", async () => {
    const fetch = async (from: bigint) => {
      if (from === 0n) throw new Error("rpc down")
      return [1]
    }
    const { items, errors } = await logsInChunks(
      fetch,
      0n,
      1_999n,
      1_000n,
      1_000n
    )
    expect(items).toEqual([1])
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatch(/0–999/)
  })
})

describe("logsInChunks against an RPC that refuses the query outright", () => {
  it("gives up after a few failures at the smallest chunk and reports the rest of the range once", async () => {
    let calls = 0
    const fetch = async (): Promise<Array<number>> => {
      calls++
      throw new Error("Please specify an address in your request")
    }
    const { items, errors } = await logsInChunks(
      fetch,
      0n,
      199_999n,
      50_000n,
      500n
    )
    expect(items).toEqual([])
    expect(calls).toBeLessThan(20)
    expect(errors.at(-1)).toMatch(/RPC refused.*Please specify an address/)
    expect(errors.at(-1)).toMatch(/199999/)
  })

  it("learns the RPC's range limit once instead of retrying a refused size on every chunk", async () => {
    let refused = 0
    const fetch = async (from: bigint, to: bigint) => {
      if (to - from + 1n > 1_000n) {
        refused++
        throw new Error("ranges over 1000 blocks are not supported")
      }
      return []
    }
    const { errors } = await logsInChunks(fetch, 0n, 99_999n, 8_000n, 500n)
    expect(errors).toEqual([])
    expect(refused).toBeLessThanOrEqual(3) // 8000 → 4000 → 2000 → 1000, then never again
  })
})

describe("scanWallet", () => {
  // A wallet that approved: unlimited TOKEN to CONTRACT, TOKEN to EOA (now revoked to 0),
  // NFT operator EOA, and a Permit2 allowance to CONTRACT. It is also 7702-delegated.
  const client: ScanClient = {
    getBlockNumber: async () => 1_000n,
    getDelegation: async () => CONTRACT,
    getCode: async ({ address }) =>
      address === EOA || address === OWNER ? undefined : "0x6080",
    getStorageAt: async () => `0x${"0".repeat(64)}`,
    getLogs: (async ({
      event,
      address,
    }: {
      event: { name: string }
      address?: string
    }) => {
      if (event.name === "ApprovalForAll")
        return [{ address: NFT, args: { operator: EOA } }]
      if (address === PERMIT2)
        return [{ address: PERMIT2, args: { token: TOKEN, spender: CONTRACT } }]
      if (event.name === "Approval")
        return [
          { address: TOKEN, args: { spender: CONTRACT } },
          { address: TOKEN, args: { spender: EOA } },
          { address: TOKEN, args: { spender: CONTRACT } }, // duplicate pair
        ]
      return []
    }) as unknown as ScanClient["getLogs"],
    multicall: (async ({
      contracts,
    }: {
      contracts: Array<{ functionName: string; args?: Array<string> }>
    }) =>
      contracts.map((c) => {
        switch (c.functionName) {
          case "allowance":
            if (c.args!.length === 3)
              return { status: "success", result: [100n, NOW + DAY, 0] }
            return {
              status: "success",
              result: c.args![1] === EOA ? 0n : UNLIMITED,
            }
          case "isApprovedForAll":
            return { status: "success", result: true }
          case "symbol":
            return { status: "success", result: "TKN" }
          case "decimals":
            return { status: "success", result: 18 }
          default:
            return { status: "failure", error: new Error("nope") }
        }
      })) as unknown as ScanClient["multicall"],
  }

  it("marks the scan incomplete when a source could not be read, so silence never looks safe", async () => {
    const broken: ScanClient = {
      ...client,
      getLogs: async () => {
        throw new Error("rate limited")
      },
    }
    const r = await scanWallet(broken, OWNER, { lookback: 2_000n, now: NOW })
    expect(r.complete).toBe(false)
    expect(r.coverage["ERC-20 approvals"]).toBe(0)
    expect(r.findings.map((f) => f.kind)).toEqual(["delegation"])
  })

  it("reports full coverage when every range was read", async () => {
    const r = await scanWallet(client, OWNER, { lookback: 500n, now: NOW })
    expect(r.complete).toBe(true)
    expect(Object.keys(r.coverage)).toContain("Transfers in")
    expect(Object.values(r.coverage).every((v) => v === 1)).toBe(true)
  })

  it("turns logs into live, deduplicated, sorted findings", async () => {
    const r = await scanWallet(client, OWNER, { lookback: 500n, now: NOW })
    expect(r.fromBlock).toBe(501n)
    expect(r.toBlock).toBe(1_000n)
    expect(r.findings.map((f) => [f.kind, f.severity])).toEqual([
      ["delegation", "high"],
      ["nft", "high"],
      ["erc20", "medium"],
      ["permit2", "low"],
    ])
    const erc20 = r.findings.find((f) => f.kind === "erc20")!
    expect(erc20.symbol).toBe("TKN")
    expect(erc20.unlimited).toBe(true)
  })
})

describe("classify with spender profiles", () => {
  it("rates a 7702-delegated EOA spender as an EOA, not a contract", () => {
    const f = classify(
      raw({ spenderIsContract: false, spenderDelegated: true, amount: 1n }),
      NOW
    )!
    expect(f.severity).toBe("high")
    expect(f.note).toMatch(/EIP-7702/)
  })

  it("rates unlimited allowances to a known protocol low, but not if it's an unknown upgradeable proxy", () => {
    expect(
      classify(raw({ amount: UNLIMITED, label: "Uniswap V3 Router" }), NOW)
        ?.severity
    ).toBe("low")
    const proxy = classify(raw({ amount: UNLIMITED, upgradeable: true }), NOW)!
    expect(proxy.severity).toBe("medium")
    expect(proxy.note).toMatch(/upgradeable/)
  })

  it("rates a delegation to a known smart account medium, an unknown one high", () => {
    expect(
      classify(
        raw({ kind: "delegation", label: "MetaMask Smart Account" }),
        NOW
      )?.severity
    ).toBe("medium")
    expect(classify(raw({ kind: "delegation" }), NOW)?.severity).toBe("high")
  })

  it("measures exposure as the smaller of allowance and balance", () => {
    const f = (amount: bigint, balance: bigint) =>
      exposure(classify(raw({ amount, balance }), NOW)!)
    expect(f(UNLIMITED, 500n)).toBe(500n)
    expect(f(100n, 500n)).toBe(100n)
  })
})

describe("codeKind", () => {
  it("tells EOAs, 7702-delegated EOAs and contracts apart", () => {
    expect(codeKind(undefined)).toBe("eoa")
    expect(codeKind("0x")).toBe("eoa")
    expect(codeKind(`0xef0100${CONTRACT.slice(2)}`)).toBe("delegated")
    expect(codeKind("0x6080604052")).toBe("contract")
  })
})

describe("scanWallet profiling", () => {
  const POISON = `0x5555${"9".repeat(32)}5555` as const
  const base: ScanClient = {
    getBlockNumber: async () => 1_000n,
    getDelegation: async () => undefined,
    getCode: async ({ address }) =>
      address === OWNER
        ? undefined
        : address === EOA
          ? `0xef0100${CONTRACT.slice(2)}`
          : "0x6080",
    getStorageAt: async ({ address, slot }) =>
      address === CONTRACT && slot.startsWith("0x3608")
        ? `0x${"0".repeat(24)}${"ab".repeat(20)}`
        : `0x${"0".repeat(64)}`,
    getLogs: (async ({
      event,
      args,
      address,
    }: {
      event: { name: string }
      args: { from?: string; to?: string }
      address?: string
    }) => {
      if (address === PERMIT2) return []
      if (event.name === "Transfer" && args.from)
        return [
          { address: TOKEN, args: { from: OWNER, to: EOA, value: 5n } },
          { address: TOKEN, args: { from: OWNER, to: POISON, value: 0n } },
        ]
      if (event.name === "Approval" && "owner" in args)
        return [{ address: TOKEN, args: { spender: CONTRACT } }]
      return []
    }) as unknown as ScanClient["getLogs"],
    multicall: (async ({
      contracts,
    }: {
      contracts: Array<{ functionName: string }>
    }) =>
      contracts.map((c) =>
        c.functionName === "allowance"
          ? { status: "success", result: UNLIMITED }
          : c.functionName === "balanceOf"
            ? { status: "success", result: 42n }
            : { status: "failure", error: new Error("nope") }
      )) as unknown as ScanClient["multicall"],
  }

  it("flags upgradeable spenders, reads balances and finds poisoning", async () => {
    const r = await scanWallet(base, OWNER, { lookback: 500n, now: NOW })
    expect(r.account).toEqual({ type: "eoa" })
    const f = r.findings.find((x) => x.kind === "erc20")!
    expect(f.upgradeable).toBe(true)
    expect(f.balance).toBe(42n)
    expect(exposure(f)).toBe(42n)
    expect(r.poisoning.suspects).toEqual([
      expect.objectContaining({ address: POISON, imitates: EOA, zeroValue: 1 }),
    ])
  })

  it("recognises a Safe and reads its threshold", async () => {
    const SAFE_OWNERS = [EOA, CONTRACT]
    const safe: ScanClient = {
      ...base,
      getCode: async () => "0x6080",
      multicall: (async ({
        contracts,
      }: {
        contracts: Array<{ functionName: string }>
      }) =>
        contracts.map((c) =>
          c.functionName === "getThreshold"
            ? { status: "success", result: 2n }
            : c.functionName === "getOwners"
              ? { status: "success", result: SAFE_OWNERS }
              : { status: "failure", error: new Error("nope") }
        )) as unknown as ScanClient["multicall"],
    }
    const r = await scanWallet(safe, OWNER, { lookback: 500n, now: NOW })
    expect(r.account).toEqual({
      type: "safe",
      threshold: 2,
      owners: SAFE_OWNERS,
    })
  })
})
