import type { ReactNode } from "react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { HugeiconsIcon } from "@hugeicons/react"
import { Loading03Icon } from "@hugeicons/core-free-icons"
import { MarketTable } from "@/components/market/market-table"
import { MoverCard } from "@/components/market/mover-card"
import type { MoverGroup } from "@/components/market/mover-card"
import { useTerminal } from "@/components/terminal/context"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import type { MarketRow, MarketSnapshot, NewsOutlook } from "@/lib/api"
import { ago, num, pct, tone } from "@/lib/format"
import {
  annualized,
  crowding,
  filterRows,
  fundingExtremes,
  movers,
  parseMarketSearch,
  priceMoves,
  segmentRows,
  sortRows,
} from "@/lib/market"
import type { MarketDir, MarketSeg, MarketSort } from "@/lib/market"
import { readStarred, toggleStarred } from "@/lib/starred"
import { browserStore } from "@/lib/terminal-nav"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/terminal/market")({
  validateSearch: parseMarketSearch,
  component: Market,
})

const POLL_MS = 30_000
const SEGMENTS: Array<{ id: MarketSeg; label: string }> = [
  { id: "all", label: "All" },
  { id: "watch", label: "Watchlist" },
  { id: "top", label: "Top volume" },
]

const visible = () => document.visibilityState === "visible"
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches

// Owns the 1 s tick so the table and cards do not re-render with it.
function Ago({ time }: { time: number }) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  return <>{ago(time, nowMs)}</>
}

