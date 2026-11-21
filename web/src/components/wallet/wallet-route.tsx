import { useEffect, useRef, useState } from "react"

/* The wallet check's seven steps as one route drawn top to bottom on a canvas.
   A spine links the steps; every step that is done turns green, node and spine alike, with a
   check drawn into its node. The step being checked carries a blue spinning ring, and blue
   sparks run down the spine from the last finished step into it. Each row also says its
   verdict (pass, review, risk). Seven transparent buttons sit over the rows, so a pointer,
   a keyboard or a screen reader can pick a step. Draws only while something moves. */

export type RouteStatus = "idle" | "active" | "done" | "ok" | "warn" | "danger"
export type RouteStep = { title: string; body: string; status: RouteStatus }

const GREEN = "74,222,128"
const BLUE = "91,124,255"
const TAG: Record<RouteStatus, { word: string; rgb: string }> = {
  idle: { word: "WAITING", rgb: "130,130,130" },
  active: { word: "CHECKING", rgb: BLUE },
  done: { word: "DONE", rgb: GREEN },
  ok: { word: "PASS", rgb: GREEN },
  warn: { word: "REVIEW", rgb: "242,201,76" },
  danger: { word: "RISK", rgb: "255,92,77" },
}
const complete = (s: RouteStatus) =>
  s === "done" || s === "ok" || s === "warn" || s === "danger"

const PAD = 12
const GAP = 6
const SPINE_X = 26
const CARD_X = 54

function layout(h: number, n: number) {
  const rowH = Math.max(44, (h - PAD * 2 - GAP * (n - 1)) / n)
  return Array.from({ length: n }, (_, i) => {
    const top = PAD + i * (rowH + GAP)
    return { top, h: rowH, cy: top + rowH / 2 }
  })
}

