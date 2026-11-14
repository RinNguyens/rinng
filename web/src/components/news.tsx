import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { api } from "@/lib/api"
import type { News, NewsItem, NewsOutlook } from "@/lib/api"
import { cn } from "@/lib/utils"

// One shared poller: the ticker and the dashboard card read the same snapshot.
const POLL_MS = 20_000
let snapshot: News | null = null
let base = ""
const listeners = new Set<() => void>()
let timer: ReturnType<typeof setTimeout> | undefined

let seq = 0

async function poll() {
  clearTimeout(timer)
  const mine = ++seq
  try {
    const next = await api.news(base)
    if (mine !== seq) return // a newer poll (e.g. after a coin change) owns the timer
    snapshot = next
    listeners.forEach((l) => l())
  } catch {
    if (mine !== seq) return
    /* keep the last snapshot; retry on the next tick */
  }
  timer = setTimeout(poll, POLL_MS)
}

export function useNews(coin?: string): News | null {
  useEffect(() => {
    if (coin !== undefined && coin !== base) {
      base = coin
      void poll()
    }
  }, [coin])
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      if (listeners.size === 1 && !snapshot) void poll()
      return () => listeners.delete(l)
    },
    () => snapshot,
    () => null
  )
}

const TONE = {
  bullish: { text: "text-up", bg: "bg-up/15 text-up", label: "Bullish" },
  bearish: { text: "text-down", bg: "bg-down/15 text-down", label: "Bearish" },
  neutral: {
    text: "text-muted-foreground",
    bg: "bg-muted text-muted-foreground",
    label: "Neutral",
  },
} as const

function ago(ms: number) {
  const m = Math.max(0, Math.round((Date.now() - ms) / 60_000))
  return m < 60
    ? `${m}m`
    : m < 1440
      ? `${Math.floor(m / 60)}h`
      : `${Math.floor(m / 1440)}d`
}

const DAY = 86_400_000

function tickerItems(n: News): Array<NewsItem> {
  const recent = n.items.filter((i) => Date.now() - i.time < DAY)
  const important = recent.filter((i) => i.impact >= 2 || i.kind === "exchange")
  return (
    important.length >= 6 ? important : recent.length ? recent : n.items
  ).slice(0, 30)
}

function Headline({ it, fresh }: { it: NewsItem; fresh: boolean }) {
  const t = TONE[it.sentiment]
  return (
    <a
      href={it.url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex shrink-0 items-center gap-1.5 px-4 text-xs hover:underline"
      title={`${it.source} · ${it.tags.join(", ") || "no tag"}`}
    >
      {fresh ? (
        <span className="rounded bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
          NEW
        </span>
      ) : null}
      <span
        className={cn(
          "size-1.5 rounded-full",
          it.sentiment === "bullish"
            ? "bg-up"
            : it.sentiment === "bearish"
              ? "bg-down"
              : "bg-muted-foreground"
        )}
      />
      {it.impact === 3 ? (
        <span className={cn("font-semibold", t.text)}>!</span>
      ) : null}
      <span className="text-muted-foreground">{it.source}</span>
      <span className={cn(it.impact === 3 && "font-medium text-foreground")}>
        {it.title}
      </span>
      {it.coins.slice(0, 3).map((c) => (
        <span
          key={c}
          className="font-heading text-[10px] text-muted-foreground"
        >
          {c}
        </span>
      ))}
      <span className="font-heading text-[10px] text-muted-foreground">
        {ago(it.time)}
      </span>
    </a>
  )
}

/** Fixed bar above the header: scrolling important headlines, colored good/bad. */
export function NewsTicker() {
  const n = useNews()
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())

  // Headlines that appear after the first load are marked NEW for 5 minutes.
  useEffect(() => {
    if (!n) return
    const ids = n.items.map((i) => i.id)
    if (!seen.current) {
      seen.current = new Set(ids)
      return
    }
    const added = ids.filter((id) => !seen.current!.has(id))
    added.forEach((id) => seen.current!.add(id))
    if (!added.length) return
    setFresh((f) => new Set([...f, ...added]))
    const t = setTimeout(
      () =>
        setFresh((f) => new Set([...f].filter((id) => !added.includes(id)))),
      300_000
    )
    return () => clearTimeout(t)
  }, [n])

  if (!n)
    return (
      <div className="h-8 shrink-0 border-b border-foreground/10 bg-card" />
    )
  const items = tickerItems(n)
  const m = TONE[n.market.label]
  return (
    <div
      className="flex h-8 shrink-0 items-center overflow-hidden border-b border-foreground/10 bg-card"
      aria-label="Market news"
    >
      <span
        className={cn(
          "z-10 flex h-full shrink-0 items-center gap-1.5 px-3 text-xs font-medium",
          m.bg
        )}
        title={`24h news sentiment ${n.market.score.toFixed(2)} from ${n.market.count} headlines (keyword rules)`}
      >
        News · {m.label}
      </span>
      <div className="relative min-w-0 flex-1 overflow-hidden">
        <div
          className="news-marquee flex w-max"
          style={{
            ["--news-dur" as string]: `${Math.max(60, items.length * 8)}s`,
          }}
        >
          {[0, 1].map((k) => (
            <div key={k} className="flex" aria-hidden={k === 1}>
              {items.map((it) => (
                <Headline
                  key={`${k}-${it.id}`}
                  it={it}
                  fresh={fresh.has(it.id)}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function OutlookPill({ o, label }: { o: NewsOutlook; label: string }) {
  const t = TONE[o.label]
  return (
    <div className="flex items-center justify-between gap-2 rounded-xl bg-muted/50 px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("rounded-md px-2 py-0.5 text-xs font-medium", t.bg)}>
        {t.label} {o.score >= 0 ? "+" : ""}
        {o.score.toFixed(2)}
      </span>
      <span className="font-heading text-[11px] text-muted-foreground">
        {o.count} in 24h
      </span>
    </div>
  )
}

/** Dashboard card: 24h news outlook for the market and the selected coin, with its headlines. */
export function NewsCard({ base: coin }: { base: string }) {
  const n = useNews(coin)
  if (!n) return null
  const list = n.coin_items.length
    ? n.coin_items
    : n.items.filter((i) => i.impact === 3).slice(0, 8)
  return (
    <Card size="sm" className="shrink-0">
      <CardHeader>
        <CardTitle>Market-moving news</CardTitle>
        <CardAction>
          <span className="text-[11px] text-muted-foreground">
            keyword-scored · updated {ago(n.updated)} ago
          </span>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 md:grid-cols-2">
          <OutlookPill o={n.market} label="Market" />
          {n.coin ? <OutlookPill o={n.coin} label={coin} /> : null}
        </div>
        <ul className="space-y-1.5">
          {list.slice(0, 8).map((it) => (
            <li key={it.id} className="flex items-start gap-2 text-xs">
              <Badge
                className={cn("shrink-0 text-[10px]", TONE[it.sentiment].bg)}
              >
                {TONE[it.sentiment].label}
              </Badge>
              <a
                href={it.url}
                target="_blank"
                rel="noreferrer"
                className="min-w-0 flex-1 hover:underline"
              >
                {it.title}
              </a>
              <span className="shrink-0 font-heading text-[10px] text-muted-foreground">
                {it.source} · {ago(it.time)}
              </span>
            </li>
          ))}
          {!list.length ? (
            <li className="text-xs text-muted-foreground">
              No important news for {coin} yet.
            </li>
          ) : null}
        </ul>
      </CardContent>
    </Card>
  )
}
