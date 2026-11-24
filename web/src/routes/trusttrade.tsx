import { useEffect, useMemo, useState } from "react"
import { Link, createFileRoute } from "@tanstack/react-router"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EquityChart } from "@/components/trusttrade/equity-chart"
import { DecisionChart } from "@/components/trusttrade/decision-chart"
import { DayPanel } from "@/components/trusttrade/day-panel"
import { num, pct, tone } from "@/lib/format"
import { cn } from "@/lib/utils"
import {
  BASELINES,
  LLM_VARIANTS,
  averageEquity,
  coin,
  grid,
  heat,
  isLLM,
  style,
  ttApi,
} from "@/lib/trusttrade"
import type { Decision, Metrics, RunDetail, RunSummary } from "@/lib/trusttrade"

// TrustTrade research runs (paper replication, arXiv 2603.22567). Backend:
// src/rinng/web/trusttrade.py reads TrustTrade/runs/<name>/ written by `rinng trusttrade backtest`.

type Search = { run?: string; symbol?: string; strategy?: string; day?: string }
const str = (v: unknown) => (typeof v === "string" && v ? v : undefined)

export const Route = createFileRoute("/trusttrade")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    run: str(s.run),
    symbol: str(s.symbol),
    strategy: str(s.strategy),
    day: str(s.day),
  }),
  component: TrustTradePage,
  head: () => ({ meta: [{ title: "TrustTrade · rinng" }] }),
})

const ALL = "all"
const MIN_DAYS = 30 // runs shorter than this (smoke tests) stay out of the cross-run mean
const DEFAULT_SHOWN = new Set<string>([...LLM_VARIANTS, "buy_hold"])

function TrustTradePage() {
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const set = (p: Partial<Search>) =>
    navigate({ search: (s: Search) => ({ ...s, ...p }), replace: true })

  const [runs, setRuns] = useState<Array<RunSummary> | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    ttApi
      .runs()
      .then(setRuns)
      .catch((e: Error) => setErr(e.message))
  }, [])

  const counted = useMemo(
    () => (runs ?? []).filter((r) => r.days >= MIN_DAYS),
    [runs]
  )
  const current = search.run ?? counted.at(-1)?.name ?? runs?.at(-1)?.name

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-3">
        <Link
          to="/terminal"
          className="font-mono text-sm text-muted-foreground hover:text-foreground"
        >
          ← terminal
        </Link>
        <h1 className="text-lg font-semibold">TrustTrade</h1>
        <span className="rounded bg-sky-500/15 px-2 py-0.5 text-xs text-sky-600 dark:text-sky-300">
          Nghiên cứu · arXiv 2603.22567
        </span>
        {runs && (
          <span className="ml-auto font-mono text-xs text-muted-foreground">
            {runs.length} lượt chạy trong TrustTrade/runs
          </span>
        )}
      </header>

      {err && (
        <div className="mx-4 mt-3 rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {err}
        </div>
      )}

      <main className="mx-auto grid max-w-[1400px] gap-4 p-4">
        <Intro />
        {runs && runs.length === 0 && (
          <Card>
            <CardContent className="text-sm text-muted-foreground">
              Chưa có lượt chạy nào trong TrustTrade/runs. Chạy{" "}
              <code className="font-mono">
                uv run rinng trusttrade backtest
              </code>{" "}
              trước.
            </CardContent>
          </Card>
        )}
        {runs && runs.length > 0 && (
          <ResearchGrid
            runs={runs}
            current={current}
            onPick={(run) => set({ run, day: undefined })}
          />
        )}
        {current && (
          <RunView
            key={current}
            name={current}
            symbol={search.symbol ?? ALL}
            strategy={search.strategy ?? "trusttrade"}
            day={search.day}
            set={set}
          />
        )}
      </main>
    </div>
  )
}

