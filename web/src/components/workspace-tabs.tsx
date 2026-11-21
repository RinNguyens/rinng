import { useEffect, useRef, useState } from "react"
import type { KeyboardEvent } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Add01Icon,
  Cancel01Icon,
  MoreHorizontalIcon,
} from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { closeTarget, tabKey } from "@/lib/workspaces"
import type { Workspace } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

export function WorkspaceTabs({
  workspaces,
  activeId,
  onSelect,
  onAdd,
  onClose,
  onRename,
  onDuplicate,
  onReset,
}: {
  workspaces: Array<Workspace>
  activeId: string
  onSelect: (id: string) => void
  onAdd: () => void
  onClose: (id: string) => void
  onRename: (id: string, name: string) => void
  onDuplicate: (id: string) => void
  onReset: () => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [confirmReset, setConfirmReset] = useState(false)
  const tabRefs = useRef(new Map<string, HTMLElement>())
  const ids = workspaces.map((w) => w.id)
  const single = workspaces.length === 1

  useEffect(() => {
    tabRefs.current
      .get(activeId)
      ?.scrollIntoView({ block: "nearest", inline: "nearest" })
  }, [activeId])

  const startEdit = (w: Workspace) => {
    setDraft(w.name)
    setEditing(w.id)
  }

  const finishEdit = (id: string, save: boolean, refocus = true) => {
    if (save) onRename(id, draft)
    setEditing(null)
    if (refocus) requestAnimationFrame(() => tabRefs.current.get(id)?.focus())
  }

  const close = (id: string) => {
    const next = closeTarget(ids, id, activeId)
    onClose(id)
    requestAnimationFrame(() => tabRefs.current.get(next ?? activeId)?.focus())
  }

  const onTabKey = (e: KeyboardEvent, w: Workspace) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      onSelect(w.id)
    } else if (e.key === "F2") {
      e.preventDefault()
      startEdit(w)
    } else if (e.key === "Delete" && !single) {
      e.preventDefault()
      close(w.id)
    } else {
      const to = tabKey(ids, w.id, e.key)
      if (to) {
        e.preventDefault()
        tabRefs.current.get(to)?.focus()
      }
    }
  }

  const active = workspaces.find((w) => w.id === activeId)

  return (
    <div className="flex min-w-0 items-center gap-1">
      <div
        role="tablist"
        aria-label="Workspaces"
        className="flex min-w-0 [scrollbar-width:none] items-center gap-0.5 overflow-x-auto [&::-webkit-scrollbar]:hidden"
      >
        {workspaces.map((w) => {
          const isActive = w.id === activeId
          return (
            <div
              key={w.id}
              className={cn(
                "group/tab relative flex shrink-0 items-center rounded-md after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-foreground after:opacity-0",
                isActive && "after:opacity-100"
              )}
            >
              {editing === w.id ? (
                <Input
                  autoFocus
                  aria-label="Tab name"
                  className="h-7 w-40"
                  maxLength={32}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onFocus={(e) => e.target.select()}
                  onBlur={() => finishEdit(w.id, true, false)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault()
                      finishEdit(w.id, true)
                    } else if (e.key === "Escape") {
                      e.preventDefault()
                      e.stopPropagation()
                      finishEdit(w.id, false)
                    }
                  }}
                />
              ) : (
                <>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    tabIndex={isActive ? 0 : -1}
                    ref={(el) => {
                      if (el) tabRefs.current.set(w.id, el)
                      else tabRefs.current.delete(w.id)
                    }}
                    onClick={() => onSelect(w.id)}
                    onDoubleClick={() => startEdit(w)}
                    onKeyDown={(e) => onTabKey(e, w)}
                    className={cn(
                      "max-w-48 truncate rounded-md py-1 pl-2.5 text-sm transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
                      single ? "pr-2.5" : "pr-6",
                      isActive ? "text-foreground" : "text-muted-foreground"
                    )}
                  >
                    {w.name}
                  </button>
                  {single ? null : (
                    <button
                      type="button"
                      tabIndex={-1}
                      aria-label={`Close tab ${w.name}`}
                      onClick={() => close(w.id)}
                      className={cn(
                        "absolute right-1 grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-foreground/10 hover:text-foreground",
                        isActive
                          ? "opacity-100"
                          : "opacity-0 group-focus-within/tab:opacity-100 group-hover/tab:opacity-100"
                      )}
                    >
                      <HugeiconsIcon icon={Cancel01Icon} className="size-3" />
                    </button>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>

      <Button
        variant="ghost"
        size="icon-xs"
        aria-label="Add chart tab"
        onClick={onAdd}
      >
        <HugeiconsIcon icon={Add01Icon} />
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="ghost" size="icon-xs" aria-label="Tab actions" />
          }
        >
          <HugeiconsIcon icon={MoreHorizontalIcon} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-auto">
          <DropdownMenuItem onClick={() => active && startEdit(active)}>
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onDuplicate(activeId)}>
            Duplicate
          </DropdownMenuItem>
          <DropdownMenuItem disabled={single} onClick={() => close(activeId)}>
            Close
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            variant="destructive"
            onClick={() => setConfirmReset(true)}
          >
            Restore default tabs…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={confirmReset} onOpenChange={setConfirmReset}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              Restore the 4 default tabs? Your {workspaces.length}{" "}
              {workspaces.length === 1 ? "tab" : "tabs"} will be replaced.
            </DialogTitle>
            <DialogDescription>This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmReset(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmReset(false)
                onReset()
              }}
            >
              Restore
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
