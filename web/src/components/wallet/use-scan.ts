import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react"
import { createPublicClient, getAddress, http } from "viem"
import { tokenPrices } from "@/lib/defi"
import type { Price } from "@/lib/defi"
import { scanWallet } from "@/lib/scan"
import type { ScanResult, Severity } from "@/lib/scan"
import { securityScore, usdAtRisk } from "@/lib/score"
import type { Score } from "@/lib/score"
import { NETWORKS, detectAddress, networkFor, networkOf } from "@/lib/chains"
import { PLANS, chainScore, scanChain } from "@/lib/multichain"
import type { ChainReport } from "@/lib/multichain"
import { useWallet } from "@/lib/wallet"
import { amountOf, stepOf } from "@/lib/wallet-steps"
import { combineScores, fingerprint, pool, rememberScan, scanFailure } from "@/lib/wallet-scan"
import type { PlanRow } from "@/lib/wallet-scan"
import { browserStore } from "@/lib/terminal-nav"
import { makeSnap, pushSnap, readWallets, storageWorks, writeWallets } from "@/lib/wallet-store"
import type { Snap } from "@/lib/wallet-store"

export const EVM_ALL = "evm-all"
const LOOKBACK = 200_000n
const CONCURRENCY = 2

export type Outcome = {
  net: string
  address: string
  score: Score
  prices: Map<string, Price>
  /** The token price lookup failed: dollar amounts are unknown, not zero. */
  pricesFailed?: boolean
  result?: ScanResult
  report?: ChainReport
}
export type NetRow = { net: string; status: "running" | "done" | "error"; outcome?: Outcome; error?: string }
/** One finding as the tables show it: flat and JSON-safe, so it can go straight into the plan export. */
export type Row = PlanRow & {
  net: string
  address: string
  allowance: string
  eoa: boolean
  proxy: boolean
  token?: string
}
export type Found = { fp: string; severity: Severity }

type Step = (label: string, reached: number) => void
const firstLine = (e: unknown) => (e instanceof Error ? e.message : String(e)).split("\n")[0]

/** One network, one address: the same functions the landing uses, nothing else touches the chain. */
export async function runScan(address: string, net: string, onStep?: Step): Promise<Outcome> {
  const d = detectAddress(address)
  if (!d.ok) throw new Error(d.reason)
  const key = networkFor(d.family, net)
  const target = networkOf(key)
  if (target.family === "evm") {
    const owner = getAddress(d.address)
    const client = createPublicClient({ transport: http(target.rpc, { retryCount: 2, batch: { batchSize: 20 } }) })
    onStep?.("Reading the account", 1)
    const result = await scanWallet(client, owner, {
      lookback: LOOKBACK,
      chainId: target.chainId!,
      onProgress: (l) => onStep?.(l, stepOf(l)),
    })
    rememberScan(owner, key, result)
    const tokens = result.findings.filter((f) => f.kind === "erc20" || f.kind === "permit2").map((f) => f.token!)
    onStep?.("Pricing what is at risk", stepOf("Pricing what is at risk"))
    const priced = await tokenPrices(target.chainId, tokens).then(
      (prices) => ({ prices, pricesFailed: false }),
      () => ({ prices: new Map<string, Price>(), pricesFailed: true })
    )
    const { prices, pricesFailed } = priced
    const score = securityScore(result, prices)
    return { net: key, address: owner, result, prices, pricesFailed, score: pricesFailed ? { ...score, provisional: true } : score }
  }
  const fam = target.family
  const report = await scanChain(fam, d.address, { onProgress: (i) => onStep?.(PLANS[fam][i].title, i + 1) })
  return { net: key, address: report.address, report, prices: new Map(), score: chainScore(report) }
}

/** A single network, or the six EVM networks two at a time; a network that fails does not stop the rest. */
export async function runNets(
  address: string,
  net: string,
  h: { onRow?: (r: NetRow) => void; onStep?: Step } = {}
): Promise<Array<NetRow>> {
  const keys = net === EVM_ALL ? NETWORKS.filter((n) => n.family === "evm").map((n) => n.key) : [net]
  if (net === EVM_ALL) {
    const d = detectAddress(address)
    if (!d.ok || d.family !== "evm") throw new Error("All EVM needs a 0x… address.")
  }
  return pool(keys, CONCURRENCY, async (k) => {
    h.onRow?.({ net: k, status: "running" })
    let row: NetRow
    try {
      row = { net: k, status: "done", outcome: await runScan(address, k, h.onStep) }
    } catch (e) {
      row = { net: k, status: "error", error: firstLine(e) }
    }
    h.onRow?.(row)
    return row
  })
}

export const rowsOf = (o: Outcome): Array<Row> =>
  (o.result?.findings ?? []).map((f) => ({
    fp: fingerprint(o.net, f),
    severity: f.severity,
    usd: usdAtRisk(f, o.prices),
    unlimited: f.unlimited,
    spender: f.spender,
    label: f.label,
    symbol: f.symbol,
    kind: f.kind,
    net: o.net,
    address: o.address,
    allowance: amountOf(f),
    eoa: !f.spenderIsContract,
    proxy: !!f.upgradeable,
    token: f.token,
  }))

export const foundOf = (o: Outcome): Array<Found> =>
  o.result
    ? rowsOf(o).map((r) => ({ fp: r.fp, severity: r.severity }))
    : (o.report?.sections ?? []).flatMap((s) =>
        s.findings.map((f) => ({ fp: fingerprint(o.net, { kind: s.title, spender: f.title }), severity: f.severity }))
      )

