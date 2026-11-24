// TrustTrade research runs: JSON contract with src/rinng/web/trusttrade.py and the pure helpers
// the /trusttrade page uses. Days are calendar dates "YYYY-MM-DD" (blind runs mapped back).

export type Metric = {
  cr_pct: number
  mdd_pct: number
  sharpe: number | null // null when the strategy never held the coin
  avg_exposure_pct?: number
  trades?: number
  days?: number
  ar_pct?: number
  fees?: number
  buy_days?: number
  sell_days?: number
}
export type Metrics = Partial<Record<string, Metric>>

export type RunSummary = {
  name: string
  start: string
  end: string
  days: number
  symbols: Array<string>
  blind: boolean
  analyst_models: Array<string>
  trader_model: string | null
  n_agents: number | null
  allocation: string | null
  variants: Array<string>
  baselines: Array<string>
  cost_usd: number | null
  calls: number | null
  average: Metrics
}

export type Equity = {
  days: Array<string>
  series: Record<string, Array<number>>
}

export type Behaviour = {
  days: number
  buy: number
  sell: number
  hold: number
  hold_pct: number
  avg_confidence: number | null
  in_market_pct: number
}
export type Agreement = {
  days: number
  unanimous_pct: number
  split_pct: number
  stances: Record<string, number>
}
export type Usage = {
  calls: number
  cache_hits: number
  errors: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
}

export type RunDetail = {
  name: string
  config: {
    symbols: Array<string>
    start: string
    end: string
    blind: boolean
    analyst_models: Array<string>
    trader_model: string
    n_agents: number
    allocation: string
    fee_bps: number
    cash: number
    variants: Array<string>
    baselines: Array<string>
    domains: Array<string>
    params: Record<string, number>
  }
  average: Metrics
  per_symbol: Partial<Record<string, Metrics>>
  consensus: Record<
    string,
    {
      days: number
      leaked: number
      avg_kept_share: number
      avg_high_groups: number
    }
  >
  usage: { total?: Usage; by_role?: Record<string, Usage> }
  equity: Partial<Record<string, Equity>>
  behaviour: Partial<Record<string, Behaviour>>
  agreement: Partial<Record<string, Agreement>>
}

export type Action = "BUY" | "SELL" | "HOLD"
export type Decision = {
  symbol: string
  day: string
  label: string
  strategy: string
  price: number
  equity: number
  exposure: number
  action: Action
  pct: number
  confidence?: number
  rationale?: string
  key_evidence?: Array<string>
}
export type Polarity = "bullish" | "bearish" | "neutral"
export type Group = {
  claim: string
  subject: string
  polarity: Polarity
  agents: number
  support: number
  cohesion: number
  score: number
  high: boolean
  members: Array<string>
}
export type ConsensusDay = {
  symbol: string
  day: string
  domain: string
  n_agents: number
  kept_share: number
  high: Array<Group>
  low: Array<Group>
  leaked: Array<unknown>
}
export type Report = {
  symbol: string
  day: string
  domain: string
  agent: number
  summary: string
  stance: Polarity
  confidence: number
  claims: Array<{ subject: string; predicate: string; polarity: Polarity }>
}
export type DayDetail = {
  symbol: string
  day: string
  decisions: Array<Decision>
  consensus: Array<ConsensusDay>
  reports: Array<Report>
}

export const LLM_VARIANTS = [
  "single",
  "multi",
  "consensus",
  "consensus_temporal",
  "trusttrade",
] as const
export const BASELINES = [
  "buy_hold",
  "sma_cross",
  "macd",
  "kdj_rsi",
  "zmr",
  "temporal_rule",
] as const

export const isLLM = (s: string) =>
  (LLM_VARIANTS as ReadonlyArray<string>).includes(s)

