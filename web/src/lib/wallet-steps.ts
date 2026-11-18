import { formatUnits } from "viem"
import { PLANS } from "@/lib/multichain"
import type { ChainFinding, ChainReport } from "@/lib/multichain"
import type { Finding, ScanResult, Severity } from "@/lib/scan"
import type { Score } from "@/lib/score"
import type { Family } from "@/lib/chains"
import type { RouteStatus } from "@/components/wallet/wallet-route"

/** Who serves each chain's reads, as said to the user. */
export const SOURCE: Record<Family, (name: string) => string> = {
  evm: (name) => `dRPC\u2019s public ${name} node`,
  tron: () => "TronGrid\u2019s public API",
  solana: () => "rinng\u2019s own read-only relay to Solana\u2019s public RPC",
  bitcoin: () => "mempool.space",
  stellar: () => "the Stellar Development Foundation\u2019s Horizon API",
}

// The seven steps of the EVM check. scanWallet reports progress as free text; each step owns the
// labels it covers (the same map as components/wallet-check.tsx), and gets a verdict at the end.
export const STEPS = [
  { title: "Read-only", body: "This page holds no key and asks for no signature.", match: [] as Array<string> },
  { title: "Account & 7702", body: "EOA, Safe or smart account, and any EIP-7702 delegate.", match: ["Reading the account", "Account type and EIP-7702 delegation"] },
  { title: "Approvals", body: "ERC-20 allowances and NFT operators the wallet granted.", match: ["ERC-20 approvals", "NFT approvals"] },
  { title: "Permit2", body: "Off-chain Permit2 signatures still live.", match: ["Permit2 approvals", "Permit2 signatures"] },
  { title: "Poisoning", body: "Look-alike addresses planted in the transfer history.", match: ["Transfers in", "Transfers out"] },
  { title: "Live allowances", body: "Re-read on-chain today, spenders profiled.", match: ["Re-reading live allowances", "Profiling spenders"] },
  { title: "Exposure & score", body: "Dollars reachable now, and a grade.", match: ["Measuring what is at risk", "Pricing what is at risk"] },
]

export const SEV_STATUS: Record<Severity, RouteStatus> = { high: "danger", medium: "warn", low: "ok" }

// Other chains: read-only first, the chain's own checks, then the score.
export const planFor = (family: Family) =>
  family === "evm"
    ? STEPS
    : [
        STEPS[0],
        ...PLANS[family].map((p) => ({ ...p, match: [] as Array<string> })),
        { title: "Exposure & score", body: "A grade, with every point it lost explained.", match: [] as Array<string> },
      ]

export const gradeStatus = (score: Score | null): RouteStatus =>
  !score ? "done" : score.grade === "A" || score.grade === "B" ? "ok" : score.grade === "C" ? "warn" : "danger"

export function chainVerdicts(r: ChainReport, score: Score | null): Array<RouteStatus> {
  const worstOf = (f: Array<ChainFinding>): RouteStatus =>
    f.some((x) => x.severity === "high") ? "danger" : f.some((x) => x.severity === "medium") ? "warn" : "ok"
  return ["ok", ...r.sections.map((s) => (s.findings.length ? worstOf(s.findings) : s.complete ? "ok" : "warn")), gradeStatus(score)]
}

export function worst(r: ScanResult, kinds: Array<string>): RouteStatus {
  const sev = r.findings.filter((f) => kinds.includes(f.kind)).map((f) => f.severity)
  return sev.includes("high") ? "danger" : sev.includes("medium") ? "warn" : "ok"
}

export function verdicts(r: ScanResult, score: Score | null): Array<RouteStatus> {
  const delegation = r.findings.find((f) => f.kind === "delegation")
  return [
    "ok",
    delegation ? SEV_STATUS[delegation.severity] : r.account.type === "unknown" ? "warn" : "ok",
    worst(r, ["erc20", "nft"]),
    worst(r, ["permit2"]),
    r.poisoning.suspects.length ? "danger" : "ok",
    r.complete ? "ok" : "warn",
    gradeStatus(score),
  ]
}

export const STATUS_WORD: Record<RouteStatus, string> = {
  idle: "waiting",
  active: "checking",
  done: "read",
  ok: "pass",
  warn: "review",
  danger: "risk",
}

export function amountOf(f: Finding) {
  if (f.kind === "delegation") return "delegated"
  if (f.kind === "nft") return "all items"
  if (f.unlimited) return "unlimited"
  if (f.amount != null && f.decimals != null) {
    const n = Number(formatUnits(f.amount, f.decimals))
    return `${n.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${f.symbol ?? ""}`.trim()
  }
  return "limited"
}

/** The index of the step that owns a scan progress label, -1 when none does. */
export const stepOf = (label: string) => STEPS.findIndex((s) => s.match.includes(label))
