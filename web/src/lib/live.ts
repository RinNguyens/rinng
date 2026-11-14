// One shared WebSocket to /ws/live for the whole page. Charts and the dashboard listen for
// events; the client subscribes to the union of timeframes that mounted charts need.
import { useEffect, useRef, useState, useSyncExternalStore } from "react"

export type LiveBar = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type Base = { exchange: string; symbol: string }
export type LiveEvent =
  | ({ type: "tick"; price: number; time: number } & Base)
  | ({ type: "mark"; mark: number; index: number | null; funding_rate: number | null; time: number } & Base)
  | ({ type: "bar"; tf: string; bar: LiveBar } & Base)
  | ({ type: "close"; tf: string; time: number } & Base)
  | ({ type: "liq"; side: string; price: number; qty: number; time: number } & Base)
  | { type: "status"; feeds: Record<string, number> }

export type LiveState = "static" | "connecting" | "live" | "delayed" | "offline"

const SILENCE_MS = 6000 // server sends status every 2s; nothing for this long = offline

class LiveClient {
  private ws: WebSocket | null = null
  private enabled = false
  private symbol = ""
  private exchange = ""
  private tfs = new Map<string, number>()
  private listeners = new Set<(e: LiveEvent) => void>()
  private stateListeners = new Set<() => void>()
  private backoff = 1000
  private lastEvent = 0
  private feedAge: number | null = null
  state: LiveState = "static"
  lastTickAt = 0

  configure(enabled: boolean) {
    if (this.enabled === enabled) return
    this.enabled = enabled
    if (enabled) {
      this.connect()
      setInterval(() => this.refresh(), 1000)
    } else {
      this.setState("static")
    }
  }

  select(symbol: string, exchange: string) {
    if (symbol === this.symbol && exchange === this.exchange) return
    this.symbol = symbol
    this.exchange = exchange
    this.feedAge = null
    this.subscribe()
  }

  // A chart needs live bars for `tf` while mounted; returns the release function.
  retain(tf: string) {
    this.tfs.set(tf, (this.tfs.get(tf) ?? 0) + 1)
    if (this.tfs.get(tf) === 1) this.subscribe()
    return () => {
      const n = (this.tfs.get(tf) ?? 1) - 1
      if (n <= 0) this.tfs.delete(tf)
      else this.tfs.set(tf, n)
    }
  }

  on(fn: (e: LiveEvent) => void) {
    this.listeners.add(fn)
    return () => {
      this.listeners.delete(fn)
    }
  }

  onState(fn: () => void) {
    this.stateListeners.add(fn)
    return () => {
      this.stateListeners.delete(fn)
    }
  }

  private setState(s: LiveState) {
    if (s === this.state) return
    this.state = s
    for (const fn of this.stateListeners) fn()
  }

  // Live: the selected exchange's feed answered within 5s; delayed: within a minute.
  private refresh() {
    if (!this.enabled) return
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.setState(this.ws?.readyState === WebSocket.CONNECTING ? "connecting" : "offline")
      return
    }
    if (Date.now() - this.lastEvent > SILENCE_MS || this.feedAge == null) {
      this.setState(this.feedAge == null && Date.now() - this.lastEvent < SILENCE_MS ? "connecting" : "offline")
      return
    }
    this.setState(this.feedAge < 5 ? "live" : this.feedAge < 60 ? "delayed" : "offline")
  }

  private subscribe() {
    if (this.ws?.readyState !== WebSocket.OPEN || !this.symbol) return
    this.ws.send(
      JSON.stringify({ op: "sub", symbol: this.symbol, exchange: this.exchange, tfs: [...this.tfs.keys()] }),
    )
  }

  private connect() {
    if (!this.enabled) return
    const proto = location.protocol === "https:" ? "wss" : "ws"
    const ws = new WebSocket(`${proto}://${location.host}/ws/live`)
    this.ws = ws
    this.setState("connecting")
    ws.onopen = () => {
      this.backoff = 1000
      this.lastEvent = Date.now()
      this.subscribe()
    }
    ws.onmessage = (m) => {
      this.lastEvent = Date.now()
      const e = JSON.parse(m.data as string) as LiveEvent
      if (e.type === "status") {
        this.feedAge = e.feeds[this.exchange] ?? null
        this.refresh()
      } else if (e.type === "tick") {
        this.lastTickAt = Date.now()
      }
      for (const fn of this.listeners) fn(e)
    }
    ws.onclose = () => {
      if (this.ws !== ws) return
      this.ws = null
      this.setState("offline")
      setTimeout(() => this.connect(), this.backoff)
      this.backoff = Math.min(this.backoff * 2, 15000)
    }
  }
}

export const live = new LiveClient()

export function useLiveState() {
  return useSyncExternalStore<LiveState>(
    (fn) => live.onState(fn),
    () => live.state,
    () => "static",
  )
}

// Latest tick and mark for one instrument (null until the first event).
export function useLiveQuote(symbol: string, exchange: string) {
  const [tick, setTick] = useState<{ price: number; time: number } | null>(null)
  const [mark, setMark] = useState<{ mark: number; funding_rate: number | null } | null>(null)
  useEffect(() => {
    setTick(null)
    setMark(null)
    return live.on((e) => {
      if (e.type === "status" || e.symbol !== symbol || e.exchange !== exchange) return
      if (e.type === "tick") setTick({ price: e.price, time: e.time })
      if (e.type === "mark") setMark({ mark: e.mark, funding_rate: e.funding_rate })
    })
  }, [symbol, exchange])
  return { tick, mark }
}

// Calls `fn` when a candle of `tf` closes for the instrument (closed-candle analysis is stale).
export function useBarClose(symbol: string, exchange: string, tf: string, fn: () => void) {
  const latest = useRef(fn)
  latest.current = fn
  useEffect(() => {
    const release = live.retain(tf)
    const off = live.on((e) => {
      if (e.type === "close" && e.symbol === symbol && e.exchange === exchange && e.tf === tf) {
        latest.current()
      }
    })
    return () => {
      off()
      release()
    }
  }, [symbol, exchange, tf])
}
