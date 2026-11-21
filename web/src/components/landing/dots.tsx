import { useEffect, useRef } from "react"

/* The RINNG wordmark as a field of tiny dots on a lattice, drawn on one canvas.
   - the letters assemble from scattered dust once, on load
   - faint lattice dots breathe with a slow wave; blue "tick" dots slide along the rows
   - dots near the pointer step aside
   - footer: a blue price wave runs through the lattice
   It stops when off screen, when `running` is false, and draws one still frame under reduced motion. */

// RINNG in 14-unit strokes on a 100-unit cap height (the NHM blocks' geometry), 1100 units wide.
export const LETTERS: Array<{ x: number; polygons: Array<string> }> = [
  {
    x: 0, // R
    polygons: [
      "0,0 14,0 14,100 0,100",
      "14,0 150,0 150,14 14,14",
      "136,14 150,14 150,57 136,57",
      "14,43 150,43 150,57 14,57",
      "62,57 90,57 180,100 152,100",
    ],
  },
  { x: 246, polygons: ["0,0 14,0 14,100 0,100"] }, // I
  {
    x: 326,
    polygons: [
      "0,0 14,0 14,100 0,100",
      "200,0 214,0 214,100 200,100",
      "0,0 33,0 214,100 181,100",
    ],
  }, // N
  {
    x: 606,
    polygons: [
      "0,0 14,0 14,100 0,100",
      "200,0 214,0 214,100 200,100",
      "0,0 33,0 214,100 181,100",
    ],
  }, // N
  {
    x: 886, // G
    polygons: [
      "0,0 14,0 14,100 0,100",
      "0,0 214,0 214,14 0,14",
      "0,86 214,86 214,100 0,100",
      "200,50 214,50 214,100 200,100",
      "110,50 214,50 214,64 110,64",
    ],
  },
]

type Tone = { ink: string; dust: string; blue: string }
const TONES: Record<"paper" | "dark", Tone> = {
  paper: { ink: "17,17,17", dust: "17,17,17", blue: "35,73,230" },
  dark: { ink: "242,242,242", dust: "255,255,255", blue: "91,124,255" },
}

const LEVELS = 6

type Dot = {
  hx: number
  hy: number
  ink: boolean
  sx: number
  sy: number
  delay: number
  seed: number
}
type Tick = { row: number; x: number; speed: number }

