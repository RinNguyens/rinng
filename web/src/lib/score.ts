import { formatUnits } from "viem"
import { exposure } from "./scan"
import type { Finding, ScanResult } from "./scan"
import type { Price } from "./defi"

// One number for "how exposed is this wallet", with every point it lost explained. It rates what
// the scan saw; a partial scan gives a provisional score that can only be lower in reality.

export type ScoreItem = { delta: number; text: string }
export type Score = {
  score: number
  grade: "A" | "B" | "C" | "D" | "F"
  items: Array<ScoreItem>
  provisional: boolean
  usdAtRisk: number
}

/** USD the finding can take today, when the token has a price. */
export function usdAtRisk(
  f: Finding,
  prices: Map<string, Price>
): number | undefined {
  if (f.kind !== "erc20" && f.kind !== "permit2") return undefined
  const units = exposure(f)
  const p = f.token ? prices.get(f.token.toLowerCase()) : undefined
  if (units == null || !p) return undefined
  return Number(formatUnits(units, f.decimals ?? p.decimals ?? 18)) * p.price
}

const cap = (n: number, max: number) => Math.min(n, max)

export function securityScore(
  r: Pick<ScanResult, "findings" | "account" | "poisoning" | "complete">,
  prices: Map<string, Price> = new Map()
): Score {
  const items: Array<ScoreItem> = []
  const lose = (delta: number, text: string) =>
    delta && items.push({ delta: -delta, text })
  const count = (sev: Finding["severity"], kind?: Finding["kind"]) =>
    r.findings.filter((f) => f.severity === sev && (!kind || f.kind === kind))
      .length

  const delegation = r.findings.find((f) => f.kind === "delegation")
  if (delegation)
    lose(
      delegation.severity === "high" ? 45 : 10,
      delegation.severity === "high"
        ? "Wallet delegated (EIP-7702) to an unrecognised contract"
        : `Wallet delegated to ${delegation.label ?? "a smart account"}`
    )
  const high = r.findings.filter(
    (f) => f.severity === "high" && f.kind !== "delegation"
  ).length
  if (high)
    lose(
      cap(high * 20, 50),
      `${high} high-risk approval${high > 1 ? "s" : ""} (EOA spenders)`
    )
  const med = count("medium")
  if (med)
    lose(
      cap(med * 5, 25),
      `${med} unlimited or long-lived approval${med > 1 ? "s" : ""}`
    )
  const low = count("low")
  if (low > 5)
    lose(
      cap(low - 5, 5),
      `${low} low-risk approvals: revoke the ones you no longer use`
    )

  const usd = r.findings
    .filter((f) => f.severity !== "low")
    .reduce((s, f) => s + (usdAtRisk(f, prices) ?? 0), 0)
  if (usd >= 100_000) lose(15, "Over $100k reachable by risky approvals")
  else if (usd >= 10_000) lose(10, "Over $10k reachable by risky approvals")
  else if (usd >= 1_000) lose(5, "Over $1k reachable by risky approvals")

  const suspects = r.poisoning.suspects.length
  if (suspects)
    lose(
      5,
      `Targeted by address poisoning (${suspects} look-alike address${suspects > 1 ? "es" : ""} in your history)`
    )
  if (r.account.type === "safe" && r.account.threshold < 2)
    lose(5, "Safe with a 1-signer threshold: one key can still move everything")
  if (r.account.type === "safe" && r.account.threshold >= 2)
    items.push({
      delta: 0,
      text: `Safe multisig, ${r.account.threshold} of ${r.account.owners.length} signers: strong setup`,
    })
  if (!r.complete)
    items.push({
      delta: 0,
      text: "Part of the history could not be read: score is provisional",
    })

  const score = Math.max(0, 100 + items.reduce((s, i) => s + i.delta, 0))
  const grade =
    score >= 90
      ? "A"
      : score >= 75
        ? "B"
        : score >= 60
          ? "C"
          : score >= 40
            ? "D"
            : "F"
  return { score, grade, items, provisional: !r.complete, usdAtRisk: usd }
}
