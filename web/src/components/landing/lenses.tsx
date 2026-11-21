import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { swings, type Bar } from "./market"

/* The nine analysis lenses, each drawn as a schematic over one fixed illustrative series
   (a markdown, a trading range with a spring, a markup). These are diagrams of what each module
   marks, not market data: no prices or dates are shown. */

export const LENSES = [
  { name: "Market structure", line: "Swing highs and lows, the trend they make and every break of structure." },
  { name: "Smart Money Concepts", line: "Order blocks, fair value gaps, BOS and CHoCH, drawn where they formed." },
  { name: "Liquidity", line: "Equal highs and lows, and the pools of stops resting beyond them." },
  { name: "Volume profile", line: "Where volume traded: point of control, value area, high and low nodes." },
  { name: "Order flow", line: "Buy and sell delta for every bar and its running total against price." },
  { name: "Derivatives", line: "Funding, open interest and long/short ratios from Binance and OKX." },
  { name: "Wyckoff", line: "Accumulation and distribution phases, springs and upthrusts." },
  { name: "Elliott waves", line: "Impulse and correction counts on confirmed swings." },
  { name: "Forecast", line: "A probability cone for the next bars and the odds of touching each level." },
] as const

// ---- the illustrative series --------------------------------------------------------------
const CLOSES = [
  70, 66, 68, 61, 58, 60, 52, 48, // markdown
  51, 45, 53, 47, 46, 52, 54, 47, 41, 49, 53, 56, // trading range, spring at 16
  59, 64, 62, 67, 71, 68, 74, 79, 75, 81, 85, 82, 87, 91, 88, 93, // markup
]
const WICKS = [2, 3, 1.5, 2.5, 1, 3, 2, 1.5, 2.5, 1, 2, 3, 1.5, 2, 1, 2.5, 3, 2, 1.5, 2]
const SERIES: Array<Bar> = CLOSES.map((c, i) => {
  const o = i === 0 ? 72 : CLOSES[i - 1]
  const w = WICKS[i % WICKS.length]
  return { t: i, o, c, h: Math.max(o, c) + w, l: Math.min(o, c) - w * 0.8 }
})
const N = SERIES.length
const LO = Math.min(...SERIES.map((b) => b.l)) - 4
const HI = Math.max(...SERIES.map((b) => b.h)) + 4
const X0 = 16
const X1 = 296
const step = (X1 - X0) / N
const x = (i: number) => X0 + step * (i + 0.5)
const y = (p: number) => 236 - ((p - LO) / (HI - LO)) * 212
const RANGE = { from: 8, to: 19 }
const rangeHigh = Math.max(...SERIES.slice(RANGE.from, RANGE.to + 1).map((b) => b.h))
const rangeLow = Math.min(...SERIES.slice(RANGE.from, 16).map((b) => b.l))

const INK = "#8f8f8f"
const WHITE = "#f2f2f2"
const BLUE = "#5b7cff"
const mono = { fontFamily: "var(--rl-mono)", fontSize: 9, letterSpacing: "0.08em" } as const

function Candles({ dim = false }: { dim?: boolean }) {
  return (
    <g opacity={dim ? 0.45 : 1}>
      {SERIES.map((b, i) => {
        const up = b.c >= b.o
        const top = y(Math.max(b.o, b.c))
        const h = Math.max(1, Math.abs(y(b.o) - y(b.c)))
        return (
          <g key={i}>
            <line x1={x(i)} x2={x(i)} y1={y(b.h)} y2={y(b.l)} stroke={INK} strokeWidth={1} />
            <rect
              x={x(i) - step * 0.32}
              y={top}
              width={step * 0.64}
              height={h}
              fill={up ? "#0a0a0a" : INK}
              stroke={INK}
              strokeWidth={1}
            />
          </g>
        )
      })}
    </g>
  )
}

