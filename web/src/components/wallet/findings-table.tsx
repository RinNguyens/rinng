import { useEffect, useRef, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowUpRight01Icon, Cancel01Icon, Copy01Icon, Tick02Icon } from "@hugeicons/core-free-icons"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { networkOf } from "@/lib/chains"
import type { ChainReport } from "@/lib/multichain"
import type { Severity } from "@/lib/scan"
import { groupFindings, money } from "@/lib/wallet-scan"
import { SevPill } from "@/components/wallet/sev-pill"
import type { Row } from "@/components/wallet/use-scan"

const KIND: Record<string, string> = { erc20: "ERC-20", nft: "NFT", permit2: "Permit2", delegation: "7702 delegate" }
const SEVS: ReadonlyArray<Severity> = ["high", "medium", "low"]
const SHOWN = 50
const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null)
  const timer = useRef(0)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      aria-label={copied === "ok" ? "Copied" : copied === "fail" ? "Copy failed" : "Copy address"}
      onClick={() => {
        const flash = (v: "ok" | "fail") => {
          setCopied(v)
          window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => setCopied(null), 1500)
        }
        Promise.resolve()
          .then(() => navigator.clipboard.writeText(text))
          .then(() => flash("ok"), () => flash("fail"))
      }}
    >
      <HugeiconsIcon icon={copied === "ok" ? Tick02Icon : copied === "fail" ? Cancel01Icon : Copy01Icon} />
    </Button>
  )
}

const Tag = ({ children }: { children: string }) => (
  <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
    {children}
  </Badge>
)

function Asset({ r }: { r: Row }) {
  const name = r.symbol ?? (r.token ? short(r.token) : "—")
  if (name.length <= 12) return <span>{name}</span>
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} />}>{name.slice(0, 12)}…</TooltipTrigger>
      <TooltipContent>{name}</TooltipContent>
    </Tooltip>
  )
}

function Spender({ r }: { r: Row }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span className="font-mono text-xs">{r.label && !r.eoa ? r.label : short(r.spender)}</span>
      {r.label && r.eoa && <span className="text-xs text-muted-foreground">({r.label})</span>}
      {r.eoa && <Tag>EOA</Tag>}
      {r.proxy && <Tag>proxy</Tag>}
      {!r.label && !r.eoa && <Tag>unknown</Tag>}
      <CopyButton text={r.spender} />
    </span>
  )
}

function AtRisk({ r }: { r: Row }) {
  if (r.usd !== undefined) return <span className="tabular-nums">{money(r.usd)}</span>
  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} />}>—</TooltipTrigger>
      <TooltipContent>No price for this token</TooltipContent>
    </Tooltip>
  )
}

export const explorerUrl = (r: Pick<Row, "net" | "address">) => networkOf(r.net).explorer.url(r.address)

