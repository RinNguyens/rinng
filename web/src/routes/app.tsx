import { useEffect, useMemo, useState } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Add01Icon,
  Cancel01Icon,
  DashboardSquare02Icon,
  LibraryIcon,
  Link04Icon,
  RefreshIcon,
} from "@hugeicons/core-free-icons"
import { ChartLibrary, LayoutIcon } from "@/components/chart-library"
import { comboById, comboWorkspace } from "@/lib/combos"
import { VenueIcon } from "@/components/coin-icon"
import { Dashboard } from "@/components/dashboard"
import { Pick, WorkspaceGrid } from "@/components/workspace-grid"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { api } from "@/lib/api"
import type { Instrument, Meta } from "@/lib/api"
import { CoinSearch } from "@/components/coin-search"
import { NewsTicker } from "@/components/news"
import { live, useLiveState } from "@/lib/live"
import type { LiveState } from "@/lib/live"
import { SyncGroup } from "@/lib/chart-sync"
import { LAYOUTS, useWorkspaces } from "@/lib/workspaces"
import type { LayoutKey } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

// The build is an SPA (the static shell holds only the root), so this page always renders in the
// browser; charts and localStorage are only touched in effects, so SSR under `pnpm dev` is safe.
export const Route = createFileRoute("/app")({ component: App })

const DASH = "dashboard"
const INST_KEY = "rinng.instrument.v1"

function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [inst, setInst] = useState<Instrument | null>(null)
  const symbol = inst?.id ?? "BTC-USDT-PERP"
  const [exchange, setExchange] = useState("binance")
  const [active, setActive] = useState<string>(DASH)
  const [library, setLibrary] = useState(true)
  const [syncOn, setSyncOn] = useState(true)
  const { workspaces, update, add, insert, remove, reset } = useWorkspaces()

  // One sync group per tab; switching tabs rebuilds the charts, so make a new group.
  const sync = useMemo(() => new SyncGroup(), [active, symbol, exchange])
  sync.enabled = syncOn

  useEffect(() => {
    api
      .meta()
      .then(setMeta)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (meta) live.configure(meta.live)
  }, [meta])

  // Last viewed coin is remembered; default is the first watchlist coin.
  useEffect(() => {
    if (!meta || inst) return
    let saved: Instrument | null = null
    try {
      saved = JSON.parse(
        localStorage.getItem(INST_KEY) ?? "null"
      ) as Instrument | null
    } catch {
      saved = null
    }
    setInst(saved ?? meta.instruments[0])
  }, [meta, inst])

  const choose = (next: Instrument) => {
    setInst(next)
    try {
      localStorage.setItem(INST_KEY, JSON.stringify(next))
    } catch {
      /* storage blocked */
    }
    // Stay on the current exchange when it lists the coin, otherwise switch.
    const key = exchange as "binance" | "okx"
    if (next[key] === false) setExchange(next.binance ? "binance" : "okx")
  }
  useEffect(() => {
    live.select(symbol, exchange)
  }, [symbol, exchange])

  const ws = workspaces.find((w) => w.id === active)
  useEffect(() => {
    if (active !== DASH && workspaces.length && !ws) setActive(DASH)
  }, [active, workspaces, ws])

  if (error) {
    return (
      <div className="grid h-svh place-items-center p-6 text-center text-sm">
        <div className="space-y-2">
          <p className="text-destructive">
            Cannot reach the rinng API: {error}
          </p>
          <p className="text-muted-foreground">
            Start the backend:{" "}
            <code className="font-heading">uv run rinng web</code>
          </p>
        </div>
      </div>
    )
  }
  if (!meta) return <div className="h-svh" />

  return (
    <div className="flex h-svh flex-col">
      <NewsTicker />
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
        <nav className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-label="Go to dashboard"
            onClick={() => setActive(DASH)}
            className="mr-1 flex cursor-pointer items-center gap-2 rounded-lg pl-1 hover:opacity-80"
          >
            <img src="/logo.svg" alt="" className="size-7 rounded-lg" />
            <span className="font-heading text-sm font-semibold tracking-tight">
              rinng
            </span>
          </button>

          <div className="flex items-center gap-1">
            <Pick
              label="Workspace"
              className="max-w-56"
              value={ws ? ws.id : DASH}
              onChange={setActive}
              items={[
                {
                  value: DASH,
                  label: "Dashboard",
                  icon: <HugeiconsIcon icon={DashboardSquare02Icon} className="size-3.5" />,
                },
                ...workspaces.map((w, i) => ({ value: w.id, label: `${i + 1}. ${w.name}` })),
              ]}
            />
            {ws && workspaces.length > 1 ? (
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
                    onClick={() => setActive(add())}
                  />
                }
              >
                <HugeiconsIcon icon={Add01Icon} />
              </TooltipTrigger>
              <TooltipContent>Add chart tab</TooltipContent>
            </Tooltip>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <LiveBadge />
            {inst ? (
              <CoinSearch
                value={inst}
                watchlist={meta.instruments}
                onSelect={choose}
              />
            ) : null}
            <Pick
              items={meta.exchanges
                .filter((v) => !inst || inst[v as "binance" | "okx"] !== false)
                .map((v) => ({
                  value: v,
                  label: v === "okx" ? "OKX" : v[0].toUpperCase() + v.slice(1),
                  icon: <VenueIcon id={v} size={14} />,
                }))}
              value={exchange}
              onChange={setExchange}
              label="Exchange"
            />
            {ws ? (
              <>
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
              </>
            ) : null}
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
                        setActive(reset())
                    }}
                  />
                }
              >
                <HugeiconsIcon icon={RefreshIcon} />
              </TooltipTrigger>
              <TooltipContent>Restore default tabs</TooltipContent>
            </Tooltip>
          </div>
        </nav>

        <main className="flex min-h-0 flex-1 gap-3">
          {ws ? (
            <>
              {library ? (
                <ChartLibrary
                  onOpenCombo={(c) => setActive(insert(comboWorkspace(c)))}
                />
              ) : null}
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <GuideStrip
                  guide={ws.guide}
                  onDismiss={() =>
                    update(ws.id, (w) => ({ ...w, guide: undefined }))
                  }
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
            </>
          ) : (
            <Dashboard
              symbol={symbol}
              exchange={exchange}
              instrument={inst ?? undefined}
            />
          )}
        </main>
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

const LIVE_LABEL: Record<
  LiveState,
  { text: string; dot: string; hint: string }
> = {
  static: {
    text: "Static",
    dot: "bg-muted-foreground",
    hint: "Stored data only. Run `rinng live` for realtime.",
  },
  connecting: {
    text: "Connecting",
    dot: "bg-muted-foreground animate-pulse",
    hint: "Opening the live connection…",
  },
  live: {
    text: "Live",
    dot: "bg-up animate-pulse",
    hint: "Exchange feed updated within the last 5 seconds.",
  },
  delayed: {
    text: "Delayed",
    dot: "bg-chart-2",
    hint: "No exchange update for 5–60 seconds.",
  },
  offline: {
    text: "Offline",
    dot: "bg-down",
    hint: "No live data; reconnecting automatically.",
  },
}

function LiveBadge() {
  const state = useLiveState()
  const l = LIVE_LABEL[state]
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            role="status"
            aria-live="polite"
            className="inline-flex h-7 items-center gap-1.5 rounded-4xl bg-muted px-2.5 text-xs font-medium"
          />
        }
      >
        <span className={cn("size-2 rounded-full", l.dot)} />
        {l.text}
      </TooltipTrigger>
      <TooltipContent>{l.hint}</TooltipContent>
    </Tooltip>
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
