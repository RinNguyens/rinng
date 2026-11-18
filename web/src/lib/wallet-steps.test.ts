import { describe, expect, it } from "vitest"
import {
  SEV_STATUS,
  SOURCE,
  STATUS_WORD,
  STEPS,
  amountOf,
  chainVerdicts,
  gradeStatus,
  planFor,
  stepOf,
  verdicts,
} from "./wallet-steps"
import type { Finding, ScanResult } from "./scan"
import type { Score } from "./score"
import type { ChainReport } from "./multichain"
import { PLANS } from "./multichain"

// wallet-steps.ts holds the logic moved unchanged out of landing/wallet-section.tsx, plus stepOf.

const OWNER = "0x1111111111111111111111111111111111111111" as const
const SPENDER = "0x2222222222222222222222222222222222222222" as const

const finding = (extra: Partial<Finding> = {}): Finding => ({
  kind: "erc20",
  spender: SPENDER,
  spenderIsContract: true,
  severity: "low",
  unlimited: false,
  note: "",
  ...extra,
})

const scan = (extra: Partial<ScanResult> = {}): ScanResult => ({
  findings: [],
  account: { type: "eoa" },
  poisoning: { counterparties: [], suspects: [] },
  fromBlock: 0n,
  toBlock: 1n,
  errors: [],
  coverage: {},
  complete: true,
  ...extra,
})

const score = (grade: Score["grade"], extra: Partial<Score> = {}): Score => ({
  score: 50,
  grade,
  items: [],
  provisional: false,
  usdAtRisk: 0,
  ...extra,
})

describe("amountOf", () => {
  it("names unlimited, all items, delegated and formatted amounts", () => {
    expect(amountOf(finding({ kind: "delegation" }))).toBe("delegated")
    expect(amountOf(finding({ kind: "nft" }))).toBe("all items")
    expect(amountOf(finding({ unlimited: true }))).toBe("unlimited")
    expect(
      amountOf(finding({ amount: 1_234_567_000n, decimals: 6, symbol: "USDC" }))
    ).toBe("1,234.57 USDC")
    expect(amountOf(finding({ amount: 5n * 10n ** 18n, decimals: 18 }))).toBe("5")
  })

  it("says limited when the amount or decimals are unknown", () => {
    expect(amountOf(finding({}))).toBe("limited")
    expect(amountOf(finding({ amount: 5n }))).toBe("limited")
  })

  it("lets delegation and nft win over unlimited", () => {
    expect(amountOf(finding({ kind: "delegation", unlimited: true }))).toBe("delegated")
    expect(amountOf(finding({ kind: "nft", unlimited: true }))).toBe("all items")
  })
})

describe("planFor", () => {
  it("returns the 7 EVM steps", () => {
    expect(planFor("evm")).toBe(STEPS)
    expect(STEPS).toHaveLength(7)
    expect(STEPS[0].title).toBe("Read-only")
    expect(STEPS[6].title).toBe("Exposure & score")
  })

  it.each(["tron", "solana", "bitcoin", "stellar"] as const)(
    "returns read-only, the %s checks, then the score",
    (family) => {
      const plan = planFor(family)
      expect(plan).toHaveLength(PLANS[family].length + 2)
      expect(plan[0]).toBe(STEPS[0])
      expect(plan.slice(1, -1).map((s) => s.title)).toEqual(PLANS[family].map((p) => p.title))
      expect(plan.at(-1)?.title).toBe("Exposure & score")
      for (const s of plan.slice(1)) expect(s.match).toEqual([])
    }
  )
})

describe("stepOf", () => {
  it("maps scan progress labels to steps", () => {
    expect(stepOf("Reading the account")).toBe(1)
    expect(stepOf("Account type and EIP-7702 delegation")).toBe(1)
    expect(stepOf("ERC-20 approvals")).toBe(2)
    expect(stepOf("NFT approvals")).toBe(2)
    expect(stepOf("Permit2 signatures")).toBe(3)
    expect(stepOf("Transfers out")).toBe(4)
    expect(stepOf("Profiling spenders")).toBe(5)
    expect(stepOf("Pricing what is at risk")).toBe(6)
  })

  it("returns -1 for a label no step owns, including the empty one", () => {
    expect(stepOf("something else")).toBe(-1)
    expect(stepOf("")).toBe(-1)
  })

  it("agrees with STEPS for every label it declares", () => {
    STEPS.forEach((s, i) => {
      for (const label of s.match) expect(stepOf(label)).toBe(i)
    })
  })
})

