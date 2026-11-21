import { useEffect, useRef, useState } from "react"
import { Link } from "@tanstack/react-router"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  ArrowRight01Icon,
  ArrowUpRight01Icon,
  Copy01Icon,
  PauseIcon,
  PlayIcon,
  Target01Icon,
  Tick02Icon,
  WaveIcon,
  Layers01Icon,
} from "@hugeicons/core-free-icons"
import { COMBOS } from "@/lib/combos"
import { LENSES, LensDiagram, SandSwap } from "./lenses"
import { Pipeline } from "./pipeline"
import { BoomerangVideoBg } from "./boomerang"
import { DotField, dotAspect } from "./dots"
import { WalletSection } from "./wallet-section"
import "./landing.css"

/* type: software (an open-source quant analysis toolkit for crypto perpetuals; site-kind software)
   look: the user's references, not a dealt hero or palette.
     NHM: the full-width wordmark and mono columns, "[ 0n ]" labels, the dark chapter panel whose
          picture dissolves like sand.
     sent.dm: off-white blueprint (margin hairlines, corner crosses), the routing diagram with
          pulses, numbered "01 — Step" lists, one blue.
     Boomerang (the hero, at the user's request): a full-bleed video played forward then back on a
          canvas, a centred serif headline, one sentence, one action, a white glass panel on the fold.
   palette: paper #fcfcfc, ink #111, dark #0a0a0a, one blue #2349e6.
   type: Newsreader light (display), Instrument Sans (text), JetBrains Mono (labels)
   plan (1440x900):
     hero      dotted wordmark header, boomerang video, headline, the "what it does" panel   1
     pipeline  exchange data to a market read: the routing diagram and 4 steps              1
     lenses    nine analysis modules: the dissolving diagram beside the lens list (moment)  1
     combos    seven chart combos, each with its question                                   1
     wallet    a read-only wallet check of any EVM address, graded                          1
     start     run it locally: the commands in a terminal frame                             1
     closing   the call, then the dotted wordmark with a price wave on a dark band          1
   motion: the wordmark assembles from dust and its dots answer the pointer; the hero video
     ping-pongs; the lens diagram dissolves; pipeline pulses; one "Pause motion" stops them all. */

const GITHUB = "https://github.com/RinNguyens/rinng"

const NAV = [
  { label: "Pipeline", href: "#pipeline" },
  { label: "Modules", href: "#lenses" },
  { label: "Combos", href: "#combos" },
  { label: "Wallet check", href: "#wallet" },
  { label: "Quick start", href: "#start" },
]

const STEPS = [
  {
    title: "Collect",
    text: "Backfill years of history, then a 24/7 collector keeps every bar, funding print and liquidation.",
  },
  {
    title: "Store",
    text: "Bars land as Parquet on your disk, queried with DuckDB and checked against the other exchange.",
  },
  {
    title: "Analyse",
    text: "Nine modules write features and events for every timeframe from 15m to 1w.",
  },
  {
    title: "Read",
    text: "The terminal streams the forming bar; heavier reads refresh when a bar closes.",
  },
]

const COMMANDS = [
  ["git clone https://github.com/RinNguyens/rinng.git && cd rinng", ""],
  ["uv sync", "install Python 3.12 and dependencies"],
  ["uv run rinng backfill --start 2024-01-01", "download history"],
  [
    "uv run rinng resample && uv run rinng analyze --timeframe 4h",
    "build timeframes, run the modules",
  ],
  ["pnpm --dir web install && pnpm --dir web build", "build the web terminal"],
  ["uv run rinng live", "open http://127.0.0.1:8000"],
] as const

// the CLI, as the README lists it
const CLI = [
  ["check", "test both exchanges"],
  ["backfill", "download dumps and REST data"],
  ["resample", "1m to 15m, 1h, 4h, 1d, 1w"],
  ["validate", "missing and duplicate bars"],
  ["analyze", "write features and events"],
  ["backtest", "train/test backtests"],
  ["collect", "realtime collector"],
  ["live", "collector + web app"],
] as const

const Arrow = () => (
  <HugeiconsIcon
    icon={ArrowRight01Icon}
    size={14}
    strokeWidth={1}
    className="text-[#9a9a9a]"
    aria-hidden="true"
  />
)

// ---- hooks ----------------------------------------------------------------------------------
function useReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)")
    setReduced(m.matches)
    const on = () => setReduced(m.matches)
    m.addEventListener("change", on)
    return () => m.removeEventListener("change", on)
  }, [])
  return reduced
}