/** One score for the outcomes, provisional when the scan was partial; null when there are none. */
export const combine = (outs: ReadonlyArray<Outcome>, partial = false): Score | null =>
  combineScores(outs.map((o) => o.score), { provisional: partial })

/** localStorage when it keeps data, else a list that lasts for this page view. */
const mem = new Map<string, string>()
const memStore: Storage = {
  getItem: (k) => mem.get(k) ?? null,
  setItem: (k, v) => void mem.set(k, v),
  removeItem: (k) => void mem.delete(k),
} as Storage
let works: boolean | undefined
export function walletStore(): Storage {
  const real = browserStore()
  works ??= storageWorks(real)
  return works && real ? real : memStore
}

/** Remember a finished scan; when the wallet is in the watchlist, push a snapshot (not for a partial scan) and return the previous one. */
export function recordScan(
  store: Storage,
  address: string,
  net: string,
  outs: ReadonlyArray<Outcome>,
  partial = false
): { prev?: Snap; fps: Array<string> } {
  const found = outs.flatMap(foundOf)
  const score = combine(outs, partial)
  const fps = found.map((f) => f.fp)
  const list = readWallets(store)
  const w = list.find((x) => x.net === net && x.address.toLowerCase() === address.toLowerCase())
  if (!w || !score) return { fps }
  const snap = makeSnap({
    at: Date.now(),
    fps,
    high: found.filter((f) => f.severity === "high").map((f) => f.fp),
    score: score.score,
    grade: score.grade,
    usd: score.usdAtRisk,
    partial,
    pricesFailed: outs.some((o) => o.pricesFailed),
  })
  if (snap) writeWallets(store, list.map((x) => (x === w ? pushSnap(x, snap) : x)))
  return { prev: w.snaps.at(-1), fps }
}

export const doneOutcomes = (rows: ReadonlyArray<NetRow>): Array<Outcome> =>
  rows.flatMap((r) => (r.outcome ? [r.outcome] : []))

const QUERY = "(prefers-reduced-motion: reduce)"
export function useReduced(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(QUERY)
      m.addEventListener("change", cb)
      return () => m.removeEventListener("change", cb)
    },
    () => window.matchMedia(QUERY).matches,
    () => false
  )
}

export type ScanState = {
  phase: "idle" | "running" | "done" | "error"
  address: string
  net: string
  step: string | null
  reached: number
  rows: Array<NetRow>
  error?: string
  switched: boolean
}
const IDLE: ScanState = { phase: "idle", address: "", net: "", step: null, reached: 0, rows: [], switched: false }
const upsert = (rows: Array<NetRow>, r: NetRow) =>
  rows.some((x) => x.net === r.net) ? rows.map((x) => (x.net === r.net ? r : x)) : [...rows, r]

export function useScan(onDone?: (r: { address: string; net: string; rows: Array<NetRow> }) => void) {
  const wallet = useWallet()
  const [s, set] = useState<ScanState>(IDLE)
  const id = useRef(0)
  const busy = useRef(false)
  const target = useRef({ address: "", net: "" })
  const done = useRef(onDone)
  const prevWallet = useRef(wallet.address)
  useEffect(() => {
    done.current = onDone
  })
  // the libs take no AbortSignal: a stale scan keeps reading, but its results are never used
  useEffect(
    () => () => {
      id.current++
    },
    []
  )

  const hooks = useCallback((live: () => boolean) => {
    return {
      onRow: (r: NetRow) => live() && set((p) => ({ ...p, rows: upsert(p.rows, r) })),
      onStep: (label: string, i: number) =>
        live() && set((p) => ({ ...p, step: label, reached: Math.max(p.reached, i) })),
    }
  }, [])

  const scan = useCallback(
    async (address: string, net: string) => {
      const me = ++id.current
      target.current = { address, net }
      busy.current = true
      set({ ...IDLE, phase: "running", address, net, reached: 1 })
      try {
        const rows = await runNets(address, net, hooks(() => me === id.current))
        if (me !== id.current) return
        const failure = scanFailure(rows)
        set((p) => ({ ...p, phase: failure ? "error" : "done", error: failure, step: null, rows }))
        if (!failure) done.current?.({ address, net, rows })
      } catch (e) {
        if (me === id.current) set((p) => ({ ...p, phase: "error", error: firstLine(e), step: null }))
      } finally {
        if (me === id.current) busy.current = false
      }
    },
    [hooks]
  )

  const cancel = useCallback(() => {
    id.current++
    busy.current = false
    set(IDLE)
  }, [])

  // Retry one network of an "All EVM" scan: its own token, so the main scan is never invalidated
  const retryId = useRef(new Map<string, number>())
  const retry = useCallback(
    async (net: string) => {
      const main = id.current
      const me = (retryId.current.get(net) ?? 0) + 1
      retryId.current.set(net, me)
      const [row] = await runNets(target.current.address, net, hooks(() => main === id.current && retryId.current.get(net) === me))
      if (main !== id.current || retryId.current.get(net) !== me) return
      set((p) => ({
        ...p,
        phase: p.phase === "error" && row.status === "done" ? "done" : p.phase,
        error: p.phase === "error" && row.status === "done" ? undefined : p.error,
        rows: upsert(p.rows, row),
      }))
    },
    [hooks]
  )

  // the wallet moved to another account while its own address was being scanned
  useEffect(() => {
    const was = prevWallet.current
    prevWallet.current = wallet.address
    if (was && wallet.address !== was && busy.current && target.current.address.toLowerCase() === was.toLowerCase()) {
      id.current++
      busy.current = false
      set({ ...IDLE, switched: true })
    }
  }, [wallet.address])

  return { ...s, wallet, scan, cancel, retry }
}
