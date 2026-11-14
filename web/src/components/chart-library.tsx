import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, DragDropIcon } from "@hugeicons/core-free-icons"
import { setDrag } from "@/components/workspace-grid"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { COMBOS } from "@/lib/combos"
import type { Combo } from "@/lib/combos"
import { LAYOUTS, PRESETS } from "@/lib/workspaces"
import type { LayoutKey } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

const TF: Record<string, string> = { "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W" }
const SHORT: Record<string, string> = {
  structure: "SMC",
  liquidity: "Liquidity",
  profile: "Profile",
  wyckoff: "Wyckoff",
  derivatives: "Derivatives",
  indicators: "Indicators",
  forecast: "Projection",
}

// Small picture of a layout, drawn with the layout's own grid-template-areas.
export function LayoutIcon({ layout, active = true, className }: { layout: LayoutKey; active?: boolean; className?: string }) {
  const l = LAYOUTS[layout]
  return (
    <span
      aria-hidden
      className={cn("grid size-4 shrink-0 gap-[2px]", className)}
      style={{
        gridTemplateColumns: l.cols,
        gridTemplateRows: l.rows,
        gridTemplateAreas: l.areas.map((a) => `"${a}"`).join(" "),
      }}
    >
      {Array.from({ length: l.n }, (_, i) => (
        <span
          key={i}
          style={{ gridArea: `s${i}` }}
          className={cn("rounded-[2px]", active ? "bg-foreground/80" : "bg-muted-foreground/60")}
        />
      ))}
    </span>
  )
}

function ComboCard({ combo, onOpen }: { combo: Combo; onOpen: (c: Combo) => void }) {
  return (
    <div
      draggable
      onDragStart={(e) => setDrag(e, { kind: "combo", id: combo.id })}
      className="group cursor-grab space-y-2 rounded-xl bg-card p-3 ring-1 ring-foreground/10 transition hover:ring-foreground/25 active:cursor-grabbing"
    >
      <div className="flex items-center gap-2">
        <LayoutIcon layout={combo.layout} className="opacity-70" />
        <span className="text-sm font-medium">{combo.title}</span>
      </div>
      <p className="text-xs leading-snug text-muted-foreground">{combo.question}</p>
      <div className="flex flex-wrap gap-1">
        {combo.charts.map((c, i) => (
          <span
            key={i}
            className="rounded-md bg-muted px-1.5 py-0.5 font-heading text-[10px] text-muted-foreground"
          >
            {c.lens === "profile" && c.period === "day" ? "Daily profile" : SHORT[c.lens]} {TF[c.tf]}
          </span>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground opacity-0 transition group-hover:opacity-100">
          Drag onto the grid to load here
        </span>
        <Button
          variant="ghost"
          size="xs"
          aria-label={`Open ${combo.title} in a new tab`}
          onClick={() => onOpen(combo)}
        >
          <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
          New tab
        </Button>
      </div>
    </div>
  )
}

function PresetCard({ index }: { index: number }) {
  const p = PRESETS[index]
  return (
    <div
      draggable
      onDragStart={(e) => setDrag(e, { kind: "preset", index })}
      className="group cursor-grab rounded-xl bg-card p-3 ring-1 ring-foreground/10 transition hover:ring-foreground/25 active:cursor-grabbing"
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{p.title}</span>
        <span className="ml-auto rounded-md bg-muted px-1.5 py-0.5 font-heading text-[10px] text-muted-foreground">
          {TF[p.tf]} · {p.days}d
        </span>
        <HugeiconsIcon
          icon={DragDropIcon}
          className="size-3.5 text-muted-foreground opacity-0 transition group-hover:opacity-100"
        />
      </div>
      <p className="mt-1 text-xs leading-snug text-muted-foreground">{p.hint}</p>
    </div>
  )
}

// Chart library: combos (charts that answer one question together) and single charts.
export function ChartLibrary({ onOpenCombo }: { onOpenCombo: (c: Combo) => void }) {
  return (
    <aside className="flex w-64 shrink-0 flex-col gap-2 overflow-hidden">
      <Tabs defaultValue="combos" className="min-h-0 flex-1">
        <TabsList className="w-full">
          <TabsTrigger value="combos">Combos</TabsTrigger>
          <TabsTrigger value="charts">Charts</TabsTrigger>
        </TabsList>
        <TabsContent value="combos" className="min-h-0 space-y-2 overflow-y-auto pr-1">
          <p className="px-1 text-xs text-muted-foreground">
            Charts that answer one question together. Same-timeframe charts share crosshair and time.
          </p>
          {COMBOS.map((c) => (
            <ComboCard key={c.id} combo={c} onOpen={onOpenCombo} />
          ))}
        </TabsContent>
        <TabsContent value="charts" className="min-h-0 space-y-2 overflow-y-auto pr-1">
          <p className="px-1 text-xs text-muted-foreground">
            Drag a card into a slot. Drag the handle on a chart header to swap slots.
          </p>
          {PRESETS.map((p, i) => (
            <PresetCard key={p.title} index={i} />
          ))}
        </TabsContent>
      </Tabs>
    </aside>
  )
}
