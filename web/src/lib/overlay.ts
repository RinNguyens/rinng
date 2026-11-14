// Primitive vẽ lớp phủ rinng lên series nến (Lightweight Charts 5 plugin API):
// vùng (zones), mức ngang (levels) và volume profile theo kỳ (profiles).
// Thời gian tùy ý (không trùng mốc nến) đổi sang chỉ số logical có phần lẻ rồi sang pixel.
import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  Logical,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts"
import type { ChartData, Level, Profile, Zone } from "./api"

// Phần của CanvasRenderingTarget2D (gói fancy-canvas) mà overlay dùng.
type CanvasRenderingTarget2D = {
  useMediaCoordinateSpace: <T>(
    f: (s: { context: CanvasRenderingContext2D; mediaSize: { width: number; height: number } }) => T,
  ) => T
}

const BUY = "38,166,154"
const SELL = "239,83,80"
const POC = "255,152,0"
const SHAPE_COLORS: Record<string, string> = {
  D: "#90a4ae",
  P: "#26a69a",
  b: "#ef5350",
  DD: "#ab47bc",
}

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

export function fmtVol(v: number, sign = true) {
  const a = Math.abs(v)
  const s =
    a >= 1e9
      ? (a / 1e9).toFixed(2) + "B"
      : a >= 1e6
        ? (a / 1e6).toFixed(1) + "M"
        : a >= 1e3
          ? (a / 1e3).toFixed(1) + "k"
          : a.toFixed(0)
  if (!sign) return s
  return (v >= 0 ? "+" : "−") + s
}

type Ctx = CanvasRenderingContext2D

export class RinngOverlay implements ISeriesPrimitive<Time> {
  private zones: Array<Zone> = []
  private levels: Array<Level> = []
  private profiles: Array<Profile> = []
  private chart: IChartApi | null = null
  private series: ISeriesApi<SeriesType> | null = null
  private request: (() => void) | null = null
  private readonly views: Array<IPrimitivePaneView>

  constructor(private readonly times: Array<number>) {
    const bg: IPrimitivePaneRenderer = {
      draw: () => {},
      drawBackground: (t) => this.drawBg(t),
    }
    const top: IPrimitivePaneRenderer = {
      draw: (t) => this.drawTop(t),
    }
    this.views = [
      { zOrder: () => "bottom", renderer: () => bg },
      { zOrder: () => "top", renderer: () => top },
    ]
  }