function Intro() {
  return (
    <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
      Tái lập TrustTrade trên crypto với Claude Haiku. Mỗi ngày 3 analyst đọc dữ
      liệu market và derivatives, tách thành các claim; bộ lọc đồng thuận chỉ
      giữ claim được nhiều analyst cùng nêu. Trader quyết định BUY/SELL/HOLD lúc
      00:00 UTC, khớp ở giá mở cửa, phí 10 bps, chỉ long. Các biến thể thêm dần
      từng thành phần: <b className="text-foreground">single</b> →{" "}
      <b className="text-foreground">multi</b> →{" "}
      <b className="text-foreground">consensus</b> →{" "}
      <b className="text-foreground">+ temporal</b> →{" "}
      <b className="text-foreground">trusttrade</b> (+ memory/reflection).
    </p>
  )
}

// ---------------------------------------------------------------------------- cross-run grid

function ResearchGrid({
  runs,
  current,
  onPick,
}: {
  runs: Array<RunSummary>
  current?: string
  onPick: (name: string) => void
}) {
  const [key, setKey] = useState<"cr_pct" | "mdd_pct">("cr_pct")
  const rows = useMemo(
    () => grid(runs, key, (r) => r.days >= MIN_DAYS),
    [runs, key]
  )
  const fmt = (v: number | null) =>
    v == null ? "—" : key === "cr_pct" ? pct(v, 1) : `${num(v, 1)}%`
  const cellBg = (v: number | null) =>
    key === "cr_pct" ? heat(v) : heat(v == null ? null : -v, 30)

  return (
    <Card size="sm">
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>Tất cả lượt chạy · trung bình 5 coin</CardTitle>
        <Segmented
          value={key}
          options={[
            { value: "cr_pct", label: "Lợi nhuận (CR)" },
            { value: "mdd_pct", label: "Max drawdown" },
          ]}
          onChange={(v) => setKey(v as "cr_pct" | "mdd_pct")}
        />
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 bg-card px-2 py-2 text-left text-xs font-medium text-muted-foreground">
                Chiến lược
              </th>
              {runs.map((r) => (
                <th key={r.name} className="px-1 py-1 align-bottom">
                  <button
                    type="button"
                    onClick={() => onPick(r.name)}
                    className={cn(
                      "grid w-full gap-0.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-muted",
                      r.name === current && "bg-muted ring-1 ring-foreground/20"
                    )}
                  >
                    <span className="font-mono text-xs font-medium text-foreground">
                      {r.name}
                    </span>
                    <span className="font-mono text-[10px] font-normal text-muted-foreground">
                      {r.start.slice(5)} → {r.end.slice(5)} · {r.days}d
                    </span>
                    <span className="flex gap-1 text-[10px] font-normal">
                      <Regime r={r} />
                      {r.blind && (
                        <span className="rounded bg-violet-500/15 px-1 text-violet-300">
                          blind
                        </span>
                      )}
                    </span>
                  </button>
                </th>
              ))}
              <th className="px-2 py-2 text-right align-bottom text-xs font-medium text-muted-foreground">
                TB các lượt ≥{MIN_DAYS}d
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.strategy}
                className={cn(
                  i === LLM_VARIANTS.length &&
                    "[&>td]:border-t [&>td]:border-border"
                )}
              >
                <td className="sticky left-0 bg-card px-2 py-1.5">
                  <StrategyName s={row.strategy} />
                </td>
                {runs.map((r) => (
                  <td key={r.name} className="px-1 py-0.5">
                    <div
                      className={cn(
                        "rounded px-2 py-1 text-right font-mono text-xs tabular-nums",
                        r.days < MIN_DAYS && "opacity-50"
                      )}
                      style={{ background: cellBg(row.cells[r.name]) }}
                    >
                      {fmt(row.cells[r.name])}
                    </div>
                  </td>
                ))}
                <td className="px-2 py-1.5 text-right font-mono text-xs font-semibold tabular-nums">
                  {fmt(row.mean)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-muted-foreground">
          Bấm vào tên lượt chạy để xem chi tiết. Mức nhiễu giữa hai lần lấy mẫu
          (bản thường so với blind) khoảng 0,8 điểm % cho trung bình 5 coin;
          chênh lệch nhỏ hơn mức này không đáng tin.
        </p>
      </CardContent>
    </Card>
  )
}

