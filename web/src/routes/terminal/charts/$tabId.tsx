import { useEffect, useMemo, useState } from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Add01Icon,
  Cancel01Icon,
  LibraryIcon,
  Link04Icon,
  RefreshIcon,
} from "@hugeicons/core-free-icons"
import { ChartLibrary, LayoutIcon } from "@/components/chart-library"
import { comboById, comboWorkspace } from "@/lib/combos"
import { Pick, WorkspaceGrid } from "@/components/workspace-grid"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useTerminal } from "@/components/terminal/context"
import { SyncGroup } from "@/lib/chart-sync"
import { tabRedirect } from "@/lib/terminal-nav"
import { LAYOUTS } from "@/lib/workspaces"
import type { LayoutKey } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/terminal/charts/$tabId")({ component: Charts })

function Charts() {
  const { tabId } = Route.useParams()
  const { meta, symbol, exchange, tabs } = useTerminal()
  const { workspaces, update, add, insert, remove, reset } = tabs
  const navigate = useNavigate()
  const [library, setLibrary] = useState(true)
  const [syncOn, setSyncOn] = useState(true)
  const go = (id: string, replace = false) =>
    navigate({ to: "/terminal/charts/$tabId", params: { tabId: id }, replace })

  // One sync group per tab; switching tabs rebuilds the charts, so make a new group.
  const sync = useMemo(() => new SyncGroup(), [tabId, symbol, exchange])
  sync.enabled = syncOn

  const ws = workspaces.find((w) => w.id === tabId)
  const forward = tabRedirect(tabId, workspaces)
  useEffect(() => {
    if (forward) navigate({ to: "/terminal/charts/$tabId", params: { tabId: forward }, replace: true })
  }, [forward, navigate])

  if (!ws) return null

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Pick
            label="Workspace"
            className="max-w-56"
            value={ws.id}
            onChange={go}
            items={workspaces.map((w, i) => ({ value: w.id, label: `${i + 1}. ${w.name}` }))}
          />
          {workspaces.length > 1 ? (
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Close tab ${ws.name}`}
              onClick={() => remove(ws.id)}
            >
              <HugeiconsIcon icon={Cancel01Icon} />
            </Button>
          ) : null}
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Add chart tab"
                  onClick={() => go(add())}
                />
              }
            >
              <HugeiconsIcon icon={Add01Icon} />
            </TooltipTrigger>
            <TooltipContent>Add chart tab</TooltipContent>
          </Tooltip>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <LayoutPicker
            value={ws.layout}
            onChange={(l) => update(ws.id, (w) => ({ ...w, layout: l }))}
          />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Switch
              checked={syncOn}
              onCheckedChange={setSyncOn}
              size="sm"
              aria-label="Sync crosshair across charts"
            />
            <HugeiconsIcon icon={Link04Icon} className="size-3.5" />
            sync
          </label>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  aria-label="Chart library"
                  aria-pressed={library}
                  variant={library ? "secondary" : "ghost"}
                  size="icon-sm"
                  onClick={() => setLibrary(!library)}
                />
              }
            >
              <HugeiconsIcon icon={LibraryIcon} />
            </TooltipTrigger>
            <TooltipContent>
              {library ? "Hide" : "Show"} chart library
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Restore default tabs"
                  onClick={() => {
                    if (
                      confirm(
                        "Restore the default tabs? Your current layout will be lost."
                      )
                    )
                      go(reset())
                  }}
                />
              }
            >
              <HugeiconsIcon icon={RefreshIcon} />
            </TooltipTrigger>
            <TooltipContent>Restore default tabs</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        {library ? (
          <ChartLibrary onOpenCombo={(c) => go(insert(comboWorkspace(c)))} />
        ) : null}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <GuideStrip
            guide={ws.guide}
            onDismiss={() => update(ws.id, (w) => ({ ...w, guide: undefined }))}
          />
          <WorkspaceGrid
            key={`${ws.id}-${symbol}-${exchange}`}
            ws={ws}
            meta={meta}
            symbol={symbol}
            exchange={exchange}
            sync={sync}
            onChange={(fn) => update(ws.id, fn)}
          />
        </div>
      </div>
    </div>
  )
}

function LayoutPicker({
  value,
  onChange,
}: {
  value: LayoutKey
  onChange: (l: LayoutKey) => void
}) {
  return (
    <div className="flex items-center gap-0.5 rounded-4xl bg-muted p-[3px]">
      {(Object.keys(LAYOUTS) as Array<LayoutKey>).map((k) => {
        const l = LAYOUTS[k]
        return (
          <Tooltip key={k}>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  aria-label={l.label}
                  onClick={() => onChange(k)}
                  className={cn(
                    "grid size-7 place-items-center rounded-full transition-colors",
                    value === k
                      ? "bg-background ring-1 ring-foreground/10 dark:bg-input/40"
                      : "hover:bg-background/50"
                  )}
                />
              }
            >
              <LayoutIcon layout={k} active={value === k} />
            </TooltipTrigger>
            <TooltipContent>{l.label}</TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}

// Reading guide for tabs built from a combo: the question and the order to read the charts.
function GuideStrip({
  guide,
  onDismiss,
}: {
  guide?: string
  onDismiss: () => void
}) {
  const combo = comboById(guide)
  const [open, setOpen] = useState(true)
  if (!combo) return null
  return (
    <section className="shrink-0 rounded-xl bg-card px-3 py-2 ring-1 ring-foreground/10">
      <div className="flex items-center gap-2 text-sm">
        <LayoutIcon layout={combo.layout} className="opacity-70" />
        <span className="font-medium">{combo.title}</span>
        <span className="truncate text-muted-foreground">{combo.question}</span>
        <Button
          variant="ghost"
          size="xs"
          className="ml-auto"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? "Hide steps" : "How to read"}
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Dismiss reading guide"
          onClick={onDismiss}
        >
          <HugeiconsIcon icon={Cancel01Icon} />
        </Button>
      </div>
      {open ? (
        <ol className="mt-1.5 grid gap-x-6 gap-y-1 text-xs leading-snug text-muted-foreground md:grid-cols-3">
          {combo.steps.map((step, i) => (
            <li key={i} className="flex gap-2">
              <span className="font-heading text-foreground">{i + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  )
}
