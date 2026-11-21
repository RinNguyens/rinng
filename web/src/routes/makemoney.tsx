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
import { Textarea } from "@/components/ui/textarea"
import { ago, num, pct, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"
import { TradeChart } from "@/components/makemoney/trade-chart"

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
  notes: string
  api_key_set: boolean
  api_key_hint: string
}
type Position = {
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
  funding: number
}
type Trade = Position & {
  exit: number
  closed: number
  pnl: number
  exit_reason: string
}
type Snap = {
  config: Config
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

function MakeMoneyPage() {
  const [snap, setSnap] = useState<Snap | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)

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

      <main className="grid gap-4 p-4 lg:grid-cols-[360px_1fr]">
        <Settings snap={snap} onSaved={setSnap} onError={setErr} />
        <div className="grid content-start gap-4">
          <Stats snap={snap} />
          <Card>
            <CardContent>
              <TradeChart
                symbols={snap?.config.symbols ?? []}
                positions={snap?.positions ?? []}
                trades={snap?.trades ?? []}
              />
            </CardContent>
          </Card>
          <EquityCurve
            curve={snap?.equity_curve ?? []}
            start={snap?.config.starting_balance ?? 1000}
          />
          <Positions rows={snap?.positions ?? []} />
          <div className="grid gap-4 xl:grid-cols-2">
            <Trades rows={snap?.trades ?? []} />
            <Log rows={snap?.log ?? []} />
          </div>
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
  const [form, setForm] = useState<Record<string, string>>({})
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
        model: form.model.trim(),
        symbols: picked,
        exchange: form.exchange,
        starting_balance: Number(form.starting_balance),
        max_leverage: Number(form.max_leverage),
        risk_per_trade_pct: Number(form.risk_per_trade_pct),
        max_positions: Number(form.max_positions),
        interval_sec: Number(form.interval_sec),
        taker_fee_pct: Number(form.taker_fee_pct),
        slippage_bps: Number(form.slippage_bps),
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
          <Select
            multiple
            value={picked}
            onValueChange={(v) => setPicked((v as Array<string>) ?? [])}
          >
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

function Stats({ snap }: { snap: Snap | null }) {
  const items = [
    ["Equity", snap ? `$${num(snap.equity, 2)}` : "–", null],
    ["Return", snap ? pct(snap.return_pct) : "–", snap?.return_pct ?? null],
    ["Available", snap ? `$${num(snap.balance, 2)}` : "–", null],
    ["Fees paid", snap ? `$${num(snap.fees_paid, 2)}` : "–", null],
    [
      "Funding",
      snap ? `$${num(snap.funding_paid, 2)}` : "–",
      snap?.funding_paid ?? null,
    ],
    ["Trades", snap ? String(snap.trades.length) : "–", null],
    [
      "Win rate",
      snap?.win_rate != null ? `${num(snap.win_rate, 0)}%` : "–",
      null,
    ],
  ] as const
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
      {items.map(([k, v, t]) => (
        <Card key={k} size="sm">
          <CardContent>
            <div className="text-xs text-muted-foreground">{k}</div>
            <div
              className={cn(
                "font-mono text-lg tabular-nums",
                t != null && tone(t)
              )}
            >
              {v}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
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
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
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
                  <td className="py-1.5 font-sans">{p.symbol}</td>
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

function Trades({ rows }: { rows: Array<Trade> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Closed trades</CardTitle>
      </CardHeader>
      <CardContent className="max-h-96 overflow-auto">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet.</p>
        ) : (
          <table className="w-full text-sm">
            <tbody className="font-mono tabular-nums">
              {rows.map((t) => (
                <tr
                  key={`${t.symbol}-${t.closed}`}
                  className="border-t"
                  title={t.reason}
                >
                  <td className="py-1.5 font-sans">
                    {t.symbol.replace("-USDT-PERP", "")}
                  </td>
                  <td>
                    <Side s={t.side} />
                  </td>
                  <td>
                    {price(t.entry)} → {price(t.exit)}
                  </td>
                  <td className="font-sans text-xs text-muted-foreground">
                    {t.exit_reason}
                  </td>
                  <td className={cn("text-right", tone(t.pnl))}>
                    {num(t.pnl, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
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