export function WalletRoute({
  steps,
  selected,
  onSelect,
  running,
  reduced,
}: {
  steps: Array<RouteStep>
  selected: number
  onSelect: (i: number) => void
  running: boolean
  reduced: boolean
}) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const props = useRef({ steps, selected, running, reduced, hover: -1 })
  props.current = { ...props.current, steps, selected, running, reduced }
  const kick = useRef<() => void>(() => {})

  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() =>
      setSize({ w: el.clientWidth, h: el.clientHeight })
    )
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const cv = canvas.current
    const ctx = cv?.getContext("2d")
    const { w: W, h: H } = size
    if (!cv || !ctx || !W || !H) return
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    cv.width = Math.round(W * dpr)
    cv.height = Math.round(H * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    // the faint dot lattice behind the route, drawn once
    const ground = document.createElement("canvas")
    ground.width = cv.width
    ground.height = cv.height
    const g = ground.getContext("2d")!
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.fillStyle = "rgba(255,255,255,0.05)"
    for (let y = 6; y < H; y += 12)
      for (let x = 6; x < W; x += 12) g.fillRect(x, y, 1, 1)

    const n = props.current.steps.length
    const rows = layout(H, n)
    const cardW = W - CARD_X - 10
    let frame = 0
    let visible = true
    let prog = -1 // how far down the green spine has grown, in steps
    const checks = new Array<number>(n).fill(0) // each node's check, drawn 0..1
    let last = performance.now()

    const rounded = (x: number, y: number, w: number, h: number, r: number) => {
      ctx.beginPath()
      ctx.moveTo(x + r, y)
      ctx.arcTo(x + w, y, x + w, y + h, r)
      ctx.arcTo(x + w, y + h, x, y + h, r)
      ctx.arcTo(x, y + h, x, y, r)
      ctx.arcTo(x, y, x + w, y, r)
      ctx.closePath()
    }
    const fit = (text: string, max: number) => {
      if (ctx.measureText(text).width <= max) return text
      let t = text
      while (t.length > 1 && ctx.measureText(`${t}…`).width > max)
        t = t.slice(0, -1)
      return `${t}…`
    }
    const font = (px: number, weight: number, mono = false) =>
      `${weight} ${px}px ${mono ? '"JetBrains Mono", ui-monospace, monospace' : '"Instrument Sans", ui-sans-serif, system-ui, sans-serif'}`

    const draw = (t: number) => {
      const {
        steps: list,
        selected: sel,
        running: run,
        reduced: red,
        hover,
      } = props.current
      const dt = Math.min(0.05, (t - last) / 1000)
      last = t
      const still = red
      const active = list.findIndex((s) => s.status === "active")
      let done = 0
      while (done < n && complete(list[done].status)) done++
      const goal = done - 1 // the green spine reaches the last finished node
      let moving = false
      if (still) prog = goal
      else if (Math.abs(goal - prog) > 0.002) {
        prog += (goal - prog) * Math.min(1, dt * 6)
        moving = true
      } else prog = goal
      list.forEach((s, i) => {
        const want = complete(s.status) ? 1 : 0
        if (still) checks[i] = want
        else if (checks[i] !== want) {
          checks[i] = want ? Math.min(1, checks[i] + dt * 3) : 0
          moving = true
        }
      })

      ctx.clearRect(0, 0, W, H)
      ctx.drawImage(ground, 0, 0, W, H)

      const y0 = rows[0].cy
      const yN = rows[n - 1].cy
      const yAt = (p: number) => {
        if (p <= 0) return y0
        const i = Math.min(n - 1, Math.floor(p))
        const f = p - i
        return i >= n - 1 ? yN : rows[i].cy + (rows[i + 1].cy - rows[i].cy) * f
      }

      // the spine: a dashed rail, then the green that has grown down it
      ctx.save()
      ctx.setLineDash([2, 5])
      ctx.strokeStyle = "rgba(255,255,255,0.16)"
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(SPINE_X, y0)
      ctx.lineTo(SPINE_X, yN)
      ctx.stroke()
      ctx.restore()
      if (prog > 0) {
        ctx.save()
        ctx.shadowColor = `rgba(${GREEN},0.7)`
        ctx.shadowBlur = 10
        ctx.strokeStyle = `rgb(${GREEN})`
        ctx.lineWidth = 2.5
        ctx.lineCap = "round"
        ctx.beginPath()
        ctx.moveTo(SPINE_X, y0)
        ctx.lineTo(SPINE_X, yAt(prog))
        ctx.stroke()
        ctx.restore()
      }

      // blue sparks running down into the step being checked
      if (active > 0 && !still) {
        const from = rows[active - 1].cy
        const to = rows[active].cy
        for (let k = 0; k < 3; k++) {
          const p = (t / 900 + k / 3) % 1
          const y = from + (to - from) * p
          const tail = ctx.createLinearGradient(SPINE_X, y - 14, SPINE_X, y)
          tail.addColorStop(0, `rgba(${BLUE},0)`)
          tail.addColorStop(1, `rgba(${BLUE},0.9)`)
          ctx.strokeStyle = tail
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(SPINE_X, y - 14)
          ctx.lineTo(SPINE_X, y)
          ctx.stroke()
          ctx.fillStyle = `rgb(${BLUE})`
          ctx.beginPath()
          ctx.arc(SPINE_X, y, 2.4, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      list.forEach((s, i) => {
        const r = rows[i]
        const tag = TAG[s.status]
        const isDone = complete(s.status)
        const isActive = s.status === "active"

        // the branch from the spine to the card
        ctx.strokeStyle = isDone
          ? `rgba(${GREEN},0.55)`
          : isActive
            ? `rgba(${BLUE},0.8)`
            : "rgba(255,255,255,0.14)"
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(SPINE_X + 12, r.cy)
        ctx.lineTo(CARD_X, r.cy)
        ctx.stroke()

        // the card
        const rad = 10
        rounded(CARD_X, r.top, cardW, r.h, rad)
        if (isActive) {
          const fill = ctx.createLinearGradient(
            CARD_X,
            r.top,
            CARD_X + cardW,
            r.top
          )
          fill.addColorStop(0, `rgba(${BLUE},0.16)`)
          fill.addColorStop(1, `rgba(${BLUE},0.03)`)
          ctx.fillStyle = fill
        } else
          ctx.fillStyle =
            i === hover ? "#181818" : isDone ? "#0f1411" : "#121212"
        ctx.fill()
        if (isActive && !still) {
          ctx.save()
          rounded(CARD_X, r.top, cardW, r.h, rad)
          ctx.clip()
          const sx = CARD_X + (((t * 0.00035) % 1.4) - 0.2) * cardW
          const sheen = ctx.createLinearGradient(sx - 80, 0, sx + 80, 0)
          sheen.addColorStop(0, `rgba(${BLUE},0)`)
          sheen.addColorStop(0.5, "rgba(170,190,255,0.14)")
          sheen.addColorStop(1, `rgba(${BLUE},0)`)
          ctx.fillStyle = sheen
          ctx.fillRect(CARD_X, r.top, cardW, r.h)
          ctx.restore()
        }
        rounded(CARD_X + 0.5, r.top + 0.5, cardW - 1, r.h - 1, rad)
        ctx.strokeStyle =
          i === sel
            ? "rgba(255,255,255,0.45)"
            : isActive
              ? `rgba(${BLUE},0.65)`
              : isDone
                ? `rgba(${GREEN},0.28)`
                : "rgba(255,255,255,0.08)"
        ctx.lineWidth = 1
        ctx.stroke()
        if (isDone) {
          ctx.fillStyle = `rgba(${GREEN},${0.35 + 0.65 * checks[i]})`
          ctx.fillRect(CARD_X, r.top + 8, 2, r.h - 16)
        }

        // the tag: the step's verdict
        ctx.font = font(10, 700, true)
        // a checking step spins a loading ring in front of its word instead of animating dots
        const spin = isActive && !still
        const tw = ctx.measureText("CHECKING").width + 16 + 14
        const tx = CARD_X + cardW - 12 - tw
        rounded(tx, r.cy - 11, tw, 22, 11)
        ctx.fillStyle = `rgba(${tag.rgb},0.14)`
        ctx.fill()
        ctx.fillStyle = `rgb(${tag.rgb})`
        ctx.textBaseline = "middle"
        ctx.textAlign = "center"
        if (spin) {
          const sx = tx + 8 + 5
          const a = (t / 160) % (Math.PI * 2)
          ctx.save()
          ctx.lineWidth = 1.6
          ctx.lineCap = "round"
          ctx.strokeStyle = `rgba(${tag.rgb},0.25)`
          ctx.beginPath()
          ctx.arc(sx, r.cy, 4.5, 0, Math.PI * 2)
          ctx.stroke()
          ctx.strokeStyle = `rgb(${tag.rgb})`
          ctx.beginPath()
          ctx.arc(sx, r.cy, 4.5, a, a + Math.PI * 1.2)
          ctx.stroke()
          ctx.restore()
          ctx.fillText(tag.word, tx + 14 + (tw - 14) / 2, r.cy + 0.5)
        } else ctx.fillText(tag.word, tx + tw / 2, r.cy + 0.5)
        ctx.textAlign = "left"

        // number, title, and the body when the row has room
        const textX = CARD_X + 16
        const textW = tx - textX - 12
        const twoLines = r.h >= 46
        ctx.font = font(10, 400, true)
        ctx.fillStyle = "rgba(255,255,255,0.45)"
        ctx.fillText(
          String(i + 1).padStart(2, "0"),
          textX,
          twoLines ? r.cy - 8 : r.cy
        )
        ctx.font = font(14.5, 600)
        ctx.fillStyle = isDone || isActive || i === sel ? "#f5f5f5" : "#bdbdbd"
        ctx.fillText(
          fit(s.title, textW - 26),
          textX + 24,
          twoLines ? r.cy - 8 : r.cy
        )
        if (twoLines) {
          ctx.font = font(12, 400)
          ctx.fillStyle = "#8f8f8f"
          ctx.fillText(fit(s.body, textW - 26), textX + 24, r.cy + 10)
        }

        // the node on the spine
        const nr = 11
        if (isActive && !still) {
          const pulse = (t % 1400) / 1400
          ctx.strokeStyle = `rgba(${BLUE},${0.5 * (1 - pulse)})`
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.arc(SPINE_X, r.cy, nr + 2 + pulse * 12, 0, Math.PI * 2)
          ctx.stroke()
          const a = (t / 600) % (Math.PI * 2)
          ctx.strokeStyle = `rgb(${BLUE})`
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.arc(SPINE_X, r.cy, nr + 4, a, a + Math.PI * 0.9)
          ctx.stroke()
        }
        ctx.beginPath()
        ctx.arc(SPINE_X, r.cy, nr, 0, Math.PI * 2)
        if (isDone) {
          ctx.save()
          ctx.shadowColor = `rgba(${GREEN},0.6)`
          ctx.shadowBlur = 12 * checks[i]
          ctx.fillStyle = `rgb(${GREEN})`
          ctx.fill()
          ctx.restore()
          // the check, drawn in
          const c = checks[i]
          const p1 = { x: SPINE_X - 4.5, y: r.cy + 0.5 }
          const p2 = { x: SPINE_X - 1.2, y: r.cy + 3.8 }
          const p3 = { x: SPINE_X + 5, y: r.cy - 3.6 }
          ctx.strokeStyle = "#0b0b0b"
          ctx.lineWidth = 2.2
          ctx.lineCap = "round"
          ctx.lineJoin = "round"
          ctx.beginPath()
          ctx.moveTo(p1.x, p1.y)
          const k1 = Math.min(1, c * 2)
          ctx.lineTo(p1.x + (p2.x - p1.x) * k1, p1.y + (p2.y - p1.y) * k1)
          if (c > 0.5) {
            const k2 = (c - 0.5) * 2
            ctx.lineTo(p2.x + (p3.x - p2.x) * k2, p2.y + (p3.y - p2.y) * k2)
          }
          ctx.stroke()
        } else {
          ctx.fillStyle = "#0d0d0d"
          ctx.fill()
          ctx.strokeStyle = isActive ? `rgb(${BLUE})` : "rgba(255,255,255,0.25)"
          ctx.lineWidth = 1.5
          ctx.stroke()
          ctx.font = font(9, 500, true)
          ctx.fillStyle = isActive ? `rgb(${BLUE})` : "rgba(255,255,255,0.55)"
          ctx.textAlign = "center"
          ctx.fillText(String(i + 1), SPINE_X, r.cy + 0.5)
          ctx.textAlign = "left"
        }
      })

      return moving || (active >= 0 && run && !still)
    }

    const loop = (t: number) => {
      frame = 0
      const keep = draw(t)
      if (keep && visible) frame = requestAnimationFrame(loop)
    }
    const start = () => {
      if (!frame) frame = requestAnimationFrame(loop)
    }
    kick.current = start
    start()
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting
      if (visible) start()
    })
    io.observe(cv)
    return () => {
      cancelAnimationFrame(frame)
      io.disconnect()
    }
  }, [size, steps.length])

  useEffect(() => {
    kick.current()
  }, [steps, selected, running, reduced])

  const rows = size.h ? layout(size.h, steps.length) : []
  const hover = (i: number) => {
    props.current.hover = i
    kick.current()
  }

  return (
    <div ref={box} className="relative h-full w-full">
      <canvas
        ref={canvas}
        className="absolute inset-0 h-full w-full"
        aria-hidden="true"
      />
      {rows.map((r, i) => (
        <button
          key={steps[i].title}
          type="button"
          onClick={() => onSelect(i)}
          onMouseEnter={() => hover(i)}
          onMouseLeave={() => hover(-1)}
          aria-pressed={i === selected}
          aria-label={`Step ${i + 1}, ${steps[i].title}: ${TAG[steps[i].status].word.toLowerCase()}`}
          className="absolute cursor-pointer rounded-[10px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5b7cff]"
          style={{ top: r.top, height: r.h, left: SPINE_X - 14, right: 10 }}
        />
      ))}
    </div>
  )
}