// ---- small parts ----------------------------------------------------------------------------
function PrimaryAction({ dark = false }: { dark?: boolean }) {
  // light ground: ink button, paper slides in. Dark ground: paper button, the page's blue slides in.
  const base = dark
    ? "border-[#f2f2f2] bg-[#f2f2f2] text-[#111] hover:border-[#2349e6] hover:shadow-[3px_3px_0px_rgba(35,73,230,0.45)]"
    : "border-[#1a1a1a] bg-[#1a1a1a] text-white hover:shadow-[3px_3px_0px_rgba(17,17,17,0.5)]"
  const panel = dark ? "bg-[#2349e6]" : "bg-[#fcfcfc]"
  const hoverText = dark ? "group-hover:text-white" : "group-hover:text-[#111]"
  return (
    <Link
      to="/terminal"
      className={`group relative inline-flex min-h-12 items-center gap-3 overflow-hidden rounded-md border px-6 py-3.5 shadow-sm transition-[translate,box-shadow,border-color] duration-300 hover:-translate-y-0.5 active:translate-y-px active:shadow-sm ${base}`}
    >
      <span
        className={`absolute inset-0 -translate-x-[101%] transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:translate-x-0 ${panel}`}
        aria-hidden="true"
      />
      {/* a candle, the toolkit's specimen */}
      <svg
        viewBox="0 0 20 20"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
        className={`relative z-10 transition-[translate,rotate,scale,color] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:-translate-y-0.5 group-hover:scale-110 group-hover:-rotate-12 ${hoverText}`}
      >
        <path d="M6 2v3M6 13v5M14 1v5M14 12v4" strokeLinecap="round" />
        <rect x="3.5" y="5" width="5" height="8" rx="0.5" />
        <rect
          x="11.5"
          y="6"
          width="5"
          height="6"
          rx="0.5"
          fill="currentColor"
        />
      </svg>
      <span
        className={`relative z-10 text-[15px] font-medium transition-colors duration-500 ${hoverText}`}
      >
        Open the terminal
      </span>
    </Link>
  )
}

function TextAction({
  href,
  children,
  dark = false,
}: {
  href: string
  children: React.ReactNode
  dark?: boolean
}) {
  return (
    <a
      href={href}
      className={`group inline-flex min-h-12 items-center gap-2 text-[15px] font-medium underline decoration-1 underline-offset-[6px] transition-colors duration-300 active:scale-[0.985] ${
        dark
          ? "text-white decoration-white/30 hover:decoration-white"
          : "text-[#111] decoration-black/25 hover:decoration-black"
      }`}
    >
      {children}
      <HugeiconsIcon
        icon={ArrowUpRight01Icon}
        size={16}
        strokeWidth={1.5}
        className="transition-transform duration-150 group-hover:translate-x-[3px]"
        aria-hidden="true"
      />
    </a>
  )
}

function SectionLabel({
  n,
  children,
  dark = false,
}: {
  n: string
  children: React.ReactNode
  dark?: boolean
}) {
  return (
    <p className="font-mono text-[10px] tracking-[0.2em] uppercase md:text-[11px]">
      <span className={dark ? "text-[#9a9a9a]" : "text-[#666]"}>[ {n} ]</span>{" "}
      <span className={`font-bold ${dark ? "text-white" : "text-[#111]"}`}>
        {children}
      </span>
    </p>
  )
}

/** sent.dm's blueprint frame: two hairlines in the page margin with a cross at each top corner,
 *  drawn as a background layer so the content keeps the page's one container. */
function Frame() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      <div className="relative mx-auto h-full max-w-[1440px]">
        <div className="absolute inset-y-0 right-3 left-3 border-x border-[#e4e4e4] md:right-10 md:left-10">
          <span className="rl-cross top-0 -left-[7px]" />
          <span className="rl-cross top-0 -right-[7px]" />
        </div>
      </div>
    </div>
  )
}

const H2 =
  "font-serif text-[2.2rem] leading-[1.08] font-light tracking-[-0.015em] md:text-[3.4rem]"
// "Abstract blue waveforms on white" by Robertas Pezas, Pexels (Pexels licence: free for commercial
// use, no credit required). https://www.pexels.com/video/abstract-blue-waveforms-on-white-background-36324409/
const HERO_VIDEO = "/video/hero.mp4"

const FOOTER_COLUMNS: Array<{
  title: string
  links: Array<{ label: string; href?: string; to?: "/terminal" }>
}> = [
  {
    title: "Product",
    links: [
      { label: "Terminal", to: "/terminal" },
      { label: "Pipeline", href: "#pipeline" },
      { label: "Analysis modules", href: "#lenses" },
      { label: "Chart combos", href: "#combos" },
      { label: "Wallet check", href: "#wallet" },
    ],
  },
  {
    title: "Project",
    links: [
      { label: "GitHub", href: "https://github.com/RinNguyens/rinng" },
      { label: "README", href: "https://github.com/RinNguyens/rinng#readme" },
      {
        label: "Realtime plan",
        href: "https://github.com/RinNguyens/rinng/blob/main/docs/10-realtime-plan.md",
      },
      {
        label: "Forecasting",
        href: "https://github.com/RinNguyens/rinng/blob/main/docs/11-forecasting.md",
      },
    ],
  },
  {
    title: "Data sources",
    links: [
      { label: "Binance public data", href: "https://data.binance.vision" },
      { label: "OKX public API", href: "https://www.okx.com/docs-v5/en/" },
      { label: "DefiLlama prices", href: "https://defillama.com/docs/api" },
      { label: "dRPC public nodes", href: "https://drpc.org" },
    ],
  },
]

