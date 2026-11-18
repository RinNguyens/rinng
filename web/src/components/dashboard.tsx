import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  ArrowDownRight01Icon,
  ArrowUpRight01Icon,
  StarIcon,
} from "@hugeicons/core-free-icons"
import { ChartView } from "@/components/chart-view"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import type { Combo } from "@/lib/combos"
import type { ChartData, Instrument, Summary } from "@/lib/api"
import { CoinIcon, VenueIcon } from "@/components/coin-icon"
import { ComboShortcuts } from "@/components/combo-shortcuts"
import { LiveDesk } from "@/components/live-desk"
import { NewsCard } from "@/components/news"
import { useBarClose, useLiveQuote } from "@/lib/live"
import { ago, num, pct, price, tone } from "@/lib/format"
import { fmtVol } from "@/lib/overlay"
import { readStarred, toggleStarred } from "@/lib/starred"
import { browserStore } from "@/lib/terminal-nav"
import { PRESETS, fromPreset } from "@/lib/workspaces"
import type { PanelCfg } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

// ----------------------------------------------------------------- shared blocks

function Delta({ v, label }: { v: number | null; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-heading text-xs",
        tone(v)
      )}
    >
      <HugeiconsIcon
        icon={v != null && v < 0 ? ArrowDownRight01Icon : ArrowUpRight01Icon}
        className="size-3.5"
      />
      {pct(v)}
      <span className="ml-1 text-muted-foreground">{label}</span>
    </span>
  )
}

