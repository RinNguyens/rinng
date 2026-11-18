import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { Badge } from "@/components/ui/badge"
import { ALLOWED_METHODS, blockedRequests, onBlocked, pageLock } from "@/lib/guard"
import { short, useWallet } from "@/lib/wallet"

const STATUS = {
  locked: {
    label: "Locked",
    tone: "text-pass border-pass",
    text: "window.ethereum points at rinng's lock and cannot be reassigned.",
  },
  wrapped: {
    label: "Partly locked",
    tone: "text-sev-medium border-sev-medium",
    text: "Your wallet pinned window.ethereum. rinng's own requests are locked; other scripts on this page are not.",
  },
  absent: {
    label: "No wallet in this browser",
    tone: "text-muted-foreground border-border",
    text: "Nothing to lock. Scans read public data.",
  },
} as const

const time = (at: number) => new Date(at).toLocaleTimeString("en-GB", { hour12: false })

export function LockPanel() {
  const wallet = useWallet()
  const { status } = pageLock()
  const blocked = useSyncExternalStore(onBlocked, blockedRequests, blockedRequests)
  const seen = useRef(blocked.length)
  const [announce, setAnnounce] = useState("")
  useEffect(() => {
    if (blocked.length > seen.current) setAnnounce(`rinng blocked a request to ${blocked[0].method} (${blocked.length} blocked this session)`)
    seen.current = blocked.length
  }, [blocked])
  const s = STATUS[status]

  return (
    <section className="flex flex-col gap-3 text-sm" aria-label="Signature lock">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2 py-0.5 font-heading text-xs ${s.tone}`}>{s.label}</span>
        <span className="text-muted-foreground">
          {wallet.address ? `Wallet ${short(wallet.address)}` : "No wallet connected"}
        </span>
      </div>
      <p>{s.text}</p>
      <div className="flex flex-wrap gap-1.5" aria-label="Allowed requests">
        {[...ALLOWED_METHODS].map((m) => (
          <Badge key={m} variant="secondary" className="font-heading text-[11px]">
            {m}
          </Badge>
        ))}
      </div>
      <details className="text-muted-foreground">
        <summary className="cursor-pointer text-foreground">What this covers / what it does not</summary>
        <p className="mt-2">
          Covers rinng's own code and every script that reaches the wallet through window.ethereum. It is
          not a sandbox: a script could still find the raw provider through EIP-6963 announcements. The
          wallet's own confirmation screen is the last line of defence.
        </p>
      </details>
      <h3 className="font-medium">Blocked this session ({blocked.length})</h3>
      <div aria-live="assertive" className="sr-only">
        {announce}
      </div>
      {blocked.length === 0 ? (
        <p className="text-muted-foreground">
          Nothing has tried to sign. Requests other than reads would be listed here.
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {blocked.map((b) => (
            <li key={`${b.at}-${b.method}`} className="desk-in flex justify-between gap-3">
              <span className="font-heading break-all">{b.method}</span>
              <span className="text-muted-foreground tabular-nums">{time(b.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
