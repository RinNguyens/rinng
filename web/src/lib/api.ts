// JSON contract with the FastAPI backend (src/rinng/web/lenses.py, summary.py).
// Times are UTC seconds.

export type Marker = {
  time: number
  position: "aboveBar" | "belowBar"
  shape: "circle" | "square" | "arrowUp" | "arrowDown"
  color: string
  text: string
  layer?: string
}
export type Zone = {
  t0: number | null
  t1: number | null
  p0: number
  p1: number
  color: string
  label?: string
  style?: "solid" | "dash" | "light" | "faint"
  layer?: string
}
export type Level = {
  t0: number | null
  t1: number | null
  price: number
  color: string
  label?: string
  dash?: boolean
  layer?: string
}
export type Line = {
  name: string
  color: string
  pane: number
  data: Array<{ time: number; value: number }>
  layer?: string
}
export type Histo = {
  name: string
  pane: number
  precision?: number
  data: Array<{ time: number; value: number; color: string }>
}
export type Profile = {
  t0: number
  t1: number
  closed: boolean
  shape: "D" | "P" | "b" | "DD"
  poc: number
  val: number
  vah: number
  buy: number
  sell: number
  rows: Array<[number, number, number, number]>
  layer?: string
}
export type Candle = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  buy: number
}

export type ForecastLevel = { label: string; price: number; color: string; probability: number }
export type Projection = {
  times: Array<number>
  bands: Record<"q05" | "q10" | "q25" | "q50" | "q75" | "q90" | "q95", Array<number>>
  horizon: number
  close: number
  analogs: number
  pool: number
  end: Record<string, number>
  levels: Array<ForecastLevel>
}
export type ProjectionStats = {
  origins: number
  coverage: Record<"50" | "80" | "90", number>
  pinball: number
  pinball_baseline: number
  skill: number
  direction_hit: number | null
  brier: number
  brier_baseline: number
}

export type ChartData = {
  candles: Array<Candle>
  source: "curated" | "live"
  markers?: Array<Marker>
  zones?: Array<Zone>
  levels?: Array<Level>
  lines?: Array<Line>
  histos?: Array<Histo>
  guides?: Array<{ pane: number; values: Array<number> }>
  profiles?: Array<Profile>
  legend?: Array<[string, string]>
  forecast?: Projection
  stats?: ProjectionStats | null
}

// Live desk (src/rinng/web/desk.py): the 5m chart with every overlay tagged by layer, plus the
// rule-based agents' votes and one long / one short setup.
export type AgentVote = {
  id: string
  name: string
  score: number // -1 (sell) … +1 (buy)
  confidence: number // 0 … 1
  stance: "buy" | "sell" | "wait"
  reasons: Array<string>
}
export type Verdict = {
  score: number
  lean: "long" | "short" | "none"
  buy: number
  sell: number
  wait: number
  total: number
}
export type Scenario = {
  side: "long" | "short"
  zone: [number, number]
  zone_label: string
  entry: number
  stop: number
  target: number
  target_label: string
  rr: number | null
  trigger: string
  favor: number
  aligned: boolean
  p_entry: number | null
  p_target: number | null
  p_stop: number | null
}
export type Desk = ChartData & {
  tf: string
  layers: Array<string>
  atr: number
  agents: Array<AgentVote>
  verdict: Verdict
  scenarios: Array<Scenario>
}

export type Instrument = {
  id: string
  kind: "perp" | "spot"
  base: string
  quote: string | null
  name: string
  icon?: string // base without Binance's 1000x multiplier (1000PEPE → PEPE)
  binance?: boolean
  okx?: boolean
  configured?: boolean // in the default watchlist (stored history + live data)
}

export type Meta = {
  instruments: Array<Instrument>
  exchanges: Array<string>
  timeframes: Array<string>
  lenses: Record<string, string>
  live: boolean
}

type Pct = number | null
export type Summary = {
  symbol: string
  exchange: string
  price: {
    close: number
    time: number
    chg_24h: Pct
    chg_7d: Pct
    high_24h: number
    low_24h: number
    spark: Array<number>
    delta_24h: number
    volume_24h: number
  }
  derivatives: {
    funding: { rate_pct: number; annual_pct: number; avg_7d_pct: number; time: number } | null
    oi: { base: number; value: number | null; chg_24h: Pct; chg_7d: Pct; time: number } | null
    ls: { ratio: number; long_pct: number; time: number } | null
  }
  structure: {
    trend: "up" | "down" | null
    last_break: { kind: "BOS" | "CHoCH"; price: number; time: number } | null
    zone: "premium" | "discount" | null
    range_high: number | null
    range_low: number | null
    equilibrium: number | null
    active_ob: { bull: number; bear: number }
  }
  profile: {
    current: WeekProfile | null
    previous: WeekProfile | null
    price_vs_prev_va: "above" | "inside" | "below" | null
  }
  liquidity: {
    bsl: number | null
    bsl_dist_pct: Pct
    ssl: number | null
    ssl_dist_pct: Pct
    last_sweep: { kind: "BSL" | "SSL"; time: number } | null
  }
  wyckoff: {
    last_event: { kind: string; time: number } | null
    in_range: { high: number; low: number; since: number } | null
  }
  momentum: {
    rsi: number | null
    macd_hist: number | null
    above_ema: Array<string>
    ema: Record<string, number | null>
  }
}
export type WeekProfile = {
  start: number
  shape: "D" | "P" | "b" | "DD"
  poc: number
  vah: number
  val: number
  delta: number
}

export type NewsItem = {
  id: string
  source: string
  kind: "exchange" | "media"
  title: string
  url: string
  time: number
  score: number
  sentiment: "bullish" | "bearish" | "neutral"
  impact: 1 | 2 | 3
  tags: Array<string>
  coins: Array<string>
}
export type NewsOutlook = { score: number; label: "bullish" | "bearish" | "neutral"; count: number; base?: string }
export type News = {
  updated: number
  items: Array<NewsItem>
  market: NewsOutlook
  coin: NewsOutlook | null
  coin_items: Array<NewsItem>
}

async function get<T>(path: string, params: Record<string, string | number>): Promise<T> {
  const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
  const r = await fetch(`${path}?${q}`)
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* body is not JSON */
    }
    throw new Error(detail)
  }
  return r.json() as Promise<T>
}

export const api = {
  meta: () => get<Meta>("/api/meta", {}),
  chart: (p: {
    lens: string
    tf: string
    days: number
    period: string
    zigzag: string
    symbol: string
    exchange: string
  }) => get<ChartData>("/api/chart", p),
  summary: (p: { symbol: string; exchange: string }) => get<Summary>("/api/summary", p),
  desk: (p: { symbol: string; exchange: string }) => get<Desk>("/api/desk", p),
  news: (base: string) => get<News>("/api/news", { base, limit: 80 }),
  instruments: (q: string) => get<Array<Instrument>>("/api/instruments", { q, limit: 30 }),
  instrument: (symbol: string) => get<Instrument>("/api/instrument", { symbol }),
}
