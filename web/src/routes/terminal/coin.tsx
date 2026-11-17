import { createFileRoute } from "@tanstack/react-router"
import { Dashboard } from "@/components/dashboard"
import { useTerminal } from "@/components/terminal/context"

export const Route = createFileRoute("/terminal/coin")({ component: Coin })

function Coin() {
  const { symbol, exchange, inst } = useTerminal()
  return <Dashboard symbol={symbol} exchange={exchange} instrument={inst} />
}
