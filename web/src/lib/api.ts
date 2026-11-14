// Hợp đồng JSON với backend FastAPI (src/rinng/web/lenses.py, summary.py).
// Thời gian là giây UTC.

export type Marker = {
  time: number
  position: "aboveBar" | "belowBar"
  shape: "circle" | "square" | "arrowUp" | "arrowDown"
  color: string
  text: string
}
export type Zone = {
  t0: number | null
  t1: number | null
  p0: number
  p1: number
  color: string
  label?: string
  style?: "solid" | "dash" | "light" | "faint"
}
export type Level = {
  t0: number | null
  t1: number | null
  price: number
  color: string
  label?: string
  dash?: boolean
}
export type Line = {
  name: string
  color: string
  pane: number
  data: Array<{ time: number; value: number }>
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
}

export type Meta = {
  instruments: Array<string>
  exchanges: Array<string>
  timeframes: Array<string>
  lenses: Record<string, string>
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

async function get<T>(path: string, params: Record<string, string | number>): Promise<T> {
  const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
  const r = await fetch(`${path}?${q}`)
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* body không phải JSON */
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
    symbol: string
    exchange: string
  }) => get<ChartData>("/api/chart", p),
  summary: (p: { symbol: string; exchange: string }) => get<Summary>("/api/summary", p),
}
