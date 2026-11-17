/* Small candlestick charts drawn as SVG for the terminal page: the same reads the terminal draws
   (order blocks, fair value gaps, liquidity lines, a volume profile, a projection cone), at mock
   size. Deterministic: a seeded random walk, so every load draws the same chart. */

export type Overlay = "structure" | "liquidity" | "profile" | "cone" | "none"

type Bar = { o: number; h: number; l: number; c: number }

function walk(seed: number, n: number, drift: number): Array<Bar> {
  let s = seed >>> 0
  const rnd = () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
  const bars: Array<Bar> = []
  let p = 100
  for (let i = 0; i < n; i++) {
    const o = p
    const c = o + (rnd() - 0.5 + drift) * 3.2
    const h = Math.max(o, c) + rnd() * 1.6
    const l = Math.min(o, c) - rnd() * 1.6
    bars.push({ o, h, l, c })
    p = c
  }
  return bars
}

const UP = "#1f9d63"
const DOWN = "#d6453d"
const INK = "#232323"

export function Candles({
  seed = 7,
  bars: n = 48,
  drift = 0.06,
  overlay = "none",
  width = 600,
  height = 300,
  label,
}: {
  seed?: number
  bars?: number
  drift?: number
  overlay?: Overlay
  width?: number
  height?: number
  /** the pane's own title, as the terminal prints it ("BTC 4h · SMC structure") */
  label?: string
}) {
  const data = walk(seed, n, drift)
  const right = overlay === "cone" ? width * 0.32 : overlay === "profile" ? width * 0.2 : 8
  const top = label ? 30 : 10
  const bottom = 12
  const hi = Math.max(...data.map((b) => b.h)) + 3
  const lo = Math.min(...data.map((b) => b.l)) - 3
  const y = (v: number) => top + ((hi - v) / (hi - lo)) * (height - top - bottom)
  const step = (width - right - 12) / n
  const x = (i: number) => 8 + i * step + step / 2
  const bw = Math.max(2, step * 0.62)
  const last = data[n - 1]

  // the reads, placed on the walk's own swings
  const lowIdx = data.reduce((m, b, i) => (b.l < data[m].l ? i : m), 0)
  const highIdx = data.reduce((m, b, i) => (b.h > data[m].h ? i : m), 0)
  const ob = data[Math.max(1, lowIdx - 1)]

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="100%" preserveAspectRatio="none" aria-hidden="true" className="tp-chart">
      <rect width={width} height={height} fill="#fff" />
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1="0" x2={width} y1={top + f * (height - top - bottom)} y2={top + f * (height - top - bottom)} stroke="#000" strokeOpacity=".05" />
      ))}
      {label ? (
        <text x="12" y="20" fontSize="12" fill={INK} fontFamily="var(--font-mono)">
          {label}
        </text>
      ) : null}

      {overlay === "structure" ? (
        <g>
          <rect x={x(lowIdx - 1) - bw} y={y(Math.max(ob.o, ob.c))} width={width - right - x(lowIdx - 1)} height={Math.max(4, y(Math.min(ob.o, ob.c)) - y(Math.max(ob.o, ob.c)))} fill={UP} fillOpacity=".14" stroke={UP} strokeOpacity=".5" />
          <text x={x(lowIdx - 1)} y={y(Math.min(ob.o, ob.c)) + 14} fontSize="11" fill={UP} fontFamily="var(--font-mono)">OB</text>
          <line x1={x(highIdx)} x2={width - right} y1={y(data[highIdx].h)} y2={y(data[highIdx].h)} stroke={INK} strokeOpacity=".55" strokeDasharray="4 3" />
          <text x={width - right - 34} y={y(data[highIdx].h) - 5} fontSize="11" fill={INK} fontFamily="var(--font-mono)">BOS</text>
        </g>
      ) : null}

      {overlay === "liquidity" ? (
        <g fontFamily="var(--font-mono)" fontSize="11">
          <line x1="8" x2={width - right} y1={y(data[highIdx].h + 0.4)} y2={y(data[highIdx].h + 0.4)} stroke={DOWN} strokeDasharray="2 3" />
          <text x={width - right - 30} y={y(data[highIdx].h + 0.4) - 5} fill={DOWN}>BSL</text>
          <line x1="8" x2={width - right} y1={y(data[lowIdx].l - 0.4)} y2={y(data[lowIdx].l - 0.4)} stroke={UP} strokeDasharray="2 3" />
          <text x={width - right - 30} y={y(data[lowIdx].l - 0.4) + 14} fill={UP}>SSL</text>
        </g>
      ) : null}

      {overlay === "profile"
        ? (() => {
            const rows = 18
            const counts = new Array<number>(rows).fill(0)
            data.forEach((b) => {
              for (let r = 0; r < rows; r++) {
                const v = lo + ((r + 0.5) / rows) * (hi - lo)
                if (v >= b.l && v <= b.h) counts[r] += Math.abs(b.c - b.o) + 0.4
              }
            })
            const max = Math.max(...counts)
            const poc = counts.indexOf(max)
            const rh = (height - top - bottom) / rows
            return (
              <g>
                {counts.map((c, r) => (
                  <rect key={r} x={width - (c / max) * (right - 10) - 4} y={top + (rows - 1 - r) * rh + 1} width={(c / max) * (right - 10)} height={rh - 2} fill={r === poc ? INK : "#9aa3a0"} fillOpacity={r === poc ? 0.7 : 0.35} />
                ))}
                <line x1="8" x2={width - 4} y1={top + (rows - 1 - poc + 0.5) * rh} y2={top + (rows - 1 - poc + 0.5) * rh} stroke={INK} strokeOpacity=".5" strokeDasharray="4 3" />
                <text x="12" y={top + (rows - 1 - poc + 0.5) * rh - 5} fontSize="11" fill={INK} fontFamily="var(--font-mono)">POC</text>
              </g>
            )
          })()
        : null}

      {data.map((b, i) => (
        <g key={i} stroke={b.c >= b.o ? UP : DOWN} fill={b.c >= b.o ? UP : DOWN}>
          <line x1={x(i)} x2={x(i)} y1={y(b.h)} y2={y(b.l)} strokeWidth="1" />
          <rect x={x(i) - bw / 2} y={y(Math.max(b.o, b.c))} width={bw} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))} />
        </g>
      ))}

      {overlay === "cone"
        ? (() => {
            const x0 = x(n - 1)
            const x1 = width - 8
            const c = last.c
            const band = (k: number) => `M${x0},${y(c)} L${x1},${y(c + k)} L${x1},${y(c - k)} Z`
            return (
              <g>
                <path d={band(9)} fill="#5b7cff" fillOpacity=".1" />
                <path d={band(5)} fill="#5b7cff" fillOpacity=".16" />
                <line x1={x0} x2={x1} y1={y(c)} y2={y(c + 0.8)} stroke="#3a5be0" strokeDasharray="4 3" />
                <text x={x1 - 30} y={y(c + 9) - 6} fontSize="11" fill="#3a5be0" fontFamily="var(--font-mono)">90%</text>
                <text x={x1 - 30} y={y(c + 5) - 6} fontSize="11" fill="#3a5be0" fontFamily="var(--font-mono)">80%</text>
              </g>
            )
          })()
        : null}
    </svg>
  )
}
