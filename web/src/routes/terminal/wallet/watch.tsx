import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { WatchlistTable } from "@/components/wallet/watchlist"

export const Route = createFileRoute("/terminal/wallet/watch")({ component: Watch })

function Watch() {
  const navigate = useNavigate()
  return (
    <WatchlistTable
      onOpen={(address, net) =>
        navigate({ to: "/terminal/wallet/scan", search: (s) => ({ ...s, address, net, hl: "new" as const }) })
      }
    />
  )
}
