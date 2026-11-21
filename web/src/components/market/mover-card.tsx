import type { ReactNode } from "react"
import { CoinIcon } from "@/components/coin-icon"
import { Card, CardContent } from "@/components/ui/card"
import type { MarketRow } from "@/lib/api"

export type MoverItem = { row: MarketRow; value: ReactNode }
export type MoverGroup = { label: string; items: Array<MoverItem> }

// One Market summary card: groups of coins, each row a button that opens the coin.
export function MoverCard({
  title,
  groups,
  onOpen,
}: {
  title: string
  groups: Array<MoverGroup>
  onOpen: (row: MarketRow) => void
}) {
  return (
    <Card size="sm" className="gap-1.5 max-md:min-w-64">
      <CardContent className="space-y-1">
        <div className="pb-1 text-xs font-medium text-muted-foreground">{title}</div>
        {groups.map((g) => (
          <div key={g.label} aria-label={g.label} role="group">
            {g.items.map(({ row, value }) => (
              <button
                key={row.symbol}
                type="button"
                onClick={() => onOpen(row)}
                className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-xs outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                <CoinIcon symbol={row.base} size={16} />
                <span className="font-medium">{row.base}</span>
                <span className="ml-auto font-heading tabular-nums">{value}</span>
              </button>
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