  set(data: ChartData) {
    this.zones = data.zones ?? []
    this.levels = data.levels ?? []
    this.profiles = data.profiles ?? []
    this.request?.()
  }

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>) {
    this.chart = chart
    this.series = series
    this.request = requestUpdate
  }

  detached() {
    this.chart = this.series = this.request = null
  }

  paneViews() {
    return this.views
  }

  // Thời gian → chỉ số logical (nội suy giữa hai mốc nến; ngoại suy sau nến cuối).
  private logical(t: number): number | null {
    const ts = this.times
    const n = ts.length
    if (!n) return null
    if (t <= ts[0]) return 0
    if (t >= ts[n - 1]) {
      const step = n > 1 ? ts[n - 1] - ts[n - 2] : 1
      return n - 1 + (t - ts[n - 1]) / step
    }
    let lo = 0
    let hi = n - 1
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (ts[mid] <= t) lo = mid
      else hi = mid
    }
    return lo + (t - ts[lo]) / (ts[hi] - ts[lo])
  }

  private x(t: number | null, fallback: number): number
  private x(t: number | null, fallback: null): number | null
  private x(t: number | null, fallback: number | null) {
    if (t == null || !this.chart) return fallback
    const l = this.logical(t)
    const x = l == null ? null : this.chart.timeScale().logicalToCoordinate(l as Logical)
    return x == null ? fallback : (x as number)
  }

  private y(p: number) {
    return this.series?.priceToCoordinate(p) ?? null
  }

  private drawBg(target: CanvasRenderingTarget2D) {
    if (!this.chart) return
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const right = mediaSize.width
      for (const z of this.zones) {
        const x0 = this.x(z.t0, 0)
        const x1 = this.x(z.t1, right)
        const y0 = this.y(z.p1)
        const y1 = this.y(z.p0)
        if (y0 == null || y1 == null || x1 < 0 || x0 > right) continue
        const a = z.style === "faint" ? 0.035 : z.style === "light" ? 0.13 : 0.2
        ctx.fillStyle = hexA(z.color, z.t1 ? a * 0.5 : a)
        ctx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0))
        if (z.style === "dash" || z.style === "solid") {
          ctx.strokeStyle = hexA(z.color, z.t1 ? 0.3 : 0.6)
          ctx.setLineDash(z.style === "dash" ? [4, 3] : [])
          ctx.strokeRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0))
          ctx.setLineDash([])
        }
        if (z.label && x1 - x0 > 24 && y1 - y0 > 9) {
          ctx.fillStyle = hexA(z.color, 0.8)
          ctx.font = "10px 'Geist Mono Variable', monospace"
          ctx.fillText(z.label, x0 + 3, y0 + 10)
        }
      }
      for (const p of this.profiles) this.drawProfile(ctx, p, right)
    })
  }

  private drawProfile(ctx: Ctx, p: Profile, right: number) {
    const x0 = this.x(p.t0, null)
    const x1 = this.x(p.t1, null)
    if (x0 == null || x1 == null || x1 < 0 || x0 > right) return
    const width = (x1 - x0) * 0.85
    let mx = 0
    for (const r of p.rows) mx = Math.max(mx, r[2] + r[3])
    if (mx <= 0) return
    const fade = p.closed ? 1 : 0.5
    let top = Infinity
    let bottom = -Infinity
    for (const [lo, hi, buy, sell] of p.rows) {
      const yHi = this.y(hi)
      const yLo = this.y(lo)
      if (yHi == null || yLo == null) continue
      top = Math.min(top, yHi)
      bottom = Math.max(bottom, yLo)
      const h = Math.max(1, yLo - yHi - 0.5)
      const inVa = hi > p.val && lo < p.vah
      const isPoc = lo <= p.poc && p.poc <= hi
      const a = (isPoc ? 0.95 : inVa ? 0.75 : 0.35) * fade
      const wb = (width * buy) / mx
      const ws = (width * sell) / mx
      ctx.fillStyle = `rgba(${BUY},${a})`
      ctx.fillRect(x0, yHi, wb, h)
      ctx.fillStyle = `rgba(${SELL},${a})`
      ctx.fillRect(x0 + wb, yHi, ws, h)
      if (isPoc) {
        ctx.strokeStyle = `rgba(${POC},${fade})`
        ctx.lineWidth = 1.5
        ctx.strokeRect(x0, yHi, wb + ws, h)
      }
    }
    const yPoc = this.y(p.poc)
    if (yPoc != null) {
      ctx.strokeStyle = `rgba(${POC},${0.9 * fade})`
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x0, yPoc)
      ctx.lineTo(x1, yPoc)
      ctx.stroke()
    }
    if (Number.isFinite(top)) {
      ctx.font = "bold 11px 'Geist Mono Variable', monospace"
      const text = p.shape + (p.closed ? "" : "…")
      const w = ctx.measureText(text).width + 8
      ctx.globalAlpha = fade
      ctx.fillStyle = SHAPE_COLORS[p.shape] ?? SHAPE_COLORS.D
      ctx.fillRect(x0, top - 18, w, 15)
      ctx.fillStyle = "#111"
      ctx.fillText(text, x0 + 4, top - 7)
      ctx.globalAlpha = 1
      const delta = p.buy - p.sell
      ctx.font = "10px 'Geist Mono Variable', monospace"
      ctx.fillStyle = delta >= 0 ? "#26a69a" : "#ef5350"
      ctx.fillText(fmtVol(delta), x0, bottom + 12)
    }
  }

  private drawTop(target: CanvasRenderingTarget2D) {
    if (!this.chart) return
    const last = this.times[this.times.length - 1]
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const right = mediaSize.width
      for (const l of this.levels) {
        const y = this.y(l.price)
        if (y == null) continue
        const x0 = this.x(l.t0, 0)
        const x1 = this.x(l.t1, right)
        if (x1 < 0 || x0 > right) continue
        ctx.strokeStyle = hexA(l.color, l.t1 && l.t1 < last ? 0.45 : 0.9)
        ctx.lineWidth = 1
        ctx.setLineDash(l.dash ? [5, 4] : [])
        ctx.beginPath()
        ctx.moveTo(x0, y)
        ctx.lineTo(x1, y)
        ctx.stroke()
        ctx.setLineDash([])
        if (l.label) {
          ctx.font = "10px 'Geist Mono Variable', monospace"
          ctx.fillStyle = hexA(l.color, 0.95)
          const w = ctx.measureText(l.label).width
          ctx.fillText(l.label, Math.min(x1, right - 40) - w - 2, y - 3)
        }
      }
    })
  }
}
