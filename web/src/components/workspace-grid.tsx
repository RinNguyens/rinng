import { useEffect, useMemo, useState } from "react"
import type { DragEvent } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Cancel01Icon,
  DragDropIcon,
  Maximize01Icon,
  Minimize01Icon,
} from "@hugeicons/core-free-icons"
import { ChartView } from "@/components/chart-view"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Meta } from "@/lib/api"
import type { SyncGroup } from "@/lib/chart-sync"
import { DAYS, LAYOUTS, PRESETS, fromPreset, setSlot, swapSlots } from "@/lib/workspaces"
import type { PanelCfg, Workspace } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

export const DND_TYPE = "application/x-rinng"
export type DragPayload = { kind: "slot"; from: number } | { kind: "preset"; index: number }

export function setDrag(e: DragEvent, p: DragPayload) {
  e.dataTransfer.setData(DND_TYPE, JSON.stringify(p))
  e.dataTransfer.effectAllowed = p.kind === "slot" ? "move" : "copy"
}

type Props = {
  ws: Workspace
  meta: Meta
  symbol: string
  exchange: string
  sync: SyncGroup
  onChange: (fn: (w: Workspace) => Workspace) => void
}

export function WorkspaceGrid({ ws, meta, symbol, exchange, sync, onChange }: Props) {
  const layout = LAYOUTS[ws.layout]
  const [over, setOver] = useState<number | null>(null)
  const [dragging, setDragging] = useState(false)
  const [max, setMax] = useState<string | null>(null)

  useEffect(() => {
    // Kéo từ thư viện rồi thả ra ngoài lưới: dragend không tới lưới, nên nghe ở window.
    const reset = () => {
      setDragging(false)
      setOver(null)
    }
    window.addEventListener("dragend", reset)
    window.addEventListener("drop", reset)
    return () => {
      window.removeEventListener("dragend", reset)
      window.removeEventListener("drop", reset)
    }
  }, [])

  // Thứ tự render cố định theo id để React không dựng lại chart khi chỉ đổi khung (grid-area).
  const items = useMemo(() => {
    const out: Array<{ key: string; slot: number; cfg: PanelCfg | null }> = []
    ws.slots.slice(0, layout.n).forEach((cfg, slot) => {
      out.push({ key: cfg ? cfg.id : `empty-${slot}`, slot, cfg })
    })
    return out.sort((a, b) => a.key.localeCompare(b.key))
  }, [ws.slots, layout.n])

  const maxItem = max ? items.find((i) => i.cfg?.id === max) : undefined

  function drop(e: DragEvent, slot: number) {
    e.preventDefault()
    setOver(null)
    setDragging(false)
    const raw = e.dataTransfer.getData(DND_TYPE)
    if (!raw) return
    const p = JSON.parse(raw) as DragPayload
    if (p.kind === "slot") {
      if (p.from !== slot) onChange((w) => swapSlots(w, p.from, slot))
    } else {
      onChange((w) => setSlot(w, slot, fromPreset(PRESETS[p.index])))
    }
  }

  return (
    <div
      className="grid min-h-0 flex-1 gap-3"
      style={
        maxItem
          ? { gridTemplateColumns: "1fr", gridTemplateRows: "1fr" }
          : {
              gridTemplateColumns: layout.cols,
              gridTemplateRows: layout.rows,
              gridTemplateAreas: layout.areas.map((a) => `"${a}"`).join(" "),
            }
      }
      onDragEnter={(e) => e.dataTransfer.types.includes(DND_TYPE) && setDragging(true)}
      onDragEnd={() => {
        setDragging(false)
        setOver(null)
      }}
    >
      {items.map(({ key, slot, cfg }) => {
        if (maxItem && maxItem.key !== key) return null
        return (
          <section
            key={key}
            style={maxItem ? undefined : { gridArea: `s${slot}` }}
            onDragOver={(e) => {
              if (!e.dataTransfer.types.includes(DND_TYPE)) return
              e.preventDefault()
              if (over !== slot) setOver(slot)
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(null)
            }}
            onDrop={(e) => drop(e, slot)}
            className={cn(
              "relative flex min-h-[260px] min-w-0 flex-col overflow-hidden rounded-2xl bg-card ring-1 ring-foreground/10 transition-shadow",
              over === slot && "ring-2 ring-primary",
            )}
          >
            {cfg ? (
              <Panel
                cfg={cfg}
                slot={slot}
                meta={meta}
                symbol={symbol}
                exchange={exchange}
                sync={sync}
                maximized={max === cfg.id}
                onMax={() => setMax(max === cfg.id ? null : cfg.id)}
                onDragStart={() => setDragging(true)}
                onChange={(next) => onChange((w) => setSlot(w, slot, next))}
              />
            ) : (
              <EmptySlot slot={slot} />
            )}
            {dragging && cfg ? (
              // Lớp phủ khi đang kéo: canvas của chart không nhận sự kiện kéo thả.
              <div
                className={cn(
                  "pointer-events-none absolute inset-0 grid place-items-center bg-background/40 text-sm font-medium backdrop-blur-[1px] transition-opacity",
                  over === slot ? "opacity-100" : "opacity-60",
                )}
              >
                <span className="rounded-full bg-card px-3 py-1 ring-1 ring-foreground/10">
                  Thả vào khung {slot + 1}
                </span>
              </div>
            ) : null}
          </section>
        )
      })}
    </div>
  )
}