function Regime({ r }: { r: RunSummary }) {
  const bh = r.average.buy_hold?.cr_pct
  if (bh == null) return null
  return (
    <span
      className={cn(
        "rounded px-1",
        bh >= 0 ? "bg-up/15 text-up" : "bg-down/15 text-down"
      )}
    >
      {bh >= 0 ? "tăng" : "giảm"} {pct(bh, 0)}
    </span>
  )
}

function StrategyName({ s }: { s: string }) {
  const st = style(s)
  return (
    <span className="flex items-center gap-2 whitespace-nowrap">
      <span
        className="inline-block h-0.5 w-4 rounded"
        style={{
          background: st.dashed
            ? `repeating-linear-gradient(90deg, ${st.color} 0 4px, transparent 4px 6px)`
            : st.color,
          height: st.width + 1,
        }}
      />
      <span
        className={cn(
          "text-sm",
          isLLM(s) ? "text-foreground" : "text-muted-foreground"
        )}
      >
        {st.label}
      </span>
    </span>
  )
}

function Segmented({
  value,
  options,
  onChange,
}: {
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-0.5 rounded-lg bg-muted p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs transition-colors",
            o.value === value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------- one run

function RunView({
  name,
  symbol,
  strategy,
  day,
  set,
}: {
  name: string
  symbol: string
  strategy: string
  day?: string
  set: (p: Partial<Search>) => void
}) {
  const [run, setRun] = useState<RunDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    ttApi
      .run(name)
      .then(setRun)
      .catch((e: Error) => setErr(e.message))
  }, [name])

  if (err) return <p className="text-sm text-destructive">{err}</p>
  if (!run)
    return <p className="text-sm text-muted-foreground">Đang tải {name}…</p>

  const symbols = run.config.symbols
  const sym = symbol === ALL || !symbols.includes(symbol) ? ALL : symbol
  const metrics: Metrics =
    sym === ALL ? run.average : (run.per_symbol[sym] ?? {})

  return (
    <div className="grid gap-4">
      <RunInfo run={run} />
      <Card size="sm">
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Kết quả theo chiến lược</CardTitle>
          <Segmented
            value={sym}
            options={[
              { value: ALL, label: `TB ${symbols.length} coin` },
              ...symbols.map((s) => ({ value: s, label: coin(s) })),
            ]}
            onChange={(v) =>
              set({ symbol: v === ALL ? undefined : v, day: undefined })
            }
          />
        </CardHeader>
        <CardContent className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
          <MetricsTable
            metrics={metrics}
            strategy={strategy}
            onPick={(s) => set({ strategy: s })}
          />
          <EquityPanel run={run} symbol={sym} />
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <BehaviourCard run={run} />
        <AgreementCard run={run} />
      </div>
      <DecisionExplorer
        run={run}
        symbol={sym === ALL ? symbols[0] : sym}
        strategy={
          isLLM(strategy) || BASELINES.includes(strategy as never)
            ? strategy
            : "trusttrade"
        }
        day={day}
        set={set}
      />
    </div>
  )
}

function RunInfo({ run }: { run: RunDetail }) {
  const c = run.config
  const total = run.usage.total
  const kept = Object.entries(run.consensus)
  const items: Array<[string, React.ReactNode]> = [
    ["Giai đoạn", `${c.start} → ${c.end}`],
    ["Coin", c.symbols.map(coin).join(" · ")],
    ["Analyst", `${c.n_agents} × ${c.analyst_models.join(" + ")}`],
    ["Trader", c.trader_model],
    ["Phân bổ", c.allocation === "partial" ? "25/50/75/100%" : "toàn bộ"],
    ["Chế độ", c.blind ? "blind (ẩn tên, ngày, giá)" : "thường"],
    [
      "Chi phí",
      total
        ? `$${total.cost_usd.toFixed(2)} · ${num(total.calls)} lượt gọi mới`
        : "—",
    ],
    [
      "Claim được giữ",
      kept
        .map(([d, v]) => `${d} ${num(100 * v.avg_kept_share)}%`)
        .join(" · ") || "—",
    ],
  ]
  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl bg-foreground/10 ring-1 ring-foreground/10 sm:grid-cols-2 lg:grid-cols-4">
      {items.map(([k, v]) => (
        <div key={k} className="grid gap-0.5 bg-card px-4 py-3">
          <span className="text-[11px] text-muted-foreground">{k}</span>
          <span
            className="font-mono text-sm break-words"
            title={typeof v === "string" ? v : undefined}
          >
            {v}
          </span>
        </div>
      ))}
    </div>
  )
}

