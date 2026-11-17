import { createContext, useContext } from "react"
import type { Instrument, Meta } from "@/lib/api"
import type { Exchange } from "@/lib/terminal-nav"
import type { useWorkspaces } from "@/lib/workspaces"

export type TerminalState = {
  meta: Meta
  inst: Instrument
  symbol: string
  exchange: Exchange
  choose: (next: Instrument) => void
  setExchange: (ex: string) => void
  tabs: ReturnType<typeof useWorkspaces>
}

export const TerminalContext = createContext<TerminalState | null>(null)

export function useTerminal(): TerminalState {
  const v = useContext(TerminalContext)
  if (!v) throw new Error("useTerminal outside /terminal")
  return v
}
