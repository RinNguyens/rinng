import { createFileRoute } from "@tanstack/react-router"
import { LockPanel } from "@/components/wallet/lock-panel"

export const Route = createFileRoute("/terminal/wallet/lock")({ component: LockPanel })
