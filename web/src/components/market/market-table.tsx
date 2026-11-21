import { memo, useEffect, useState } from "react"
import type { ReactNode } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { StarIcon } from "@hugeicons/core-free-icons"
import { CoinIcon } from "@/components/coin-icon"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { MarketRow } from "@/lib/api"
import { num, pct, price, tone } from "@/lib/format"
import { annualized, countdown } from "@/lib/market"
import type { MarketDir, MarketSort } from "@/lib/market"
import { fmtVol } from "@/lib/overlay"
import { cn } from "@/lib/utils"

type Col = {
  key: MarketSort
  label: string
  // Responsive visibility: Vol and OI from md, OI 24h and L/S from xl (docs/13 §10).
  show: string
}

const COLS: Array<Col> = [
  { key: "price", label: "Price", show: "" },
  { key: "chg_24h", label: "24h", show: "" },
  { key: "volume_24h", label: "Vol 24h", show: "max-md:hidden" },
  { key: "funding_rate_pct", label: "Funding / 8h", show: "" },
  { key: "oi_value", label: "OI", show: "max-md:hidden" },
  { key: "oi_chg_24h", label: "OI 24h", show: "max-xl:hidden" },
  { key: "ls_ratio", label: "L/S", show: "max-xl:hidden" },
]

const NOT_COLLECTED =
  "Not collected for this coin. Add it to configs/instruments.yaml."

function Missing() {
  return (
    <Tooltip>
      <TooltipTrigger render={<span className="text-muted-foreground" />}>
        —
      </TooltipTrigger>
      <TooltipContent>{NOT_COLLECTED}</TooltipContent>
    </Tooltip>
  )
}

// The only thing that ticks every second: rows themselves stay memoised.
function Countdown({ next }: { next: number }) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  return <>{countdown(next, nowMs)}</>
}

function Tier({ row, children }: { row: MarketRow; children: ReactNode }) {
  return row.collected ? children : <Missing />
}

const Row = memo(function RowView({
  r,
  starred: on,
  flash: f,
  onToggleStar,
  onOpen,
}: {
  r: MarketRow
  starred: boolean
  flash: "up" | "down" | undefined
  onToggleStar: (symbol: string) => void
  onOpen: (row: MarketRow) => void
}) {
  return (
    <tr
      onClick={() => onOpen(r)}
      title={
        r.collected
          ? `OI 24h ${pct(r.oi_chg_24h)} · L/S ${r.ls_ratio == null ? "—" : num(r.ls_ratio, 2)}`
          : undefined
      }
      className={cn(
        "h-9 cursor-pointer transition-colors duration-300 [contain-intrinsic-size:auto_36px] [content-visibility:auto] focus-within:bg-muted/50 hover:bg-muted/50",
        f === "up" && "bg-up/10",
        f === "down" && "bg-down/10"
      )}
    >
      <td className="px-2">
        <button
          type="button"
          aria-pressed={on}
          aria-label={`Star ${r.base}`}
          onClick={(e) => {
            e.stopPropagation()
            onToggleStar(r.symbol)
          }}
          className={cn(
            "grid size-6 place-items-center rounded-full outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
            on ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <HugeiconsIcon
            icon={StarIcon}
            className="size-4"
            fill={on ? "currentColor" : "none"}
          />
        </button>
      </td>
      <td className="px-2">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onOpen(r)
          }}
          aria-label={`Open ${r.base}`}
          className="flex items-center gap-2 rounded outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <CoinIcon symbol={r.base} size={20} />
          <span className="font-medium">{r.base}</span>
          <span className="max-w-40 truncate text-xs text-muted-foreground">
            {r.name}
          </span>
        </button>
      </td>
      <td className="px-2 text-right font-heading tabular-nums">
        {price(r.price)}
      </td>
      <td
        className={cn(
          "px-2 text-right font-heading tabular-nums",
          tone(r.chg_24h)
        )}
      >
        {pct(r.chg_24h)}
      </td>
      <td className="px-2 text-right font-heading tabular-nums max-md:hidden">
        {fmtVol(r.volume_24h, false)}
      </td>
      <td className="px-2 text-right font-heading tabular-nums">
        <Tooltip>
          <TooltipTrigger render={<span />}>
            {num(r.funding_rate_pct, 4)}%{" "}
            <span className="text-xs text-muted-foreground">
              <Countdown next={r.next_funding} />
            </span>
          </TooltipTrigger>
          <TooltipContent>
            ≈ {pct(annualized(r.funding_rate_pct), 1)} / year
          </TooltipContent>
        </Tooltip>
      </td>
      <td className="px-2 text-right font-heading tabular-nums max-md:hidden">
        <Tier row={r}>
          {r.oi_value == null ? "—" : fmtVol(r.oi_value, false)}
        </Tier>
      </td>
      <td
        className={cn(
          "px-2 text-right font-heading tabular-nums max-xl:hidden",
          r.collected && tone(r.oi_chg_24h)
        )}
      >
        <Tier row={r}>{pct(r.oi_chg_24h)}</Tier>
      </td>
      <td className="px-2 text-right font-heading tabular-nums max-xl:hidden">
        <Tier row={r}>{r.ls_ratio == null ? "—" : num(r.ls_ratio, 2)}</Tier>
      </td>
    </tr>
  )
})

export function MarketTable({
  rows,
  sort,
  dir,
  onSort,
  starred,
  onToggleStar,
  onOpen,
  flash,
}: {
  rows: Array<MarketRow>
  sort: MarketSort
  dir: MarketDir
  onSort: (key: MarketSort) => void
  starred: Array<string>
  onToggleStar: (symbol: string) => void
  onOpen: (row: MarketRow) => void
  flash: Record<string, "up" | "down">
}) {
  const aria = (key: MarketSort) =>
    sort === key ? (dir === "asc" ? "ascending" : "descending") : undefined
  const sortButton = (key: MarketSort, label: string, right: boolean) => (
    <button
      type="button"
      onClick={() => onSort(key)}
      className={cn(
        "inline-flex items-center gap-1 rounded outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50",
        right && "flex-row-reverse"
      )}
    >
      {label}
      <span aria-hidden className="w-2 text-[10px]">
        {sort === key ? (dir === "asc" ? "▲" : "▼") : ""}
      </span>
    </button>
  )

  return (
    <table className="w-full border-separate border-spacing-0 text-sm">
      <thead>
        <tr className="text-xs text-muted-foreground">
          <th
            scope="col"
            className="sticky top-0 z-10 w-8 bg-background px-2 py-2 text-left font-normal"
          >
            <span className="sr-only">Watchlist</span>
          </th>
          <th
            scope="col"
            aria-sort={aria("base")}
            className="sticky top-0 z-10 bg-background px-2 py-2 text-left font-normal"
          >
            {sortButton("base", "Coin", false)}
          </th>
          {COLS.map((c) => (
            <th
              key={c.key}
              scope="col"
              aria-sort={aria(c.key)}
              className={cn(
                "sticky top-0 z-10 bg-background px-2 py-2 text-right font-normal",
                c.show
              )}
            >
              {sortButton(c.key, c.label, true)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <Row
            key={r.symbol}
            r={r}
            starred={starred.includes(r.symbol)}
            flash={flash[r.symbol]}
            onToggleStar={onToggleStar}
            onOpen={onOpen}
          />
        ))}
      </tbody>
    </table>
  )
}
