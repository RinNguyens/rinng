// Workspace = one tab holding several slots arranged by a layout; each slot holds a chart with
// its own lens, or stays empty until a chart is dropped in. Saved in the browser's localStorage.
import { useCallback, useEffect, useState } from "react"
import { COMBOS, comboWorkspace } from "./combos"

export type PanelCfg = {
  id: string
  lens: string
  tf: string
  days: number
  period: "week" | "day"
  zigzag?: string // zigzag reversal % for the Wyckoff / Elliott lens; "auto" (default) by timeframe
}

export type LayoutKey = "1" | "2" | "2v" | "1+2" | "1|2" | "3" | "2x2" | "1+3" | "3x2"

export type Workspace = {
  id: string
  name: string
  layout: LayoutKey
  slots: Array<PanelCfg | null>
  guide?: string // combo id when the tab was built from a chart combo (shows its reading guide)
  sync?: boolean // crosshair/time sync across the tab's charts (default on)
}

export const LAYOUTS: Record<
  LayoutKey,
  { label: string; cols: string; rows: string; areas: Array<string>; n: number }
> = {
  "1": { label: "Single", cols: "1fr", rows: "1fr", areas: ["s0"], n: 1 },
  "2": { label: "2 columns", cols: "1fr 1fr", rows: "1fr", areas: ["s0 s1"], n: 2 },
  "2v": { label: "2 rows", cols: "1fr", rows: "1fr 1fr", areas: ["s0", "s1"], n: 2 },
  "1+2": {
    label: "1 large + 2",
    cols: "3fr 2fr",
    rows: "1fr 1fr",
    areas: ["s0 s1", "s0 s2"],
    n: 3,
  },
  "1|2": {
    label: "1 + 2 halves",
    cols: "1fr 1fr",
    rows: "1fr 1fr",
    areas: ["s0 s1", "s0 s2"],
    n: 3,
  },
  "3": { label: "3 columns", cols: "1fr 1fr 1fr", rows: "1fr", areas: ["s0 s1 s2"], n: 3 },
  "2x2": { label: "2×2", cols: "1fr 1fr", rows: "1fr 1fr", areas: ["s0 s1", "s2 s3"], n: 4 },
  "1+3": {
    label: "1 top + 3",
    cols: "1fr 1fr 1fr",
    rows: "3fr 2fr",
    areas: ["s0 s0 s0", "s1 s2 s3"],
    n: 4,
  },
  "3x2": {
    label: "3×2",
    cols: "1fr 1fr 1fr",
    rows: "1fr 1fr",
    areas: ["s0 s1 s2", "s3 s4 s5"],
    n: 6,
  },
}

export const DAYS = [14, 30, 90, 180, 365, 1000, 2000]

// Chart presets to drag from the library into a slot.
export type Preset = Omit<PanelCfg, "id"> & { title: string; hint: string }
export const PRESETS: Array<Preset> = [
  {
    title: "SMC structure",
    hint: "Swing, BOS/CHoCH, OB, FVG, premium/discount",
    lens: "structure",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Liquidity",
    hint: "BSL/SSL, EQH/EQL, sweep",
    lens: "liquidity",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Weekly volume profile",
    hint: "Buy/sell profile, POC, D/P/b/DD, naked POC",
    lens: "profile",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Weekly volume profile (1D)",
    hint: "One profile per week on 1D candles",
    lens: "profile",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Wyckoff / Elliott",
    hint: "SC/BC, spring/UT, trading range, zigzag",
    lens: "wyckoff",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Derivatives & CVD",
    hint: "Funding, OI, long/short, CVD",
    lens: "derivatives",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Projection",
    hint: "Probability cone, median path, touch odds for key levels",
    lens: "forecast",
    tf: "1d",
    days: 365,
    period: "week",
  },
  {
    title: "Indicators",
    hint: "EMA 21/50/200, RSI, MACD, delta",
    lens: "indicators",
    tf: "1d",
    days: 365,
    period: "week",
  },
]

let counter = 0
export function newId() {
  counter += 1
  return `${Date.now().toString(36)}${counter}${Math.random().toString(36).slice(2, 6)}`
}

export function fromPreset(p: Preset): PanelCfg {
  return { id: newId(), lens: p.lens, tf: p.tf, days: p.days, period: p.period }
}

const P = (i: number) => fromPreset(PRESETS[i])

function defaults(): Array<Workspace> {
  return [
    {
      id: newId(),
      name: "Overview",
      layout: "2x2",
      slots: [P(0), P(2), P(1), P(5)],
    },
    ...["top-down", "value-liquidity", "risk-map"].map((id) =>
      comboWorkspace(COMBOS.find((x) => x.id === id)!),
    ),
  ]
}

const KEY = "rinng.workspaces.v3"
// v2 tabs are carried over once with every chart reset to the 1D / 365-day default.
const OLD_KEY = "rinng.workspaces.v2"
const OLD_OVERVIEW = "T\u1ed5ng quan"

