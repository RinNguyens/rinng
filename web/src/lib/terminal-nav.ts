// Pure helpers for the /terminal shell: URL search, section routing, last-section memory, and
// resolving which coin and exchange the URL points at. Kept free of React so node tests can run it.
import type { Instrument } from "@/lib/api"

export type Exchange = "binance" | "okx"
export type Section = "market" | "coin" | "charts" | "wallet"
export type TerminalSearch = { symbol?: string; ex?: Exchange }

const SECTIONS: ReadonlyArray<Section> = ["market", "coin", "charts", "wallet"]
const SECTION_KEY = "rinng.section.v1"
const INSTRUMENT_KEY = "rinng.instrument.v1"

export const isExchange = (v: unknown): v is Exchange => v === "binance" || v === "okx"

// validateSearch body: keep a non-empty symbol and a known exchange, drop everything else.
export function parseSearch(raw: Record<string, unknown>): TerminalSearch {
  const out: TerminalSearch = {}
  const symbol = typeof raw.symbol === "string" ? raw.symbol.trim() : ""
  if (symbol) out.symbol = symbol
  if (isExchange(raw.ex)) out.ex = raw.ex
  return out
}

export function sectionFromPath(pathname: string): Section | null {
  const m = /^\/terminal\/([^/]+)/.exec(pathname)
  return SECTIONS.find((s) => s === m?.[1]) ?? null
}

export function readSection(store?: Pick<Storage, "getItem">): Section {
  try {
    const v = store?.getItem(SECTION_KEY)
    return SECTIONS.find((s) => s === v) ?? "coin"
  } catch {
    return "coin"
  }
}

// The page's localStorage, or undefined when there is none (dev SSR) or the browser blocks site data:
// then even reading the global throws, before any helper's own try/catch can run.
export function browserStore(): Storage | undefined {
  try {
    return typeof localStorage === "undefined" ? undefined : localStorage
  } catch {
    return undefined
  }
}

export function writeSection(store: Pick<Storage, "setItem"> | undefined, s: Section) {
  try {
    store?.setItem(SECTION_KEY, s)
  } catch {
    // storage blocked or full: the section just isn't remembered
  }
}

// Forward a missing or unknown tab to the first workspace; null while there is nothing to do.
export function tabRedirect(
  tabId: string | undefined,
  workspaces: ReadonlyArray<{ id: string }>
): string | null {
  if (workspaces.length === 0 || workspaces.some((w) => w.id === tabId)) return null
  return workspaces[0].id
}

// Switch exchange when the current one doesn't list the coin (same `=== false` rule as before).
export function exchangeFor(inst: Instrument, current: Exchange): Exchange {
  if (inst[current] === false) return inst.binance ? "binance" : "okx"
  return current
}

// The exchange on screen: Market keeps what the URL says (it lists every exchange), the other
// sections flip to one that lists the coin.
export function sectionExchange(
  section: Section | null,
  inst: Instrument,
  ex: Exchange | undefined
): Exchange {
  return section === "market" ? (ex ?? "binance") : exchangeFor(inst, ex ?? "binance")
}

export function readSavedInstrument(store?: Pick<Storage, "getItem">): Instrument | null {
  try {
    const raw = store?.getItem(INSTRUMENT_KEY)
    const v = raw ? JSON.parse(raw) : null
    return typeof v?.id === "string" ? (v as Instrument) : null
  } catch {
    return null
  }
}

// undefined means the symbol isn't known locally, so the caller must ask the network.
export function resolveInstrument(
  symbol: string | undefined,
  watchlist: ReadonlyArray<Instrument>,
  saved: Instrument | null
): Instrument | undefined {
  if (symbol === undefined) return saved ?? watchlist[0]
  if (saved?.id === symbol) return saved
  return watchlist.find((i) => i.id === symbol)
}

// The coin on screen: `key` is the URL symbol it answers; `error` is set when that symbol could not be
// opened and `inst` is a fallback shown instead.
export type Current = { key: string | undefined; inst: Instrument; error?: string }

// True when the current coin already answers the URL symbol (requested alias or canonical id).
export function isResolved(symbol: string | undefined, cur: Current | null): boolean {
  return (
    !!cur &&
    (symbol === undefined || symbol === cur.key || (!cur.error && symbol === cur.inst.id))
  )
}

// Rewrite the URL to the canonical id and exchange, unless the coin shown is a fallback for a failed
// lookup: then the URL keeps what the user asked for, so a reload retries.
export function needsWriteBack(
  search: TerminalSearch,
  cur: Current | null,
  exchange: Exchange | undefined
): boolean {
  if (!cur || cur.error || !exchange || !isResolved(search.symbol, cur)) return false
  return search.symbol !== cur.inst.id || search.ex !== exchange
}
