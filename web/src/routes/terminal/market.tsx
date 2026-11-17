import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/terminal/market")({ component: Market })

function Market() {
  return (
    <div className="grid flex-1 place-items-center text-sm text-muted-foreground">
      Market — every perp on one exchange. Coming in a later release.
    </div>
  )
}