function Market() {
  const { exchange } = useTerminal()
  const search = Route.useSearch()
  const navigate = useNavigate({ from: "/terminal/market" })
  const seg = search.seg ?? "all"
  const sort = search.sort ?? "volume_24h"
  const dir = search.dir ?? "desc"

  const [snap, setSnap] = useState<MarketSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [flash, setFlash] = useState<Record<string, "up" | "down">>({})
  const [news, setNews] = useState<NewsOutlook | null>(null)
  const [query, setQuery] = useState("")
  const [starred, setStarred] = useState(() => readStarred(browserStore()))
  const [newsFailed, setNewsFailed] = useState(false)
  const last = useRef<MarketSnapshot | null>(null)
  const seq = useRef(0)
  const flashTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const exchangeRef = useRef(exchange)
  exchangeRef.current = exchange

  const load = useCallback(async () => {
    const ex = exchange
    const id = ++seq.current
    const live = () => exchangeRef.current === ex && seq.current === id
    setRefreshing(true)
    let next: MarketSnapshot
    try {
      next = await api.market({ exchange: ex })
    } catch (e) {
      if (live()) {
        setError(e instanceof Error ? e.message : "request failed")
        setRefreshing(false)
      }
      return
    }
    if (!live()) return
    setRefreshing(false)
    const prev = last.current?.exchange === next.exchange ? last.current : null
    last.current = next
    setSnap(next)
    setError(null)
    clearTimeout(flashTimer.current)
    if (!prev || reducedMotion()) return
    setFlash(priceMoves(prev.rows, next.rows))
    flashTimer.current = setTimeout(() => setFlash({}), 600)
  }, [exchange])

  useEffect(() => {
    last.current = null
    setFlash({})
    setSnap(null)
    setError(null)
    load()
    const t = setInterval(() => visible() && load(), POLL_MS)
    const onVisible = () => visible() && load()
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      clearInterval(t)
      document.removeEventListener("visibilitychange", onVisible)
      clearTimeout(flashTimer.current)
    }
  }, [load])

  useEffect(() => {
    let alive = true
    api
      .news("BTC")
      .then((n) => alive && setNews(n.market))
      .catch(() => alive && setNewsFailed(true))
    return () => {
      alive = false
    }
  }, [])

  const rows = snap?.rows
  const view = useMemo(() => {
    if (!rows) return []
    return sortRows(filterRows(segmentRows(rows, seg, starred), query), sort, dir)
  }, [rows, seg, starred, query, sort, dir])
  const counts = useMemo(
    () =>
      Object.fromEntries(
        SEGMENTS.map((s) => [s.id, rows ? segmentRows(rows, s.id, starred).length : 0])
      ),
    [rows, starred]
  )

  const open = useCallback(
    (row: MarketRow) =>
      navigate({ to: "/terminal/coin", search: { symbol: row.symbol, ex: exchange } }),
    [navigate, exchange]
  )

  const setSearch = (patch: { seg?: MarketSeg; sort?: MarketSort; dir?: MarketDir }) =>
    navigate({
      to: ".",
      replace: true,
      search: (p) => {
        const n = { ...p, ...patch }
        return {
          ...n,
          seg: n.seg === "all" ? undefined : n.seg,
          sort: n.sort === "volume_24h" ? undefined : n.sort,
          dir: n.dir === "desc" ? undefined : n.dir,
        }
      },
    })

  const onSort = (key: MarketSort) =>
    key === sort
      ? setSearch({ dir: dir === "asc" ? "desc" : "asc" })
      : setSearch({ sort: key, dir: key === "base" ? "asc" : "desc" })

  const cards = useMemo(() => {
    if (!rows) return null
    const m = movers(rows)
    const f = fundingExtremes(rows)
    const c = crowding(rows)
    const change = (r: MarketRow) => <span className={tone(r.chg_24h)}>{pct(r.chg_24h)}</span>
    const yearly = (r: MarketRow) => (
      <span className={tone(r.funding_rate_pct)}>
        {pct(annualized(r.funding_rate_pct), 0)} / yr
      </span>
    )
    const ratio = (r: MarketRow, side: string) => (
      <>
        {num(r.ls_ratio ?? 0, 2)} <span className="text-muted-foreground">{side}</span>
      </>
    )
    const group = (label: string, list: Array<MarketRow>, value: (r: MarketRow) => ReactNode) =>
      ({ label, items: list.map((row) => ({ row, value: value(row) })) }) satisfies MoverGroup
    return {
      movers: [group("Up", m.up, change), group("Down", m.down, change)],
      funding: [group("Highest", f.high, yearly), group("Lowest", f.low, yearly)],
      crowding: [
        group("Long", c.long, (r) => ratio(r, "long")),
        group("Short", c.short, (r) => ratio(r, "short")),
      ],
    }
  }, [rows])

  const toggle = useCallback(
    (symbol: string) => setStarred(toggleStarred(browserStore(), symbol)),
    []
  )
  const q = query.trim()

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-2">
      <div className="grid grid-cols-2 gap-3 max-md:flex max-md:overflow-x-auto xl:grid-cols-4">
        {cards ? (
          <>
            <MoverCard title="Movers 24h" groups={cards.movers} onOpen={open} />
            <MoverCard title="Funding extremes" groups={cards.funding} onOpen={open} />
            <MoverCard title="Crowding (L/S)" groups={cards.crowding} onOpen={open} />
          </>
        ) : (
          Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-44 rounded-2xl max-md:min-w-64" />
          ))
        )}
        {news ? (
          <Card size="sm" className="gap-1.5 max-md:min-w-64">
            <CardContent className="space-y-1">
              <div className="pb-1 text-xs font-medium text-muted-foreground">News outlook</div>
              <div className="flex items-baseline gap-2 font-heading">
                <span
                  className={cn(
                    "text-lg font-medium capitalize",
                    news.label === "neutral" ? "text-muted-foreground" : news.label === "bullish" ? "text-up" : "text-down"
                  )}
                >
                  {news.label}
                </span>
                <span className="tabular-nums">{num(news.score, 2)}</span>
                <span className="text-xs text-muted-foreground">({news.count})</span>
              </div>
            </CardContent>
          </Card>
        ) : newsFailed ? (
          <Card size="sm" className="gap-1.5 max-md:min-w-64">
            <CardContent className="space-y-1">
              <div className="pb-1 text-xs font-medium text-muted-foreground">News outlook</div>
              <p role="alert" className="text-sm text-muted-foreground">
                News outlook unavailable
              </p>
            </CardContent>
          </Card>
        ) : !snap ? (
          <Skeleton className="h-44 rounded-2xl max-md:min-w-64" />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {SEGMENTS.map((s) => (
          <Button
            key={s.id}
            size="sm"
            variant={seg === s.id ? "secondary" : "ghost"}
            aria-pressed={seg === s.id}
            onClick={() => setSearch({ seg: s.id })}
          >
            {s.label}
            <span className="font-heading tabular-nums text-muted-foreground">{counts[s.id]}</span>
          </Button>
        ))}
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter coins…"
          aria-label="Filter coins"
          className="ml-auto w-full sm:w-64"
        />
        {snap ? (
          <span className="flex items-center gap-1.5 font-heading text-xs text-muted-foreground">
            {refreshing ? (
              <HugeiconsIcon icon={Loading03Icon} className="size-3 animate-spin motion-reduce:animate-none" />
            ) : null}
            updated <Ago time={snap.time} />
          </span>
        ) : null}
      </div>

      {error && snap ? (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <span>
            Could not refresh market data: {error}. Showing data from <Ago time={snap.time} />.
          </span>
          <Button size="xs" variant="outline" className="ml-auto" onClick={load}>
            Retry
          </Button>
        </div>
      ) : null}

      {!snap && error ? (
        <div
          role="alert"
          className="grid flex-1 place-items-center gap-2 py-16 text-center text-sm text-muted-foreground"
        >
          <p>Could not load market data: {error}. No coins are shown.</p>
          <Button size="sm" variant="outline" onClick={load}>
            Retry
          </Button>
        </div>
      ) : !snap ? (
        <div className="space-y-px">
          {Array.from({ length: 12 }, (_, i) => (
            <Skeleton key={i} className="h-9 rounded-md" />
          ))}
        </div>
      ) : view.length === 0 ? (
        <div className="grid place-items-center gap-2 py-16 text-center text-sm text-muted-foreground">
          {q ? (
            <>
              <p>No coin matches “{q}”.</p>
              <Button size="sm" variant="outline" onClick={() => setQuery("")}>
                Clear filter
              </Button>
            </>
          ) : seg === "watch" ? (
            <p>Star a coin to add it here.</p>
          ) : (
            <p>No coins.</p>
          )}
        </div>
      ) : (
        <MarketTable
          rows={view}
          sort={sort}
          dir={dir}
          onSort={onSort}
          starred={starred}
          onToggleStar={toggle}
          onOpen={open}
          flash={flash}
        />
      )}
    </div>
  )
}