function MetricsTable({
  metrics,
  strategy,
  onPick,
}: {
  metrics: Metrics
  strategy: string
  onPick: (s: string) => void
}) {
  const rows = [...LLM_VARIANTS, ...BASELINES].flatMap((s) => {
    const m = metrics[s]
    return m ? [{ s, m }] : []
  })
  const scale = Math.max(1, ...rows.map(({ m }) => Math.abs(m.cr_pct)))
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[460px] text-sm">
        <thead>
          <tr className="text-xs text-muted-foreground">
            <th className="py-1.5 text-left font-medium">Chiến lược</th>
            <th className="py-1.5 text-left font-medium">CR</th>
            <th className="py-1.5 text-right font-medium">MDD</th>
            <th className="py-1.5 text-right font-medium">Sharpe</th>
            <th
              className="py-1.5 text-right font-medium"
              title="Tỷ lệ vốn nằm trong coin, trung bình"
            >
              Cầm coin
            </th>
            <th className="py-1.5 text-right font-medium">Lệnh</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ s, m }, i) => {
            return (
              <tr
                key={s}
                onClick={() => onPick(s)}
                className={cn(
                  "cursor-pointer hover:bg-muted/40",
                  s === strategy && "bg-muted/60",
                  i === LLM_VARIANTS.length &&
                    "[&>td]:border-t [&>td]:border-border"
                )}
              >
                <td className="py-1.5 pr-2">
                  <StrategyName s={s} />
                </td>
                <td className="w-[34%] py-1.5 pr-3">
                  <CrBar v={m.cr_pct} scale={scale} />
                </td>
                <td className="py-1.5 text-right font-mono text-xs tabular-nums">
                  {num(m.mdd_pct, 1)}%
                </td>
                <td
                  className={cn(
                    "py-1.5 text-right font-mono text-xs tabular-nums",
                    tone(m.sharpe)
                  )}
                >
                  {m.sharpe == null ? "—" : num(m.sharpe, 2)}
                </td>
                <td className="py-1.5 text-right font-mono text-xs text-muted-foreground tabular-nums">
                  {m.avg_exposure_pct == null
                    ? "—"
                    : `${num(m.avg_exposure_pct)}%`}
                </td>
                <td className="py-1.5 text-right font-mono text-xs text-muted-foreground tabular-nums">
                  {m.trades == null
                    ? "—"
                    : num(m.trades, Number.isInteger(m.trades) ? 0 : 1)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CrBar({ v, scale }: { v: number; scale: number }) {
  const w = (50 * Math.abs(v)) / scale
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 flex-1 rounded-full bg-muted/50">
        <div className="absolute inset-y-0 left-1/2 w-px bg-foreground/30" />
        <div
          className={cn(
            "absolute inset-y-0 rounded-full",
            v >= 0 ? "bg-up" : "bg-down"
          )}
          style={
            v >= 0
              ? { left: "50%", width: `${w}%` }
              : { right: "50%", width: `${w}%` }
          }
        />
      </div>
      <span
        className={cn(
          "w-16 text-right font-mono text-xs tabular-nums",
          tone(v)
        )}
      >
        {pct(v, 1)}
      </span>
    </div>
  )
}

function EquityPanel({ run, symbol }: { run: RunDetail; symbol: string }) {
  const [shown, setShown] = useState(DEFAULT_SHOWN)
  const equity = useMemo(
    () =>
      symbol === ALL
        ? averageEquity(
            Object.values(run.equity).filter((e) => e !== undefined)
          )
        : run.equity[symbol],
    [run, symbol]
  )
  if (!equity?.days.length)
    return (
      <p className="text-sm text-muted-foreground">Không có đường equity.</p>
    )
  const names = [...LLM_VARIANTS, ...BASELINES].filter(
    (s) => s in equity.series
  )
  const toggle = (s: string) =>
    setShown((cur) => {
      const next = new Set(cur)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  return (
    <div className="grid content-start gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-xs text-muted-foreground">
          Lợi nhuận tích luỹ{" "}
          {symbol === ALL ? "(danh mục chia đều các coin)" : coin(symbol)}
        </span>
        <span className="flex gap-2 text-[11px]">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => setShown(new Set(names))}
          >
            hiện tất cả
          </button>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => setShown(DEFAULT_SHOWN)}
          >
            mặc định
          </button>
        </span>
      </div>
      <EquityChart equity={equity} start={run.config.cash} shown={shown} />
      <div className="flex flex-wrap gap-1">
        {names.map((s) => {
          const st = style(s)
          const on = shown.has(s)
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggle(s)}
              className={cn(
                "flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] transition-opacity",
                !on && "opacity-40"
              )}
            >
              <span
                className="size-2 rounded-full"
                style={{ background: st.color }}
              />
              {st.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function BehaviourCard({ run }: { run: RunDetail }) {
  const rows = LLM_VARIANTS.flatMap((v) => {
    const b = run.behaviour[v]
    return b ? [{ v, b }] : []
  })
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Hành vi của trader</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {rows.map(({ v, b }) => {
          const seg = [
            { k: "BUY", n: b.buy, c: "bg-up" },
            { k: "SELL", n: b.sell, c: "bg-down" },
            { k: "HOLD", n: b.hold, c: "bg-muted-foreground/30" },
          ]
          return (
            <div key={v} className="grid gap-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <StrategyName s={v} />
                <span className="font-mono text-[11px] text-muted-foreground">
                  B{b.buy} · S{b.sell} · HOLD {num(b.hold_pct)}% · conf{" "}
                  {b.avg_confidence ?? "—"} · cầm coin {num(b.in_market_pct)}%
                  số ngày
                </span>
              </div>
              <div className="flex h-2 overflow-hidden rounded-full">
                {seg.map((s) => (
                  <div
                    key={s.k}
                    className={s.c}
                    style={{ width: `${(100 * s.n) / b.days}%` }}
                    title={`${s.k} ${s.n}`}
                  />
                ))}
              </div>
            </div>
          )
        })}
        <p className="text-xs text-muted-foreground">
          Haiku làm trader rất thận trọng: phần lớn các ngày là HOLD, kể cả
          trong giai đoạn tăng.
        </p>
      </CardContent>
    </Card>
  )
}

function AgreementCard({ run }: { run: RunDetail }) {
  const entries = Object.entries(run.agreement).flatMap(([d, a]) =>
    a ? [[d, a] as const] : []
  )
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Analyst có thật sự khác nhau?</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {entries.map(([dom, a]) => {
          const total = Object.values(a.stances).reduce((x, y) => x + y, 0)
          const order = ["bullish", "neutral", "bearish"] as const
          const col = {
            bullish: "bg-up",
            neutral: "bg-muted-foreground/40",
            bearish: "bg-down",
          }
          return (
            <div key={dom} className="grid gap-1.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <span className="text-sm capitalize">{dom}</span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  cùng stance {num(a.unanimous_pct)}% số ngày · bull vs bear{" "}
                  {num(a.split_pct)}%
                </span>
              </div>
              <div className="flex h-2 overflow-hidden rounded-full">
                {order.map((k) => (
                  <div
                    key={k}
                    className={col[k]}
                    style={{ width: `${(100 * (a.stances[k] ?? 0)) / total}%` }}
                    title={`${k} ${a.stances[k] ?? 0}`}
                  />
                ))}
              </div>
              <div className="flex gap-3 font-mono text-[10px] text-muted-foreground">
                {order.map((k) => (
                  <span key={k}>
                    {k} {num((100 * (a.stances[k] ?? 0)) / total)}%
                  </span>
                ))}
              </div>
            </div>
          )
        })}
        <p className="text-xs text-muted-foreground">
          Ba analyst cùng là Haiku nên gần như luôn đồng ý; bộ lọc đồng thuận vì
          vậy có rất ít thứ để loại. Đây là lý do chưa thấy được tác dụng riêng
          của consensus.
        </p>
      </CardContent>
    </Card>
  )
}

function DecisionExplorer({
  run,
  symbol,
  strategy,
  day,
  set,
}: {
  run: RunDetail
  symbol: string
  strategy: string
  day?: string
  set: (p: Partial<Search>) => void
}) {
  const [rows, setRows] = useState<Array<Decision>>([])
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    ttApi
      .decisions(run.name, symbol, strategy)
      .then((r) => alive && (setRows(r), setErr(null)))
      .catch((e: Error) => alive && setErr(e.message))
    return () => {
      alive = false
    }
  }, [run.name, symbol, strategy])

  const trades = rows.filter((r) => r.action !== "HOLD" && r.pct > 0)
  const picked =
    day && rows.some((r) => r.day === day)
      ? day
      : (trades.at(0)?.day ?? rows.at(0)?.day ?? null)
  const idx = rows.findIndex((r) => r.day === picked)
  const step = (d: number) => {
    const r = idx + d >= 0 ? rows.at(idx + d) : undefined
    if (r) set({ day: r.day })
  }

  return (
    <Card size="sm">
      <CardHeader className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Từng quyết định</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Segmented
              value={symbol}
              options={run.config.symbols.map((s) => ({
                value: s,
                label: coin(s),
              }))}
              onChange={(v) => set({ symbol: v, day: undefined })}
            />
            <Segmented
              value={strategy}
              options={[...LLM_VARIANTS, ...BASELINES]
                .filter((s) => run.average[s])
                .map((s) => ({ value: s, label: style(s).label }))}
              onChange={(v) => set({ strategy: v })}
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Giá khớp mỗi ngày{run.config.blind && " (rebase 100 như model thấy)"},
          mũi tên là lệnh mua/bán và % vốn, cột dưới là tỷ lệ vốn đang cầm coin.
          Bấm một ngày trên biểu đồ để xem trader và analyst đã dựa vào đâu.
        </p>
      </CardHeader>
      <CardContent className="grid gap-4">
        {err && <p className="text-sm text-destructive">{err}</p>}
        <DecisionChart
          rows={rows}
          picked={picked}
          onPick={(d) => set({ day: d })}
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-md border px-2 py-1 font-mono text-xs disabled:opacity-40"
            disabled={idx <= 0}
            onClick={() => step(-1)}
          >
            ← ngày trước
          </button>
          <button
            type="button"
            className="rounded-md border px-2 py-1 font-mono text-xs disabled:opacity-40"
            disabled={idx < 0 || idx >= rows.length - 1}
            onClick={() => step(1)}
          >
            ngày sau →
          </button>
          <span className="text-xs text-muted-foreground">Ngày có lệnh:</span>
          {trades.map((t) => (
            <button
              key={t.day}
              type="button"
              onClick={() => set({ day: t.day })}
              className={cn(
                "rounded px-1.5 py-0.5 font-mono text-[11px]",
                t.action === "BUY"
                  ? "bg-up/15 text-up"
                  : "bg-down/15 text-down",
                t.day === picked && "ring-1 ring-yellow-400"
              )}
            >
              {t.day.slice(5)} {t.action[0]}
              {t.pct}
            </button>
          ))}
          {rows.length > 0 && trades.length === 0 && (
            <span className="text-xs text-muted-foreground">
              không có (HOLD suốt giai đoạn)
            </span>
          )}
        </div>
        {picked && (
          <div className="border-t pt-4">
            <DayPanel
              run={run.name}
              symbol={symbol}
              day={picked}
              strategy={strategy}
              blind={run.config.blind}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
