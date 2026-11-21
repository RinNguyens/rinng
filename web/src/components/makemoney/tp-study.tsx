// Take-profit study (backend: makemoney_backtest.tp_study, re-run on a schedule): how far price
// goes in our favour after each signal, the net expectancy of every fixed take-profit on the
// data used to pick it and on data it never saw, and the full-simulator check of the best ones.
import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { ago, num, pct, tone } from "@/lib/format"
import { cn } from "@/lib/utils"
import { postJson } from "@/lib/http"

type CurvePt = {
  tp_r: number
  expectancy_r: number
  hit_rate: number
  trades: number
}
type M = {
  trades: number
  win_rate: number | null
  return_pct: number
  profit_factor: number | null
  max_drawdown_pct: number
  avg_r: number | null
}
type Combo = {
  name: string
  tp2_r: number
  tp1_r: number
  tp1_frac: number
  test: M
  full: M
}
type Study = {
  t: number
  trigger: string
  days: number
  tf: string
  mode: string
  from: number
  cut: number
  to: number
  current_tp: { tp2_r: number; tp1_r: number; tp1_frac: number }
  signals_train: number
  signals_test: number
  curve_train: Array<CurvePt>
  curve_test: Array<CurvePt>
  best_train: CurvePt | null
  best_on_test: CurvePt | null
  mfe_hist: Array<number>
  mfe_median: number | null
  stop_rate: number
  confirm: Array<Combo>
  pick: Combo | null
  checks: Record<string, boolean>
  adopt: boolean
}
type State = {
  running: boolean
  auto: boolean
  every_h: number
  next: number | null
  current: {
    tp2_r: number
    tp1_r: number
    tp1_frac: number
    tf: string
    mode: string
  }
  studies: Array<Study>
}

const exitName = (x: { tp2_r: number; tp1_r: number; tp1_frac: number }) =>
  x.tp1_frac
    ? `TP1 ${x.tp1_r}R (${Math.round(x.tp1_frac * 100)}%) + TP ${x.tp2_r}R`
    : `TP ${x.tp2_r}R`

