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
import { ChartLibrary } from "@/components/chart-library"
import { Dashboard } from "@/components/dashboard"
import { Pick, WorkspaceGrid } from "@/components/workspace-grid"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api } from "@/lib/api"
import type { Meta } from "@/lib/api"
import { SyncGroup } from "@/lib/chart-sync"
import { LAYOUTS, useWorkspaces } from "@/lib/workspaces"
import type { LayoutKey } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

// Bản build là SPA (shell tĩnh chỉ có root), nên trang này luôn render ở trình duyệt; chart và
// localStorage chỉ được đụng tới trong effect nên render phía server khi `pnpm dev` vẫn an toàn.
export const Route = createFileRoute("/")({ component: App })

const DASH = "dashboard"

function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [symbol, setSymbol] = useState("BTC-USDT-PERP")
  const [exchange, setExchange] = useState("binance")
  const [active, setActive] = useState<string>(DASH)
  const [library, setLibrary] = useState(true)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [syncOn, setSyncOn] = useState(true)
  const { workspaces, update, add, remove, reset } = useWorkspaces()

  // Mỗi tab một nhóm đồng bộ; đổi tab là dựng lại chart nên tạo nhóm mới.
  const sync = useMemo(() => new SyncGroup(), [active, symbol, exchange])
  sync.enabled = syncOn

  useEffect(() => {
    api
      .meta()
      .then(setMeta)
      .catch((e: Error) => setError(e.message))
  }, [])

  const ws = workspaces.find((w) => w.id === active)
  useEffect(() => {
    if (active !== DASH && workspaces.length && !ws) setActive(DASH)
  }, [active, workspaces, ws])

  if (error) {
    return (
      <div className="grid h-svh place-items-center p-6 text-center text-sm">
        <div className="space-y-2">
          <p className="text-destructive">Không gọi được API rinng: {error}</p>
          <p className="text-muted-foreground">
            Chạy backend: <code className="font-heading">uv run rinng web</code>
          </p>
        </div>
      </div>
    )
  }
  if (!meta) return <div className="h-svh" />

  return (
    <div className="flex h-svh flex-col gap-3 p-3">
      <nav className="flex flex-wrap items-center gap-2">
        <div className="mr-1 flex items-center gap-2 pl-1">
          <span className="grid size-7 place-items-center rounded-lg bg-primary font-heading text-sm font-bold text-primary-foreground">
            r
          </span>
          <span className="font-heading text-sm font-semibold tracking-tight">rinng</span>
        </div>

        <div className="flex flex-wrap items-center gap-1 rounded-4xl bg-muted p-[3px]">
          <TabButton active={active === DASH} onClick={() => setActive(DASH)}>
            <HugeiconsIcon icon={DashboardSquare02Icon} className="size-4" />
            Dashboard
          </TabButton>
          {workspaces.map((w) =>
            renaming === w.id ? (
              <Input
                key={w.id}
                autoFocus
                defaultValue={w.name}
                className="h-7 w-36 text-sm"
                onBlur={(e) => {
                  const name = e.currentTarget.value.trim()
                  if (name) update(w.id, (x) => ({ ...x, name }))
                  setRenaming(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur()
                  if (e.key === "Escape") setRenaming(null)
                }}
              />
            ) : (
              <TabButton
                key={w.id}
                active={active === w.id}
                onClick={() => setActive(w.id)}
                onDoubleClick={() => setRenaming(w.id)}
                onClose={workspaces.length > 1 ? () => remove(w.id) : undefined}
                closeLabel={`Đóng tab ${w.name}`}
              >
                {w.name}
              </TabButton>
            ),
          )}
          <Tooltip>
            <TooltipTrigger
              render={
                <Button variant="ghost" size="icon-xs" aria-label="Thêm tab chart" onClick={() => setActive(add())} />
              }
            >
              <HugeiconsIcon icon={Add01Icon} />
            </TooltipTrigger>
            <TooltipContent>Thêm tab chart</TooltipContent>
          </Tooltip>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Pick
            items={meta.instruments.map((v) => ({ value: v, label: v }))}
            value={symbol}
            onChange={setSymbol}
            label="Cặp giao dịch"
            className="font-medium"
          />
          <Pick
            items={meta.exchanges.map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))}
            value={exchange}
            onChange={setExchange}
            label="Sàn"
          />
          {ws ? (
            <>
              <LayoutPicker value={ws.layout} onChange={(l) => update(ws.id, (w) => ({ ...w, layout: l }))} />
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Switch checked={syncOn} onCheckedChange={setSyncOn} size="sm" aria-label="Đồng bộ con trỏ giữa các chart" />
                <HugeiconsIcon icon={Link04Icon} className="size-3.5" />
                đồng bộ
              </label>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      aria-label="Thư viện chart"
                      aria-pressed={library}
                      variant={library ? "secondary" : "ghost"}
                      size="icon-sm"
                      onClick={() => setLibrary(!library)}
                    />
                  }
                >
                  <HugeiconsIcon icon={LibraryIcon} />
                </TooltipTrigger>
                <TooltipContent>{library ? "Ẩn" : "Hiện"} thư viện chart</TooltipContent>
              </Tooltip>
            </>
          ) : null}
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Khôi phục tab mặc định"
                  onClick={() => {
                    if (confirm("Khôi phục các tab mặc định? Bố cục hiện tại sẽ mất.")) setActive(reset())
                  }}
                />
              }
            >
              <HugeiconsIcon icon={RefreshIcon} />
            </TooltipTrigger>
            <TooltipContent>Khôi phục tab mặc định</TooltipContent>
          </Tooltip>
        </div>
      </nav>

      <main className="flex min-h-0 flex-1 gap-3">
        {ws ? (
          <>
            {library ? <ChartLibrary /> : null}
            <WorkspaceGrid
              key={`${ws.id}-${symbol}-${exchange}`}
              ws={ws}
              meta={meta}
              symbol={symbol}
              exchange={exchange}
              sync={sync}
              onChange={(fn) => update(ws.id, fn)}
            />
          </>
        ) : (
          <Dashboard symbol={symbol} exchange={exchange} />
        )}
      </main>
    </div>
  )
}

