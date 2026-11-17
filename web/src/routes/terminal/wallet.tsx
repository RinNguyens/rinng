import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/terminal/wallet")({ component: Wallet })

function Wallet() {
  return (
    <div className="grid flex-1 place-items-center text-sm text-muted-foreground">
      Wallet — read-only scan, send check and lock. Coming in a later release.
    </div>
  )
}
