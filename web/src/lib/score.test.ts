import { describe, expect, it } from "vitest"
import { securityScore, usdAtRisk } from "./score"
import type { Finding } from "./scan"

const f = (x: Partial<Finding>): Finding => ({
  kind: "erc20",
  spender: "0x4444444444444444444444444444444444444444",
  spenderIsContract: true,
  severity: "medium",
  unlimited: true,
  note: "",
  ...x,
})
const empty = { suspects: [], counterparties: [] }

describe("securityScore", () => {
  it("gives a clean EOA an A", () => {
    const s = securityScore({
      findings: [],
      account: { type: "eoa" },
      poisoning: empty,
      complete: true,
    })
    expect(s).toMatchObject({ score: 100, grade: "A", provisional: false })
  })

  it("sinks an unknown delegation plus a drainer approval to F", () => {
    const s = securityScore({
      findings: [
        f({ kind: "delegation", severity: "high" }),
        f({ severity: "high" }),
      ],
      account: {
        type: "delegated",
        delegate: "0x4444444444444444444444444444444444444444",
      },
      poisoning: empty,
      complete: true,
    })
    expect(s.grade).toBe("F")
    expect(s.items.length).toBeGreaterThanOrEqual(2)
  })

  it("charges for dollars at risk and marks a partial scan provisional", () => {
    const token = "0x2222222222222222222222222222222222222222"
    const prices = new Map([[token, { price: 2, decimals: 18 }]])
    const finding = f({
      token,
      amount: 10n ** 30n,
      balance: 10_000n * 10n ** 18n,
      decimals: 18,
    })
    expect(usdAtRisk(finding, prices)).toBe(20_000)
    const s = securityScore(
      {
        findings: [finding],
        account: { type: "eoa" },
        poisoning: empty,
        complete: false,
      },
      prices
    )
    expect(s.usdAtRisk).toBe(20_000)
    expect(s.provisional).toBe(true)
    expect(s.items.map((i) => i.text).join()).toMatch(/\$10k/)
  })
})