type Style = {
  color: string
  width: 1 | 2 | 3
  dashed: boolean
  label: string
  note: string
}
export const STRATEGY: Record<string, Style> = {
  single: {
    color: "#94a3b8",
    width: 2,
    dashed: false,
    label: "single",
    note: "1 analyst",
  },
  multi: {
    color: "#60a5fa",
    width: 2,
    dashed: false,
    label: "multi",
    note: "3 analyst, tin đều",
  },
  consensus: {
    color: "#a78bfa",
    width: 2,
    dashed: false,
    label: "consensus",
    note: "+ lọc đồng thuận",
  },
  consensus_temporal: {
    color: "#f59e0b",
    width: 2,
    dashed: false,
    label: "consensus + temporal",
    note: "+ tín hiệu thời gian",
  },
  trusttrade: {
    color: "#10b981",
    width: 3,
    dashed: false,
    label: "trusttrade",
    note: "+ memory/reflection",
  },
  buy_hold: {
    color: "#e7e5e4",
    width: 2,
    dashed: true,
    label: "buy & hold",
    note: "baseline",
  },
  sma_cross: {
    color: "#78716c",
    width: 1,
    dashed: true,
    label: "SMA 10/30",
    note: "baseline",
  },
  macd: {
    color: "#a8a29e",
    width: 1,
    dashed: true,
    label: "MACD",
    note: "baseline",
  },
  kdj_rsi: {
    color: "#57534e",
    width: 1,
    dashed: true,
    label: "KDJ + RSI",
    note: "baseline",
  },
  zmr: {
    color: "#8b8580",
    width: 1,
    dashed: true,
    label: "Z mean-rev",
    note: "baseline",
  },
  temporal_rule: {
    color: "#f472b6",
    width: 1,
    dashed: true,
    label: "temporal rule",
    note: "baseline",
  },
}
export const style = (s: string): Style =>
  STRATEGY[s] ?? {
    color: "#a8a29e",
    width: 1,
    dashed: true,
    label: s,
    note: "",
  }

export const coin = (symbol: string) => symbol.split("-")[0]

/** Equal-weight portfolio across symbols: mean equity per day per strategy. Symbols must share
 *  the same days (one run window); a symbol with a different length is left out. */
export function averageEquity(curves: Array<Equity>): Equity {
  const ok = curves.filter((c) => c.days.length > 0)
  if (!ok.length) return { days: [], series: {} }
  const days = ok[0].days
  const same = ok.filter((c) => c.days.length === days.length)
  const names = Object.keys(same[0].series)
  const series: Record<string, Array<number>> = {}
  for (const n of names) {
    const rows = same.map((c) => c.series[n]).filter(Boolean)
    series[n] = days.map(
      (_, i) => rows.reduce((a, r) => a + r[i], 0) / rows.length
    )
  }
  return { days, series }
}

/** Equity → cumulative return in percent of `start`. */
export const toReturn = (equity: Array<number>, start: number) =>
  equity.map((v) => (100 * v) / start - 100)

export const mean = (xs: Array<number>) =>
  xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null

/** Cross-run grid: strategy → run name → metric, and the mean over runs that count. */
export function grid(
  runs: Array<RunSummary>,
  key: "cr_pct" | "mdd_pct",
  counts: (r: RunSummary) => boolean
) {
  const strategies = [...LLM_VARIANTS, ...BASELINES].filter((s) =>
    runs.some((r) => r.average[s] !== undefined)
  )
  return strategies.map((s) => {
    const cells = Object.fromEntries(
      runs.map((r) => [r.name, r.average[s]?.[key] ?? null])
    )
    const counted = runs
      .filter(counts)
      .map((r) => r.average[s]?.[key])
      .filter((v): v is number => v != null)
    return { strategy: s, cells, mean: mean(counted) }
  })
}

/** Background for a return cell: green/red with strength by size, capped at `cap` percent. */
export function heat(v: number | null, cap = 20) {
  if (v == null) return "transparent"
  const a = Math.min(1, Math.abs(v) / cap) * 0.55 + 0.05
  return v >= 0
    ? `rgba(16,185,129,${a.toFixed(3)})`
    : `rgba(239,83,80,${a.toFixed(3)})`
}

/** Short marker text for a decision: "B50", "S100". */
export const markText = (d: Pick<Decision, "action" | "pct">) =>
  d.action === "HOLD" ? "" : `${d.action[0]}${d.pct}`

const API = "/api/trusttrade/runs"
async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" })
  if (!r.ok) {
    let d = r.statusText
    try {
      d = (await r.json()).detail ?? d
    } catch {
      /* not JSON */
    }
    throw new Error(d)
  }
  return r.json() as Promise<T>
}
const q = (p: Record<string, string>) => new URLSearchParams(p).toString()

export const ttApi = {
  runs: () => get<Array<RunSummary>>(API),
  run: (name: string) => get<RunDetail>(`${API}/${encodeURIComponent(name)}`),
  decisions: (name: string, symbol: string, strategy: string) =>
    get<Array<Decision>>(
      `${API}/${encodeURIComponent(name)}/decisions?${q({ symbol, strategy })}`
    ),
  day: (name: string, symbol: string, day: string) =>
    get<DayDetail>(
      `${API}/${encodeURIComponent(name)}/day?${q({ symbol, day })}`
    ),
}
