// Pure helpers for the Wallet route: revoke plan, "marked revoked" memory, exports, scan pool,
// grouping, search parsing and a per-session scan cache. No React, storage comes in as an argument.
import { NETWORKS } from "./chains"
import type { ScanResult, Severity } from "./scan"
import type { Score } from "./score"

export type Grade = "A" | "B" | "C" | "D" | "F"
export type PlanItem = { fp: string; severity: Severity; usd?: number; unlimited: boolean }
export type PlanRow = PlanItem & {
  spender: string
  label?: string
  symbol?: string
  kind: string
}
export type RevokeMap = Record<string, { checkedAt: number }>

const REVOKE_KEY = "rinng.revoke.v1"
const KEEP_MS = 90 * 86_400_000
const SEVERITY_RANK: Record<Severity, number> = { high: 0, medium: 1, low: 2 }
const GRADES: ReadonlyArray<Grade> = ["A", "B", "C", "D", "F"]

export const fingerprint = (
  net: string,
  f: { kind: string; token?: string; spender: string }
): string => `${net}:${f.kind}:${f.token ?? "-"}:${f.spender}`.toLowerCase()

// Highest severity first, then biggest USD at risk (unpriced last), then unlimited; stable otherwise.
export function revokePlan<T extends PlanItem>(items: ReadonlyArray<T>): Array<T> {
  return [...items].sort(
    (a, b) =>
      SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
      (b.usd ?? -1) - (a.usd ?? -1) ||
      Number(b.unlimited) - Number(a.unlimited)
  )
}