function TabButton({
  active,
  children,
  onClose,
  closeLabel,
  ...props
}: React.ComponentProps<"button"> & {
  active: boolean
  onClose?: () => void
  closeLabel?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center rounded-4xl transition-colors",
        active
          ? "bg-background text-foreground ring-1 ring-foreground/10 dark:bg-input/40"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      <button
        type="button"
        {...props}
        className={cn(
          "inline-flex h-full items-center gap-1.5 rounded-4xl text-sm font-medium whitespace-nowrap",
          onClose ? "pr-1 pl-3" : "px-3",
        )}
      >
        {children}
      </button>
      {onClose ? (
        <button
          type="button"
          aria-label={closeLabel}
          onClick={onClose}
          className="mr-1.5 grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
        >
          <HugeiconsIcon icon={Cancel01Icon} className="size-3" />
        </button>
      ) : null}
    </span>
  )
}

// Ô chọn bố cục vẽ bằng chính grid-template-areas của bố cục đó.
function LayoutPicker({ value, onChange }: { value: LayoutKey; onChange: (l: LayoutKey) => void }) {
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
                    value === k ? "bg-background ring-1 ring-foreground/10 dark:bg-input/40" : "hover:bg-background/50",
                  )}
                />
              }
            >
              <span
                className="grid size-4 gap-[2px]"
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
                    className={cn("rounded-[2px]", value === k ? "bg-foreground/80" : "bg-muted-foreground/60")}
                  />
                ))}
              </span>
            </TooltipTrigger>
            <TooltipContent>{l.label}</TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}
