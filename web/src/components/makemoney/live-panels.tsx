import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ago, num, pct, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"

// Live account status, per-coin signal watch, the signal journal and continuous training.
// Backend: src/rinng/makemoney.py (snapshot, /analysis, /training).

export type LivePosition = {
  id?: number
  symbol: string
  side: "long" | "short"
  qty: number
  entry: number
  leverage: number
  margin: number
  stop: number
  take: number
  tp1?: number | null
  be?: boolean
  liq: number
  opened: number
  deadline?: number | null
  mark?: number
  upnl: number
  source?: string
}
export type JournalEntry = {
  t: number
  symbol: string
  side: "long" | "short"
  bar: number
  tf: string
  price: number
  stop: number
  tp1: number | null
  take: number
  reasons: Array<string>
  action: "opened" | "skipped" | "rejected"
  detail: string
  order_id: number | null
  result: number | null
  exit_reason?: string
}

const usd = (v: number, d = 2) => `${v < 0 ? "-" : ""}$${num(Math.abs(v), d)}`
const coin = (s: string) => s.split("-")[0]

/* ------------------------------------------------------------- live status */

export function LiveStatus({
  start,
  equity,
  balance,
  marginUsed,
  upnl,
  realized,
  realizedToday,
  positions,
  running,
  autoSignal,
  tf,
}: {
  start: number
  equity: number
  balance: number
  marginUsed: number
  upnl: number
  realized: number
  realizedToday: number
  positions: Array<LivePosition>
  running: boolean
  autoSignal: boolean
  tf: string
}) {
  const total = Math.max(equity, 1)
  const freePct = (balance / total) * 100
  const marginPct = (marginUsed / total) * 100
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle>Live trading</CardTitle>
        <span
          className={cn(
            "rounded px-2 py-0.5 text-xs",
            running || autoSignal
              ? "bg-emerald-500/15 text-emerald-500"
              : "bg-muted text-muted-foreground"
          )}
        >
          {autoSignal
            ? `auto-trading ${tf} signals`
            : "signals not auto-traded"}
          {running ? " · Haiku on" : " · Haiku off"}
        </span>
        <span className="ml-auto font-mono text-xs text-muted-foreground">
          started with {usd(start, 0)}
        </span>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Big
            k="Equity now"
            v={usd(equity)}
            sub={pct((equity / start - 1) * 100)}
            t={equity - start}
          />
          <Big k="Free cash" v={usd(balance)} />
          <Big
            k="In margin"
            v={usd(marginUsed)}
            sub={`${positions.length} open`}
          />
          <Big k="Unrealized" v={usd(upnl)} t={upnl} />
          <Big
            k="Realized"
            v={usd(realized)}
            sub={`today ${usd(realizedToday)}`}
            t={realized}
          />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>Where the money is</span>
            <span className="font-mono">
              free {num(freePct, 0)}% · margin {num(marginPct, 0)}%
            </span>
          </div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
            <div
              className="bg-emerald-500/70"
              style={{ width: `${Math.max(0, freePct)}%` }}
            />
            <div
              className="bg-sky-500/80"
              style={{ width: `${Math.max(0, marginPct)}%` }}
            />
          </div>
        </div>
        {positions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No open trade. The bot is waiting for a signal; the watch below
            shows how close each coin is.
          </p>
        ) : (
          <div className="grid gap-3">
            {positions.map((p) => (
              <PositionCard key={p.symbol} p={p} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function PositionCard({ p }: { p: LivePosition }) {
  const long = p.side === "long"
  const mark = p.mark ?? p.entry
  // a straight line from the stop (0%) to the take-profit (100%)
  const pos = (x: number) =>
    Math.min(100, Math.max(0, ((x - p.stop) / (p.take - p.stop)) * 100))
  const risk = Math.abs(p.entry - p.stop) * p.qty
  const reward = Math.abs(p.take - p.entry) * p.qty
  const left = p.deadline ? p.deadline - Date.now() / 1000 : null
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-mono text-muted-foreground">#{p.id ?? "–"}</span>
        <b>{coin(p.symbol)}</b>
        <span
          className={cn(
            "rounded px-1.5 text-xs font-semibold",
            long
              ? "bg-emerald-500/15 text-emerald-500"
              : "bg-red-500/15 text-red-500"
          )}
        >
          {long ? "LONG" : "SHORT"} x{p.leverage}
        </span>
        <span className="text-xs text-muted-foreground">
          {p.source === "signal" ? "auto signal" : "Haiku"} · opened{" "}
          {ago(p.opened)}
          {p.be && " · stop at break-even"}
        </span>
        <span
          className={cn(
            "ml-auto font-mono text-base font-semibold",
            tone(p.upnl)
          )}
        >
          {p.upnl >= 0 ? "+" : ""}
          {usd(p.upnl)}
        </span>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-gradient-to-r from-red-500/60 via-muted to-emerald-500/60">
        <Tick at={pos(p.entry)} label="entry" color="bg-sky-400" />
        {p.tp1 != null && !p.be && (
          <Tick at={pos(p.tp1)} label="TP1" color="bg-emerald-300" />
        )}
        <div
          className="absolute -top-1 size-4 -translate-x-1/2 rounded-full border-2 border-background bg-foreground"
          style={{ left: `${pos(mark)}%` }}
          title={`mark ${mark}`}
        />
      </div>
      <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-xs tabular-nums sm:grid-cols-4">
        <span>
          <span className="text-red-500">SL</span> {price(p.stop)} (
          {p.be ? "BE" : `-${usd(risk)}`})
        </span>
        <span>
          entry {price(p.entry)} → mark {price(mark)}
        </span>
        <span>
          <span className="text-emerald-500">TP</span> {price(p.take)} (+
          {usd(reward)})
        </span>
        <span>
          <span className="text-amber-500">liq</span> {price(p.liq)}
          {left != null &&
            ` · ${left > 0 ? `${num(left / 3600, 1)}h left` : "time stop"}`}
        </span>
      </div>
    </div>
  )
}

function Tick({
  at,
  label,
  color,
}: {
  at: number
  label: string
  color: string
}) {
  return (
    <div className="absolute top-0 -translate-x-1/2" style={{ left: `${at}%` }}>
      <div className={cn("h-2 w-0.5", color)} />
      <div className="mt-0.5 text-[10px] text-muted-foreground">{label}</div>
    </div>
  )
}

function Big({
  k,
  v,
  sub,
  t,
}: {
  k: string
  v: string
  sub?: string
  t?: number
}) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{k}</div>
      <div
        className={cn("font-mono text-lg tabular-nums", t != null && tone(t))}
      >
        {v}
      </div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

/* ------------------------------------------------------------- signal watch */

type Check = { label: string; ok: boolean; value: string }
type Watch = {
  price: number
  bias: string
  checklist: {
    bar: number
    ready: boolean
    long: Array<Check>
    short: Array<Check>
  } | null
  last_signal: { time: number; side: string; outcome: string } | null
}

export function SignalWatch({
  symbols,
  tf,
}: {
  symbols: Array<string>
  tf: string
}) {
  const [rows, setRows] = useState<Partial<Record<string, Watch>>>({})
  useEffect(() => {
    let alive = true
    const load = () =>
      Promise.all(
        symbols.map((s) =>
          fetch(`/api/makemoney/analysis?symbol=${encodeURIComponent(s)}`, {
            cache: "no-store",
          })
            .then((r) => r.json())
            .then((a) => [s, a.summary] as const)
            .catch(() => null)
        )
      ).then((xs) => {
        if (!alive) return
        const next: Partial<Record<string, Watch>> = {}
        for (const x of xs) if (x) next[x[0]] = x[1]
        setRows(next)
      })
    load()
    const id = setInterval(load, 15_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [symbols.join(",")])

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2">
        <CardTitle>Signal watch</CardTitle>
        <span className="text-xs text-muted-foreground">
          every condition on the last closed {tf} bar · a signal fires when one
          side is all green
        </span>
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-3">
        {symbols.map((s) => {
          const w = rows[s]
          const ck = w?.checklist
          return (
            <div key={s} className="rounded-lg border p-3">
              <div className="flex items-baseline gap-2">
                <b>{coin(s)}</b>
                <span className="font-mono text-sm">
                  {w ? price(w.price) : "…"}
                </span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {w?.bias}
                </span>
              </div>
              {ck?.ready ? (
                <div className="mt-2 grid gap-2">
                  {(["long", "short"] as const).map((side) => {
                    const items = ck[side]
                    const met = items.filter((c) => c.ok).length
                    const all = met === items.length
                    return (
                      <div
                        key={side}
                        className={cn(
                          "rounded-md border p-2",
                          all &&
                            (side === "long"
                              ? "border-emerald-500/70 bg-emerald-500/10"
                              : "border-red-500/70 bg-red-500/10")
                        )}
                      >
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span
                            className={
                              side === "long"
                                ? "font-semibold text-emerald-500"
                                : "font-semibold text-red-500"
                            }
                          >
                            {side === "long" ? "▲ LONG" : "▼ SHORT"}
                          </span>
                          <span
                            className={cn("font-mono", all && "font-semibold")}
                          >
                            {all ? "SIGNAL" : `${met}/${items.length}`}
                          </span>
                        </div>
                        <ul className="grid gap-0.5 text-xs">
                          {items.map((c) => (
                            <li
                              key={c.label}
                              className="flex justify-between gap-2"
                            >
                              <span
                                className={c.ok ? "" : "text-muted-foreground"}
                              >
                                {c.ok ? "✓" : "·"} {c.label}
                              </span>
                              <span className="font-mono text-muted-foreground">
                                {c.value}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                  })}
                  <div className="text-xs text-muted-foreground">
                    bar{" "}
                    {new Date(ck.bar * 1000).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })}
                    {w?.last_signal &&
                      ` · last signal ${w.last_signal.side} ${ago(w.last_signal.time)} (${w.last_signal.outcome})`}
                  </div>
                </div>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">Loading…</p>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------- journal */

export function SignalJournal({ rows }: { rows: Array<JournalEntry> }) {
  const opened = rows.filter((r) => r.action === "opened")
  const closed = opened.filter((r) => r.result != null)
  const wins = closed.filter((r) => (r.result ?? 0) > 0).length
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle>Signal journal</CardTitle>
        <span className="text-xs text-muted-foreground">
          {rows.length} caught · {opened.length} traded ·{" "}
          {rows.length - opened.length} skipped/rejected
          {closed.length > 0 &&
            ` · live hit rate ${num((wins / closed.length) * 100, 0)}% (${wins}/${closed.length})`}
        </span>
      </CardHeader>
      <CardContent className="max-h-96 overflow-auto">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No live signal caught yet. Every signal the bot sees lands here,
            with what it did and how the trade ended.
          </p>
        ) : (
          <table className="w-full min-w-[820px] text-sm whitespace-nowrap [&_td]:px-1.5 [&_td]:py-1.5 [&_th]:px-1.5 [&_th]:font-normal">
            <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
              <tr>
                <th>Caught</th>
                <th>Coin</th>
                <th>Side</th>
                <th className="text-right">Price</th>
                <th className="text-right">SL</th>
                <th className="text-right">TP</th>
                <th>Action</th>
                <th>Detail</th>
                <th className="text-right">Result</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {rows.map((r) => (
                <tr
                  key={`${r.symbol}-${r.bar}-${r.side}`}
                  className="border-t"
                  title={r.reasons.join("\n")}
                >
                  <td className="text-xs">{ago(r.t)}</td>
                  <td className="font-sans">{coin(r.symbol)}</td>
                  <td
                    className={
                      r.side === "long" ? "text-emerald-500" : "text-red-500"
                    }
                  >
                    {r.side.toUpperCase()}
                  </td>
                  <td className="text-right">{price(r.price)}</td>
                  <td className="text-right">{price(r.stop)}</td>
                  <td className="text-right">{price(r.take)}</td>
                  <td>
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 font-sans text-xs",
                        r.action === "opened" && "bg-sky-500/15 text-sky-400",
                        r.action === "skipped" &&
                          "bg-muted text-muted-foreground",
                        r.action === "rejected" &&
                          "bg-amber-500/15 text-amber-500"
                      )}
                    >
                      {r.action === "opened"
                        ? `opened #${r.order_id}`
                        : r.action}
                    </span>
                  </td>
                  <td className="font-sans text-xs text-muted-foreground">
                    {r.detail}
                  </td>
                  <td
                    className={cn(
                      "text-right",
                      r.result != null && tone(r.result)
                    )}
                  >
                    {r.result == null
                      ? r.action === "opened"
                        ? "open"
                        : "–"
                      : `${r.result >= 0 ? "+" : ""}${num(r.result, 2)} (${r.exit_reason})`}
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

/* ------------------------------------------------------------- training */

type M = {
  trades: number
  win_rate: number | null
  return_pct: number
  profit_factor: number | null
  max_drawdown_pct: number
}
type Run = {
  t: number
  seconds: number
  tested: number
  trigger: string
  days: number
  candidate: { tf: string; mode: string }
  candidate_rules: Array<string>
  candidate_train: M
  candidate_test: M
  candidate_full: M
  current: { tf: string; mode: string }
  current_test: M
  current_full: M
  checks: Record<string, boolean>
  adopt: boolean
}
type Training = {
  running: boolean
  auto: boolean
  every_h: number
  days: number
  tfs: Array<string>
  next: number | null
  current: { tf: string; mode: string; rules: Array<string> }
  runs: Array<Run>
}

export function TrainingPanel() {
  const [st, setSt] = useState<Training | null>(null)
  const load = useCallback(
    () =>
      fetch("/api/makemoney/training", { cache: "no-store" })
        .then((r) => r.json())
        .then(setSt)
        .catch(() => {}),
    []
  )
  useEffect(() => {
    load()
    const id = setInterval(load, st?.running ? 3000 : 20_000)
    return () => clearInterval(id)
  }, [load, st?.running])

  const run = () =>
    fetch("/api/makemoney/training/run", { method: "POST", cache: "no-store" })
      .then((r) => r.json())
      .then(setSt)

  const m = (x: M) => (
    <span className="font-mono tabular-nums">
      {x.trades}t · {x.win_rate == null ? "–" : `${num(x.win_rate, 0)}%`} ·{" "}
      <span className={tone(x.return_pct)}>{pct(x.return_pct, 1)}</span>
    </span>
  )

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle>Continuous training</CardTitle>
        <span className="text-xs text-muted-foreground">
          {st?.auto
            ? `every ${st.every_h}h on the last ${st.days} days · ${st.tfs.join(", ")}`
            : "automatic training is off"}
          {st?.next &&
            ` · next ${new Date(st.next * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })}`}
        </span>
        <Button
          size="sm"
          className="ml-auto"
          onClick={run}
          disabled={st?.running}
        >
          {st?.running ? "Training…" : "Train now"}
        </Button>
      </CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-xs text-muted-foreground">
          Each run searches setups on the first two thirds of the window and
          judges the winner on the last third it never saw. It replaces the live
          setup only if it makes money there (PF ≥ 1.1, ≥ 8 trades) and beats
          the current setup both there and over the whole window.
        </p>
        {st && (
          <div className="rounded-lg border p-3 text-sm">
            <div className="mb-1 text-xs text-muted-foreground">
              Live setup: {st.current.tf} {st.current.mode}
            </div>
            <ul className="grid gap-0.5 text-xs">
              {st.current.rules.map((x) => (
                <li key={x}>• {x}</li>
              ))}
            </ul>
          </div>
        )}
        {st?.running && (
          <p className="text-sm text-muted-foreground">
            Downloading fresh data and testing setups…
          </p>
        )}
        {st?.runs.length === 0 && !st.running && (
          <p className="text-sm text-muted-foreground">No training run yet.</p>
        )}
        {st?.runs.map((r) => (
          <div
            key={r.t}
            className={cn(
              "rounded-lg border p-3 text-sm",
              r.adopt ? "border-emerald-500/50" : ""
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-xs",
                  r.adopt
                    ? "bg-emerald-500/15 text-emerald-500"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {r.adopt ? "adopted" : "kept current"}
              </span>
              <span className="text-xs text-muted-foreground">
                {new Date(r.t * 1000).toLocaleString()} · {r.trigger} ·{" "}
                {r.tested} setups · {num(r.seconds, 0)}s
              </span>
            </div>
            <div className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
              <div>
                <div className="text-muted-foreground">
                  Best found: {r.candidate.tf} {r.candidate.mode}
                </div>
                <div>train {m(r.candidate_train)}</div>
                <div>unseen {m(r.candidate_test)}</div>
                <div>whole {m(r.candidate_full)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">
                  Current: {r.current.tf} {r.current.mode}
                </div>
                <div>unseen {m(r.current_test)}</div>
                <div>whole {m(r.current_full)}</div>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
              {Object.entries(r.checks).map(([k, ok]) => (
                <span
                  key={k}
                  className={cn(
                    "rounded px-1.5 py-0.5",
                    ok
                      ? "bg-emerald-500/10 text-emerald-500"
                      : "bg-red-500/10 text-red-500"
                  )}
                >
                  {ok ? "✓" : "✗"} {k}
                </span>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