function toDaily(ws: Array<Workspace>): Array<Workspace> {
  return ws.map((w) => ({
    ...w,
    slots: w.slots.map((s) => (s ? { ...s, tf: "1d", days: 365, period: "week" } : s)),
  }))
}

function load(): Array<Workspace> | null {
  try {
    let raw = localStorage.getItem(KEY)
    let migrate = false
    if (!raw) {
      raw = localStorage.getItem(OLD_KEY)
      migrate = true
    }
    if (!raw) return null
    const parsed = JSON.parse(raw) as Array<Workspace>
    const ws = migrate && Array.isArray(parsed) ? toDaily(parsed) : parsed
    if (!Array.isArray(ws) || !ws.length) return null
    // Tabs saved before the UI switched to English keep their old default name.
    return ws.map((w) => (w.name === OLD_OVERVIEW ? { ...w, name: "Overview" } : w))
  } catch {
    return null
  }
}

function fit(ws: Workspace): Workspace {
  const n = LAYOUTS[ws.layout].n
  const slots = ws.slots.slice(0, Math.max(n, ws.slots.length))
  while (slots.length < n) slots.push(null)
  return { ...ws, slots }
}

const NAME_MAX = 32

// Trimmed and capped new tab name; a blank name keeps the old one.
export function tabName(next: string, old: string): string {
  const name = next.trim().slice(0, NAME_MAX)
  return name || old
}

// Copy of a tab inserted right after it, with fresh ids; null when the id is unknown.
export function duplicateAfter(
  all: Array<Workspace>,
  id: string,
): { next: Array<Workspace>; id: string } | null {
  const i = all.findIndex((w) => w.id === id)
  if (i < 0) return null
  const src = all[i]
  const copy: Workspace = {
    ...src,
    id: newId(),
    name: `${src.name} copy`.slice(0, NAME_MAX),
    slots: src.slots.map((s) => (s ? { ...s, id: newId() } : null)),
  }
  return { next: [...all.slice(0, i + 1), copy, ...all.slice(i + 1)], id: copy.id }
}

// Tab to open after closing `closing`: a neighbour when it is the active tab, else null.
export function closeTarget(ids: Array<string>, closing: string, active: string): string | null {
  const i = ids.indexOf(closing)
  if (i < 0 || closing !== active || ids.length < 2) return null
  return ids[i + 1] ?? ids[i - 1]
}

// Tab a navigation key lands on (wraps around), or null for other keys.
export function tabKey(ids: Array<string>, current: string, key: string): string | null {
  if (!ids.length) return null
  const i = ids.indexOf(current)
  if (key === "Home") return ids[0]
  if (key === "End") return ids[ids.length - 1]
  if (key === "ArrowRight") return ids[(i + 1) % ids.length]
  if (key === "ArrowLeft") return ids[(i - 1 + ids.length) % ids.length]
  return null
}

export function useWorkspaces() {
  const [workspaces, setAll] = useState<Array<Workspace>>([])

  useEffect(() => {
    setAll(load() ?? defaults())
  }, [])

  const set = useCallback((next: Array<Workspace>) => {
    setAll(next)
    try {
      localStorage.setItem(KEY, JSON.stringify(next))
    } catch {
      /* storage blocked by the browser: keep for this session only */
    }
  }, [])

  const update = useCallback(
    (id: string, fn: (w: Workspace) => Workspace) =>
      setAll((all) => {
        const next = all.map((w) => (w.id === id ? fit(fn(w)) : w))
        try {
          localStorage.setItem(KEY, JSON.stringify(next))
        } catch {
          /* ignore */
        }
        return next
      }),
    [],
  )

  return {
    workspaces,
    update,
    insert: (w: Workspace) => {
      set([...workspaces, w])
      return w.id
    },
    add: () => {
      const w: Workspace = {
        id: newId(),
        name: `Tab ${workspaces.length + 1}`,
        layout: "2",
        slots: [null, null],
      }
      set([...workspaces, w])
      return w.id
    },
    rename: (id: string, name: string) =>
      update(id, (w) => ({ ...w, name: tabName(name, w.name) })),
    duplicate: (id: string) => {
      const out = duplicateAfter(workspaces, id)
      if (!out) return null
      set(out.next)
      return out.id
    },
    remove: (id: string) => set(workspaces.filter((w) => w.id !== id)),
    reset: () => {
      const d = defaults()
      set(d)
      return d[0].id
    },
  }
}

// Swap two slots (drag a chart from one slot to another).
export function swapSlots(w: Workspace, a: number, b: number): Workspace {
  const slots = [...w.slots]
  ;[slots[a], slots[b]] = [slots[b], slots[a]]
  return { ...w, slots }
}

export function setSlot(w: Workspace, i: number, cfg: PanelCfg | null): Workspace {
  const slots = [...w.slots]
  slots[i] = cfg
  return { ...w, slots }
}
