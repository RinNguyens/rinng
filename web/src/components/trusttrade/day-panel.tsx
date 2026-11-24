import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { num, price } from "@/lib/format"
import { isLLM, style, ttApi } from "@/lib/trusttrade"
import type {
  ConsensusDay,
  DayDetail,
  Decision,
  Group,
  Polarity,
  Report,
} from "@/lib/trusttrade"

// One symbol-day of a run: what every strategy did, which analyst claims survived the consensus
// filter (support from several analysts × cohesion of the wording), and the analysts' own reports.

const POL: Record<Polarity, string> = {
  bullish: "text-up",
  bearish: "text-down",
  neutral: "text-muted-foreground",
}
const POL_BG: Record<Polarity, string> = {
  bullish: "bg-up/15 text-up",
  bearish: "bg-down/15 text-down",
  neutral: "bg-muted text-muted-foreground",
}
const ACT: Record<string, string> = {
  BUY: "bg-up/15 text-up",
  SELL: "bg-down/15 text-down",
  HOLD: "bg-muted text-muted-foreground",
}

export function DayPanel({
  run,
  symbol,
  day,
  strategy,
  blind,
}: {
  run: string
  symbol: string
  day: string
  strategy: string
  blind: boolean
}) {
  const [data, setData] = useState<DayDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setData(null)
    ttApi
      .day(run, symbol, day)
      .then((d) => alive && (setData(d), setErr(null)))
      .catch((e: Error) => alive && setErr(e.message))
    return () => {
      alive = false
    }
  }, [run, symbol, day])

  if (err) return <p className="text-sm text-destructive">{err}</p>
  if (!data)
    return <p className="text-sm text-muted-foreground">Đang tải ngày {day}…</p>

  const mine = data.decisions.find((d) => d.strategy === strategy)
  const label = data.decisions[0]?.label

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-mono text-base font-semibold">{day}</h3>
        {blind && label && (
          <span className="font-mono text-xs text-muted-foreground">
            model thấy: “{label}”, giá rebase 100
          </span>
        )}
      </div>

      <Strategies rows={data.decisions} current={strategy} />

      {mine?.rationale && <Rationale d={mine} />}

      {data.consensus.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.consensus.map((c) => (
            <ConsensusCard key={c.domain} c={c} />
          ))}
        </div>
      )}

      {data.reports.length > 0 && <Reports rows={data.reports} />}
    </div>
  )
}

function Strategies({
  rows,
  current,
}: {
  rows: Array<Decision>
  current: string
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {rows.map((d) => (
        <div
          key={d.strategy}
          className={cn(
            "flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs",
            d.strategy === current && "border-foreground/40 bg-muted/40"
          )}
        >
          <span
            className="size-2 rounded-full"
            style={{ background: style(d.strategy).color }}
          />
          <span className="text-muted-foreground">
            {style(d.strategy).label}
          </span>
          <span
            className={cn(
              "rounded px-1.5 py-0.5 font-mono font-medium",
              ACT[d.action]
            )}
          >
            {d.action}
            {d.action !== "HOLD" && ` ${d.pct}%`}
          </span>
          {isLLM(d.strategy) && d.confidence != null && (
            <span className="font-mono text-muted-foreground">
              {d.confidence}
            </span>
          )}
          <span className="font-mono text-muted-foreground">
            {num(100 * d.exposure)}% coin
          </span>
        </div>
      ))}
    </div>
  )
}