export function DotField({
  tone = "paper",
  wave = false,
  running,
  reduced,
  padY = 0.18,
}: {
  tone?: "paper" | "dark"
  wave?: boolean
  running: boolean
  reduced: boolean
  /** empty lattice above and below the letters, as a share of the letter height */
  padY?: number
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const live = useRef({ running, reduced })
  live.current = { running, reduced }
  const kick = useRef<() => void>(() => {})

  useEffect(() => {
    const cv = canvas.current
    if (!cv) return
    const ctx = cv.getContext("2d")
    if (!ctx) return
    const T = TONES[tone]
    let W = 0
    let H = 0
    let gap = 5
    let dots: Array<Dot> = []
    let ticks: Array<Tick> = []
    let buckets: Array<Float32Array> = []
    let rows = 0
    let frame = 0
    let visible = true
    let born = performance.now()
    let last = born
    const ptr = { x: -9999, y: -9999, tx: -9999, ty: -9999 }

    const build = () => {
      const r = cv.getBoundingClientRect()
      W = r.width
      H = r.height
      if (!W || !H) return
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      cv.width = Math.round(W * dpr)
      cv.height = Math.round(H * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      gap = Math.max(3.5, Math.min(7, W / 270))
      // the letters fill the width; the lattice runs padY of a letter height above and below
      const s = W / 1100
      const top = (H - 100 * s) / 2
      // rasterise the letters once and read the mask back, instead of a path test per dot
      const mask = document.createElement("canvas")
      mask.width = Math.ceil(W)
      mask.height = Math.ceil(H)
      const mctx = mask.getContext("2d")!
      mctx.fillStyle = "#000"
      for (const l of LETTERS) {
        for (const poly of l.polygons) {
          mctx.beginPath()
          poly.split(" ").forEach((pt, i) => {
            const [px, py] = pt.split(",").map(Number)
            const X = (l.x + px) * s
            const Y = top + py * s
            if (i) mctx.lineTo(X, Y)
            else mctx.moveTo(X, Y)
          })
          mctx.closePath()
          mctx.fill()
        }
      }
      const alpha = mctx.getImageData(0, 0, mask.width, mask.height).data
      const inside = (x: number, y: number) => {
        const ix = Math.min(mask.width - 1, Math.max(0, Math.round(x)))
        const iy = Math.min(mask.height - 1, Math.max(0, Math.round(y)))
        return alpha[(iy * mask.width + ix) * 4 + 3] > 127
      }
      dots = []
      rows = Math.floor(H / gap)
      for (let j = 0; j <= rows; j++) {
        for (let i = 0; i * gap <= W; i++) {
          const hx = i * gap + gap / 2
          const hy = j * gap + gap / 2
          dots.push({
            hx,
            hy,
            ink: inside(hx, hy),
            sx: (Math.random() - 0.5) * W * 0.35,
            sy: (Math.random() - 0.5) * H * 2.2,
            delay: (hx / W) * 520 + Math.random() * 260,
            seed: Math.random() * Math.PI * 2,
          })
        }
      }
      buckets = Array.from(
        { length: LEVELS * 2 + 1 },
        () => new Float32Array(dots.length * 2)
      )
      ticks = Array.from({ length: Math.max(6, Math.round(W / 60)) }, () => ({
        row: Math.floor(Math.random() * (rows + 1)),
        x: Math.random() * W,
        speed: 30 + Math.random() * 90,
      }))
    }

    const ease = (t: number) => 1 - Math.pow(1 - t, 4)

    const draw = (now: number, still: boolean) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const t = still ? 1e9 : now - born
      ctx.clearRect(0, 0, W, H)
      ptr.x += (ptr.tx - ptr.x) * 0.18
      ptr.y += (ptr.ty - ptr.y) * 0.18
      const R = Math.max(50, W / 16)
      const waveY = (x: number) =>
        H * 0.5 +
        Math.sin(x * 0.009 - t * 0.0012) * H * 0.22 +
        Math.sin(x * 0.023 + t * 0.0007) * H * 0.08
      const inkSize = gap * 0.52
      const dustSize = Math.max(1, gap * 0.22)

      // sort every dot into a colour bucket, then draw each bucket with one fillStyle:
      // bucket 0 is ink, 1..LEVELS dust by brightness, LEVELS+1..2*LEVELS the blue wave
      const counts = new Array(LEVELS * 2 + 1).fill(0)
      for (const d of dots) {
        let x = d.hx
        let y = d.hy
        if (d.ink && !still) {
          const p = Math.min(1, Math.max(0, (t - d.delay) / 1300))
          const k = 1 - ease(p)
          x += d.sx * k
          y += d.sy * k
        }
        const dx = x - ptr.x
        const dy = y - ptr.y
        if (dx * dx + dy * dy < R * R) {
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist > 0.01) {
            const push = Math.pow(1 - dist / R, 2) * (d.ink ? 10 : 6)
            x += (dx / dist) * push
            y += (dy / dist) * push
          }
        }
        let b = 0
        if (!d.ink) {
          const off = wave ? Math.abs(d.hy - waveY(d.hx)) : Infinity
          if (off < gap * 1.2) {
            b =
              LEVELS +
              1 +
              Math.min(LEVELS - 1, Math.floor((off / (gap * 1.2)) * LEVELS))
          } else {
            const level =
              0.5 +
              0.5 *
                Math.sin(
                  d.hx * 0.011 + d.hy * 0.03 - t * 0.0015 + d.seed * 0.15
                )
            b = 1 + Math.min(LEVELS - 1, Math.floor(level * LEVELS))
          }
        }
        const arr = buckets[b]
        arr[counts[b] * 2] = x
        arr[counts[b] * 2 + 1] = y
        counts[b]++
      }
      for (let b = 0; b < buckets.length; b++) {
        const n = counts[b]
        if (!n) continue
        let size: number
        if (b === 0) {
          ctx.fillStyle = `rgba(${T.ink},1)`
          size = inkSize
        } else if (b <= LEVELS) {
          const a = (0.07 + 0.11 * ((b - 0.5) / LEVELS)) * (wave ? 1.4 : 1)
          ctx.fillStyle = `rgba(${T.dust},${a.toFixed(3)})`
          size = dustSize
        } else {
          const a = 0.9 - ((b - LEVELS - 1 + 0.5) / LEVELS) * 0.6
          ctx.fillStyle = `rgba(${T.blue},${a.toFixed(3)})`
          size = inkSize * 0.85
        }
        const arr = buckets[b]
        const half = size / 2
        for (let k = 0; k < n; k++)
          ctx.fillRect(arr[k * 2] - half, arr[k * 2 + 1] - half, size, size)
      }

      // blue ticks sliding along the lattice rows, each with a short trail
      for (const k of ticks) {
        if (!still) {
          k.x += k.speed * dt
          if (k.x > W + gap * 4) {
            k.x = -gap * 4
            k.row = Math.floor(Math.random() * (rows + 1))
          }
        }
        const y = k.row * gap + gap / 2
        const snapped = Math.round((k.x - gap / 2) / gap) * gap + gap / 2
        for (let n = 0; n < 4; n++) {
          ctx.fillStyle = `rgba(${T.blue},${0.95 - n * 0.24})`
          const sz = inkSize * (1 - n * 0.15)
          ctx.fillRect(snapped - n * gap - sz / 2, y - sz / 2, sz, sz)
        }
      }
    }

    const loop = (now: number) => {
      frame = 0
      const { running: run, reduced: red } = live.current
      if (red || !run || !visible) {
        draw(now, true)
        return
      }
      draw(now, false)
      frame = requestAnimationFrame(loop)
    }
    const start = () => {
      if (!frame) frame = requestAnimationFrame(loop)
    }
    kick.current = start

    build()
    born = performance.now()
    start()

    const ro = new ResizeObserver(() => {
      build()
      start()
    })
    ro.observe(cv)
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting
      if (visible) start()
    })
    io.observe(cv)
    const host = cv.parentElement ?? cv
    const move = (e: PointerEvent) => {
      const r = cv.getBoundingClientRect()
      ptr.tx = e.clientX - r.left
      ptr.ty = e.clientY - r.top
      if (ptr.x < -999) {
        ptr.x = ptr.tx
        ptr.y = ptr.ty
      }
    }
    const leave = () => {
      ptr.tx = ptr.ty = -9999
    }
    host.addEventListener("pointermove", move)
    host.addEventListener("pointerleave", leave)
    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      io.disconnect()
      host.removeEventListener("pointermove", move)
      host.removeEventListener("pointerleave", leave)
    }
  }, [tone, wave, padY])

  // resume (or draw the still frame) when play/pause or reduced motion changes
  useEffect(() => {
    kick.current()
  }, [running, reduced])

  return (
    <canvas
      ref={canvas}
      className="absolute inset-0 h-full w-full"
      aria-hidden="true"
    />
  )
}

/** The aspect ratio a DotField's box should have for a given vertical padding. */
export const dotAspect = (padY: number) =>
  `1100 / ${Math.round(100 * (1 + padY * 2))}`
