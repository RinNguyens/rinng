import type { ReactNode } from "react"
import { ExchangeBinance, ExchangeOkx } from "@web3icons/react"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Activity01Icon,
  CodeIcon,
  ComputerIcon,
  DatabaseIcon,
  Layers01Icon,
  TestTube01Icon,
} from "@hugeicons/core-free-icons"

/* rinng's data route as a routing diagram: the two exchanges feed one collector, a local store,
   the analysis modules, and three ways to read the result. `step` (0-3) lights the part a
   pipeline step names; pulses run along the lines unless paused or under reduced motion. */

type NodeId =
  | "binance"
  | "okx"
  | "collector"
  | "store"
  | "analysis"
  | "terminal"
  | "backtest"
  | "pine"
type Node = {
  id: NodeId
  title: string
  sub: string
  icon: ReactNode
  step: number
}

const hi = (icon: typeof DatabaseIcon) => (
  <HugeiconsIcon icon={icon} size={20} strokeWidth={1.5} />
)

const NODES: Array<Node> = [
  {
    id: "binance",
    title: "Binance",
    sub: "USDT perps",
    icon: <ExchangeBinance variant="branded" size={20} />,
    step: 0,
  },
  {
    id: "okx",
    title: "OKX",
    sub: "USDT perps",
    icon: <ExchangeOkx variant="branded" size={20} />,
    step: 0,
  },
  {
    id: "collector",
    title: "Collector",
    sub: "WebSocket, 24/7",
    icon: hi(Activity01Icon),
    step: 0,
  },
  {
    id: "store",
    title: "Local store",
    sub: "Parquet + DuckDB",
    icon: hi(DatabaseIcon),
    step: 1,
  },
  {
    id: "analysis",
    title: "Analysis",
    sub: "9 modules",
    icon: hi(Layers01Icon),
    step: 2,
  },
  {
    id: "terminal",
    title: "Web terminal",
    sub: "Live charts",
    icon: hi(ComputerIcon),
    step: 3,
  },
  {
    id: "backtest",
    title: "Backtests",
    sub: "Fees, slippage",
    icon: hi(TestTube01Icon),
    step: 3,
  },
  {
    id: "pine",
    title: "Pine Script",
    sub: "TradingView v6",
    icon: hi(CodeIcon),
    step: 3,
  },
]

type Layout = {
  w: number
  h: number
  nodeW: number
  pos: Record<NodeId, [number, number]>
  paths: Array<{ d: string; step: number }>
}

// wide: left to right
const WIDE: Layout = {
  w: 1320,
  h: 440,
  nodeW: 200,
  pos: {
    binance: [20, 100],
    okx: [20, 276],
    collector: [300, 188],
    store: [580, 188],
    analysis: [860, 188],
    terminal: [1110, 60],
    backtest: [1110, 188],
    pine: [1110, 316],
  },
  paths: [
    { d: "M220 132 C260 132 260 220 300 220", step: 0 },
    { d: "M220 308 C260 308 260 220 300 220", step: 0 },
    { d: "M500 220 L580 220", step: 1 },
    { d: "M780 220 L860 220", step: 2 },
    { d: "M1060 220 C1085 220 1085 92 1110 92", step: 3 },
    { d: "M1060 220 L1110 220", step: 3 },
    { d: "M1060 220 C1085 220 1085 348 1110 348", step: 3 },
  ],
}

// narrow: top to bottom
const TALL: Layout = {
  w: 360,
  h: 760,
  nodeW: 168,
  pos: {
    binance: [8, 8],
    okx: [184, 8],
    collector: [96, 136],
    store: [96, 264],
    analysis: [96, 392],
    terminal: [8, 560],
    backtest: [184, 560],
    pine: [96, 680],
  },
  paths: [
    { d: "M92 72 C92 104 180 104 180 136", step: 0 },
    { d: "M268 72 C268 104 180 104 180 136", step: 0 },
    { d: "M180 200 L180 264", step: 1 },
    { d: "M180 328 L180 392", step: 2 },
    { d: "M180 456 C180 508 92 508 92 560", step: 3 },
    { d: "M180 456 C180 508 268 508 268 560", step: 3 },
    { d: "M180 456 L180 680", step: 3 },
  ],
}

function Diagram({
  layout,
  step,
  live,
  className,
}: {
  layout: Layout
  step: number
  live: boolean
  className: string
}) {
  const H = 64
  return (
    <svg
      viewBox={`0 0 ${layout.w} ${layout.h}`}
      className={className}
      role="img"
      aria-label="Binance and OKX feed the rinng collector, a local Parquet and DuckDB store and nine analysis modules, which serve the web terminal, backtests and Pine Script indicators."
    >
      {layout.paths.map((p, k) => (
        <path
          key={k}
          id={`${layout.w}-p${k}`}
          d={p.d}
          fill="none"
          stroke={p.step === step ? "var(--rl-blue)" : "#cfcfcf"}
          strokeWidth={p.step === step ? 1.5 : 1}
          style={{ transition: "stroke 300ms" }}
        />
      ))}
      {live &&
        layout.paths.map((_, k) => (
          <circle key={k} r={3.5} fill="var(--rl-blue)" opacity={0.9}>
            <animateMotion
              dur="3s"
              begin={`${(k % 4) * 0.45}s`}
              repeatCount="indefinite"
              calcMode="spline"
              keyTimes="0;1"
              keySplines="0.45 0 0.55 1"
            >
              <mpath href={`#${layout.w}-p${k}`} />
            </animateMotion>
          </circle>
        ))}
      {NODES.map((n) => {
        const [nx, ny] = layout.pos[n.id]
        const lit = n.step === step
        return (
          <g
            key={n.id}
            transform={`translate(${nx},${ny})`}
            style={{ transition: "opacity 300ms" }}
            opacity={lit ? 1 : 0.62}
          >
            <rect
              width={layout.nodeW}
              height={H}
              rx={12}
              fill="#fff"
              stroke={lit ? "var(--rl-blue)" : "#dcdcdc"}
              strokeWidth={lit ? 1.5 : 1}
            />
            <rect
              x={10}
              y={12}
              width={40}
              height={40}
              rx={9}
              fill="#fafafa"
              stroke="#e6e6e6"
            />
            <g transform="translate(20,22)" color="#111">
              {n.icon}
            </g>
            <text
              x={62}
              y={30}
              fill="#111"
              style={{
                fontFamily: "var(--rl-sans)",
                fontSize: 15,
                fontWeight: 500,
              }}
            >
              {n.title}
            </text>
            <text
              x={62}
              y={47}
              fill="#6b6b6b"
              style={{ fontFamily: "var(--rl-mono)", fontSize: 11 }}
            >
              {n.sub}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export function Pipeline({ step, live }: { step: number; live: boolean }) {
  return (
    <>
      <Diagram
        layout={WIDE}
        step={step}
        live={live}
        className="hidden h-auto w-full md:block"
      />
      <Diagram
        layout={TALL}
        step={step}
        live={live}
        className="mx-auto block h-auto w-full max-w-[360px] md:hidden"
      />
    </>
  )
}
