import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { COMBOS } from "@/lib/combos"
import type { Combo } from "@/lib/combos"

// One row of chart-combo cards; each opens its combo as a new Charts tab.
export function ComboShortcuts({
  ids,
  onOpen,
}: {
  ids: Array<string>
  onOpen: (combo: Combo) => void
}) {
  const combos = ids.flatMap((id) => COMBOS.filter((c) => c.id === id))
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
      {combos.map((c) => (
        <Card key={c.id} size="sm" className="gap-2">
          <CardContent className="flex h-full flex-col gap-3">
            <div className="space-y-1">
              <div className="font-heading text-sm font-medium">{c.title}</div>
              <p className="text-xs text-muted-foreground">{c.question}</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="mt-auto self-start"
              onClick={() => onOpen(c)}
            >
              Open as chart tab
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
