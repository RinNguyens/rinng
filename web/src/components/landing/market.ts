// Live BTCUSDT perpetual data for the landing page, straight from Binance's public futures API
// (no key, CORS open), the same public data rinng itself collects.

const FAPI = "https://fapi.binance.com/fapi/v1"

export type Bar = { t: number; o: number; h: number; l: number; c: number }
export type Swing = {
  i: number
  price: number
  kind: "HH" | "HL" | "LH" | "LL"
}
export type Specimen = {
  symbol: string
  bars: Array<Bar>
  last: number
  change24h: number // percent
  funding: number // percent per 8h
  openInterest: number // in BTC
  swings: Array<Swing>
  trend: "Higher highs" | "Lower lows" | "Range"
}

async function json<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal })
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.json() as Promise<T>
}

/** Swing highs and lows: a bar whose high (low) is the extreme of `k` bars on each side,
 *  labelled against the previous swing of the same side, as rinng's structure module reads them. */
export function swings(bars: Array<Bar>, k = 4): Array<Swing> {
  const out: Array<Swing> = []
  let lastHigh: number | null = null
  let lastLow: number | null = null
  for (let i = k; i < bars.length - k; i++) {
    const win = bars.slice(i - k, i + k + 1)
    if (bars[i].h === Math.max(...win.map((b) => b.h))) {
      out.push({
        i,
        price: bars[i].h,
        kind: lastHigh === null || bars[i].h > lastHigh ? "HH" : "LH",
      })
      lastHigh = bars[i].h
    } else if (bars[i].l === Math.min(...win.map((b) => b.l))) {
      out.push({
        i,
        price: bars[i].l,
        kind: lastLow === null || bars[i].l > lastLow ? "HL" : "LL",
      })
      lastLow = bars[i].l
    }
  }
  return out
}

function trendOf(s: Array<Swing>): Specimen["trend"] {
  const highs = s.filter((x) => x.kind === "HH" || x.kind === "LH").slice(-2)
  const lows = s.filter((x) => x.kind === "HL" || x.kind === "LL").slice(-2)
  const hh = highs.at(-1)?.kind === "HH"
  const hl = lows.at(-1)?.kind === "HL"
  if (hh && hl) return "Higher highs"
  if (!hh && !hl) return "Lower lows"
  return "Range"
}

export async function loadSpecimen(
  signal?: AbortSignal,
  symbol = "BTCUSDT"
): Promise<Specimen> {
  const [klines, ticker, premium, oi] = await Promise.all([
    json<Array<Array<string | number>>>(
      `${FAPI}/klines?symbol=${symbol}&interval=4h&limit=120`,
      signal
    ),
    json<{ priceChangePercent: string; lastPrice: string }>(
      `${FAPI}/ticker/24hr?symbol=${symbol}`,
      signal
    ),
    json<{ lastFundingRate: string }>(
      `${FAPI}/premiumIndex?symbol=${symbol}`,
      signal
    ),
    json<{ openInterest: string }>(
      `${FAPI}/openInterest?symbol=${symbol}`,
      signal
    ),
  ])
  const bars = klines.map((k) => ({
    t: +k[0],
    o: +k[1],
    h: +k[2],
    l: +k[3],
    c: +k[4],
  }))
  const s = swings(bars)
  return {
    symbol,
    bars,
    last: +ticker.lastPrice,
    change24h: +ticker.priceChangePercent,
    funding: +premium.lastFundingRate * 100,
    openInterest: +oi.openInterest,
    swings: s,
    trend: trendOf(s),
  }
}

export const fmtPrice = (n: number) =>
  n.toLocaleString("en-US", { maximumFractionDigits: n < 100 ? 3 : 1 })
export const fmtPct = (n: number, d = 2) =>
  `${n > 0 ? "+" : ""}${n.toFixed(d)}%`
export const fmtCompact = (n: number) =>
  n.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 })