function Label({ px, py, children, fill = WHITE, anchor = "middle" }: {
  px: number
  py: number
  children: ReactNode
  fill?: string
  anchor?: "start" | "middle" | "end"
}) {
  return (
    <text x={px} y={py} fill={fill} textAnchor={anchor} style={mono}>
      {children}
    </text>
  )
}

function Structure() {
  const s = swings(SERIES, 2)
  return (
    <>
      <Candles dim />
      <polyline
        points={s.map((p) => `${x(p.i)},${y(p.price)}`).join(" ")}
        fill="none"
        stroke={WHITE}
        strokeWidth={1.2}
      />
      {s.map((p) => {
        const high = p.kind === "HH" || p.kind === "LH"
        return (
          <g key={p.i}>
            <circle cx={x(p.i)} cy={y(p.price)} r={2.5} fill={p.kind === "HH" || p.kind === "HL" ? BLUE : WHITE} />
            <Label px={x(p.i)} py={y(p.price) + (high ? -8 : 15)}>
              {p.kind}
            </Label>
          </g>
        )
      })}
    </>
  )
}

function Smc() {
  const ob = SERIES[16]
  const fvg = SERIES.findIndex((_, i) => i > 19 && i < N - 1 && SERIES[i - 1].h < SERIES[i + 1].l)
  const breakAt = SERIES.findIndex((b, i) => i > RANGE.to && b.c > rangeHigh)
  return (
    <>
      <Candles dim />
      <rect x={x(16) - step / 2} y={y(ob.h)} width={X1 - x(16) + step / 2} height={y(ob.l) - y(ob.h)} fill={BLUE} fillOpacity={0.18} stroke={BLUE} strokeWidth={1} />
      <Label px={X1 + 6} py={y(ob.h) + 10} fill={BLUE} anchor="start">OB</Label>
      {fvg > 0 && (
        <>
          <rect x={x(fvg) - step / 2} y={y(SERIES[fvg + 1].l)} width={X1 - x(fvg) + step / 2} height={y(SERIES[fvg - 1].h) - y(SERIES[fvg + 1].l)} fill={WHITE} fillOpacity={0.12} />
          <Label px={X1 + 6} py={y(SERIES[fvg + 1].l) + 9} anchor="start">FVG</Label>
        </>
      )}
      <line x1={x(14)} x2={x(breakAt)} y1={y(rangeHigh)} y2={y(rangeHigh)} stroke={WHITE} strokeDasharray="4 3" />
      <Label px={(x(14) + x(breakAt)) / 2} py={y(rangeHigh) - 6}>BOS</Label>
    </>
  )
}

function Liquidity() {
  return (
    <>
      <Candles dim />
      <line x1={x(RANGE.from)} x2={X1} y1={y(rangeHigh)} y2={y(rangeHigh)} stroke={WHITE} strokeDasharray="2 3" />
      <Label px={X1 + 6} py={y(rangeHigh) + 3} anchor="start">EQH</Label>
      <line x1={x(RANGE.from)} x2={x(19)} y1={y(rangeLow)} y2={y(rangeLow)} stroke={BLUE} strokeDasharray="2 3" />
      <Label px={x(19) + 8} py={y(rangeLow) + 3} fill={BLUE} anchor="start">EQL · stops</Label>
      <circle cx={x(16)} cy={y(SERIES[16].l)} r={7} fill="none" stroke={BLUE} />
      <Label px={x(16)} py={y(SERIES[16].l) + 18} fill={BLUE}>sweep</Label>
    </>
  )
}

function Profile() {
  const bins = 16
  const vol = new Array(bins).fill(0)
  SERIES.forEach((b, i) => {
    const k = Math.min(bins - 1, Math.floor(((b.c - LO) / (HI - LO)) * bins))
    vol[k] += i >= RANGE.from && i <= RANGE.to ? 3 : 1.2
  })
  const max = Math.max(...vol)
  const poc = vol.indexOf(max)
  const bh = 212 / bins
  return (
    <>
      <Candles dim />
      {vol.map((v, k) => (
        <rect key={k} x={300} y={236 - (k + 1) * bh + 1} width={(v / max) * 88} height={bh - 2} fill={k === poc ? BLUE : INK} fillOpacity={k === poc ? 0.9 : 0.5} />
      ))}
      <line x1={X0} x2={388} y1={236 - (poc + 0.5) * bh} y2={236 - (poc + 0.5) * bh} stroke={BLUE} strokeWidth={1} />
      <Label px={X0} py={236 - (poc + 0.5) * bh - 6} fill={BLUE} anchor="start">POC</Label>
    </>
  )
}

