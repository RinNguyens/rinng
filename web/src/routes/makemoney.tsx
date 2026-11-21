import { useCallback, useEffect, useState } from "react"
import { Link, createFileRoute } from "@tanstack/react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ago, num, pct, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"
import { TradeChart } from "@/components/makemoney/trade-chart"
import { TradeDesk } from "@/components/makemoney/trade-desk"
import { api } from "@/lib/api"
import { live } from "@/lib/live"
import { Backtest } from "@/components/makemoney/backtest"
import {
  LiveStatus,
  SignalJournal,
  SignalWatch,
  TrainingPanel,
} from "@/components/makemoney/live-panels"
import type { JournalEntry } from "@/components/makemoney/live-panels"

// MakeMoney: a simulated futures account that Claude Haiku trades long/short.
// Backend: src/rinng/makemoney.py (no exchange account is touched; everything is paper).

export const Route = createFileRoute("/makemoney")({
  component: MakeMoneyPage,
  head: () => ({ meta: [{ title: "MakeMoney · rinng" }] }),
})

type Config = {
  model: string
  symbols: Array<string>
  exchange: string
  starting_balance: number
  max_leverage: number
  risk_per_trade_pct: number
  max_positions: number
  interval_sec: number
  taker_fee_pct: number
  slippage_bps: number
  auto_signal: boolean
  notes: string
  api_key_set: boolean
  api_key_hint: string
}
type Position = {
  id?: number
  symbol: string
  side: "long" | "short"
  qty: number
  entry: number
  leverage: number
  margin: number
  stop: number
  take: number
  opened: number
  reason: string
  mark?: number
  upnl: number
  liq: number
  funding?: number
  tp1?: number | null
  be?: boolean
  deadline?: number | null
  source?: string
}
type Trade = Position & {
  exit: number
  closed: number
  pnl: number
  exit_reason: string
  margin_in?: number
  open_fee?: number
  exit_fee?: number
  fees?: number
  gross_pnl?: number
  roe_pct?: number
}
type Snap = {
  config: Config
  strategy: { rules: Array<string>; tp2_r: number; tf: string }
  running: boolean
  busy: boolean
  last_tick: number | null
  last_error: string | null
  balance: number
  equity: number
  return_pct: number
  win_rate: number | null
  positions: Array<Position>
  trades: Array<Trade>
  log: Array<{ t: number; msg: string }>
  equity_curve: Array<[number, number]>
  margin_used: number
  upnl: number
  realized: number
  realized_today: number
  signal_log: Array<JournalEntry>
  last_guard: number | null
  fees_paid: number
  funding_paid: number
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    cache: "no-store",
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) {
    let d = r.statusText
    try {
      d = (await r.json()).detail ?? d
    } catch {
      /* not JSON */
    }
    throw new Error(d)
  }
  return r.json() as Promise<T>
}

const SETTINGS_KEY = "rinng.makemoney.settings"