const ROWS = [
  { n: "01", label: "Collect", href: "#pipeline" },
  { n: "02", label: "Analyse", href: "#lenses" },
  { n: "03", label: "Check a wallet", href: "#wallet" },
]

function MotionToggle({
  on,
  onToggle,
  dark = false,
}: {
  on: boolean
  onToggle: () => void
  dark?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={!on}
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 font-mono text-[10px] tracking-widest uppercase transition-colors duration-150 ${
        dark ? "text-[#bbb] hover:text-white" : "text-[#333] hover:text-black"
      }`}
    >
      <HugeiconsIcon
        icon={on ? PauseIcon : PlayIcon}
        size={14}
        aria-hidden="true"
      />
      {on ? "Pause motion" : "Play motion"}
    </button>
  )
}

// ---- the page -------------------------------------------------------------------------------
export function Landing() {
  const reduced = useReducedMotion()
  const [motion, setMotion] = useState(true)
  const moving = motion && !reduced
  const [menuOpen, setMenuOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [pulses, setPulses] = useState(true)
  const [lens, setLens] = useState(0)
  const [cycleHeld, setCycleHeld] = useState(false)
  const [cycleOff, setCycleOff] = useState(false)
  const [copied, setCopied] = useState(false)
  const nav = useRef<HTMLElement>(null)
  const [navH, setNavH] = useState(0)

  // the header lies over the hero; the hero keeps one screen and starts its copy below it
  useEffect(() => {
    const el = nav.current
    if (!el) return
    const ro = new ResizeObserver(() => setNavH(el.offsetHeight))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (cycleHeld || cycleOff || !moving) return
    const t = window.setTimeout(
      () => setLens((i) => (i + 1) % LENSES.length),
      4000
    )
    return () => window.clearTimeout(t)
  }, [lens, cycleHeld, cycleOff, moving])

  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false)
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [menuOpen])

  const copyCommands = async () => {
    try {
      await navigator.clipboard.writeText(COMMANDS.map(([c]) => c).join("\n"))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  const lensNo = String(lens + 1).padStart(2, "0")
  const navLink =
    "inline-flex min-h-6 items-center text-[#333] underline-offset-4 transition-colors duration-150 hover:text-black hover:underline"

  return (
    <>
      <a
        href="#pipeline"
        className="sr-only z-[70] rounded-md bg-[#111] px-4 py-3 font-mono text-xs tracking-widest text-white uppercase focus:not-sr-only focus:fixed focus:top-4 focus:left-4"
      >
        Skip to content
      </a>

      {/* ============ NAV: the dotted wordmark and the NHM columns ============ */}
      <header ref={nav} className="nav absolute inset-x-0 top-0 z-20">
        <div className="wrap pt-4">
          <a
            href="#top"
            aria-label="rinng, back to top"
            className="relative block"
            style={{ aspectRatio: dotAspect(0.08) }}
          >
            <DotField running={moving} reduced={reduced} padY={0.08} />
          </a>
          <div
            className="rl-in mt-4 flex items-start justify-between font-mono text-[10px] tracking-[0.2em] uppercase md:text-[11px]"
            style={{ ["--d" as string]: "500ms" }}
          >
            <p className="shrink-0 pr-5 leading-relaxed md:w-[15%] md:pr-0">
              Quant
              <br />
              Analysis
              <br />
              Toolkit
            </p>
            <div
              className="hidden w-[5%] justify-center pt-[3px] md:flex"
              aria-hidden="true"
            >
              <Arrow />
            </div>
            <p className="flex-1 leading-relaxed text-[#333] md:w-[30%] md:flex-none">
              <span className="hidden md:inline">
                Reading crypto perpetuals
                <br />
                through structure, liquidity
                <br />
                and order flow.
              </span>
              <span className="md:hidden">
                Reading crypto
                <br />
                perpetuals through
                <br />
                structure and flow.
              </span>
            </p>
            <div
              className="hidden w-[5%] justify-center pt-[3px] md:flex"
              aria-hidden="true"
            >
              <Arrow />
            </div>
            <nav aria-label="Main" className="hidden w-[15%] md:block">
              <ul className="leading-relaxed">
                {NAV.map((l) => (
                  <li key={l.href}>
                    <a href={l.href} className={navLink}>
                      {l.label}
                    </a>
                  </li>
                ))}
                <li>
                  <Link
                    to="/terminal"
                    className={`${navLink} font-bold text-[#111]`}
                  >
                    Terminal ↗
                  </Link>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => setMotion((m) => !m)}
                    aria-pressed={!motion}
                    className={`${navLink} cursor-pointer gap-1.5 tracking-[0.2em] uppercase`}
                  >
                    <HugeiconsIcon
                      icon={motion ? PauseIcon : PlayIcon}
                      size={11}
                      aria-hidden="true"
                    />
                    {motion ? "Pause motion" : "Play motion"}
                  </button>
                </li>
              </ul>
            </nav>
            <button
              type="button"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              aria-controls="rl-menu"
              onClick={() => setMenuOpen((o) => !o)}
              className="group relative z-[60] -mt-3 -mr-1.5 flex h-11 w-11 shrink-0 cursor-pointer flex-col items-end justify-center gap-[6px] md:hidden"
            >
              <span
                className={`block h-[1.5px] bg-black transition-all duration-300 ${menuOpen ? "w-8 translate-y-[3.75px] rotate-45" : "w-8 group-hover:w-6"}`}
              />
              <span
                className={`block h-[1.5px] bg-black transition-all duration-300 ${menuOpen ? "w-8 -translate-y-[3.75px] -rotate-45" : "w-8 group-hover:w-10"}`}
              />
            </button>
          </div>
        </div>
        {menuOpen && (
          <div
            id="rl-menu"
            className="rl-in absolute top-full left-0 z-50 w-full border-b border-[#e4e4e4] bg-[#fcfcfc] shadow-xl md:hidden"
          >
            <nav aria-label="Mobile" className="wrap pt-2 pb-6">
              <ul className="font-mono text-sm tracking-[0.2em] uppercase">
                {NAV.map((l) => (
                  <li key={l.href}>
                    <a
                      href={l.href}
                      onClick={() => setMenuOpen(false)}
                      className="flex min-h-12 items-center text-[#333] hover:text-black hover:underline"
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
                <li>
                  <Link
                    to="/terminal"
                    className="flex min-h-12 items-center font-bold text-[#111] hover:underline"
                  >
                    Terminal ↗
                  </Link>
                </li>
                <li>
                  <MotionToggle
                    on={motion}
                    onToggle={() => setMotion((m) => !m)}
                  />
                </li>
              </ul>
            </nav>
          </div>
        )}
      </header>

      <main>
        {/* ============ HERO (Boomerang composition) ============ */}
        <section
          id="top"
          data-enter
          aria-labelledby="hero-h"
          className="hero relative flex min-h-svh flex-col overflow-hidden bg-white"
          style={{ paddingTop: navH }}
        >
          <BoomerangVideoBg
            src={HERO_VIDEO}
            running={moving}
            reduced={reduced}
          />
          <div
            className="pointer-events-none absolute inset-0 z-0 bg-[radial-gradient(ellipse_42%_34%_at_50%_44%,rgba(255,255,255,0.92),rgba(255,255,255,0.55)_55%,transparent_80%)]"
            aria-hidden="true"
          />

          <div className="wrap relative z-10 flex flex-1 flex-col items-center">
            <div className="flex flex-col items-center pt-10 text-center md:pt-2">
              <h1
                id="hero-h"
                className="font-serif text-4xl leading-[1.02] font-light tracking-tighter text-[#191919] sm:text-5xl md:text-6xl lg:text-[4.25rem]"
              >
                Quant analysis for
                <br />
                crypto perpetuals.
              </h1>
              <p className="mt-5 max-w-sm text-sm leading-relaxed text-[#191919]/75 sm:max-w-lg md:mt-6 md:text-base">
                rinng reads all ~790 USDT perps on Binance and OKX for
                structure, liquidity and order flow, on your machine.
              </p>
              <div className="mt-6 md:mt-7">
                <PrimaryAction />
              </div>
            </div>

            {/* the "what it does" panel, flush to the fold */}
            <div className="mt-auto w-full max-w-5xl pt-6">
              <div className="border border-b-0 border-gray-200 bg-white/90 px-5 pt-7 shadow-sm backdrop-blur-sm sm:px-8 md:px-12 md:pt-8">
                <div className="grid gap-6 sm:gap-8 md:grid-cols-2 md:gap-16">
                  <div>
                    <p className="text-[11px] font-medium tracking-[0.2em] text-[#191919]/70 uppercase">
                      What does rinng do?
                    </p>
                    <p className="mt-3 font-serif text-2xl leading-tight font-light tracking-tight sm:text-[1.75rem]">
                      One toolkit for <br className="hidden sm:block" />
                      reading the tape
                    </p>
                  </div>
                  <p className="self-end text-sm leading-relaxed text-[#191919]/85 md:text-[15px]">
                    An open-source quant toolkit for USDT perpetuals. It
                    collects public market data, keeps it on your disk, and
                    shows its work on every chart. No API keys, and it never
                    places an order.
                  </p>
                </div>
                <div
                  className="mt-5 h-px w-full bg-gray-200 sm:mt-6"
                  aria-hidden="true"
                />
                <ul className="grid gap-2 py-3 sm:grid-cols-3 sm:gap-3">
                  {ROWS.map((r) => (
                    <li key={r.n}>
                      <a
                        href={r.href}
                        className="group flex min-h-12 items-center justify-between bg-[#F4F3F3] px-4 py-3 transition-all duration-200 hover:bg-[#eaeaea] sm:px-6"
                      >
                        <span className="text-sm">
                          <span className="text-[#191919]/70">{r.n}</span>
                          <span
                            className="mx-2 text-[#191919]/60"
                            aria-hidden="true"
                          >
                            /
                          </span>
                          <span className="font-medium">{r.label}</span>
                        </span>
                        <HugeiconsIcon
                          icon={ArrowRight01Icon}
                          size={16}
                          className="text-gray-500 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-gray-800"
                          aria-hidden="true"
                        />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ============ PIPELINE (sent.dm blueprint) ============ */}
        <section
          id="pipeline"
          aria-labelledby="pipeline-h"
          className="relative flex min-h-svh flex-col border-t border-[#e4e4e4] bg-[#fcfcfc]"
        >
          <Frame />
          <div className="wrap relative flex flex-1 flex-col justify-between gap-6 pt-16 pb-[72px] md:pt-20">
            <div>
              <SectionLabel n="02">Pipeline</SectionLabel>
              <div className="mt-6 flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
                <h2 id="pipeline-h" className={`max-w-[820px] ${H2}`}>
                  One pipeline from exchange data to a full market read
                </h2>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                  <TextAction
                    href={`${GITHUB}/blob/main/docs/10-realtime-plan.md`}
                  >
                    How the collector works
                  </TextAction>
                  <button
                    type="button"
                    onClick={() => setPulses((p) => !p)}
                    aria-pressed={!pulses}
                    className="inline-flex min-h-11 cursor-pointer items-center gap-2 font-mono text-[10px] tracking-widest text-[#333] uppercase transition-colors duration-150 hover:text-black active:scale-[0.985]"
                  >
                    <HugeiconsIcon
                      icon={pulses && moving ? PauseIcon : PlayIcon}
                      size={14}
                      aria-hidden="true"
                    />
                    {pulses && moving ? "Pause the flow" : "Play the flow"}
                  </button>
                </div>
              </div>
            </div>

            <div className="rl-dots rl-dots--fade py-4" data-visual>
              <div className="mx-auto max-w-[1160px]">
                <Pipeline step={step} live={pulses && moving} />
              </div>
            </div>

            <ol className="grid gap-x-6 gap-y-2 md:grid-cols-4">
              {STEPS.map((s, i) => (
                <li key={s.title}>
                  <button
                    type="button"
                    onMouseEnter={() => setStep(i)}
                    onFocus={() => setStep(i)}
                    onClick={() => setStep(i)}
                    aria-pressed={step === i}
                    className="group relative block h-full w-full cursor-pointer py-3 text-left"
                  >
                    <span
                      className="absolute top-0 bottom-0 -left-3 w-px bg-[#e4e4e4] transition-colors duration-150 group-hover:bg-[#bbb]"
                      aria-hidden="true"
                    />
                    <span
                      className={`absolute top-0 bottom-0 -left-3 w-[2px] bg-[var(--rl-blue)] transition-opacity duration-300 ${step === i ? "opacity-100" : "opacity-0"}`}
                      aria-hidden="true"
                    />
                    <span className="font-mono text-[11px] tracking-wider text-[#111]">
                      {String(i + 1).padStart(2, "0")} — {s.title}
                    </span>
                    <span className="mt-2 block text-[14px] leading-[1.6] text-[#555]">
                      {s.text}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ============ LENSES (the NHM chapter panel, the page's moment) ============ */}
        <section
          id="lenses"
          aria-labelledby="lenses-h"
          className="relative flex min-h-svh flex-col bg-[#0a0a0a] text-white"
        >
          <div className="wrap flex flex-1 flex-col gap-8 pt-16 pb-[72px] md:pt-20">
            <div className="flex flex-col justify-between gap-8 xl:flex-row xl:items-end">
              <div>
                <SectionLabel n="03" dark>
                  Analysis modules
                </SectionLabel>
                <h2 id="lenses-h" className={`mt-6 max-w-[860px] ${H2}`}>
                  Nine analysis lenses on one chart, each computed on your
                  machine
                </h2>
              </div>
              <div className="shrink-0">
                <div className="mb-5 flex gap-2" aria-hidden="true">
                  {[Layers01Icon, WaveIcon, Target01Icon].map((icon, k) => (
                    <span
                      key={k}
                      className="flex h-11 w-11 items-center justify-center rounded-full border border-[#444] text-[#9a9a9a] transition-colors duration-300 hover:border-white hover:bg-white hover:text-black"
                    >
                      <HugeiconsIcon icon={icon} size={20} strokeWidth={1.3} />
                    </span>
                  ))}
                </div>
                <p className="mb-4 font-mono text-[10px] leading-relaxed tracking-widest text-[#9a9a9a] uppercase">
                  It describes the market
                  <br />
                  It does not trade it
                </p>
                <ul className="flex flex-wrap gap-2">
                  {["Open source", "Local-first", "Read-only"].map((t) => (
                    <li
                      key={t}
                      className="rounded-full border border-[#444] px-4 py-2 font-mono text-[10px] tracking-widest text-[#ccc] uppercase"
                    >
                      {t}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div
              className="grid flex-1 grid-cols-1 md:grid-cols-12 md:gap-x-6"
              onMouseEnter={() => setCycleHeld(true)}
              onMouseLeave={() => setCycleHeld(false)}
              onFocus={() => setCycleHeld(true)}
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget))
                  setCycleHeld(false)
              }}
            >
              <div
                className="relative flex min-h-[340px] flex-col justify-between border-b border-[#262626] pb-6 md:col-span-5 md:border-r md:border-b-0 md:pr-6 md:pb-0"
                data-visual
              >
                <span
                  className="text-xl tracking-[0.3em] text-[#777]"
                  aria-hidden="true"
                >
                  ***
                </span>
                <div className="relative my-4 flex-1">
                  <div className="absolute inset-0">
                    <SandSwap
                      index={lens}
                      reduced={reduced}
                      render={(i) => <LensDiagram index={i} />}
                    />
                  </div>
                </div>
                <p className="flex items-center gap-2 font-mono text-[10px] tracking-widest text-[#9a9a9a] uppercase">
                  <span className="tabular-nums">{lensNo}</span>
                  <span className="text-[#555]" aria-hidden="true">
                    /
                  </span>
                  <span>09</span>
                </p>
              </div>

              <div className="flex flex-col md:col-span-7">
                <div className="flex min-h-16 items-center justify-between gap-6 border-b border-[#262626] py-3">
                  <p className="text-[14px] leading-[1.5] text-[#cfcfcf]">
                    <span className="mr-3 font-mono text-[10px] tracking-widest text-[#9a9a9a] uppercase">
                      Lens {lensNo}
                    </span>
                    {LENSES[lens].line}
                  </p>
                  <button
                    type="button"
                    onClick={() => setCycleOff((o) => !o)}
                    aria-pressed={cycleOff}
                    className="inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-2 font-mono text-[10px] tracking-widest text-[#ccc] uppercase transition-colors duration-150 hover:text-white"
                  >
                    <HugeiconsIcon
                      icon={cycleOff || !moving ? PlayIcon : PauseIcon}
                      size={14}
                      aria-hidden="true"
                    />
                    {cycleOff || !moving ? "Play" : "Pause"}
                  </button>
                </div>
                <ul className="flex flex-1 flex-col">
                  {LENSES.map((l, i) => {
                    const active = i === lens
                    return (
                      <li key={l.name} className="flex flex-1">
                        <button
                          type="button"
                          aria-pressed={active}
                          onClick={() => setLens(i)}
                          className={`group flex min-h-12 w-full cursor-pointer items-center justify-between gap-6 border-b border-[#1f1f1f] py-2 text-left transition-colors duration-300 ${
                            active
                              ? "text-white"
                              : "text-[#8a8a8a] hover:text-[#dcdcdc]"
                          }`}
                        >
                          <span className="text-[1.2rem] font-medium tracking-tight md:text-[1.4rem]">
                            {l.name}
                          </span>
                          <HugeiconsIcon
                            icon={ArrowUpRight01Icon}
                            size={20}
                            strokeWidth={1}
                            className={`shrink-0 text-[#9a9a9a] transition-[opacity,translate] duration-300 ${active ? "translate-x-0 opacity-100" : "-translate-x-2 opacity-0"}`}
                            aria-hidden="true"
                          />
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ============ COMBOS ============ */}
        <section
          id="combos"
          aria-labelledby="combos-h"
          className="relative flex min-h-svh flex-col bg-[#fcfcfc]"
        >
          <Frame />
          <div className="wrap relative flex flex-1 flex-col gap-10 pt-16 pb-[72px] md:pt-20">
            <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
              <div>
                <SectionLabel n="04">Chart combos</SectionLabel>
                <h2 id="combos-h" className={`mt-6 max-w-[780px] ${H2}`}>
                  Seven chart combos, each built to answer one question
                </h2>
              </div>
              <p className="max-w-[300px] text-[14px] leading-[1.6] text-[#555]">
                Each opens as a tab of linked charts with a suggested reading
                order.
              </p>
            </div>
            <ul className="grid flex-1 gap-px overflow-hidden rounded-lg border border-[#e4e4e4] bg-[#e4e4e4] sm:grid-cols-2 lg:grid-cols-4">
              {COMBOS.map((c, i) => (
                <li key={c.id} className="flex">
                  <Link
                    to="/terminal"
                    className="group flex w-full flex-col justify-between gap-6 bg-[#fcfcfc] p-6 transition-[background-color,translate] duration-200 hover:-translate-y-0.5 hover:bg-white"
                  >
                    <div>
                      <p className="flex items-center justify-between gap-3 font-mono text-[10px] tracking-widest text-[#666] uppercase">
                        <span>
                          {String(i + 1).padStart(2, "0")} · {c.title}
                        </span>
                        <HugeiconsIcon
                          icon={ArrowUpRight01Icon}
                          size={16}
                          strokeWidth={1.5}
                          className="shrink-0 text-[#9a9a9a] transition-[translate,color] duration-150 group-hover:translate-x-[3px] group-hover:text-[var(--rl-blue)]"
                          aria-hidden="true"
                        />
                      </p>
                      <p className="mt-4 font-serif text-[1.35rem] leading-[1.25] font-light text-[#111]">
                        {c.question}
                      </p>
                    </div>
                    <p className="flex flex-wrap gap-1.5">
                      {c.charts.map((ch, k) => (
                        <span
                          key={k}
                          className="rounded border border-[#e0e0e0] bg-white px-2 py-1 font-mono text-[10px] text-[#555]"
                        >
                          {ch.lens} {ch.tf}
                        </span>
                      ))}
                    </p>
                  </Link>
                </li>
              ))}
              <li className="flex">
                <Link
                  to="/terminal"
                  className="group flex w-full flex-col justify-end gap-4 bg-[#111] p-6 text-white transition-[translate] duration-200 hover:-translate-y-0.5"
                >
                  <p className="font-mono text-[10px] tracking-widest text-[#aaa] uppercase">
                    In the terminal
                  </p>
                  <p className="font-serif text-[1.6rem] leading-[1.2] font-light">
                    Open a combo from the chart library
                    <HugeiconsIcon
                      icon={ArrowRight01Icon}
                      size={22}
                      strokeWidth={1.3}
                      className="ml-2 inline align-[-3px] transition-transform duration-150 group-hover:translate-x-[3px]"
                      aria-hidden="true"
                    />
                  </p>
                </Link>
              </li>
            </ul>
          </div>
        </section>

        {/* ============ WALLET CHECK ============ */}
        <section
          id="wallet"
          aria-labelledby="wallet-h"
          className="relative border-t border-[#e4e4e4] bg-[#fcfcfc]"
        >
          <Frame />
          <WalletSection
            label={<SectionLabel n="05">Wallet check</SectionLabel>}
            h2Class={H2}
            running={moving}
            reduced={reduced}
          />
        </section>

        {/* ============ QUICK START ============ */}
        <section
          id="start"
          aria-labelledby="start-h"
          className="relative border-t border-[#e4e4e4] bg-[#fcfcfc]"
        >
          <Frame />
          <div className="wrap relative grid items-start gap-12 pt-16 pb-20 md:grid-cols-12 md:gap-x-6 md:pt-20">
            <div className="flex flex-col gap-10 md:col-span-5">
              <div>
                <SectionLabel n="06">Quick start</SectionLabel>
                <h2 id="start-h" className={`mt-6 ${H2}`}>
                  From clone to live charts in six commands
                </h2>
              </div>
              <div>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-6">
                  {[
                    ["Runs on", "macOS or Linux"],
                    ["Needs", "uv, Node 22, pnpm"],
                    ["Data", "Public Binance and OKX"],
                    ["Licence", "MIT"],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt className="font-mono text-[10px] tracking-widest text-[#666] uppercase">
                        {k}
                      </dt>
                      <dd className="mt-1 text-[15px] font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-8 max-w-[420px] text-[13px] leading-[1.6] text-[#555]">
                  rinng only analyses and backtests. It never places an order,
                  and nothing it shows is investment advice.
                </p>
              </div>
            </div>

            <div
              className="app-frame flex flex-col overflow-hidden rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] shadow-[0_30px_60px_-30px_rgba(0,0,0,0.45)] md:col-span-7"
              data-visual
            >
              <div className="flex items-center justify-between border-b border-[#222] px-4">
                <span className="flex gap-1.5" aria-hidden="true">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#333]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#333]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#333]" />
                </span>
                <span className="font-mono text-[11px] text-[#9a9a9a]">
                  ~/rinng
                </span>
                <button
                  type="button"
                  onClick={copyCommands}
                  className="inline-flex min-h-11 cursor-pointer items-center gap-1.5 font-mono text-[11px] text-[#bbb] transition-colors duration-150 hover:text-white active:scale-[0.985]"
                >
                  <HugeiconsIcon
                    icon={copied ? Tick02Icon : Copy01Icon}
                    size={14}
                    aria-hidden="true"
                  />
                  {copied ? "Copied" : "Copy commands"}
                </button>
              </div>
              <pre className="flex-1 overflow-x-auto px-5 py-5 font-mono text-[12.5px] leading-[1.85] break-words whitespace-pre-wrap text-[#e6e6e6] sm:whitespace-pre md:text-[13px]">
                {COMMANDS.map(([cmd, note]) => (
                  <span key={cmd} className="block">
                    {note && (
                      <span className="block text-[#8f8f8f]"># {note}</span>
                    )}
                    <span className="text-[var(--rl-blue-soft)]">$ </span>
                    {cmd}
                  </span>
                ))}
                <span className="mt-4 block text-[#8f8f8f]">
                  # every command: uv run rinng &lt;command&gt; --help
                </span>
                {CLI.map(([cmd, what]) => (
                  <span key={cmd} className="block">
                    <span className="inline-block w-[10ch] text-[#e6e6e6]">
                      {cmd}
                    </span>
                    <span className="text-[#8f8f8f]">{what}</span>
                  </span>
                ))}
              </pre>
            </div>
          </div>
        </section>
      </main>

      {/* ============ CLOSING: one dark block on the page container ============ */}
      <footer
        className="closing relative flex min-h-svh flex-col bg-[#0a0a0a] text-[#cfcfcf]"
        aria-labelledby="closing-h"
      >
        <div className="wrap flex flex-1 flex-col">
          {/* the call */}
          <div className="grid gap-10 pt-16 pb-10 md:grid-cols-12 md:gap-x-6 md:pt-20">
            <div className="md:col-span-7">
              <SectionLabel n="07" dark>
                Start reading
              </SectionLabel>
              <h2 id="closing-h" className={`mt-6 text-white ${H2}`}>
                Read the next bar with the whole market in view
              </h2>
            </div>
            <div className="flex flex-col items-start gap-3 md:col-span-5 md:items-end md:justify-end">
              <PrimaryAction dark />
              <TextAction href={GITHUB} dark>
                Star rinng on GitHub
              </TextAction>
            </div>
          </div>

          {/* the index */}
          <div className="grid gap-10 border-t border-white/10 py-8 sm:grid-cols-2 md:grid-cols-12 md:gap-x-6">
            {FOOTER_COLUMNS.map((col) => (
              <nav
                key={col.title}
                aria-label={col.title}
                className="md:col-span-3"
              >
                <p className="font-mono text-[10px] tracking-widest text-[#8a8a8a] uppercase">
                  {col.title}
                </p>
                <ul className="mt-4 space-y-1">
                  {col.links.map((l) => (
                    <li key={l.label}>
                      {l.to ? (
                        <Link
                          to={l.to}
                          className="inline-flex min-h-9 items-center text-[15px] text-[#e6e6e6] underline-offset-4 transition-colors duration-150 hover:text-white hover:underline"
                        >
                          {l.label}
                        </Link>
                      ) : (
                        <a
                          href={l.href}
                          className="inline-flex min-h-9 items-center text-[15px] text-[#e6e6e6] underline-offset-4 transition-colors duration-150 hover:text-white hover:underline"
                        >
                          {l.label}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
            <div className="md:col-span-3">
              <p className="font-mono text-[10px] tracking-widest text-[#8a8a8a] uppercase">
                Read this first
              </p>
              <p className="mt-4 text-[14px] leading-[1.6] text-[#a8a8a8]">
                rinng only analyses and backtests. It never places an order, and
                nothing it shows is investment advice.
              </p>
            </div>
          </div>

          {/* the wordmark, held to the bottom of the screen */}
          <div
            className="relative mt-auto border-t border-white/10 py-6"
            style={{ aspectRatio: dotAspect(0.32) }}
          >
            <DotField
              tone="dark"
              wave
              running={moving}
              reduced={reduced}
              padY={0.32}
            />
            <span className="sr-only">rinng</span>
          </div>

          {/* the bar */}
          <div className="flex flex-col gap-2 border-t border-white/10 py-4 font-mono text-[10px] tracking-widest text-[#8a8a8a] uppercase sm:flex-row sm:items-center sm:justify-between">
            <p>© 2026 rinng contributors · MIT licence</p>
            <div className="flex flex-wrap items-center gap-x-6">
              <MotionToggle
                on={motion}
                onToggle={() => setMotion((m) => !m)}
                dark
              />
              <a
                href="#top"
                className="inline-flex min-h-11 items-center gap-2 text-[#bbb] transition-colors duration-150 hover:text-white"
              >
                Back to top ↑
              </a>
            </div>
          </div>
        </div>
      </footer>
    </>
  )
}