export function readRevoke(store: Pick<Storage, "getItem"> | undefined, now: number): RevokeMap {
  try {
    const raw = store?.getItem(REVOKE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {}
    const out: RevokeMap = {}
    for (const [fp, v] of Object.entries(parsed)) {
      const at = (v as { checkedAt?: unknown } | null)?.checkedAt
      if (typeof at === "number" && now - at <= KEEP_MS) out[fp] = { checkedAt: at }
    }
    return out
  } catch {
    return {}
  }
}

export function writeRevoke(store: Pick<Storage, "setItem"> | undefined, map: RevokeMap): void {
  try {
    store?.setItem(REVOKE_KEY, JSON.stringify(map))
  } catch {
    // storage blocked or full: the marks just last for this page view
  }
}

export function money(n: number | undefined): string {
  if (n === undefined || Number.isNaN(n)) return "—"
  if (n === 0) return "$0"
  if (n < 0.01) return "<$0.01"
  if (n < 1) return `$${n.toFixed(2)}`
  return `$${Math.round(n).toLocaleString("en-US")}`
}

// Token symbols and labels come from the chain: no Markdown, no line breaks.
const md = (s: string) => s.replace(/\s*[\r\n]+\s*/g, " ").replace(/[\\`*_{}[\]()<>#+!|~&]/g, "\\$&")

const describe = (r: PlanRow) =>
  [
    md(r.spender),
    r.label && `(${md(r.label)})`,
    r.symbol && md(r.symbol),
    md(r.kind),
    `${r.severity} risk`,
    r.unlimited && "unlimited",
    r.usd !== undefined && money(r.usd),
  ]
    .filter(Boolean)
    .join(" · ")

export function planMarkdown(items: ReadonlyArray<PlanRow>, net: string): string {
  const head = `# Revoke plan (${md(net)})`
  if (items.length === 0) return `${head}\n\nNothing to revoke.\n`
  return `${head}\n\n${items.map((r, i) => `${i + 1}. ${describe(r)}`).join("\n")}\n`
}

export const planJson = (items: ReadonlyArray<PlanRow>, net: string): string =>
  JSON.stringify({ network: net, items }, null, 2)

// Runs fn over items with at most n in flight; results keep input order; first failure rejects.
export async function pool<T, TResult>(
  items: ReadonlyArray<T>,
  n: number,
  fn: (item: T, index: number) => Promise<TResult>
): Promise<Array<TResult>> {
  const out = new Array<TResult>(items.length)
  let next = 0
  const worker = async () => {
    while (next < items.length) {
      const i = next++
      out[i] = await fn(items[i], i)
    }
  }
  await Promise.all(Array.from({ length: Math.min(Math.max(1, n), items.length) }, worker))
  return out
}

export function worstGrade(grades: ReadonlyArray<Grade>): Grade | null {
  if (grades.length === 0) return null
  return GRADES[Math.max(...grades.map((g) => GRADES.indexOf(g)))]
}

export function groupFindings<T extends { spender: string; net: string }>(
  rows: ReadonlyArray<T>,
  by: "none" | "spender" | "network"
): Array<{ key: string; rows: Array<T> }> {
  const groups = new Map<string, Array<T>>()
  for (const r of rows) {
    const key = by === "none" ? "" : by === "spender" ? r.spender.toLowerCase() : r.net
    groups.set(key, [...(groups.get(key) ?? []), r])
  }
  return [...groups].map(([key, list]) => ({ key, rows: list }))
}

// validateSearch body: only a non-empty address, a known network and hl=new (show the saved diff) ride in the URL.
export function parseWalletSearch(raw: Record<string, unknown>): { address?: string; net?: string; hl?: "new" } {
  const out: { address?: string; net?: string; hl?: "new" } = {}
  if (raw.hl === "new") out.hl = "new"
  const address = typeof raw.address === "string" ? raw.address.trim() : ""
  if (address) out.address = address
  if (typeof raw.net === "string" && (raw.net === "evm-all" || NETWORKS.some((n) => n.key === raw.net)))
    out.net = raw.net
  return out
}

export function verifyState(
  fp: string,
  checked: RevokeMap,
  live: ReadonlySet<string> | null
): "verified" | "still-live" | "open" {
  if (!(fp in checked) || live === null) return "open"
  return live.has(fp) ? "still-live" : "verified"
}

/** Fingerprints a finished scan found; null when the scan was partial, so nothing can be called verified. */
export const liveFps = (rows: ReadonlyArray<{ fp: string }>, partial: boolean): Set<string> | null =>
  partial ? null : new Set(rows.map((r) => r.fp))

type RowLike = { status: string; error?: string; outcome?: { result?: { complete: boolean }; report?: { complete: boolean } } }

/** A network errored, or a network's history was not fully read. */
export const scanIsPartial = (rows: ReadonlyArray<RowLike>): boolean =>
  rows.some((r) => r.status === "error" || r.outcome?.result?.complete === false || r.outcome?.report?.complete === false)

/** Why a scan produced nothing: the single network's error, or "none of them" when every network failed. */
export function scanFailure(rows: ReadonlyArray<RowLike>): string | undefined {
  if (rows.length === 0 || !rows.every((r) => r.status === "error")) return undefined
  return rows.length === 1
    ? rows[0].error
    : "Could not read any network. Check your connection, then retry a network below."
}

/** One score for any number of networks: the worst grade and score, the summed dollars; null when there is none. */
export function combineScores(scores: ReadonlyArray<Score>, opts: { provisional?: boolean } = {}): Score | null {
  if (scores.length === 0) return null
  const low = scores.reduce((a, b) => (b.score < a.score ? b : a))
  return {
    ...low,
    grade: worstGrade(scores.map((s) => s.grade)) ?? low.grade,
    provisional: !!opts.provisional || scores.some((s) => s.provisional),
    usdAtRisk: scores.reduce((n, s) => n + s.usdAtRisk, 0),
  }
}

// Last scan per address and network, kept for this page view so Send check can reuse it.
const scans = new Map<string, ScanResult>()
const scanKey = (address: string, net: string) => `${address.toLowerCase()}|${net}`

export function rememberScan(address: string, net: string, r: ScanResult): void {
  scans.set(scanKey(address, net), r)
}

export const lastScan = (address: string, net: string): ScanResult | undefined =>
  scans.get(scanKey(address, net))