function MakeMoneyPage() {
  const [snap, setSnap] = useState<Snap | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(() => {
    try {
      return localStorage.getItem(SETTINGS_KEY) !== "hidden"
    } catch {
      return true
    }
  })
  const toggleSettings = () =>
    setShowSettings((v) => {
      try {
        localStorage.setItem(SETTINGS_KEY, v ? "hidden" : "shown")
      } catch {
        /* storage unavailable: the choice lasts for this page only */
      }
      return !v
    })

  // start the live price feed like the terminal shell does
  useEffect(() => {
    api
      .meta()
      .then((m) => live.configure(m.live))
      .catch(() => {})
  }, [])
  const firstSymbol = snap?.config.symbols[0]
  useEffect(() => {
    if (firstSymbol) live.select(firstSymbol, "binance")
  }, [firstSymbol])

  const load = useCallback(() => {
    call<Snap>("/api/makemoney")
      .then((s) => {
        setSnap(s)
        setErr(null)
      })
      .catch((e: Error) => setErr(e.message))
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [load])

  const act = async (action: string) => {
    if (
      action === "reset" &&
      !confirm("Reset the paper account to the starting balance?")
    )
      return
    setPending(action)
    try {
      setSnap(await call<Snap>(`/api/makemoney/${action}`, {}))
      setErr(null)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <Link
          to="/terminal"
          className="font-mono text-sm text-muted-foreground hover:text-foreground"
        >
          ← terminal
        </Link>
        <h1 className="text-lg font-semibold">MakeMoney</h1>
        <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">
          PAPER · Binance USDT-M simulation
        </span>
        <div className="ml-auto flex items-center gap-2">
          <StatusDot snap={snap} />
          {snap?.running ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => act("stop")}
              disabled={!!pending}
            >
              Stop
            </Button>
          ) : (
            <Button size="sm" onClick={() => act("start")} disabled={!!pending}>
              Start bot
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={toggleSettings}>
            {showSettings ? "Ẩn thiết lập" : "Hiện thiết lập"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => act("tick")}
            disabled={!!pending}
          >
            {pending === "tick" ? "Thinking…" : "Run one step"}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => act("reset")}
            disabled={!!pending}
          >
            Reset
          </Button>
        </div>
      </header>

      {(err || snap?.last_error) && (
        <div className="mx-4 mt-3 rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {err ?? snap?.last_error}
        </div>
      )}

      <main
        className={cn(
          "grid gap-4 p-4",
          showSettings && "lg:grid-cols-[360px_1fr]"
        )}
      >
        {showSettings && (
          <Settings snap={snap} onSaved={setSnap} onError={setErr} />
        )}
        <div className="grid content-start gap-4">
          {snap && (
            <LiveStatus
              start={snap.config.starting_balance}
              equity={snap.equity}
              balance={snap.balance}
              marginUsed={snap.margin_used}
              upnl={snap.upnl}
              realized={snap.realized}
              realizedToday={snap.realized_today}
              positions={snap.positions}
              running={snap.running}
              autoSignal={snap.config.auto_signal}
              tf={snap.strategy.tf}
            />
          )}
          {snap && snap.config.symbols.length > 0 && (
            <TradeDesk
              symbols={snap.config.symbols}
              positions={snap.positions}
              trades={snap.trades}
              log={snap.log}
              tf={snap.strategy.tf}
            />
          )}
          {snap && (
            <SignalWatch symbols={snap.config.symbols} tf={snap.strategy.tf} />
          )}
          <Card>
            <CardContent>
              <TradeChart
                symbols={snap?.config.symbols ?? []}
                positions={snap?.positions ?? []}
                trades={snap?.trades ?? []}
                autoSignal={snap?.config.auto_signal ?? false}
              />
            </CardContent>
          </Card>
          <Backtest
            rules={snap?.strategy.rules ?? []}
            equity={snap?.equity ?? 1000}
            riskPct={snap?.config.risk_per_trade_pct ?? 1}
            tp2R={snap?.strategy.tp2_r ?? 3}
          />
          <SignalJournal rows={snap?.signal_log ?? []} />
          <TrainingPanel />
          <EquityCurve
            curve={snap?.equity_curve ?? []}
            start={snap?.config.starting_balance ?? 1000}
          />
          <Positions rows={snap?.positions ?? []} />
          <Trades rows={snap?.trades ?? []} />
          <Log rows={snap?.log ?? []} />
        </div>
      </main>
    </div>
  )
}

function StatusDot({ snap }: { snap: Snap | null }) {
  const label = !snap
    ? "…"
    : snap.busy
      ? "thinking"
      : snap.running
        ? "running"
        : "stopped"
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span
        className={cn(
          "size-2 rounded-full",
          snap?.busy
            ? "animate-pulse bg-amber-500"
            : snap?.running
              ? "bg-emerald-500"
              : "bg-muted-foreground/40"
        )}
      />
      {label}
      {snap?.last_tick ? ` · Haiku ${ago(snap.last_tick)}` : ""}
      {snap?.last_guard ? ` · SL/TP check ${ago(snap.last_guard)}` : ""}
    </span>
  )
}