function EmptySlot({ slot }: { slot: number }) {
  return (
    <div className="m-3 grid flex-1 place-items-center rounded-xl border border-dashed border-foreground/15 text-center text-sm text-muted-foreground">
      <div className="space-y-1">
        <HugeiconsIcon icon={DragDropIcon} className="mx-auto size-6 opacity-60" />
        <p>Khung {slot + 1} trống</p>
        <p className="text-xs">Kéo một chart từ thư viện bên trái vào đây</p>
      </div>
    </div>
  )
}

const TF_LABEL: Record<string, string> = { "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W" }

function Panel({
  cfg,
  slot,
  meta,
  symbol,
  exchange,
  sync,
  maximized,
  onMax,
  onDragStart,
  onChange,
}: {
  cfg: PanelCfg
  slot: number
  meta: Meta
  symbol: string
  exchange: string
  sync: SyncGroup
  maximized: boolean
  onMax: () => void
  onDragStart: () => void
  onChange: (cfg: PanelCfg | null) => void
}) {
  const [status, setStatus] = useState<{ source?: string; error?: string; loading: boolean }>({
    loading: true,
  })
  const lensItems = Object.entries(meta.lenses).map(([value, label]) => ({ value, label }))
  const tfItems = meta.timeframes.map((t) => ({ value: t, label: TF_LABEL[t] ?? t }))
  const dayItems = DAYS.map((d) => ({ value: String(d), label: `${d} ngày` }))
  const periodItems = [
    { value: "week", label: "Profile tuần" },
    { value: "day", label: "Profile ngày" },
  ]

  return (
    <>
      <header className="flex flex-wrap items-center gap-1.5 border-b border-foreground/10 px-2 py-1.5">
        <Tooltip>
          <TooltipTrigger
            render={
              <span
                draggable
                role="button"
                aria-label={`Kéo khung ${slot + 1} sang khung khác`}
                onDragStart={(e) => {
                  setDrag(e, { kind: "slot", from: slot })
                  onDragStart()
                }}
                className="grid size-7 cursor-grab place-items-center rounded-lg text-muted-foreground hover:bg-muted active:cursor-grabbing"
              />
            }
          >
            <HugeiconsIcon icon={DragDropIcon} className="size-4" />
          </TooltipTrigger>
          <TooltipContent>Kéo để đổi chỗ sang khung khác</TooltipContent>
        </Tooltip>
        <Pick
          items={lensItems}
          value={cfg.lens}
          onChange={(v) => onChange({ ...cfg, lens: v })}
          className="font-medium"
          label="Lens"
        />
        <Pick
          items={tfItems}
          value={cfg.tf}
          onChange={(v) => onChange({ ...cfg, tf: v })}
          label="Khung thời gian"
        />
        <Pick
          items={dayItems}
          value={String(cfg.days)}
          onChange={(v) => onChange({ ...cfg, days: Number(v) })}
          label="Số ngày"
        />
        {cfg.lens === "profile" ? (
          <Pick
            items={periodItems}
            value={cfg.period}
            onChange={(v) => onChange({ ...cfg, period: v as PanelCfg["period"] })}
            label="Kỳ profile"
          />
        ) : null}
        <span
          className={cn(
            "ml-auto truncate pl-2 font-heading text-[11px]",
            status.error ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {status.loading
            ? "đang tải…"
            : status.error
              ? "lỗi"
              : status.source === "live"
                ? "REST trực tiếp"
                : "curated"}
        </span>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={maximized ? "Thu nhỏ" : "Phóng to"}
                onClick={onMax}
              />
            }
          >
            <HugeiconsIcon icon={maximized ? Minimize01Icon : Maximize01Icon} />
          </TooltipTrigger>
          <TooltipContent>{maximized ? "Thu nhỏ" : "Phóng to khung này"}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Bỏ chart khỏi khung"
                onClick={() => onChange(null)}
              />
            }
          >
            <HugeiconsIcon icon={Cancel01Icon} />
          </TooltipTrigger>
          <TooltipContent>Bỏ chart khỏi khung</TooltipContent>
        </Tooltip>
      </header>
      <ChartView cfg={cfg} symbol={symbol} exchange={exchange} sync={sync} onStatus={setStatus} />
    </>
  )
}

export function Pick({
  items,
  value,
  onChange,
  className,
  label,
}: {
  items: Array<{ value: string; label: string }>
  value: string
  onChange: (v: string) => void
  className?: string
  label?: string
}) {
  return (
    <Select items={items} value={value} onValueChange={(v) => v != null && onChange(String(v))}>
      <SelectTrigger size="sm" aria-label={label} className={cn("h-7 gap-1 px-2.5 text-xs", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        {items.map((i) => (
          <SelectItem key={i.value} value={i.value} className="text-xs">
            {i.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
