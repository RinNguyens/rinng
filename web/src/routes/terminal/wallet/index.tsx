import { createFileRoute, redirect } from "@tanstack/react-router"

// /terminal/wallet has no page of its own: open Scan.
export const Route = createFileRoute("/terminal/wallet/")({
  beforeLoad: ({ search }) => {
    throw redirect({ to: "/terminal/wallet/scan", search, replace: true })
  },
})
