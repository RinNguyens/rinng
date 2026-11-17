// Public DeFi data straight from DefiLlama (CORS-open, no key). Both payloads are ~10 MB,
// so each is fetched once per page load and shared by every view.

export type Protocol = {
  name: string
  slug: string
  symbol: string // "-" when the protocol has no token yet
  category: string
  chains: Array<string>
  tvl: number
  change_1d: number | null
  change_7d: number | null
  logo: string
  url: string
}

export type Pool = {
  pool: string
  chain: string
  project: string
  symbol: string
  tvlUsd: number
  apy: number | null
  apyBase: number | null
  apyReward: number | null
  stablecoin: boolean
  ilRisk: string
  exposure: string
}

const once = <T>(load: () => Promise<T>) => {
  let p: Promise<T> | null = null
  return () => {
    if (!p) p = load().catch((e: unknown) => ((p = null), Promise.reject(e)))
    return p
  }
}

async function json<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url} → ${r.status}`)
  return (await r.json()) as T
}

export const protocols = once(async () =>
  (await json<Array<Protocol>>("https://api.llama.fi/protocols"))
    .filter((p) => p.category !== "CEX" && p.tvl > 0)
    .sort((a, b) => b.tvl - a.tvl)
)

export const pools = once(async () =>
  (
    await json<{ data: Array<Pool> }>("https://yields.llama.fi/pools")
  ).data.filter((p) => p.apy != null && p.tvlUsd > 1e6)
)

/** Projects whose pools are staking / liquid staking / restaking, by DefiLlama category. */
export const STAKING_CATEGORIES = new Set([
  "Liquid Staking",
  "Liquid Restaking",
  "Restaking",
  "Staking Pool",
])

/** Tokenless protocols with real TVL: the usual hunting ground for points and airdrops. */
export function airdropCandidates(list: Array<Protocol>, min = 20e6) {
  return list.filter((p) => (p.symbol === "-" || !p.symbol) && p.tvl >= min)
}

export const usd = (n: number) =>
  n >= 1e9
    ? `$${(n / 1e9).toFixed(2)}B`
    : n >= 1e6
      ? `$${(n / 1e6).toFixed(1)}M`
      : `$${Math.round(n / 1e3)}K`

export const pct = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : `${n.toFixed(digits)}%`

/** DefiLlama's chain slugs for the coins API. */
const LLAMA_CHAIN: Record<number, string> = {
  1: "ethereum",
  10: "optimism",
  56: "bsc",
  137: "polygon",
  8453: "base",
  42161: "arbitrum",
  43114: "avax",
  59144: "linea",
  534352: "scroll",
}

export type Price = { price: number; decimals?: number; symbol?: string }

/**
 * Current USD prices for token contracts, keyed by lowercase address. Only token addresses are
 * sent, never the wallet's. Tokens DefiLlama can't price (scams, dust) are simply missing.
 */
export async function tokenPrices(
  chainId: number | null | undefined,
  tokens: Array<string>
): Promise<Map<string, Price>> {
  const chain = chainId != null ? LLAMA_CHAIN[chainId] : undefined
  const out = new Map<string, Price>()
  if (!chain || tokens.length === 0) return out
  const uniq = [...new Set(tokens.map((t) => t.toLowerCase()))]
  for (let i = 0; i < uniq.length; i += 80) {
    const ids = uniq.slice(i, i + 80).map((t) => `${chain}:${t}`)
    const r = await json<{ coins: Record<string, Price> }>(
      `https://coins.llama.fi/prices/current/${ids.join(",")}`
    )
    for (const [k, v] of Object.entries(r.coins))
      out.set(k.split(":")[1].toLowerCase(), v)
  }
  return out
}
