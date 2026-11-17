import { createFileRoute, redirect } from "@tanstack/react-router"
import { browserStore, readSection } from "@/lib/terminal-nav"

// /terminal opens the last section you visited. Search is passed on explicitly because
// retainSearchParams does not apply to redirects.
export const Route = createFileRoute("/terminal/")({
  beforeLoad: ({ search }) => {
    const section = readSection(browserStore())
    throw redirect({ to: `/terminal/${section}` as const, search, replace: true })
  },
})