export function TpStudy() {
  const [st, setSt] = useState<State | null>(null)
  const load = useCallback(
    () =>
      fetch("/api/makemoney/tp", { cache: "no-store" })
        .then((r) => r.json())
        .then(setSt)
        .catch(() => {}),
    []
  )
  useEffect(() => {
    load()
    const id = setInterval(load, st?.running ? 2000 : 30_000)
    return () => clearInterval(id)
  }, [load, st?.running])
  const run = () => postJson<State>("/api/makemoney/tp/run").then(setSt)

  const s = st?.studies[0]
  return (
    <div className="grid gap-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div>
          <div className="text-sm font-medium">Take-profit study</div>
          <div className="text-xs text-muted-foreground">
            {st
              ? `Live exits: ${exitName(st.current)} · ${st.current.tf} ${st.current.mode}`
              : "…"}
            {st?.auto && ` · re-runs every ${st.every_h}h`}
            {st?.next &&
              ` · next ${new Date(st.next * 1000).toLocaleTimeString(
                undefined,
                {
                  hour: "2-digit",
                  minute: "2-digit",
                  hour12: false,
                }
              )}`}
          </div>
        </div>
        <Button
          size="sm"
          className="ml-auto"
          onClick={run}
          disabled={st?.running}
        >
          {st?.running ? "Studying…" : "Find take-profit now"}
        </Button>
      </div>

      {!s && !st?.running && (
        <p className="text-sm text-muted-foreground">No study yet.</p>
      )}
      {s && (
        <>
          <Verdict s={s} />
          <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
            <CurveChart s={s} />
            <MfeHist s={s} />
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">
              Full simulator on the unseen part (
              {new Date(s.cut * 1000).toLocaleDateString()} → now) and on the
              whole {s.days} days
            </div>
            <table className="w-full text-sm whitespace-nowrap [&_td]:px-1.5 [&_td]:py-1 [&_th]:px-1.5 [&_th]:font-normal">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th>Exits</th>
                  <th className="text-right">Trades</th>
                  <th className="text-right">Win</th>
                  <th className="text-right">PF</th>
                  <th className="text-right">Unseen</th>
                  <th className="text-right">Whole</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {s.confirm.map((c) => (
                  <tr
                    key={c.name}
                    className={cn(
                      "border-t",
                      s.pick?.name === c.name && "bg-muted/50",
                      c.name === "current" && "text-muted-foreground"
                    )}
                  >
                    <td className="font-sans">
                      {c.name === "current"
                        ? `current (${exitName(c)})`
                        : c.name}
                      {s.pick?.name === c.name && " ← best"}
                    </td>
                    <td className="text-right">{c.test.trades}</td>
                    <td className="text-right">
                      {c.test.win_rate == null
                        ? "–"
                        : `${num(c.test.win_rate, 0)}%`}
                    </td>
                    <td className="text-right">
                      {c.test.profit_factor == null
                        ? "–"
                        : num(c.test.profit_factor, 2)}
                    </td>
                    <td className={cn("text-right", tone(c.test.return_pct))}>
                      {pct(c.test.return_pct, 2)}
                    </td>
                    <td className={cn("text-right", tone(c.full.return_pct))}>
                      {pct(c.full.return_pct, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
              {Object.entries(s.checks).map(([k, ok]) => (
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
          {st.studies.length > 1 && (
            <div>
              <div className="mb-1 text-xs text-muted-foreground">
                Earlier runs
              </div>
              <ul className="grid gap-0.5 text-xs">
                {st.studies.slice(1, 8).map((x) => (
                  <li key={x.t} className="flex gap-2 font-mono tabular-nums">
                    <span className="w-20 text-muted-foreground">
                      {ago(x.t)}
                    </span>
                    <span>
                      best {x.best_train ? `${x.best_train.tp_r}R` : "–"}
                    </span>
                    <span className={tone(x.best_on_test?.expectancy_r ?? 0)}>
                      unseen{" "}
                      {x.best_on_test
                        ? `${num(x.best_on_test.expectancy_r, 3)}R/trade`
                        : "–"}
                    </span>
                    <span
                      className={
                        x.adopt ? "text-emerald-500" : "text-muted-foreground"
                      }
                    >
                      {x.adopt ? "adopted" : "kept"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Verdict({ s }: { s: Study }) {
  const b = s.best_train
  const t = s.best_on_test
  const positive = (t?.expectancy_r ?? -1) > 0
  return (
    <div
      className={cn(
        "rounded-md px-3 py-2 text-sm",
        s.adopt
          ? "bg-emerald-500/10"
          : positive
            ? "bg-amber-500/10"
            : "bg-red-500/10"
      )}
    >
      {b && t ? (
        <>
          <b>Best take-profit: {b.tp_r}R</b> · hit {num(b.hit_rate, 0)}% ·{" "}
          {num(b.expectancy_r, 3)}R/trade where it was picked,{" "}
          <span className={tone(t.expectancy_r)}>
            {num(t.expectancy_r, 3)}R/trade
          </span>{" "}
          on data it never saw.{" "}
          {s.adopt
            ? `Adopted: the live exits are now ${s.pick ? exitName(s.pick) : ""}.`
            : positive
              ? "Positive on unseen data but did not pass every check, so the live exits stay."
              : "No take-profit makes this entry profitable after costs: the entries are what need work, not the TP."}
        </>
      ) : (
        "Not enough signals to study."
      )}
      <div className="mt-1 text-xs text-muted-foreground">
        {s.signals_train + s.signals_test} signals ({s.signals_train} to pick,{" "}
        {s.signals_test} unseen) · {num(s.stop_rate, 0)}% hit the stop · median
        best move {s.mfe_median != null ? `${num(s.mfe_median, 2)}R` : "–"} ·{" "}
        {ago(s.t)} ({s.trigger})
      </div>
    </div>
  )
}

function CurveChart({ s }: { s: Study }) {
  const W = 520
  const H = 200
  const P = 28
  const xs = s.curve_train.map((r) => r.tp_r)
  const ys = [...s.curve_train, ...s.curve_test]
    .map((r) => r.expectancy_r)
    .concat(0)
  const lo = Math.min(...ys)
  const hi = Math.max(...ys)
  const span = hi - lo || 1
  const x = (v: number) =>
    P + ((v - xs[0]) / (xs[xs.length - 1] - xs[0])) * (W - P - 8)
  const y = (v: number) => 8 + (1 - (v - lo) / span) * (H - 36)
  const path = (rows: Array<CurvePt>) =>
    rows
      .map(
        (r, i) =>
          `${i ? "L" : "M"}${x(r.tp_r).toFixed(1)},${y(r.expectancy_r).toFixed(1)}`
      )
      .join("")
  const cur = s.current_tp.tp2_r
  const best = s.best_train?.tp_r
  return (
    <div>
      <div className="mb-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
        <span>Net R per trade by take-profit (costs included)</span>
        <span className="text-sky-400">— picked on</span>
        <span className="text-amber-400">— unseen</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-52 w-full">
        <line
          x1={P}
          x2={W - 8}
          y1={y(0)}
          y2={y(0)}
          className="stroke-muted-foreground/50"
          strokeDasharray="4 4"
        />
        <text x={2} y={y(0) + 3} className="fill-muted-foreground text-[9px]">
          0R
        </text>
        {xs
          .filter((v) => Number.isInteger(v * 2))
          .map((v) => (
            <text
              key={v}
              x={x(v)}
              y={H - 6}
              textAnchor="middle"
              className="fill-muted-foreground text-[9px]"
            >
              {v}R
            </text>
          ))}
        <line
          x1={x(cur)}
          x2={x(cur)}
          y1={8}
          y2={H - 26}
          className="stroke-foreground/40"
          strokeDasharray="2 3"
        />
        <text
          x={x(cur) + 3}
          y={16}
          className="fill-muted-foreground text-[9px]"
        >
          current
        </text>
        {best != null && (
          <>
            <line
              x1={x(best)}
              x2={x(best)}
              y1={8}
              y2={H - 26}
              className="stroke-emerald-500/70"
            />
            <text
              x={x(best) + 3}
              y={28}
              className="fill-emerald-500 text-[9px]"
            >
              best {best}R
            </text>
          </>
        )}
        <path
          d={path(s.curve_train)}
          fill="none"
          strokeWidth={2}
          className="stroke-sky-400"
        />
        <path
          d={path(s.curve_test)}
          fill="none"
          strokeWidth={2}
          className="stroke-amber-400"
          strokeDasharray="5 3"
        />
        {s.curve_train.map((r) => (
          <circle
            key={r.tp_r}
            cx={x(r.tp_r)}
            cy={y(r.expectancy_r)}
            r={2}
            className="fill-sky-400"
          >
            <title>
              TP {r.tp_r}R · {num(r.expectancy_r, 3)}R/trade · hit{" "}
              {num(r.hit_rate, 0)}%
            </title>
          </circle>
        ))}
      </svg>
    </div>
  )
}

function MfeHist({ s }: { s: Study }) {
  const max = Math.max(...s.mfe_hist, 1)
  const total = s.mfe_hist.reduce((a, b) => a + b, 0) || 1
  const label = (i: number) =>
    i === 11 ? "5.5R+" : `${i * 0.5}–${(i + 1) * 0.5}R`
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">
        How far price went for us before the stop (best move, in R)
      </div>
      <div className="flex h-40 items-end gap-1">
        {s.mfe_hist.map((v, i) => (
          <div
            key={i}
            className="flex h-full flex-1 flex-col items-center justify-end gap-1"
            title={`${label(i)}: ${v} signals`}
          >
            <span className="font-mono text-[9px] text-muted-foreground">
              {num((v / total) * 100, 0)}%
            </span>
            <div
              className={cn(
                "w-full rounded-t",
                i < 2 ? "bg-red-500/60" : "bg-emerald-500/60"
              )}
              style={{ height: `${(v / max) * 100}%`, minHeight: v ? 2 : 0 }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9px] text-muted-foreground">
        <span>0R</span>
        <span>1R</span>
        <span>2.5R</span>
        <span>5.5R+</span>
      </div>
    </div>
  )
}
