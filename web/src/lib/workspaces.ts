// Workspace = một tab gồm nhiều khung (slot) xếp theo một bố cục; mỗi khung chứa một chart
// với lens riêng, hoặc để trống chờ kéo chart vào. Lưu trong localStorage của trình duyệt.
import { useCallback, useEffect, useState } from "react"

export type PanelCfg = {
  id: string
  lens: string
  tf: string
  days: number
  period: "week" | "day"
}

export type LayoutKey = "1" | "2" | "2v" | "1+2" | "3" | "2x2" | "1+3" | "3x2"

export type Workspace = {
  id: string
  name: string
  layout: LayoutKey
  slots: Array<PanelCfg | null>
}

export const LAYOUTS: Record<
  LayoutKey,
  { label: string; cols: string; rows: string; areas: Array<string>; n: number }
> = {
  "1": { label: "1 khung", cols: "1fr", rows: "1fr", areas: ["s0"], n: 1 },
  "2": { label: "2 cột", cols: "1fr 1fr", rows: "1fr", areas: ["s0 s1"], n: 2 },
  "2v": { label: "2 hàng", cols: "1fr", rows: "1fr 1fr", areas: ["s0", "s1"], n: 2 },
  "1+2": {
    label: "1 lớn + 2",
    cols: "3fr 2fr",
    rows: "1fr 1fr",
    areas: ["s0 s1", "s0 s2"],
    n: 3,
  },
  "3": { label: "3 cột", cols: "1fr 1fr 1fr", rows: "1fr", areas: ["s0 s1 s2"], n: 3 },
  "2x2": { label: "2×2", cols: "1fr 1fr", rows: "1fr 1fr", areas: ["s0 s1", "s2 s3"], n: 4 },
  "1+3": {
    label: "1 trên + 3",
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

// Mẫu chart để kéo từ thư viện vào khung.
export type Preset = Omit<PanelCfg, "id"> & { title: string; hint: string }
export const PRESETS: Array<Preset> = [
  {
    title: "Cấu trúc SMC",
    hint: "Swing, BOS/CHoCH, OB, FVG, premium/discount",
    lens: "structure",
    tf: "4h",
    days: 90,
    period: "week",
  },
  {
    title: "Thanh khoản",
    hint: "BSL/SSL, EQH/EQL, sweep",
    lens: "liquidity",
    tf: "1h",
    days: 30,
    period: "week",
  },
  {
    title: "Volume profile tuần",
    hint: "Profile mua/bán, POC, D/P/b/DD, naked POC",
    lens: "profile",
    tf: "4h",
    days: 90,
    period: "week",
  },
  {
    title: "Volume profile ngày",
    hint: "Profile từng ngày trên khung 1h",
    lens: "profile",
    tf: "1h",
    days: 14,
    period: "day",
  },
  {
    title: "Wyckoff / Elliott",
    hint: "SC/BC, spring/UT, trading range, zigzag",
    lens: "wyckoff",
    tf: "1d",
    days: 1000,
    period: "week",
  },
  {
    title: "Phái sinh & CVD",
    hint: "Funding, OI, long/short, CVD",
    lens: "derivatives",
    tf: "1h",
    days: 30,
    period: "week",
  },
  {
    title: "Indicator",
    hint: "EMA 21/50/200, RSI, MACD, delta",
    lens: "indicators",
    tf: "4h",
    days: 180,
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
      name: "Tổng quan",
      layout: "2x2",
      slots: [P(0), P(2), P(1), P(5)],
    },
    { id: newId(), name: "Volume profile", layout: "2", slots: [P(2), P(3)] },
    {
      id: newId(),
      name: "Wyckoff / Elliott",
      layout: "1+2",
      slots: [P(4), { ...P(4), tf: "4h", days: 180 }, P(6)],
    },
  ]
}

const KEY = "rinng.workspaces.v2"

function load(): Array<Workspace> | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const ws = JSON.parse(raw) as Array<Workspace>
    return Array.isArray(ws) && ws.length ? ws : null
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
      /* trình duyệt chặn bộ nhớ: chỉ giữ trong phiên */
    }
  }, [])

  const update = useCallback(
    (id: string, fn: (w: Workspace) => Workspace) =>
      setAll((all) => {
        const next = all.map((w) => (w.id === id ? fit(fn(w)) : w))
        try {
          localStorage.setItem(KEY, JSON.stringify(next))
        } catch {
          /* bỏ qua */
        }
        return next
      }),
    [],
  )

  return {
    workspaces,
    update,
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
    remove: (id: string) => set(workspaces.filter((w) => w.id !== id)),
    reset: () => {
      const d = defaults()
      set(d)
      return d[0].id
    },
  }
}

// Đổi chỗ hai khung (kéo chart từ khung này sang khung khác).
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
