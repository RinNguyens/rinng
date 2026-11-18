// Saved wallets for the Wallet route: add/rename/remove, the last two scan snapshots per wallet and
// what changed between them. Pure, storage comes in as an argument (style: terminal-nav.ts).
/** `high` holds the fingerprints of HIGH findings; score, grade and usd summarise that scan. */
import type { Grade } from "./wallet-scan"

export type Snap = { at: number; fps: Array<string>; score?: number; grade?: Grade; usd?: number; high?: Array<string> }
export type Wallet = { address: string; net: string; label: string; snaps: Array<Snap> }
export type AddResult =
  | { ok: true; list: Array<Wallet> }
  | { ok: false; error: "duplicate" | "full" | "empty" }

const KEY = "rinng.wallets.v1"
const MAX_WALLETS = 20
const MAX_LABEL = 24

const same = (w: Wallet, address: string, net: string) =>
  w.net === net && w.address.toLowerCase() === address.toLowerCase()
const shortAddr = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`
const cleanLabel = (label: string | undefined) => (label ?? "").trim().slice(0, MAX_LABEL)

export function addWallet(
  list: ReadonlyArray<Wallet>,
  input: { address: string; net: string; label?: string }
): AddResult {
  const address = input.address.trim()
  if (!address) return { ok: false, error: "empty" }
  if (list.some((w) => same(w, address, input.net))) return { ok: false, error: "duplicate" }
  if (list.length >= MAX_WALLETS) return { ok: false, error: "full" }
  const label = cleanLabel(input.label) || shortAddr(address)
  return { ok: true, list: [...list, { address, net: input.net, label, snaps: [] }] }
}

export function renameWallet(
  list: ReadonlyArray<Wallet>,
  address: string,
  net: string,
  label: string
): Array<Wallet> {
  const next = cleanLabel(label)
  return list.map((w) => (next && same(w, address, net) ? { ...w, label: next } : w))
}

export const removeWallet = (list: ReadonlyArray<Wallet>, address: string, net: string): Array<Wallet> =>
  list.filter((w) => !same(w, address, net))

export const pushSnap = (wallet: Wallet, snap: Snap): Wallet => ({
  ...wallet,
  snaps: [...wallet.snaps, snap].slice(-2),
})

export function diffSnaps(
  prev: Snap | undefined,
  cur: Snap,
  sevOf: (fp: string) => "high" | "medium" | "low"
): { newHigh: Array<string>; newOther: Array<string>; removed: Array<string> } {
  if (!prev) return { newHigh: [], newOther: [], removed: [] }
  const before = new Set(prev.fps)
  const now = new Set(cur.fps)
  const added = cur.fps.filter((fp) => !before.has(fp))
  return {
    newHigh: added.filter((fp) => sevOf(fp) === "high"),
    newOther: added.filter((fp) => sevOf(fp) !== "high"),
    removed: prev.fps.filter((fp) => !now.has(fp)),
  }
}

/** The snapshot of a finished scan; none for a partial one (it would drop what the failed network held). */
export function makeSnap(i: {
  at: number
  fps: Array<string>
  high: Array<string>
  score: number
  grade: Grade
  usd: number
  partial: boolean
  pricesFailed: boolean
}): Snap | undefined {
  if (i.partial) return undefined
  return { at: i.at, fps: i.fps, score: i.score, grade: i.grade, usd: i.pricesFailed ? undefined : i.usd, high: i.high }
}

/** What changed between a saved wallet's last two snapshots; null when there are not two. */
export function savedDiff(list: ReadonlyArray<Wallet>, address: string, net: string) {
  const w = list.find((x) => same(x, address, net))
  const last = w?.snaps.at(-1)
  return w && last && w.snaps.length > 1 ? diffSnaps(w.snaps.at(-2), last, sevFromSnap(last)) : null
}

export const sevFromSnap =
  (snap: Snap) =>
  (fp: string): "high" | "low" =>
    snap.high?.includes(fp) ? "high" : "low"

const isStrings = (v: unknown): v is Array<string> => Array.isArray(v) && v.every((f) => typeof f === "string")
const isSnap = (s: unknown): s is Snap =>
  !!s && typeof (s as Snap).at === "number" && isStrings((s as Snap).fps)

// Keep the summary fields that have the right type; a bad one is dropped, not the snapshot.
function cleanSnap(s: Snap): Snap {
  const out: Snap = { at: s.at, fps: s.fps }
  if (typeof s.score === "number") out.score = s.score
  if (typeof s.grade === "string" && "ABCDF".includes(s.grade) && s.grade.length === 1) out.grade = s.grade
  if (typeof s.usd === "number") out.usd = s.usd
  if (isStrings(s.high)) out.high = s.high
  return out
}

export function readWallets(store: Pick<Storage, "getItem"> | undefined): Array<Wallet> {
  try {
    const raw = store?.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    if (!Array.isArray(parsed)) return []
    return parsed.flatMap((v): Array<Wallet> => {
      const w = v as Partial<Wallet> | null
      if (!w || typeof w.address !== "string" || typeof w.net !== "string") return []
      const snaps = Array.isArray(w.snaps) ? w.snaps.filter(isSnap).map(cleanSnap) : []
      return [{ address: w.address, net: w.net, label: typeof w.label === "string" ? w.label : shortAddr(w.address), snaps }]
    })
  } catch {
    return []
  }
}

export function writeWallets(store: Pick<Storage, "setItem"> | undefined, list: ReadonlyArray<Wallet>): void {
  try {
    store?.setItem(KEY, JSON.stringify(list))
  } catch {
    // storage blocked or full: wallets last for this page view only
  }
}

// True only when a value written now can be read back (private modes may drop writes silently).
export function storageWorks(store: Pick<Storage, "getItem" | "setItem" | "removeItem"> | undefined): boolean {
  const probe = "rinng.probe"
  try {
    if (!store) return false
    store.setItem(probe, "1")
    const ok = store.getItem(probe) === "1"
    store.removeItem(probe)
    return ok
  } catch {
    return false
  }
}
