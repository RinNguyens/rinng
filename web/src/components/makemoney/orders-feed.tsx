// The "Lệnh" tab and the alert toasts: open orders with their live R, and every order event
// (opened, +0.5R steps, heading to the stop, TP1, take-profit, stop-loss, liquidation) as it
// happens, as an in-page toast and, if allowed, a browser notification with a short sound.
import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { ago, num, price, tone } from "@/lib/format"
import { cn } from "@/lib/utils"

export type Alert = {
  id: number
  t: number
  order_id: number | null
  symbol: string | null
  side: "long" | "short" | null
  kind: "open" | "r_up" | "r_down" | "tp1" | "close"
  level: "good" | "bad" | "info"
  title: string
  body: string
}
export type FeedPosition = {
  id?: number
  symbol: string
  side: "long" | "short"
  entry: number
  stop: number
  take: number
  leverage: number
  mark?: number
  upnl: number
  opened: number
  be?: boolean
}

const SEEN_KEY = "rinng.makemoney.alerts.seen"
const SOUND_KEY = "rinng.makemoney.alerts.sound"
const ICON: Record<Alert["kind"], string> = {
  open: "●",
  r_up: "▲",
  r_down: "▼",
  tp1: "◆",
  close: "■",
}
const coin = (s: string) => s.split("-")[0]

function readSeen(): number {
  try {
    return Number(localStorage.getItem(SEEN_KEY) ?? 0)
  } catch {
    return 0
  }
}

export function useUnseen(alerts: Array<Alert>) {
  const [seen, setSeen] = useState(readSeen)
  const unseen = alerts.filter((a) => a.id > seen).length
  const markSeen = () => {
    const top = alerts[0]?.id ?? seen
    setSeen(top)
    try {
      localStorage.setItem(SEEN_KEY, String(top))
    } catch {
      /* no storage */
    }
  }
  return { unseen, markSeen }
}

/* ------------------------------------------------------------- the tab */