function Flow() {
  let cum = 0
  const pts: Array<string> = []
  return (
    <>
      <Candles dim />
      {SERIES.map((b, i) => {
        const d = b.c - b.o
        cum += d
        pts.push(`${x(i)},${272 - cum * 0.55}`)
        return <rect key={i} x={x(i) - step * 0.3} y={d >= 0 ? 272 - d * 1.6 : 272} width={step * 0.6} height={Math.max(1, Math.abs(d) * 1.6)} fill={d >= 0 ? BLUE : INK} />
      })}
      <polyline points={pts.join(" ")} fill="none" stroke={WHITE} strokeWidth={1} />
      <Label px={X1 + 6} py={276} anchor="start">Δ</Label>
    </>
  )
}

function Derivatives() {
  const oi = SERIES.map((_, i) => `${x(i)},${284 - (i * 0.9 + Math.sin(i / 2) * 3)}`)
  return (
    <>
      <Candles dim />
      <polyline points={oi.join(" ")} fill="none" stroke={BLUE} strokeWidth={1.2} />
      {SERIES.map((_, i) => (
        <rect key={i} x={x(i) - 1} y={i > 24 ? 290 - (i - 24) * 0.7 : 290} width={2} height={i > 24 ? (i - 24) * 0.7 : 1} fill={WHITE} />
      ))}
      <Label px={X1 + 6} py={262} fill={BLUE} anchor="start">OI</Label>
      <Label px={X1 + 6} py={292} anchor="start">funding</Label>
    </>
  )
}

function Wyckoff() {
  const pts: Array<[number, string, "h" | "l"]> = [
    [7, "SC", "l"], [10, "AR", "h"], [12, "ST", "l"], [16, "Spring", "l"], [19, "SOS", "h"],
  ]
  return (
    <>
      <Candles dim />
      <rect x={x(RANGE.from) - step / 2} y={y(rangeHigh)} width={x(RANGE.to) - x(RANGE.from) + step} height={y(rangeLow) - y(rangeHigh)} fill="none" stroke={WHITE} strokeDasharray="3 3" />
      {pts.map(([i, label, side]) => (
        <Label key={label} px={x(i)} py={side === "h" ? y(SERIES[i].h) - 7 : y(SERIES[i].l) + 15} fill={label === "Spring" ? BLUE : WHITE}>
          {label}
        </Label>
      ))}
      {["A", "B", "C", "D", "E"].map((p, k) => (
        <Label key={p} px={x(6 + k * 6)} py={290} fill={INK}>
          {p}
        </Label>
      ))}
    </>
  )
}

function Elliott() {
  const s = swings(SERIES, 1).filter((p) => p.i >= 16).slice(0, 6)
  return (
    <>
      <Candles dim />
      <polyline points={s.map((p) => `${x(p.i)},${y(p.price)}`).join(" ")} fill="none" stroke={BLUE} strokeWidth={1.4} />
      {s.map((p, k) => {
        const high = p.kind === "HH" || p.kind === "LH"
        return (
          <Label key={p.i} px={x(p.i)} py={y(p.price) + (high ? -8 : 15)}>
            {k === 0 ? "0" : String(k)}
          </Label>
        )
      })}
    </>
  )
}

