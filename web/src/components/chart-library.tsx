import { HugeiconsIcon } from "@hugeicons/react"
import { DragDropIcon } from "@hugeicons/core-free-icons"
import { setDrag } from "@/components/workspace-grid"
import { PRESETS } from "@/lib/workspaces"

const TF: Record<string, string> = { "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W" }

// Thư viện chart: kéo một thẻ vào khung bất kỳ của tab đang mở.
export function ChartLibrary() {
  return (
    <aside className="flex w-60 shrink-0 flex-col gap-2 overflow-y-auto pr-1">
      <div className="px-1 pb-1">
        <h2 className="font-heading text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Thư viện chart
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Kéo thẻ vào khung bên phải. Kéo tay nắm trên đầu chart để đổi chỗ.
        </p>
      </div>
      {PRESETS.map((p, i) => (
        <div
          key={p.title}
          draggable
          onDragStart={(e) => setDrag(e, { kind: "preset", index: i })}
          className="group cursor-grab rounded-xl bg-card p-3 ring-1 ring-foreground/10 transition hover:ring-foreground/25 active:cursor-grabbing"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{p.title}</span>
            <span className="ml-auto rounded-md bg-muted px-1.5 py-0.5 font-heading text-[10px] text-muted-foreground">
              {TF[p.tf]} · {p.days}n
            </span>
            <HugeiconsIcon
              icon={DragDropIcon}
              className="size-3.5 text-muted-foreground opacity-0 transition group-hover:opacity-100"
            />
          </div>
          <p className="mt-1 text-xs leading-snug text-muted-foreground">{p.hint}</p>
        </div>
      ))}
    </aside>
  )
}