function ExplorerLink({ r }: { r: Row }) {
  const n = networkOf(r.net)
  return (
    <a
      href={explorerUrl(r)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Open on ${n.explorer.name}`}
      className="inline-flex size-6 items-center justify-center rounded text-muted-foreground hover:text-foreground"
    >
      <HugeiconsIcon icon={ArrowUpRight01Icon} size={14} />
    </a>
  )
}

const rowTint = (r: Row, hl?: Set<string>) => (hl?.has(r.fp) ? "bg-sev-high/10" : "")
const NewBadge = () => (
  <Badge variant="destructive" className="ml-1 h-4 px-1.5 text-[10px]">
    New
  </Badge>
)

type GroupBy = "none" | "spender" | "network"

export function FindingsTable({
  rows,
  highlight,
  lookback,
}: {
  rows: Array<Row>
  highlight?: Set<string>
  /** First block each EVM network's scan read; anything older was not. */
  lookback: Array<{ name: string; block: bigint }>
}) {
  const [sev, setSev] = useState<Severity | "all">("all")
  const [by, setBy] = useState<GroupBy>(rows.length > SHOWN ? "spender" : "none")
  const [all, setAll] = useState(false)
  const count = (s: Severity) => rows.filter((r) => r.severity === s).length
  const filtered = sev === "all" ? rows : rows.filter((r) => r.severity === sev)
  const visible = all ? filtered : filtered.slice(0, SHOWN)
  const groups = groupFindings(visible, by)
  const old = lookback.filter((l) => l.block > 0n)

  return (
    <section aria-label="Findings" className="rounded-2xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-2 font-heading text-sm">Findings ({rows.length})</h3>
        {(["all", ...SEVS] as const).map((s) => (
          <Button key={s} size="xs" variant={sev === s ? "secondary" : "ghost"} aria-pressed={sev === s} onClick={() => setSev(s)}>
            {s === "all" ? "All" : `${s[0].toUpperCase()}${s.slice(1)} ${count(s)}`}
          </Button>
        ))}
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button size="xs" variant="outline" className="ml-auto" />}>group: {by}</DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuRadioGroup value={by} onValueChange={(v) => setBy(v as GroupBy)}>
              {(["none", "spender", "network"] as const).map((g) => (
                <DropdownMenuRadioItem key={g} value={g}>
                  {g}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <table className="mt-3 hidden w-full text-left text-sm md:table">
        <thead className="text-xs text-muted-foreground">
          <tr>
            {["Sev", "Kind", "Asset", "Spender", "Allowance", "At risk", ""].map((h) => (
              <th key={h || "link"} scope="col" className="py-1 pr-3 font-normal">
                {h}
                {!h && <span className="sr-only">Link</span>}
              </th>
            ))}
          </tr>
        </thead>
        {groups.map((g) => (
          <tbody key={g.key}>
            {g.key && (
              <tr>
                <th colSpan={7} scope="rowgroup" className="pt-3 pb-1 text-left font-mono text-xs text-muted-foreground">
                  {by === "network" ? networkOf(g.key).name : short(g.key)} · {g.rows.length}
                </th>
              </tr>
            )}
            {g.rows.map((r) => (
              <tr key={r.fp} className={`border-t border-border ${rowTint(r, highlight)}`}>
                <td className="py-1.5 pr-3">
                  <SevPill severity={r.severity} />
                  {highlight?.has(r.fp) && <NewBadge />}
                </td>
                <td className="pr-3">{KIND[r.kind] ?? r.kind}</td>
                <td className="pr-3">
                  <Asset r={r} />
                </td>
                <td className="pr-3">
                  <Spender r={r} />
                </td>
                <td className="pr-3">{r.allowance}</td>
                <td className="pr-3">
                  <AtRisk r={r} />
                </td>
                <td>
                  <ExplorerLink r={r} />
                </td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>

      <ul className="mt-3 flex flex-col gap-2 md:hidden">
        {visible.map((r) => (
          <li key={r.fp} className={`flex flex-col gap-1 rounded-xl border border-border p-3 text-sm ${rowTint(r, highlight)}`}>
            <div className="flex items-center gap-2">
              <SevPill severity={r.severity} />
              {highlight?.has(r.fp) && <NewBadge />}
              <span className="text-muted-foreground">{KIND[r.kind] ?? r.kind}</span>
              <span className="ml-auto">
                <ExplorerLink r={r} />
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-1">
              <Asset r={r} />
              <span aria-hidden="true">→</span>
              <Spender r={r} />
            </div>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{r.allowance}</span>
              <span>
                at risk <AtRisk r={r} />
              </span>
            </div>
          </li>
        ))}
      </ul>

      {!all && filtered.length > SHOWN && (
        <Button className="mt-3" size="sm" variant="outline" onClick={() => setAll(true)}>
          Show all {filtered.length}
        </Button>
      )}
      {old.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          {old.map((l) => `Approvals granted before block ${l.block.toLocaleString("en-US")}${old.length > 1 ? ` on ${l.name}` : ""} were not read.`).join(" ")}{" "}
          Check on revoke.cash for the full history.
        </p>
      )}
    </section>
  )
}

/** Tron, Solana, Bitcoin, Stellar: the chain's own sections, each finding a row. */
export function ChainSections({ report }: { report: ChainReport }) {
  return (
    <div className="flex flex-col gap-3">
      {report.sections.map((s) => (
        <section key={s.title} className="rounded-2xl border border-border bg-card p-4">
          <h3 className="font-heading text-sm">{s.title}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{s.summary}</p>
          <ul className="mt-2 flex flex-col gap-2">
            {s.findings.map((f) => (
              <li key={f.title} className="flex items-start gap-2 text-sm">
                <SevPill severity={f.severity} />
                <div className="min-w-0 flex-1">
                  <div>{f.title}</div>
                  <div className="text-xs text-muted-foreground">{f.note}</div>
                </div>
                {f.amount && <span className="shrink-0 tabular-nums">{f.amount}</span>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