function Forecast() {
  const last = SERIES[N - 1]
  const x0 = x(N - 1)
  const y0 = y(last.c)
  const cone = (w: number) => `M${x0},${y0} L388,${y0 - 34 - w} L388,${y0 - 34 + w} Z`
  return (
    <>
      <Candles dim />
      <path d={cone(46)} fill={BLUE} fillOpacity={0.14} />
      <path d={cone(22)} fill={BLUE} fillOpacity={0.28} />
      <line x1={x0} x2={388} y1={y0} y2={y0 - 34} stroke={WHITE} strokeDasharray="3 3" />
      <Label px={386} py={y0 - 34 - 52} anchor="end" fill={BLUE}>80%</Label>
      <Label px={386} py={y0 - 34 - 26} anchor="end">50%</Label>
    </>
  )
}

const DRAW = [Structure, Smc, Liquidity, Profile, Flow, Derivatives, Wyckoff, Elliott, Forecast]

export function LensDiagram({ index }: { index: number }) {
  const Draw = DRAW[index]
  return (
    <svg viewBox="0 0 400 300" className="h-full w-full" role="img" aria-label={`${LENSES[index].name}, drawn as a diagram`}>
      <Draw />
    </svg>
  )
}

/* A sand dissolve between children: turbulence, displacement, drift, blur and fade in one SVG
   filter, driven by requestAnimationFrame (out 600 ms, cubic ease-in; in 900 ms, quartic ease-out). */
export function SandSwap({ index, render, reduced }: { index: number; render: (i: number) => ReactNode; reduced: boolean }) {
  const [shown, setShown] = useState(index)
  const filterId = `sand-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`
  const box = useRef<HTMLDivElement>(null)
  const disp = useRef<SVGFEDisplacementMapElement>(null)
  const off = useRef<SVGFEOffsetElement>(null)
  const blur = useRef<SVGFEGaussianBlurElement>(null)
  const fade = useRef<SVGFEColorMatrixElement>(null)
  const phase = useRef<"in" | "out" | "idle">("idle")

  const apply = (p: number, entering: boolean) => {
    const q = Math.min(1, Math.max(0, p))
    disp.current?.setAttribute("scale", String(150 * q))
    off.current?.setAttribute("dx", String((entering ? -30 : 30) * q))
    off.current?.setAttribute("dy", String((entering ? -80 : 120) * q))
    blur.current?.setAttribute("stdDeviation", String(6 * q))
    fade.current?.setAttribute("values", `1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 ${Math.max(0, 1 - q * 1.2)} 0`)
    if (box.current) box.current.style.filter = q < 0.001 ? "none" : `url(#${filterId})`
  }

  const run = (ms: number, entering: boolean, done?: () => void) => {
    let start: number | null = null
    let frame = 0
    const tick = (now: number) => {
      start ??= now
      const t = Math.min(1, (now - start) / ms)
      apply(entering ? Math.pow(1 - t, 4) : Math.pow(t, 3), entering)
      if (t < 1) frame = requestAnimationFrame(tick)
      else done?.()
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }

  // index changed: blow the current drawing away, then let the next one settle
  useEffect(() => {
    if (index === shown) return
    if (reduced) {
      setShown(index)
      return
    }
    phase.current = "out"
    return run(600, false, () => {
      phase.current = "in"
      setShown(index)
    })
  }, [index, reduced])

  useEffect(() => {
    if (phase.current !== "in") return
    return run(900, true, () => {
      phase.current = "idle"
      apply(0, true)
    })
  }, [shown])

  return (
    <>
      <svg width="0" height="0" className="absolute" aria-hidden="true" focusable="false">
        <filter id={filterId} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="1.8" numOctaves={4} result="noise" />
          <feDisplacementMap ref={disp} in="SourceGraphic" in2="noise" scale="0" xChannelSelector="R" yChannelSelector="G" result="d" />
          <feOffset ref={off} in="d" dx="0" dy="0" result="o" />
          <feGaussianBlur ref={blur} in="o" stdDeviation="0" result="b" />
          <feColorMatrix ref={fade} in="b" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0" />
        </filter>
      </svg>
      <div ref={box} className="h-full w-full">
        {render(shown)}
      </div>
    </>
  )
}