export function OrdersFeed({
  positions,
  rNow,
  alerts,
}: {
  positions: Array<FeedPosition>
  rNow: Partial<Record<string, number>>
  alerts: Array<Alert>
}) {
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(
    () =>
      typeof Notification === "undefined"
        ? "unsupported"
        : Notification.permission
  )
  const [sound, setSound] = useState(() => {
    try {
      return localStorage.getItem(SOUND_KEY) !== "off"
    } catch {
      return true
    }
  })
  const ask = () => {
    if (typeof Notification === "undefined") return
    void Notification.requestPermission().then(setPerm)
  }
  const toggleSound = () =>
    setSound((v) => {
      try {
        localStorage.setItem(SOUND_KEY, v ? "off" : "on")
      } catch {
        /* no storage */
      }
      return !v
    })

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {perm === "granted" ? (
          <span className="rounded bg-emerald-500/15 px-2 py-1 text-emerald-500">
            Browser notifications on
          </span>
        ) : perm === "unsupported" ? (
          <span className="text-muted-foreground">
            Browser notifications unavailable
          </span>
        ) : (
          <Button size="sm" variant="outline" onClick={ask}>
            Bật thông báo trình duyệt
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={toggleSound}>
          {sound ? "🔔 Âm thanh bật" : "🔕 Âm thanh tắt"}
        </Button>
      </div>

      <section>
        <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
          Đang mở ({positions.length})
        </h3>
        {positions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Chưa có lệnh. Bot đang chờ tín hiệu.
          </p>
        ) : (
          <ul className="grid gap-2">
            {positions.map((p) => {
              const r = rNow[String(p.id)] ?? 0
              // a bar from the stop (-1R) to the target
              const tR =
                Math.abs(p.take - p.entry) / Math.abs(p.entry - p.stop || 1)
              const at = Math.min(100, Math.max(0, ((r + 1) / (tR + 1)) * 100))
              return (
                <li key={p.id} className="rounded-lg border p-2.5">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-mono text-xs text-muted-foreground">
                      #{p.id}
                    </span>
                    <b>{coin(p.symbol)}</b>
                    <span
                      className={cn(
                        "rounded px-1 text-[11px] font-semibold",
                        p.side === "long"
                          ? "bg-emerald-500/15 text-emerald-500"
                          : "bg-red-500/15 text-red-500"
                      )}
                    >
                      {p.side === "long" ? "LONG" : "SHORT"} x{p.leverage}
                    </span>
                    <span
                      className={cn(
                        "ml-auto font-mono font-semibold",
                        tone(p.upnl)
                      )}
                    >
                      {p.upnl >= 0 ? "+" : ""}
                      {num(p.upnl, 2)}$
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between font-mono text-[11px] text-muted-foreground">
                    <span>
                      {price(p.entry)} → {price(p.mark ?? p.entry)}
                    </span>
                    <span className={tone(r)}>
                      {r >= 0 ? "+" : ""}
                      {num(r, 2)}R
                    </span>
                  </div>
                  <div className="relative mt-1.5 h-1.5 rounded-full bg-gradient-to-r from-red-500/60 via-muted to-emerald-500/60">
                    <div
                      className="absolute top-0 h-1.5 w-0.5 bg-sky-400"
                      style={{ left: `${(1 / (tR + 1)) * 100}%` }}
                    />
                    <div
                      className="absolute -top-0.5 size-2.5 -translate-x-1/2 rounded-full bg-foreground transition-[left] duration-500"
                      style={{ left: `${at}%` }}
                    />
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                    <span>SL {p.be ? "BE" : "-1R"}</span>
                    <span>{ago(p.opened)}</span>
                    <span>TP +{num(tR, 1)}R</span>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
          Thông báo realtime
        </h3>
        {alerts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Chưa có thông báo. Mỗi lệnh mở, mỗi +0.5R, khi tiến về stop, TP1, TP
            hay SL đều hiện ở đây.
          </p>
        ) : (
          <ul className="grid gap-1.5">
            {alerts.map((a) => (
              <li
                key={a.id}
                className={cn(
                  "rounded-md border-l-2 bg-muted/40 px-2.5 py-1.5",
                  a.level === "good" && "border-emerald-500",
                  a.level === "bad" && "border-red-500",
                  a.level === "info" && "border-sky-400"
                )}
              >
                <div className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className={cn(
                      a.level === "good" && "text-emerald-500",
                      a.level === "bad" && "text-red-500",
                      a.level === "info" && "text-sky-400"
                    )}
                  >
                    {ICON[a.kind]}
                  </span>
                  <span className="font-medium">{a.title}</span>
                  <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                    {ago(a.t)}
                  </span>
                </div>
                <div className="font-mono text-[11px] text-muted-foreground">
                  {a.body}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

/* ------------------------------------------------------------- toasts */

function beep(good: boolean) {
  try {
    const ctx = new AudioContext()
    const o = ctx.createOscillator()
    const g = ctx.createGain()
    o.frequency.value = good ? 880 : 330
    g.gain.setValueAtTime(0.06, ctx.currentTime)
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35)
    o.connect(g).connect(ctx.destination)
    o.start()
    o.stop(ctx.currentTime + 0.35)
  } catch {
    /* audio blocked until the user interacts with the page */
  }
}

export function AlertToaster({ alerts }: { alerts: Array<Alert> }) {
  const [toasts, setToasts] = useState<Array<Alert>>([])
  const last = useRef<number | null>(null)

  useEffect(() => {
    const top = alerts[0]?.id ?? 0
    if (last.current == null) {
      last.current = top // do not replay history when the page opens
      return
    }
    const fresh = alerts.filter((a) => a.id > (last.current ?? 0)).reverse()
    if (!fresh.length) return
    last.current = top
    setToasts((t) => [...fresh, ...t].slice(0, 4))
    let soundOn = true
    try {
      soundOn = localStorage.getItem(SOUND_KEY) !== "off"
    } catch {
      /* default on */
    }
    for (const a of fresh) {
      if (soundOn) beep(a.level !== "bad")
      if (
        typeof Notification !== "undefined" &&
        Notification.permission === "granted"
      ) {
        try {
          new Notification(a.title, { body: a.body, tag: `mm-${a.id}` })
        } catch {
          /* some browsers only allow notifications from a service worker */
        }
      }
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== a.id)), 9000)
    }
  }, [alerts])

  if (!toasts.length) return null
  return (
    <div className="pointer-events-none fixed top-14 right-4 z-50 grid w-80 gap-2">
      {toasts.map((a) => (
        <div
          key={a.id}
          className={cn(
            "pointer-events-auto rounded-lg border bg-card p-3 shadow-lg",
            a.level === "good" && "border-emerald-500/60",
            a.level === "bad" && "border-red-500/60",
            a.level === "info" && "border-sky-400/60"
          )}
        >
          <div className="flex items-start gap-2">
            <span
              className={cn(
                "text-base leading-none",
                a.level === "good" && "text-emerald-500",
                a.level === "bad" && "text-red-500",
                a.level === "info" && "text-sky-400"
              )}
            >
              {ICON[a.kind]}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">{a.title}</div>
              <div className="font-mono text-[11px] text-muted-foreground">
                {a.body}
              </div>
            </div>
            <button
              type="button"
              aria-label="Dismiss"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => setToasts((t) => t.filter((x) => x.id !== a.id))}
            >
              ×
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
