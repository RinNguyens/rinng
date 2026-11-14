// Chart combos: sets of charts that answer one analysis question together, with a reading
// order. Charts on the same timeframe share crosshair and time range, so most combos keep a
// common timeframe and add one higher-timeframe chart for context.
import { newId } from "./workspaces"
import type { LayoutKey, PanelCfg, Workspace } from "./workspaces"

type Chart = Omit<PanelCfg, "id">

export type Combo = {
  id: string
  title: string
  question: string
  layout: LayoutKey
  charts: Array<Chart>
  steps: Array<string>
}

const c = (lens: string, tf: string, days: number, period: "week" | "day" = "week"): Chart => ({
  lens,
  tf,
  days,
  period,
})

export const COMBOS: Array<Combo> = [
  {
    id: "top-down",
    title: "Top-down structure",
    question: "Which way is the higher-timeframe trend, and where is price inside it?",
    layout: "1+2",
    charts: [c("structure", "1d", 365), c("structure", "4h", 90), c("liquidity", "1h", 30)],
    steps: [
      "1D: read the trend (HH/HL or LH/LL) and whether price sits in premium or discount.",
      "4H: check the last BOS/CHoCH agrees with 1D; a 4H CHoCH against 1D is only a pullback until 1D breaks too.",
      "1H: find the nearest BSL/SSL; with-trend moves usually run the liquidity on the far side first.",
    ],
  },
  {
    id: "value-liquidity",
    title: "Value vs. liquidity",
    question: "Where has the market accepted price, and where are the stops resting?",
    layout: "2",
    charts: [c("profile", "4h", 90), c("liquidity", "4h", 90)],
    steps: [
      "Profile: POC and value area show accepted prices; D = balance, P/b = one-sided, DD = value moved.",
      "Liquidity: BSL/SSL outside value are the likely targets of a move out of balance.",
      "Naked POCs and untouched equal highs/lows act as magnets; both charts share the 4H time axis.",
    ],
  },
  {
    id: "trend-health",
    title: "Trend health",
    question: "Is the move backed by momentum, volume and positioning?",
    layout: "1+2",
    charts: [c("structure", "4h", 180), c("indicators", "4h", 180), c("derivatives", "4h", 180)],
    steps: [
      "Structure: confirm the trend and the last break.",
      "Indicators: price vs. EMA 21/50/200, RSI divergence and MACD fading against new highs/lows.",
      "Derivatives: rising OI with price = new positions; CVD diverging from price = weak follow-through.",
    ],
  },
  {
    id: "positioning",
    title: "Positioning & squeeze risk",
    question: "Is leverage crowded on one side, and where would a squeeze run to?",
    layout: "1+2",
    charts: [c("derivatives", "1h", 30), c("liquidity", "1h", 30), c("profile", "1h", 14, "day")],
    steps: [
      "Derivatives: high funding + rising OI + skewed long/short = crowded side.",
      "Liquidity: the crowded side's stops sit beyond the nearest BSL/SSL; that is where a squeeze ends.",
      "Daily profile: P/b days and delta show who was aggressive during the build-up.",
    ],
  },
  {
    id: "cycle",
    title: "Market cycle",
    question: "Accumulation, markup, distribution or markdown?",
    layout: "1+2",
    charts: [c("wyckoff", "1d", 1000), c("profile", "1d", 365), c("wyckoff", "4h", 180)],
    steps: [
      "1D Wyckoff: SC/BC and trading ranges mark where the phase changed.",
      "Weekly profile: value building inside a range supports accumulation/distribution.",
      "4H Wyckoff: spring or upthrust at the range edge is the trigger to watch.",
    ],
  },
  {
    id: "risk-map",
    title: "Risk map",
    question: "How far can price reasonably travel, and which levels are in reach?",
    layout: "1+2",
    charts: [c("forecast", "4h", 90), c("liquidity", "4h", 90), c("profile", "4h", 90)],
    steps: [
      "Projection: the 80% band is a realistic range for the next 7 days; it does not call direction.",
      "Liquidity and profile: levels inside the band are in reach; the touch odds are printed on the projection.",
      "Levels outside the 90% band need a regime change (news, breakout) to be reached.",
    ],
  },
  {
    id: "intraday",
    title: "Intraday plan",
    question: "What matters for the next 12–48 hours?",
    layout: "2x2",
    charts: [
      c("profile", "1h", 14, "day"),
      c("liquidity", "15m", 14),
      c("indicators", "15m", 14),
      c("forecast", "1h", 14),
    ],
    steps: [
      "Daily profile: yesterday's POC/VA are today's reference levels.",
      "15m liquidity and indicators: sweeps of local highs/lows with RSI divergence mark exhaustion.",
      "1H projection: keep plans inside the 80% band for the next 2 days.",
    ],
  },
]

export function comboWorkspace(combo: Combo): Workspace {
  return {
    id: newId(),
    name: combo.title,
    layout: combo.layout,
    slots: combo.charts.map((ch) => ({ ...ch, id: newId() })),
    guide: combo.id,
  }
}

// Apply a combo to an existing tab (keeps the tab, replaces its layout and charts).
export function applyCombo(w: Workspace, combo: Combo): Workspace {
  return {
    ...w,
    name: combo.title,
    layout: combo.layout,
    slots: combo.charts.map((ch) => ({ ...ch, id: newId() })),
    guide: combo.id,
  }
}

export const comboById = (id: string | undefined) => COMBOS.find((x) => x.id === id)