function Rationale({ d }: { d: Decision }) {
  return (
    <div className="grid gap-2 rounded-xl border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">
          Trader · {style(d.strategy).label}
        </span>
        <span>giá khớp {price(d.price)}</span>
        <span>equity {num(d.equity, 0)}</span>
      </div>
      <p className="font-serif text-[15px] leading-relaxed">{d.rationale}</p>
      {d.key_evidence && d.key_evidence.length > 0 && (
        <ul className="grid gap-1 text-sm text-muted-foreground">
          {d.key_evidence.map((e) => (
            <li key={e} className="flex gap-2">
              <span className="text-foreground/40">—</span>
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ConsensusCard({ c }: { c: ConsensusDay }) {
  const [showLow, setShowLow] = useState(false)
  return (
    <div className="grid content-start gap-3 rounded-xl border p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold capitalize">{c.domain}</h4>
        <span className="font-mono text-xs text-muted-foreground">
          giữ {num(100 * c.kept_share)}% claim · {c.high.length} nhóm mạnh /{" "}
          {c.low.length} yếu
        </span>
      </div>
      <KeptBar share={c.kept_share} />
      <ul className="grid gap-2">
        {c.high.map((g) => (
          <GroupRow key={g.claim} g={g} n={c.n_agents} />
        ))}
      </ul>
      {c.low.length > 0 && (
        <div>
          <button
            type="button"
            className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            onClick={() => setShowLow((v) => !v)}
          >
            {showLow ? "Ẩn" : "Xem"} {c.low.length} nhóm bị loại
          </button>
          {showLow && (
            <ul className="mt-2 grid gap-2 opacity-70">
              {c.low.map((g) => (
                <GroupRow key={g.claim} g={g} n={c.n_agents} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function KeptBar({ share }: { share: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-emerald-500/70"
        style={{ width: `${100 * share}%` }}
      />
    </div>
  )
}

function GroupRow({ g, n }: { g: Group; n: number }) {
  // the stored claim text ends with "[value] (polarity)"; the chips carry those already
  const text = g.claim.replace(/\s*\((bullish|bearish|neutral)\)\s*$/, "")
  return (
    <li className="grid gap-1">
      <div className="flex items-start gap-2 text-sm">
        <span
          className={cn(
            "mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
            POL_BG[g.polarity]
          )}
        >
          {g.polarity.slice(0, 4)}
        </span>
        <span className="leading-snug">{text}</span>
      </div>
      <div className="flex items-center gap-3 pl-[46px] font-mono text-[11px] text-muted-foreground">
        <span title="Số analyst cùng nêu claim này">
          {g.agents}/{n} analyst
        </span>
        <span title="S = α·support + (1−α)·cohesion">
          S {g.score.toFixed(2)}
        </span>
        <span>coh {g.cohesion.toFixed(2)}</span>
        <Dots n={n} k={g.agents} polarity={g.polarity} />
      </div>
    </li>
  )
}

function Dots({
  n,
  k,
  polarity,
}: {
  n: number
  k: number
  polarity: Polarity
}) {
  return (
    <span className="flex gap-0.5">
      {Array.from({ length: n }, (_, i) => (
        <span
          key={i}
          className={cn(
            "size-1.5 rounded-full",
            i < k ? "bg-current" : "bg-muted",
            i < k && POL[polarity]
          )}
        />
      ))}
    </span>
  )
}

function Reports({ rows }: { rows: Array<Report> }) {
  const domains = [...new Set(rows.map((r) => r.domain))]
  return (
    <div className="grid gap-3">
      <h4 className="text-sm font-semibold">Báo cáo của từng analyst</h4>
      <div className="grid gap-3 lg:grid-cols-2">
        {domains.map((dom) => (
          <div key={dom} className="grid content-start gap-2">
            <span className="text-xs text-muted-foreground capitalize">
              {dom}
            </span>
            {rows
              .filter((r) => r.domain === dom)
              .map((r) => (
                <details
                  key={`${dom}-${r.agent}`}
                  className="group rounded-lg border px-3 py-2"
                >
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-xs">
                    <span className="font-mono text-muted-foreground">
                      #{r.agent + 1}
                    </span>
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 font-medium",
                        POL_BG[r.stance]
                      )}
                    >
                      {r.stance}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      conf {r.confidence}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {r.claims.length} claim
                    </span>
                    <span className="ml-auto text-muted-foreground group-open:rotate-90">
                      ›
                    </span>
                  </summary>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {r.summary}
                  </p>
                </details>
              ))}
          </div>
        ))}
      </div>
    </div>
  )
}
