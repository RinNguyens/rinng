// Starred coins (Market's Watchlist segment and Coin's ★). Callers pass browserStore(), which is
// undefined when site data is blocked; then nothing is read or saved.
const KEY = "rinng.watchlist.v1"

type Store = Pick<Storage, "getItem" | "setItem">

export function readStarred(store: Store | undefined): Array<string> {
  try {
    const v: unknown = JSON.parse(store?.getItem(KEY) ?? "[]")
    return Array.isArray(v) ? v.filter((s): s is string => typeof s === "string") : []
  } catch {
    return []
  }
}

export function toggleStarred(store: Store | undefined, symbol: string): Array<string> {
  const cur = readStarred(store)
  const next = cur.includes(symbol) ? cur.filter((s) => s !== symbol) : [...cur, symbol]
  try {
    store?.setItem(KEY, JSON.stringify(next))
  } catch {
    /* storage unavailable: the list just won't persist */
  }
  return next
}
