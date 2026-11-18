import { useEffect, useRef, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowUpRight01Icon, Cancel01Icon, Copy01Icon, Download01Icon, Loading03Icon, Tick02Icon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { networkOf } from "@/lib/chains"
import { browserStore } from "@/lib/terminal-nav"
import { money, planJson, planMarkdown, readRevoke, revokePlan, verifyState, writeRevoke } from "@/lib/wallet-scan"
import type { RevokeMap } from "@/lib/wallet-scan"
import { explorerUrl } from "@/components/wallet/findings-table"
import type { Row } from "@/components/wallet/use-scan"

const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`

export function RevokePlan({
  rows,
  live,
  running,
  onVerify,
}: {
  /** The findings the plan covers: kept from before a verify scan so items that vanish can show Verified. */
  rows: Array<Row>
  /** Fingerprints found by the latest finished scan, null while none has finished. */
  live: ReadonlySet<string> | null
  running: boolean
  onVerify: () => void
}) {
  const [checked, setChecked] = useState<RevokeMap>(() => readRevoke(browserStore(), Date.now()))
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null)
  const timer = useRef(0)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  if (rows.length === 0) return null

  const state = (r: Row) => verifyState(r.fp, checked, live)
  const ordered = revokePlan(rows)
  const items = [...ordered.filter((r) => state(r) !== "verified"), ...ordered.filter((r) => state(r) === "verified")]
  const net = [...new Set(rows.map((r) => r.net))].map((k) => networkOf(k).name).join(", ")

  const toggle = (fp: string) => {
    const next = { ...checked }
    if (fp in next) delete next[fp]
    else next[fp] = { checkedAt: Date.now() }
    setChecked(next)
    writeRevoke(browserStore(), next)
  }
  const copy = () => {
    const flash = (v: "ok" | "fail") => {
      setCopied(v)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setCopied(null), 1500)
    }
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(planMarkdown(items, net)))
      .then(() => flash("ok"), () => flash("fail"))
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([planJson(items, net)], { type: "application/json" }))
    const a = document.createElement("a")
    a.href = url
    a.download = "rinng-revoke-plan.json"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section aria-label="Revoke plan" className="rounded-2xl border border-border bg-card p-4">
      <h3 className="font-heading text-sm">Revoke plan</h3>
      <ol className="mt-3 flex flex-col gap-2">
        {items.map((r, i) => {
          const st = state(r)
          const done = r.fp in checked
          return (
            <li key={r.fp} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <label className="flex min-w-0 flex-1 items-center gap-2">
                <input type="checkbox" checked={done} onChange={() => toggle(r.fp)} aria-label="I revoked this" className="size-4 accent-current" />
                <span className="text-muted-foreground tabular-nums">{i + 1}</span>
                <span className={done ? "text-muted-foreground line-through" : ""}>
                  Revoke {r.symbol ?? KINDS[r.kind] ?? r.kind} → {r.label ?? short(r.spender)} on {networkOf(r.net).name}
                </span>
              </label>
              {st === "verified" && <span className="text-xs text-pass">Verified</span>}
              {st === "still-live" && <span className="text-xs text-sev-medium">Still live</span>}
              <span className="tabular-nums">{money(r.usd)}</span>
              <a href={explorerUrl(r)} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground">
                revoke.cash <HugeiconsIcon icon={ArrowUpRight01Icon} size={12} />
              </a>
            </li>
          )
        })}
      </ol>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={running} onClick={onVerify}>
          {running && <HugeiconsIcon icon={Loading03Icon} className="animate-spin motion-reduce:animate-none" />}
          Re-scan to verify
        </Button>
        <span className="ml-auto flex gap-2">
          <Button variant="ghost" size="sm" onClick={copy}>
            <HugeiconsIcon icon={copied === "ok" ? Tick02Icon : copied === "fail" ? Cancel01Icon : Copy01Icon} />
            {copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : "Copy as Markdown"}
          </Button>
          <Button variant="ghost" size="sm" onClick={download}>
            <HugeiconsIcon icon={Download01Icon} />
            Download JSON
          </Button>
        </span>
      </div>
    </section>
  )
}

const KINDS: Partial<Record<string, string>> = { nft: "NFT approval", delegation: "7702 delegate" }
