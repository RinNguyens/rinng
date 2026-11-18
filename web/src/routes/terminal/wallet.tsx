import { Outlet, createFileRoute } from "@tanstack/react-router"
import { WalletToolbar } from "@/components/wallet/toolbar"

// Layout for the Wallet sub-tabs: toolbar, then the sub-tab page.
export const Route = createFileRoute("/terminal/wallet")({ component: Wallet })

function Wallet() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <WalletToolbar />
      <Outlet />
    </div>
  )
}