function Stat({
  label,
  value,
  sub,
  className,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  className?: string
}) {
  return (
    <Card size="sm" className={cn("gap-1.5", className)}>
      <CardContent className="space-y-1.5">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="font-heading text-xl font-medium tabular-nums">
          {value}
        </div>
        {sub ? (
          <div className="space-y-0.5 text-xs text-muted-foreground">{sub}</div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function Sparkline({ values }: { values: Array<number> }) {
  if (values.length < 2) return null
  const w = 320
  const h = 64
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const k = hi > lo ? h / (hi - lo) : 0
  const pts = values.map((v, i) => [
    (i / (values.length - 1)) * w,
    h - (v - lo) * k,
  ])
  const d = pts
    .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join("")
  const up = values[values.length - 1] >= values[0]
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className={cn("h-16 w-full", up ? "text-up" : "text-down")}
    >
      <defs>
        <linearGradient id="spark" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.25" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d}L${w},${h}L0,${h}Z`} fill="url(#spark)" />
      <path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

function Row({
  k,
  v,
  className,
}: {
  k: string
  v: ReactNode
  className?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{k}</span>
      <span className={cn("font-heading tabular-nums", className)}>{v}</span>
    </div>
  )
}

// ----------------------------------------------------------------- dashboard

export function Dashboard({
  symbol,
  exchange,
  instrument,
  onOpenCombo,
}: {
  symbol: string
  exchange: string
  instrument?: Instrument
  onOpenCombo: (combo: Combo) => void
}) {
  const base = instrument?.base ?? symbol.split("-")[0]
  const [s, setS] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starred, setStarred] = useState(() => readStarred(browserStore()))
  // Live quote between candle closes; the closed-candle summary reloads when 1H closes.
  const { tick, mark } = useLiveQuote(symbol, exchange)
  const [rev, setRev] = useState(0)
  useBarClose(symbol, exchange, "1h", () => setRev((n) => n + 1))

  useEffect(() => {
    setS(null)
  }, [symbol, exchange])

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .summary({ symbol, exchange })
      .then((d) => alive && setS(d))
      .catch((e: Error) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [symbol, exchange, rev])

  if (error) {
    return (
      <div className="grid flex-1 place-items-center text-sm text-destructive">
        {error}
      </div>
    )
  }
  if (!s) {
    return (
      <div className="grid grid-cols-12 gap-3">
        {Array.from({ length: 10 }, (_, i) => (
          <Skeleton
            key={i}
            className={cn(
              "h-36 rounded-2xl",
              i === 0 ? "col-span-4" : i < 5 ? "col-span-2" : "col-span-4"
            )}
          />
        ))}
      </div>
    )
  }

  const { price: p, derivatives: d } = s
  const watched = starred.includes(symbol)
  const close = tick?.price ?? p.close
  // Change vs. the reference candles of the summary, re-based on the live price.
  const rebase = (chg: number | null) =>
    chg == null ? null : (close / (p.close / (1 + chg / 100)) - 1) * 100
  const chg24 = rebase(p.chg_24h)
  const chg7 = rebase(p.chg_7d)
  const liveFunding =
    mark?.funding_rate != null ? mark.funding_rate * 100 : null
  const fundingPct = liveFunding ?? d.funding?.rate_pct ?? null

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-2">
      {/* ------------------------------------------------ stats row */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6 xl:grid-cols-12">
        <Card size="sm" className="col-span-2 md:col-span-6 xl:col-span-4">
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <CoinIcon symbol={base} size={22} />
              <span className="text-sm font-medium text-foreground">
                {instrument?.name ?? base}
              </span>
              <button
                type="button"
                aria-pressed={watched}
                aria-label={
                  watched ? "Remove from watchlist" : "Add to watchlist"
                }
                onClick={() => setStarred(toggleStarred(browserStore(), symbol))}
                className={cn(
                  "grid size-6 place-items-center rounded-full outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                  watched
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <HugeiconsIcon
                  icon={StarIcon}
                  className="size-4"
                  fill={watched ? "currentColor" : "none"}
                />
              </button>
              <span className="font-heading">{symbol}</span>
              <Badge variant="secondary" className="gap-1 text-[10px]">
                <VenueIcon id={exchange} size={11} />
                {exchange === "okx" ? "OKX" : "Binance"}
              </Badge>
              <span className="ml-auto font-heading">
                1H candle closed {ago(p.time + 3600)}
              </span>
            </div>
            <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
              <div className="font-heading text-4xl font-medium tracking-tight tabular-nums">
                {price(close)}
              </div>
              <div className="flex flex-col gap-0.5 pb-1">
                <Delta v={chg24} label="24h" />
                <Delta v={chg7} label="7d" />
              </div>
            </div>
            <Sparkline values={p.spark} />
            <div className="flex justify-between font-heading text-[11px] text-muted-foreground">
              <span>24h low {price(p.low_24h)}</span>
              <span>24h high {price(p.high_24h)}</span>
            </div>
          </CardContent>
        </Card>

        <Stat
          className="md:col-span-2 xl:col-span-2"
          label="Funding (per 8h)"
          value={
            <span className={tone(fundingPct)}>
              {fundingPct != null ? `${num(fundingPct, 4)}%` : "—"}
            </span>
          }
          sub={
            d.funding ? (
              <>
                <div>
                  {liveFunding != null ? "predicted · " : "last settled · "}
                  <FundingCountdown />
                </div>
                <div>≈ {pct((fundingPct ?? 0) * 3 * 365, 1)} / year</div>
                <div>7d avg {num(d.funding.avg_7d_pct, 4)}%</div>
                <div className="pt-1 text-[11px] leading-snug">
                  Positive: longs pay shorts.
                </div>
              </>
            ) : (
              "no data"
            )
          }
        />
        <Stat
          className="md:col-span-2 xl:col-span-2"
          label="Open interest"
          value={d.oi ? `${num(d.oi.base)} ${base}` : "—"}
          sub={
            d.oi ? (
              <>
                {d.oi.value ? <div>≈ ${fmtVol(d.oi.value, false)}</div> : null}
                <Delta v={d.oi.chg_24h} label="24h" />
                <br />
                <Delta v={d.oi.chg_7d} label="7d" />
              </>
            ) : (
              "no data"
            )
          }
        />
        <Stat
          className="md:col-span-2 xl:col-span-2"
          label="Long / short accounts"
          value={d.ls ? num(d.ls.ratio, 2) : "—"}
          sub={
            d.ls ? (
              <div className="space-y-1.5 pt-0.5">
                <div className="flex h-1.5 overflow-hidden rounded-full">
                  <span
                    className="bg-up"
                    style={{ width: `${d.ls.long_pct}%` }}
                  />
                  <span className="flex-1 bg-down" />
                </div>
                <div className="flex justify-between font-heading text-[11px]">
                  <span className="text-up">long {num(d.ls.long_pct, 1)}%</span>
                  <span className="text-down">
                    short {num(100 - d.ls.long_pct, 1)}%
                  </span>
                </div>
                <div className="text-[11px] leading-snug">
                  Ratio of accounts, not position size.
                </div>
              </div>
            ) : (
              "no data"
            )
          }
        />
        <Stat
          className="col-span-2 md:col-span-2 xl:col-span-2"
          label="24h taker delta"
          value={
            <span className={tone(p.delta_24h)}>{fmtVol(p.delta_24h)}</span>
          }
          sub={
            <>
              <div>Volume 24h {fmtVol(p.volume_24h, false)}</div>
              <div>
                Aggressive buys − aggressive sells (
                {num((Math.abs(p.delta_24h) / p.volume_24h) * 100, 1)}% volume)
              </div>
            </>
          }
        />
      </div>

      {/* ------------------------------------------------ live desk: 5m chart + agents */}
      <LiveDesk symbol={symbol} exchange={exchange} />

      <NewsCard base={base} />

      {/* ------------------------------------------------ projection + combo shortcuts */}
      <ProjectionPanel symbol={symbol} exchange={exchange} />

      <ComboShortcuts
        ids={["top-down", "value-liquidity", "positioning"]}
        onOpen={onOpenCombo}
      />

      <p className="px-1 text-[11px] text-muted-foreground">
        Figures describe market state from closed candles; not trading advice.
      </p>
    </div>
  )
}

// Binance and OKX settle BTC/ETH perp funding every 8h at 00:00, 08:00 and 16:00 UTC.
function FundingCountdown() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const period = 8 * 3600 * 1000
  const left = Math.floor((period - (now % period)) / 1000)
  const hh = String(Math.floor(left / 3600)).padStart(2, "0")
  const mm = String(Math.floor((left % 3600) / 60)).padStart(2, "0")
  const ss = String(left % 60).padStart(2, "0")
  return (
    <span className="font-heading tabular-nums">
      next in {hh}:{mm}:{ss}
    </span>
  )
}

// Projection: probability cone for the next 7 days on 4H, with how well it held up historically.
function ProjectionPanel({
  symbol,
  exchange,
}: {
  symbol: string
  exchange: string
}) {
  const [cfg] = useState<PanelCfg>(() => ({
    ...fromPreset(PRESETS[6]),
    days: 60,
  }))
  const [d, setD] = useState<ChartData | null>(null)
  const f = d?.forecast
  const st = d?.stats
  const levels = [...(f?.levels ?? [])].sort(
    (a, b) => b.probability - a.probability
  )
  return (
    <Card size="sm" className="shrink-0 gap-0 py-0">
      <div className="grid min-h-[440px] grid-cols-1 xl:grid-cols-[340px_1fr]">
        <div className="space-y-3 border-b border-foreground/10 p-4 xl:border-r xl:border-b-0">
          <div className="flex items-center gap-2">
            <span className="font-heading text-sm font-medium">Projection</span>
            <Badge variant="outline" className="font-heading text-[10px]">
              4H · next {f?.horizon ?? 42} candles
            </Badge>
          </div>
          {f ? (
            <>
              <div className="space-y-1.5">
                <Row k="Median after 7 days" v={price(f.end.q50)} />
                <Row
                  k="50% range"
                  v={`${price(f.end.q25)} – ${price(f.end.q75)}`}
                />
                <Row
                  k="80% range"
                  v={`${price(f.end.q10)} – ${price(f.end.q90)}`}
                />
                <Row
                  k="90% range"
                  v={`${price(f.end.q05)} – ${price(f.end.q95)}`}
                />
              </div>
              <div className="space-y-1.5">
                <div className="text-xs text-muted-foreground">
                  Chance of touching within 7 days
                </div>
                {levels.length ? (
                  levels.map((l) => (
                    <div key={l.label + l.price} className="space-y-0.5">
                      <div className="flex items-baseline justify-between text-xs">
                        <span>
                          <span style={{ color: l.color }}>{l.label}</span>{" "}
                          <span className="font-heading text-muted-foreground">
                            {price(l.price)}
                          </span>
                        </span>
                        <span className="font-heading tabular-nums">
                          {(l.probability * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-muted">
                        <span
                          className="block h-full rounded-full"
                          style={{
                            width: `${l.probability * 100}%`,
                            background: l.color,
                          }}
                        />
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No key level inside the projection window.
                  </p>
                )}
              </div>
            </>
          ) : (
            <Skeleton className="h-40 rounded-xl" />
          )}
          {st ? (
            <div className="space-y-1 rounded-lg bg-muted/50 p-2.5 text-[11px] leading-snug text-muted-foreground">
              <div className="font-medium text-foreground">
                How reliable is this?
              </div>
              <div>
                Re-run on {st.origins} past moments using only data available
                then: the 80% band contained the real outcome{" "}
                {(st.coverage["80"] * 100).toFixed(0)}% of the time, the 50%
                band {(st.coverage["50"] * 100).toFixed(0)}%.
              </div>
              <div>
                The median got the direction right{" "}
                {st.direction_hit == null
                  ? "—"
                  : `${(st.direction_hit * 100).toFixed(0)}%`}{" "}
                of the time, so treat the bands as a range of likely outcomes,
                not a direction call.
              </div>
            </div>
          ) : null}
        </div>
        <div className="flex min-h-[420px] flex-col">
          <ChartView
            cfg={cfg}
            symbol={symbol}
            exchange={exchange}
            onData={setD}
            hideStrip
          />
        </div>
      </div>
    </Card>
  )
}