describe("gradeStatus", () => {
  it("maps grades to a route status", () => {
    expect(gradeStatus(null)).toBe("done")
    expect(gradeStatus(score("A"))).toBe("ok")
    expect(gradeStatus(score("B"))).toBe("ok")
    expect(gradeStatus(score("C"))).toBe("warn")
    expect(gradeStatus(score("D"))).toBe("danger")
    expect(gradeStatus(score("F"))).toBe("danger")
  })
})

describe("verdicts", () => {
  it("passes every step for a clean, complete wallet", () => {
    expect(verdicts(scan(), score("A"))).toEqual(["ok", "ok", "ok", "ok", "ok", "ok", "ok"])
  })

  it("flags a delegated account as danger when the delegation is high severity", () => {
    const r = scan({
      account: { type: "delegated", delegate: SPENDER },
      findings: [finding({ kind: "delegation", severity: "high" })],
    })
    expect(verdicts(r, score("F"))[1]).toBe("danger")
  })

  it("follows the delegation finding's severity, and warns on an unreadable account", () => {
    const medium = scan({ findings: [finding({ kind: "delegation", severity: "medium" })] })
    expect(verdicts(medium, null)[1]).toBe("warn")
    const low = scan({ findings: [finding({ kind: "delegation", severity: "low" })] })
    expect(verdicts(low, null)[1]).toBe("ok")
    expect(verdicts(scan({ account: { type: "unknown" } }), null)[1]).toBe("warn")
  })

  it("rates approvals and permit2 by their worst finding", () => {
    const r = scan({
      findings: [
        finding({ kind: "erc20", severity: "medium" }),
        finding({ kind: "nft", severity: "high" }),
        finding({ kind: "permit2", severity: "medium" }),
      ],
    })
    const v = verdicts(r, null)
    expect(v[2]).toBe("danger")
    expect(v[3]).toBe("warn")
  })

  it("marks poisoning suspects as danger and an incomplete scan as review", () => {
    const r = scan({
      complete: false,
      poisoning: {
        counterparties: [],
        suspects: [{ address: OWNER, imitates: SPENDER, planted: 1, zeroValue: 1 }],
      },
    })
    const v = verdicts(r, null)
    expect(v[4]).toBe("danger")
    expect(v[5]).toBe("warn")
    expect(v[6]).toBe("done")
  })
})

describe("chainVerdicts", () => {
  const report = (sections: ChainReport["sections"]): ChainReport => ({
    family: "tron",
    address: "T",
    sections,
    suspects: [],
    complete: true,
  })
  const section = (
    findings: Array<{ severity: "high" | "medium" | "low" }>,
    complete = true
  ) => ({
    title: "t",
    summary: "",
    complete,
    findings: findings.map((f) => ({ ...f, title: "x", note: "" })),
  })

  it("starts ok, one verdict per section, ends with the grade", () => {
    const r = report([section([{ severity: "high" }]), section([{ severity: "medium" }]), section([])])
    expect(chainVerdicts(r, score("C"))).toEqual(["ok", "danger", "warn", "ok", "warn"])
  })

  it("warns for an empty section that could not be read in full", () => {
    expect(chainVerdicts(report([section([], false)]), null)).toEqual(["ok", "warn", "done"])
  })

  it("treats low findings as ok", () => {
    expect(chainVerdicts(report([section([{ severity: "low" }])]), score("A"))).toEqual(["ok", "ok", "ok"])
  })
})

describe("tables", () => {
  it("SEV_STATUS maps severities to route statuses", () => {
    expect(SEV_STATUS).toEqual({ high: "danger", medium: "warn", low: "ok" })
  })

  it("STATUS_WORD has a word for every status", () => {
    expect(STATUS_WORD).toEqual({
      idle: "waiting",
      active: "checking",
      done: "read",
      ok: "pass",
      warn: "review",
      danger: "risk",
    })
  })

  it("SOURCE names who serves each chain", () => {
    expect(SOURCE.evm("Base")).toContain("Base")
    expect(SOURCE.evm("Base")).toContain("dRPC")
    expect(SOURCE.tron("")).toContain("TronGrid")
    expect(SOURCE.bitcoin("")).toBe("mempool.space")
    expect(SOURCE.solana("")).toContain("Solana")
    expect(SOURCE.stellar("")).toContain("Horizon")
  })
})
