import { Link } from "@tanstack/react-router"
import { HugeiconsIcon } from "@hugeicons/react"
import { LockIcon } from "@hugeicons/core-free-icons"

const TABS = [
  { to: "/terminal/wallet/scan", label: "Scan" },
  { to: "/terminal/wallet/watch", label: "Watchlist" },
  { to: "/terminal/wallet/check", label: "Send check" },
  { to: "/terminal/wallet/lock", label: "Lock" },
] as const

// Wallet sub-tabs are routes, so they are links (aria-current) rather than a tablist.
export function WalletToolbar() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <nav
        aria-label="Wallet sections"
        className="flex items-center gap-0.5 rounded-4xl bg-muted p-[3px]"
      >
        {TABS.map((t) => (
          <Link
            key={t.to}
            to={t.to}
            className="inline-flex h-7 items-center rounded-full px-3 text-xs font-medium transition-colors"
            activeProps={{
              className:
                "bg-background ring-1 ring-foreground/10 dark:bg-input/40",
            }}
            inactiveProps={{ className: "hover:bg-background/50" }}
          >
            {t.label}
          </Link>
        ))}
      </nav>
      <Link
        to="/terminal/wallet/lock"
        className="ml-auto flex items-center gap-1.5 rounded-full px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <HugeiconsIcon icon={LockIcon} className="size-3.5 text-pass" />
        Read-only · rinng never asks you to sign
      </Link>
    </div>
  )
}
