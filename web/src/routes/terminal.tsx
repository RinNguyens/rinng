import { useEffect, useState } from "react"
import {
  Link,
  Outlet,
  createFileRoute,
  retainSearchParams,
  useLocation,
  useNavigate,
} from "@tanstack/react-router"
import { VenueIcon } from "@/components/coin-icon"
import { Pick } from "@/components/workspace-grid"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { api } from "@/lib/api"
import type { Instrument, Meta } from "@/lib/api"
import { CoinSearch } from "@/components/coin-search"
import { NewsTicker } from "@/components/news"
import { TerminalContext } from "@/components/terminal/context"
import { live, useLiveState } from "@/lib/live"
import type { LiveState } from "@/lib/live"
import {
  browserStore,
  exchangeFor,
  isExchange,
  isResolved,
  needsWriteBack,
  parseSearch,
  readSavedInstrument,
  resolveInstrument,
  sectionFromPath,
  writeSection,
} from "@/lib/terminal-nav"
import type { Current } from "@/lib/terminal-nav"
import { useWorkspaces } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

// The build is an SPA (the static shell holds only the root), so this page always renders in the
// browser; charts and localStorage are only touched in effects, so SSR under `pnpm dev` is safe.
// This is the layout for every /terminal/* section; the coin and exchange live in the URL.
export const Route = createFileRoute("/terminal")({
  validateSearch: parseSearch,
  search: { middlewares: [retainSearchParams(["symbol", "ex"])] },
  component: Shell,
})

const INST_KEY = "rinng.instrument.v1"

const NAV = [
  { to: "/terminal/market", label: "Market" },
  { to: "/terminal/coin", label: "Coin" },
  { to: "/terminal/charts", label: "Charts" },
  { to: "/terminal/wallet", label: "Wallet" },
] as const

function Shell() {
  const search = Route.useSearch()
  const navigate = useNavigate()
  const pathname = useLocation({ select: (l) => l.pathname })
  const section = sectionFromPath(pathname)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cur, setCur] = useState<Current | null>(null)
  const tabs = useWorkspaces()

  useEffect(() => {
    api
      .meta()
      .then(setMeta)
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (meta) live.configure(meta.live)
  }, [meta])

  // Resolve the URL symbol: watchlist, then the saved coin, then the network, then saved or first.
  useEffect(() => {
    if (!meta || isResolved(search.symbol, cur)) return
    const key = search.symbol
    const saved = readSavedInstrument(browserStore())
    const local = resolveInstrument(key, meta.instruments, saved)
    if (local || key === undefined) {
      if (local) setCur({ key, inst: local })
      return
    }
    // A failed lookup still shows a coin (saved or first) but says so, and keeps the URL as asked.
    let alive = true
    api.instrument(key).then(
      (inst) => alive && setCur({ key, inst }),
      (e: Error) => {
        const inst = resolveInstrument(undefined, meta.instruments, saved)
        if (alive && inst) setCur({ key, inst, error: e.message })
      }
    )
    return () => {
      alive = false
    }
    // cur is read only to skip work; the effect must re-run on the URL symbol, not on cur.
  }, [meta, search.symbol])

  const symbol = cur?.inst.id
  const exchange = cur ? exchangeFor(cur.inst, search.ex ?? "binance") : undefined

  // Canonicalise the URL (alias, missing or unlisted exchange) without a history entry.
  useEffect(() => {
    if (!cur || !needsWriteBack(search, cur, exchange)) return
    navigate({
      to: ".",
      search: (p) => ({ ...p, symbol: cur.inst.id, ex: exchange }),
      replace: true,
    })
  }, [cur, exchange, search, navigate])

  // Remember the coin, but not a fallback shown for a failed lookup.
  useEffect(() => {
    if (!cur || cur.error) return
    try {
      browserStore()?.setItem(INST_KEY, JSON.stringify(cur.inst))
    } catch {
      /* storage full */
    }
  }, [cur])

  useEffect(() => {
    if (section) writeSection(browserStore(), section)
  }, [section])

  useEffect(() => {
    if (symbol && exchange) live.select(symbol, exchange)
  }, [symbol, exchange])

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
  if (!meta || !cur || !symbol || !exchange) return <div className="h-svh" />

  // User picks push a history entry so Back restores the previous coin.
  const choose = (next: Instrument) => {
    setCur({ key: next.id, inst: next })
    navigate({
      to: ".",
      search: (p) => ({ ...p, symbol: next.id, ex: exchangeFor(next, exchange) }),
    })
  }
  const setExchange = (v: string) => {
    if (isExchange(v)) navigate({ to: ".", search: (p) => ({ ...p, ex: v }) })
  }

  return (
    <div className="flex h-svh flex-col">
      <NewsTicker />
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
        <nav className="flex flex-wrap items-center gap-2">
          <Link
            to="/"
            aria-label="Go to home"
            className="mr-1 flex cursor-pointer items-center gap-2 rounded-lg pl-1 hover:opacity-80"
          >
            <img src="/logo.svg" alt="" className="size-7 rounded-lg" />
            <span className="font-heading text-sm font-semibold tracking-tight">
              rinng
            </span>
          </Link>

          <div className="flex items-center gap-0.5 rounded-4xl bg-muted p-[3px]">
            {NAV.map((n) => (
              <Link
                key={n.to}
                to={n.to}
                className="inline-flex h-7 items-center rounded-full px-3 text-xs font-medium transition-colors"
                activeProps={{
                  className: "bg-background ring-1 ring-foreground/10 dark:bg-input/40",
                }}
                inactiveProps={{ className: "hover:bg-background/50" }}
              >
                {n.label}
              </Link>
            ))}
          </div>

          {section && section !== "wallet" ? (
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {section !== "market" ? (
                <>
                  <LiveBadge />
                  <CoinSearch
                    value={cur.inst}
                    watchlist={meta.instruments}
                    onSelect={choose}
                  />
                </>
              ) : null}
              <Pick
                items={meta.exchanges
                  .filter((v) => cur.inst[v as "binance" | "okx"] !== false)
                  .map((v) => ({
                    value: v,
                    label: v === "okx" ? "OKX" : v[0].toUpperCase() + v.slice(1),
                    icon: <VenueIcon id={v} size={14} />,
                  }))}
                value={exchange}
                onChange={setExchange}
                label="Exchange"
              />
            </div>
          ) : null}
        </nav>

        <TerminalContext.Provider
          value={{ meta, inst: cur.inst, symbol, exchange, choose, setExchange, tabs }}
        >
          {cur.error ? (
            <p
              role="alert"
              className="shrink-0 rounded-xl bg-card px-3 py-2 text-xs ring-1 ring-foreground/10"
            >
              <span className="text-destructive">
                Could not open{" "}
                <span className="font-heading">{cur.key}</span>: {cur.error}.
              </span>{" "}
              <span className="text-muted-foreground">
                Showing {cur.inst.name} instead. Reload to try again, or pick a coin.
              </span>
            </p>
          ) : null}
          <main className="flex min-h-0 flex-1 gap-3">
            <Outlet />
          </main>
        </TerminalContext.Provider>
      </div>
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
