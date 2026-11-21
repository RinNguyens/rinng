import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Score } from "@/lib/score"
import { money } from "@/lib/wallet-scan"

export const GRADE_TEXT: Record<Score["grade"], string> = {
  A: "text-pass",
  B: "text-pass",
  C: "text-sev-medium",
  D: "text-sev-high",
  F: "text-sev-high",
}

const COUNT_MS = 600

// 0 -> to over 600 ms, ease-out; under reduced motion it is simply `to`.
function useCountUp(to: number, reduced: boolean) {
  const [v, setV] = useState(0)
  useEffect(() => {
    if (reduced) return
    const t0 = performance.now()
    let raf = requestAnimationFrame(function tick(now) {
      const t = Math.min(1, (now - t0) / COUNT_MS)
      setV(Math.round(to * (1 - (1 - t) ** 4)))
      if (t < 1) raf = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(raf)
  }, [to, reduced])
  return reduced ? to : v
}

export function ScoreCard({ score, reduced, title, pricesFailed }: { score: Score; reduced: boolean; title?: string; pricesFailed?: boolean }) {
  const shown = useCountUp(score.score, reduced)
  return (
    <section aria-label={title ?? "Score"} className="rounded-2xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className={`font-heading text-5xl ${GRADE_TEXT[score.grade]}`} aria-label={`Grade ${score.grade}`}>
          {score.grade}
        </span>
        <span className="font-heading text-lg tabular-nums">{shown}/100</span>
        <span className="text-sm text-muted-foreground">{pricesFailed ? "—" : money(score.usdAtRisk)} can be taken today</span>
        {score.provisional && (
          <Tooltip>
            <TooltipTrigger render={<Badge variant="outline" tabIndex={0} />}>provisional ⓘ</TooltipTrigger>
            <TooltipContent className="max-w-64">
              Part of the scan did not finish or approvals older than the lookback window were not read. The real
              score can only be lower.
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      {pricesFailed && (
        <p role="alert" className="mt-2 text-sm text-sev-medium">
          Token prices could not be loaded, so dollar amounts are not shown.
        </p>
      )}
      {score.items.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 text-sm">
          {score.items.map((it) => (
            <li key={it.text} className="flex gap-3">
              <span className="w-9 shrink-0 text-right font-heading text-sev-high tabular-nums">−{Math.abs(it.delta)}</span>
              <span>{it.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