const MODELS = [
  { value: "claude-haiku-5-5", label: "Claude Haiku 5.5 — fast, cheapest" },
  { value: "claude-sonnet-5-5", label: "Claude Sonnet 5.5 — balanced" },
  { value: "claude-opus-5-5", label: "Claude Opus 5.5 — strongest" },
  { value: "claude-fable-5-2", label: "Claude Fable 5.2" },
]
const SOURCES = [
  { value: "binance", label: "Binance" },
  { value: "okx", label: "OKX" },
]
const MAJORS = ["BTC-USDT-PERP", "ETH-USDT-PERP"]

function Settings({
  snap,
  onSaved,
  onError,
}: {
  snap: Snap | null
  onSaved: (s: Snap) => void
  onError: (e: string | null) => void
}) {
  const cfg = snap?.config
  const [form, setForm] = useState<Partial<Record<string, string>>>({})
  const [key, setKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [universe, setUniverse] = useState<Array<{ id: string; base: string }>>(
    MAJORS.map((id) => ({ id, base: id.split("-")[0] }))
  )

  useEffect(() => {
    call<Array<{ id: string; base: string }>>("/api/makemoney/symbols")
      .then(setUniverse)
      .catch(() => {})
  }, [])

  const picked = (form.symbols ?? "").split(",").filter(Boolean)
  const setPicked = (v: Array<string>) =>
    setForm((f) => ({ ...f, symbols: v.join(",") }))
  const symbolItems = [
    ...picked
      .filter((id) => !universe.some((u) => u.id === id))
      .map((id) => ({ id, base: id.split("-")[0] })),
    ...universe,
  ]

  useEffect(() => {
    if (!cfg) return
    setForm((f) =>
      Object.keys(f).length
        ? f
        : {
            model: cfg.model,
            symbols: cfg.symbols.join(","),
            exchange: cfg.exchange,
            starting_balance: String(cfg.starting_balance),
            max_leverage: String(cfg.max_leverage),
            risk_per_trade_pct: String(cfg.risk_per_trade_pct),
            max_positions: String(cfg.max_positions),
            interval_sec: String(cfg.interval_sec),
            taker_fee_pct: String(cfg.taker_fee_pct),
            slippage_bps: String(cfg.slippage_bps),
            auto_signal: cfg.auto_signal ? "1" : "",
            notes: cfg.notes,
          }
    )
  }, [cfg])

  const set = (k: string) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const save = async () => {
    setSaving(true)
    try {
      await call("/api/makemoney/config", {
        api_key: key.trim(),
        model: (form.model ?? "").trim(),
        symbols: picked,
        exchange: form.exchange,
        starting_balance: Number(form.starting_balance),
        max_leverage: Number(form.max_leverage),
        risk_per_trade_pct: Number(form.risk_per_trade_pct),
        max_positions: Number(form.max_positions),
        interval_sec: Number(form.interval_sec),
        taker_fee_pct: Number(form.taker_fee_pct),
        slippage_bps: Number(form.slippage_bps),
        auto_signal: form.auto_signal === "1",
        notes: form.notes,
      })
      setKey("")
      onSaved(await call<Snap>("/api/makemoney"))
      onError(null)
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const field = (k: string, label: string, hint?: string, type = "text") => (
    <div className="grid gap-1">
      <Label htmlFor={`mm-${k}`}>{label}</Label>
      <Input
        id={`mm-${k}`}
        type={type}
        value={form[k] ?? ""}
        onChange={set(k)}
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>Thiết lập</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-1">
          <Label htmlFor="mm-key">Claude API key</Label>
          <Input
            id="mm-key"
            type="password"
            autoComplete="off"
            placeholder={
              cfg?.api_key_set
                ? `saved ${cfg.api_key_hint} — leave blank to keep`
                : "sk-ant-…"
            }
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Stored only on this machine in data/makemoney/config.json.
          </p>
        </div>
        <div className="grid gap-1">
          <Label>Model</Label>
          <Select
            items={MODELS}
            value={form.model ?? null}
            onValueChange={(v) =>
              v && setForm((f) => ({ ...f, model: String(v) }))
            }
          >
            <SelectTrigger aria-label="Model" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODELS.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Each step is one call to this model.
          </p>
        </div>
        <div className="grid gap-1">
          <Label>Symbols</Label>
          <Select multiple value={picked} onValueChange={(v) => setPicked(v)}>
            <SelectTrigger aria-label="Symbols" className="w-full">
              <span className="truncate">
                {picked.length
                  ? `${picked.length} selected — add or remove`
                  : "Choose coins…"}
              </span>
            </SelectTrigger>
            <SelectContent className="max-h-80" alignItemWithTrigger={false}>
              {symbolItems.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.base}
                  <span className="text-muted-foreground"> /USDT perp</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {picked.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setPicked(picked.filter((x) => x !== id))}
                className="rounded-full border px-2 py-0.5 text-xs hover:border-destructive hover:text-destructive"
                aria-label={`Remove ${id}`}
              >
                {id.split("-")[0]} ×
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Binance USDT perpetuals, highest 24h volume first.
          </p>
        </div>
        <div className="grid gap-1">
          <Label>Price source</Label>
          <Select
            items={SOURCES}
            value={form.exchange ?? null}
            onValueChange={(v) =>
              v && setForm((f) => ({ ...f, exchange: String(v) }))
            }
          >
            <SelectTrigger aria-label="Price source" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SOURCES.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Chart data Haiku reads. Fills always use the Binance order book.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {field(
            "starting_balance",
            "Starting $",
            "Applies on Reset",
            "number"
          )}
          {field("max_leverage", "Max leverage", undefined, "number")}
          {field("risk_per_trade_pct", "Risk / trade %", undefined, "number")}
          {field("max_positions", "Max positions", undefined, "number")}
        </div>
        {field(
          "interval_sec",
          "Step every (sec)",
          "Each step = one Haiku call; min 60",
          "number"
        )}
        <div className="grid grid-cols-2 gap-3">
          {field(
            "taker_fee_pct",
            "Taker fee %",
            "Binance regular: 0.05",
            "number"
          )}
          {field(
            "slippage_bps",
            "Slippage (bps)",
            "Past best bid/ask",
            "number"
          )}
        </div>
        <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
          <div className="grid gap-0.5">
            <Label htmlFor="mm-auto">Auto-trade 5m signals</Label>
            <p className="text-xs text-muted-foreground">
              Open a simulated order the moment a long/short signal closes.
              Haiku still manages every position while the bot runs.
            </p>
          </div>
          <Switch
            id="mm-auto"
            checked={form.auto_signal === "1"}
            onCheckedChange={(v) =>
              setForm((f) => ({ ...f, auto_signal: v ? "1" : "" }))
            }
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="mm-notes">Extra instructions</Label>
          <Textarea
            id="mm-notes"
            rows={3}
            value={form.notes ?? ""}
            onChange={set("notes")}
          />
        </div>
        <Button onClick={save} disabled={saving || !snap}>
          {saving ? "Saving…" : "Save settings"}
        </Button>
      </CardContent>
    </Card>
  )
}

function EquityCurve({
  curve,
  start,
}: {
  curve: Array<[number, number]>
  start: number
}) {
  const W = 800
  const H = 160
  const pts: Array<[number, number]> = curve.length ? curve : []
  if (pts.length < 2)
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Equity curve appears after a couple of steps.
        </CardContent>
      </Card>
    )
  const vals = pts.map((p) => p[1]).concat(start)
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const span = hi - lo || 1
  const x = (i: number) => (i / (pts.length - 1)) * W
  const y = (v: number) => H - ((v - lo) / span) * (H - 10) - 5
  const d = pts
    .map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`)
    .join("")
  const up = pts[pts.length - 1][1] >= start
  return (
    <Card>
      <CardContent>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-40 w-full"
          preserveAspectRatio="none"
        >
          <line
            x1={0}
            x2={W}
            y1={y(start)}
            y2={y(start)}
            className="stroke-muted-foreground/40"
            strokeDasharray="4 4"
          />
          <path
            d={d}
            fill="none"
            strokeWidth={2}
            className={up ? "stroke-emerald-500" : "stroke-red-500"}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </CardContent>
    </Card>
  )
}

function Side({ s }: { s: "long" | "short" }) {
  return (
    <span
      className={cn(
        "font-medium uppercase",
        s === "long" ? "text-emerald-500" : "text-red-500"
      )}
    >
      {s}
    </span>
  )
}

function Positions({ rows }: { rows: Array<Position> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Open positions</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Flat.</p>
        ) : (
          <table className="w-full min-w-[820px] text-sm whitespace-nowrap [&_td]:px-1.5 [&_th]:px-1.5 [&_th]:font-normal">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Lev</th>
                <th>Qty</th>
                <th>Entry</th>
                <th>Mark</th>
                <th>SL</th>
                <th>TP</th>
                <th>Liq</th>
                <th>Margin</th>
                <th>uPnL</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {rows.map((p) => (
                <tr key={p.symbol} title={p.reason} className="border-t">
                  <td className="py-1.5 text-muted-foreground">
                    #{p.id ?? "–"}
                  </td>
                  <td className="font-sans">
                    {p.symbol.replace("-USDT-PERP", "")}
                  </td>
                  <td>
                    <Side s={p.side} />
                  </td>
                  <td>{p.leverage}x</td>
                  <td>{p.qty}</td>
                  <td>{price(p.entry)}</td>
                  <td>{price(p.mark ?? p.entry)}</td>
                  <td>{price(p.stop)}</td>
                  <td>{price(p.take)}</td>
                  <td className="text-amber-500">{price(p.liq)}</td>
                  <td>${num(p.margin, 2)}</td>
                  <td className={tone(p.upnl)}>{num(p.upnl, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  )
}

const EXIT_LABEL: Record<string, string> = {
  "take-profit": "Take-profit",
  stop: "Stop-loss",
  liquidated: "Liquidated",
}

function hold(sec: number) {
  const m = Math.max(0, Math.round(sec / 60))
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  return h < 48 ? `${h}h ${m % 60}m` : `${Math.floor(h / 24)}d ${h % 24}h`
}

function stamp(t: number) {
  return new Date(t * 1000).toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

function Trades({ rows }: { rows: Array<Trade> }) {
  const [only, setOnly] = useState("all")
  const coins = Array.from(new Set(rows.map((t) => t.symbol)))
  const shown = only === "all" ? rows : rows.filter((t) => t.symbol === only)
  const total = (k: (t: Trade) => number) => shown.reduce((a, t) => a + k(t), 0)
  const net = total((t) => t.pnl)
  const wins = shown.filter((t) => t.pnl > 0).length
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle>Order history</CardTitle>
        <span className="text-xs text-muted-foreground">
          {shown.length} orders · {wins}W / {shown.length - wins}L
        </span>
        {coins.length > 1 && (
          <div className="ml-auto flex flex-wrap gap-1">
            {["all", ...coins].map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setOnly(c)}
                className={cn(
                  "rounded-md border px-2 py-0.5 font-mono text-xs",
                  only === c
                    ? "border-foreground bg-muted"
                    : "text-muted-foreground"
                )}
              >
                {c === "all" ? "All" : c.split("-")[0]}
              </button>
            ))}
          </div>
        )}
      </CardHeader>
      <CardContent className="max-h-[32rem] overflow-auto">
        {shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">No closed orders yet.</p>
        ) : (
          <table className="w-full min-w-[1100px] text-sm whitespace-nowrap">
            <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
              <tr className="[&>th]:px-1.5 [&>th]:py-1 [&>th]:font-normal">
                <th>#</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Opened</th>
                <th>Closed</th>
                <th>Held</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Lev</th>
                <th className="text-right">Entry</th>
                <th className="text-right">Exit</th>
                <th className="text-right">Margin</th>
                <th className="text-right">Gross PnL</th>
                <th className="text-right">Fees</th>
                <th className="text-right">Funding</th>
                <th className="text-right">Net PnL</th>
                <th className="text-right">ROE</th>
                <th>Closed by</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {shown.map((t) => {
                const margin = t.margin_in ?? t.margin
                const roe = t.roe_pct ?? (margin ? (t.pnl / margin) * 100 : 0)
                return (
                  <tr
                    key={`${t.id}-${t.closed}`}
                    className="border-t [&>td]:px-1.5 [&>td]:py-1.5"
                    title={t.reason}
                  >
                    <td className="text-muted-foreground">#{t.id ?? "–"}</td>
                    <td className="font-sans">
                      {t.symbol.replace("-USDT-PERP", "")}
                    </td>
                    <td>
                      <Side s={t.side} />
                    </td>
                    <td className="text-xs">{stamp(t.opened)}</td>
                    <td className="text-xs">{stamp(t.closed)}</td>
                    <td className="text-xs text-muted-foreground">
                      {hold(t.closed - t.opened)}
                    </td>
                    <td className="text-right">{t.qty}</td>
                    <td className="text-right">{t.leverage}x</td>
                    <td className="text-right">{price(t.entry)}</td>
                    <td className="text-right">{price(t.exit)}</td>
                    <td className="text-right">{num(margin, 2)}</td>
                    <td className={cn("text-right", tone(t.gross_pnl ?? 0))}>
                      {t.gross_pnl == null ? "–" : num(t.gross_pnl, 2)}
                    </td>
                    <td className="text-right text-muted-foreground">
                      {t.fees == null ? "–" : `-${num(t.fees, 3)}`}
                    </td>
                    <td className={cn("text-right", tone(t.funding ?? 0))}>
                      {num(t.funding ?? 0, 3)}
                    </td>
                    <td className={cn("text-right font-semibold", tone(t.pnl))}>
                      {t.pnl >= 0 ? "+" : ""}
                      {num(t.pnl, 2)}
                    </td>
                    <td className={cn("text-right", tone(roe))}>{pct(roe)}</td>
                    <td className="font-sans text-xs">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5",
                          t.exit_reason === "take-profit" &&
                            "bg-emerald-500/15 text-emerald-500",
                          t.exit_reason === "stop" &&
                            "bg-red-500/15 text-red-500",
                          t.exit_reason === "liquidated" &&
                            "bg-amber-500/15 text-amber-500",
                          !EXIT_LABEL[t.exit_reason] &&
                            "bg-muted text-muted-foreground"
                        )}
                      >
                        {EXIT_LABEL[t.exit_reason] ?? `Haiku: ${t.exit_reason}`}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot className="sticky bottom-0 border-t-2 bg-card font-mono text-xs tabular-nums">
              <tr className="[&>td]:px-1.5 [&>td]:py-1.5">
                <td colSpan={11} className="font-sans text-muted-foreground">
                  Total ({shown.length})
                </td>
                <td
                  className={cn(
                    "text-right",
                    tone(total((t) => t.gross_pnl ?? 0))
                  )}
                >
                  {num(
                    total((t) => t.gross_pnl ?? 0),
                    2
                  )}
                </td>
                <td className="text-right text-muted-foreground">
                  -
                  {num(
                    total((t) => t.fees ?? 0),
                    3
                  )}
                </td>
                <td
                  className={cn(
                    "text-right",
                    tone(total((t) => t.funding ?? 0))
                  )}
                >
                  {num(
                    total((t) => t.funding ?? 0),
                    3
                  )}
                </td>
                <td className={cn("text-right font-semibold", tone(net))}>
                  {net >= 0 ? "+" : ""}
                  {num(net, 2)}
                </td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        )}
      </CardContent>
    </Card>
  )
}

function Log({ rows }: { rows: Array<{ t: number; msg: string }> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Haiku log</CardTitle>
      </CardHeader>
      <CardContent className="max-h-96 overflow-auto">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Run a step to see decisions.
          </p>
        ) : (
          <ul className="grid gap-1.5 text-sm">
            {rows.map((r, i) => (
              <li key={i} className="grid grid-cols-[4.5rem_1fr] gap-2">
                <span className="text-xs text-muted-foreground">
                  {ago(r.t)}
                </span>
                <span>{r.msg}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
