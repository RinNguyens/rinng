import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Dashboard } from "@/components/dashboard"
import { useTerminal } from "@/components/terminal/context"
import { comboWorkspace } from "@/lib/combos"

export const Route = createFileRoute("/terminal/coin")({ component: Coin })

function Coin() {
  const { symbol, exchange, inst, tabs } = useTerminal()
  const navigate = useNavigate()
  return (
    <Dashboard
      symbol={symbol}
      exchange={exchange}
      instrument={inst}
      onOpenCombo={(c) => {
        const id = tabs.insert(comboWorkspace(c))
        navigate({ to: "/terminal/charts/$tabId", params: { tabId: id } })
      }}
    />
  )
}
