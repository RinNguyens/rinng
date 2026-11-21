import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { num, pct, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"

// Strategy rules and a realistic $-account backtest (backend: src/rinng/makemoney_backtest.py).

type Group = Record<string, { trades: number; win_rate: number; pnl: number }>
type BtTrade = {
  symbol: string
  side: "long" | "short"
  opened: number
  closed: number
  entry: number
  exit: number
  qty: number
  gross: number
  fees: number
  funding: number
  pnl: number
  r: number
  exit_reason: string
  tp1: boolean
}
type Window = {
  from: number
  to: number
  trades: number
  win_rate: number | null
  return_pct: number
  max_drawdown_pct: number
  profit_factor: number | null
  avg_r: number | null
}
type Result = {
  start_balance: number
  end_equity: number
  net_pnl: number
  return_pct: number
  days: number
  trades: number
  win_rate: number | null
  tp1_rate: number | null
  avg_win: number | null
  avg_loss: number | null
  profit_factor: number | null
  expectancy: number | null
  avg_r: number | null
  max_drawdown_pct: number
  worst_losing_streak: number
  sharpe: number | null
  fees: number
  funding: number
  skipped: Record<string, number>
  by: { symbol: Group; side: Group; exit_reason: Group }
  trades_list: Array<BtTrade>
  equity_curve: Array<[number, number]>
  windows: Array<Window>
  strategy: {
    rules: Array<string>
    tp2_r: number
    tp1_frac: number
    tp1_r: number
  }
  account: {
    balance: number
    risk_pct: number
    leverage: number
    max_positions: number
    taker_fee: number
    slippage: number
  }
  symbols: Array<string>
  ran_at: number
}
type State = { running: boolean; error: string | null; result: Result | null }

const date = (t: number) =>
  new Date(t * 1000).toLocaleDateString(undefined, {
    month: "2-digit",
    day: "2-digit",
  })
const usd = (v: number | null | undefined, d = 2) =>
  v == null ? "–" : `${v < 0 ? "-" : ""}$${num(Math.abs(v), d)}`

export function Backtest({
  rules,
  equity,
  riskPct,
  tp2R,
}: {
  rules: Array<string>
  equity: number
  riskPct: number
  tp2R: number
}) {
  const [st, setSt] = useState<State | null>(null)
  const [days, setDays] = useState(60)

  const load = useCallback(
    () =>
      fetch("/api/makemoney/backtest", { cache: "no-store" })
        .then((r) => r.json())
        .then(setSt)
        .catch(() => {}),
    []
  )
  useEffect(() => {
    load()
  }, [load])
  useEffect(() => {
    if (!st?.running) return
    const id = setInterval(load, 2000)
    return () => clearInterval(id)
  }, [st?.running, load])

  const run = () =>
    fetch(`/api/makemoney/backtest/run?days=${days}`, {
      method: "POST",
      cache: "no-store",
    })
      .then((r) => r.json())
      .then(setSt)

  const r = st?.result
  const risk = (equity * riskPct) / 100
  const breakEven = 100 / (1 + tp2R)
  const positiveWindows = r?.windows.filter((w) => w.return_pct > 0).length ?? 0

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle>Strategy & backtest</CardTitle>
        <div className="ml-auto flex items-center gap-1.5">
          {[30, 60, 120].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={cn(
                "rounded-md border px-2 py-0.5 font-mono text-xs",
                days === d
                  ? "border-foreground bg-muted"
                  : "text-muted-foreground"
              )}
            >
              {d}d
            </button>
          ))}
          <Button size="sm" onClick={run} disabled={st?.running}>
            {st?.running ? "Running…" : "Run backtest"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        {/* rules + money per trade */}
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border p-3">
            <div className="mb-1.5 text-xs text-muted-foreground">
              Rules (live and backtest use the same code)
            </div>
            <ol className="grid list-decimal gap-1 pl-4 text-sm">
              {rules.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ol>
          </div>
          <div className="grid content-start gap-1.5 rounded-lg border p-3 text-sm">
            <div className="text-xs text-muted-foreground">
              Money per trade on the current account
            </div>
            <Row k="Equity">{usd(equity)}</Row>
            <Row k={`Risk per trade (${riskPct}%)`}>
              <span className="text-red-500">-{usd(risk)}</span> if the stop
              fills (fees included)
            </Row>
            <Row k={`Win at TP2 (${tp2R}R)`}>
              <span className="text-emerald-500">+{usd(risk * tp2R)}</span>{" "}
              before exit costs
            </Row>
            <Row k="Hit rate needed to break even">
              ≈ {num(breakEven, 0)}% (more after fees)
            </Row>
            <p className="pt-1 text-xs text-muted-foreground">
              Position size = risk ÷ (stop distance + slippage + both fees),
              rounded down to the Binance step size and capped by margin at the
              max leverage.
            </p>
          </div>
        </div>

        {st?.error && (
          <p className="text-sm text-destructive">
            Backtest failed: {st.error}
          </p>
        )}
        {!r && !st?.running && (
          <p className="text-sm text-muted-foreground">
            No backtest yet. Run one to replay the strategy on real Binance
            history with a $ account, fees, slippage and funding.
          </p>
        )}
        {st?.running && (
          <p className="text-sm text-muted-foreground">
            Downloading {days} days of 5m bars and funding, then replaying every
            signal…
          </p>
        )}

        {r && (
          <>
            <div
              className={cn(
                "rounded-lg border px-3 py-2 text-sm",
                r.net_pnl > 0 && positiveWindows === r.windows.length
                  ? "border-emerald-500/50 bg-emerald-500/10"
                  : r.net_pnl > 0
                    ? "border-amber-500/50 bg-amber-500/10"
                    : "border-red-500/50 bg-red-500/10"
              )}
            >
              <b>
                {usd(r.start_balance, 0)} → {usd(r.end_equity)} (
                {r.return_pct >= 0 ? "+" : ""}
                {num(r.return_pct, 1)}%)
              </b>{" "}
              over {num(r.days, 0)} days on{" "}
              {r.symbols.map((s) => s.split("-")[0]).join(", ")} ·{" "}
              {positiveWindows}/{r.windows.length} periods profitable ·{" "}
              {r.net_pnl > 0 && positiveWindows === r.windows.length
                ? "consistent edge in this sample"
                : r.net_pnl > 0
                  ? "profitable overall but not in every period: treat with caution"
                  : "no edge after costs in this sample"}
              <span className="block text-xs text-muted-foreground">
                Ran {new Date(r.ran_at * 1000).toLocaleString()} · risk{" "}
                {r.account.risk_pct}% · max {r.account.leverage}x ·{" "}
                {r.account.max_positions} positions · taker{" "}
                {num(r.account.taker_fee * 100, 3)}% · slippage{" "}
                {num(r.account.slippage * 10000, 1)} bps
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
              <Kpi k="Net PnL" v={usd(r.net_pnl)} t={r.net_pnl} />
              <Kpi k="Trades" v={String(r.trades)} />
              <Kpi
                k="Win rate"
                v={r.win_rate == null ? "–" : `${num(r.win_rate, 1)}%`}
                sub={r.tp1_rate ? `TP1 hit ${num(r.tp1_rate, 0)}%` : undefined}
              />
              <Kpi
                k="Profit factor"
                v={r.profit_factor == null ? "–" : num(r.profit_factor, 2)}
                t={r.profit_factor == null ? null : r.profit_factor - 1}
              />
              <Kpi
                k="Avg win / loss"
                v={`${usd(r.avg_win)} / ${usd(r.avg_loss)}`}
              />
              <Kpi
                k="Expectancy"
                v={`${usd(r.expectancy)}/trade`}
                t={r.expectancy}
                sub={r.avg_r == null ? undefined : `${num(r.avg_r, 2)}R`}
              />
              <Kpi
                k="Max drawdown"
                v={`${num(r.max_drawdown_pct, 1)}%`}
                sub={`worst streak ${r.worst_losing_streak}`}
              />
              <Kpi
                k="Costs"
                v={usd(-r.fees)}
                sub={`funding ${usd(r.funding)}`}
              />
            </div>

            <Curve curve={r.equity_curve} start={r.start_balance} />

            <div className="grid gap-3 lg:grid-cols-2">
              <div>
                <div className="mb-1 text-xs text-muted-foreground">
                  Stability: the same rules in each period
                </div>
                <table className="w-full text-sm whitespace-nowrap [&_td]:px-1.5 [&_td]:py-1 [&_th]:px-1.5 [&_th]:font-normal">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr>
                      <th>Period</th>
                      <th className="text-right">Trades</th>
                      <th className="text-right">Win</th>
                      <th className="text-right">PF</th>
                      <th className="text-right">Max DD</th>
                      <th className="text-right">Return</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono tabular-nums">
                    {r.windows.map((w) => (
                      <tr key={w.from} className="border-t">
                        <td>
                          {date(w.from)} – {date(w.to)}
                        </td>
                        <td className="text-right">{w.trades}</td>
                        <td className="text-right">
                          {w.win_rate == null ? "–" : `${num(w.win_rate, 0)}%`}
                        </td>
                        <td className="text-right">
                          {w.profit_factor == null
                            ? "–"
                            : num(w.profit_factor, 2)}
                        </td>
                        <td className="text-right">
                          {num(w.max_drawdown_pct, 1)}%
                        </td>
                        <td className={cn("text-right", tone(w.return_pct))}>
                          {pct(w.return_pct, 1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-3">
                <Breakdown title="By exit" g={r.by.exit_reason} />
                <Breakdown title="By side" g={r.by.side} />
                <Breakdown title="By coin" g={r.by.symbol} short />
              </div>
            </div>

            <div>
              <div className="mb-1 text-xs text-muted-foreground">
                Last {Math.min(40, r.trades_list.length)} simulated trades
                {r.skipped.max_positions +
                  r.skipped.busy +
                  r.skipped.too_small >
                  0 &&
                  ` · signals skipped: ${r.skipped.max_positions} max positions, ${r.skipped.busy} coin busy, ${r.skipped.too_small} below Binance minimum`}
              </div>
              <div className="max-h-72 overflow-auto">
                <table className="w-full min-w-[760px] text-sm whitespace-nowrap [&_td]:px-1.5 [&_td]:py-1 [&_th]:px-1.5 [&_th]:font-normal">
                  <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
                    <tr>
                      <th>Opened</th>
                      <th>Coin</th>
                      <th>Side</th>
                      <th className="text-right">Entry</th>
                      <th className="text-right">Exit</th>
                      <th className="text-right">Gross</th>
                      <th className="text-right">Fees</th>
                      <th className="text-right">Net</th>
                      <th className="text-right">R</th>
                      <th>Exit</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono tabular-nums">
                    {[...r.trades_list]
                      .reverse()
                      .slice(0, 40)
                      .map((t) => (
                        <tr
                          key={`${t.symbol}-${t.opened}`}
                          className="border-t"
                        >
                          <td className="text-xs">
                            {new Date(t.opened * 1000).toLocaleString(
                              undefined,
                              {
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                                hour12: false,
                              }
                            )}
                          </td>
                          <td className="font-sans">
                            {t.symbol.split("-")[0]}
                          </td>
                          <td
                            className={
                              t.side === "long"
                                ? "text-emerald-500"
                                : "text-red-500"
                            }
                          >
                            {t.side.toUpperCase()}
                          </td>
                          <td className="text-right">{price(t.entry)}</td>
                          <td className="text-right">{price(t.exit)}</td>
                          <td className={cn("text-right", tone(t.gross))}>
                            {num(t.gross, 2)}
                          </td>
                          <td className="text-right text-muted-foreground">
                            -{num(t.fees, 2)}
                          </td>
                          <td
                            className={cn(
                              "text-right font-semibold",
                              tone(t.pnl)
                            )}
                          >
                            {t.pnl >= 0 ? "+" : ""}
                            {num(t.pnl, 2)}
                          </td>
                          <td className={cn("text-right", tone(t.r))}>
                            {num(t.r, 2)}
                          </td>
                          <td className="font-sans text-xs">
                            {t.exit_reason}
                            {t.tp1 && t.exit_reason !== "tp1"
                              ? " (after TP1)"
                              : ""}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-right font-mono tabular-nums">{children}</span>
    </div>
  )
}

function Kpi({
  k,
  v,
  t,
  sub,
}: {
  k: string
  v: string
  t?: number | null
  sub?: string
}) {
  return (
    <div className="rounded-lg border px-2.5 py-2">
      <div className="text-xs text-muted-foreground">{k}</div>
      <div
        className={cn("font-mono text-sm tabular-nums", t != null && tone(t))}
      >
        {v}
      </div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

function Breakdown({
  title,
  g,
  short,
}: {
  title: string
  g: Group
  short?: boolean
}) {
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">{title}</div>
      <ul className="grid gap-1 text-xs">
        {Object.entries(g)
          .sort((a, b) => b[1].trades - a[1].trades)
          .map(([k, v]) => (
            <li
              key={k}
              className="flex justify-between gap-2 font-mono tabular-nums"
            >
              <span className="font-sans">{short ? k.split("-")[0] : k}</span>
              <span>
                {v.trades} · {num(v.win_rate, 0)}% ·{" "}
                <span className={tone(v.pnl)}>{usd(v.pnl, 0)}</span>
              </span>
            </li>
          ))}
      </ul>
    </div>
  )
}

function Curve({
  curve,
  start,
}: {
  curve: Array<[number, number]>
  start: number
}) {
  if (curve.length < 2) return null
  const W = 900
  const H = 170
  const vals = curve.map((p) => p[1]).concat(start)
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const span = hi - lo || 1
  const x = (i: number) => (i / (curve.length - 1)) * W
  const y = (v: number) => H - 6 - ((v - lo) / span) * (H - 12)
  const d = curve
    .map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`)
    .join("")
  const end = curve[curve.length - 1][1]
  const up = end >= start
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
        <span>
          Equity ({date(curve[0][0])} → {date(curve[curve.length - 1][0])})
        </span>
        <span className="font-mono">
          low {usd(lo, 0)} · high {usd(hi, 0)}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-44 w-full"
        preserveAspectRatio="none"
      >
        <line
          x1={0}
          x2={W}
          y1={y(start)}
          y2={y(start)}
          className="stroke-muted-foreground/40"
          strokeDasharray="4 4"
          vectorEffect="non-scaling-stroke"
        />
        <path
          d={`${d}L${W},${y(start)}L0,${y(start)}Z`}
          className={up ? "fill-emerald-500/10" : "fill-red-500/10"}
        />
        <path
          d={d}
          fill="none"
          strokeWidth={2}
          className={up ? "stroke-emerald-500" : "stroke-red-500"}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  )
}
