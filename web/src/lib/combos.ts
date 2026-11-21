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

const c = (
  lens: string,
  tf: string,
  days: number,
  period: "week" | "day" = "week"
): Chart => ({
  lens,
  tf,
  days,
  period,
})

export const COMBOS: Array<Combo> = [
  {
    id: "rin",
    title: "rin",
    question:
      "Structure on the left; value and Wyckoff/Elliott phase on the right.",
    layout: "1|2",
    charts: [
      c("structure", "1d", 365),
      c("profile", "1d", 365),
      c("wyckoff", "1d", 365),
    ],
    steps: [
      "SMC structure: trend, last BOS/CHoCH and the major-swing Fibonacci (0.618 golden pocket).",
      "Volume profile: is the 0.618 level backed by a POC or value-area edge?",
      "Wyckoff / Elliott: which phase or wave price is in, and whether a pullback to 0.618 fits it.",
    ],
  },
  {
    id: "top-down",
    title: "Top-down structure",
    question:
      "Which way is the higher-timeframe trend, and where is price inside it?",
    layout: "1+2",
    charts: [
      c("structure", "1d", 365),
      c("structure", "1d", 365),
      c("liquidity", "1d", 365),
    ],
    steps: [
      "1D: read the trend (HH/HL or LH/LL) and whether price sits in premium or discount.",
      "Check the last BOS/CHoCH; a lower-timeframe CHoCH against it is only a pullback until 1D breaks too.",
      "Liquidity: find the nearest BSL/SSL; with-trend moves usually run the liquidity on the far side first.",
    ],
  },
  {
    id: "value-liquidity",
    title: "Value vs. liquidity",
    question:
      "Where has the market accepted price, and where are the stops resting?",
    layout: "2",
    charts: [c("profile", "1d", 365), c("liquidity", "1d", 365)],
    steps: [
      "Profile: POC and value area show accepted prices; D = balance, P/b = one-sided, DD = value moved.",
      "Liquidity: BSL/SSL outside value are the likely targets of a move out of balance.",
      "Naked POCs and untouched equal highs/lows act as magnets; both charts share the 1D time axis.",
    ],
  },
  {
    id: "trend-health",
    title: "Trend health",
    question: "Is the move backed by momentum, volume and positioning?",
    layout: "1+2",
    charts: [
      c("structure", "1d", 365),
      c("indicators", "1d", 365),
      c("derivatives", "1d", 365),
    ],
    steps: [
      "Structure: confirm the trend and the last break.",
      "Indicators: price vs. EMA 21/50/200, RSI divergence and MACD fading against new highs/lows.",
      "Derivatives: rising OI with price = new positions; CVD diverging from price = weak follow-through.",
    ],
  },
  {
    id: "positioning",
    title: "Positioning & squeeze risk",
    question:
      "Is leverage crowded on one side, and where would a squeeze run to?",
    layout: "1+2",
    charts: [
      c("derivatives", "1d", 365),
      c("liquidity", "1d", 365),
      c("profile", "1d", 365),
    ],
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
    charts: [
      c("wyckoff", "1d", 365),
      c("profile", "1d", 365),
      c("wyckoff", "1d", 365),
    ],
    steps: [
      "1D Wyckoff: SC/BC and trading ranges mark where the phase changed.",
      "Weekly profile: value building inside a range supports accumulation/distribution.",
      "Wyckoff: spring or upthrust at the range edge is the trigger to watch.",
    ],
  },
  {
    id: "risk-map",
    title: "Risk map",
    question:
      "How far can price reasonably travel, and which levels are in reach?",
    layout: "1+2",
    charts: [
      c("forecast", "1d", 365),
      c("liquidity", "1d", 365),
      c("profile", "1d", 365),
    ],
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
      c("profile", "1d", 365),
      c("liquidity", "1d", 365),
      c("indicators", "1d", 365),
      c("forecast", "1d", 365),
    ],
    steps: [
      "Daily profile: yesterday's POC/VA are today's reference levels.",
      "Liquidity and indicators: sweeps of local highs/lows with RSI divergence mark exhaustion.",
      "Projection: keep plans inside the 80% band.",
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

export const comboById = (id: string | undefined) =>
  COMBOS.find((x) => x.id === id)
