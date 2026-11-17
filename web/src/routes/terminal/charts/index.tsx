import { useEffect } from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useTerminal } from "@/components/terminal/context"
import { tabRedirect } from "@/lib/terminal-nav"

export const Route = createFileRoute("/terminal/charts/")({ component: ChartsIndex })

// /terminal/charts has no view of its own: forward to the first workspace once they load.
function ChartsIndex() {
  const { tabs } = useTerminal()
  const navigate = useNavigate()
  const tabId = tabRedirect(undefined, tabs.workspaces)
  useEffect(() => {
    if (tabId) navigate({ to: "/terminal/charts/$tabId", params: { tabId }, replace: true })
  }, [tabId, navigate])
  return null
}
