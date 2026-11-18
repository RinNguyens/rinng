import { useMemo, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Loading03Icon, MoreHorizontalIcon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Pick } from "@/components/workspace-grid"
import { browserStore } from "@/lib/terminal-nav"
import { NETWORKS, detectAddress, networkFor, networkOf } from "@/lib/chains"
import { ago } from "@/lib/format"
import { money, pool, scanIsPartial } from "@/lib/wallet-scan"
import { addWallet, diffSnaps, readWallets, removeWallet, renameWallet, sevFromSnap, storageWorks, writeWallets } from "@/lib/wallet-store"
import type { Wallet } from "@/lib/wallet-store"
import { NetworkIcon } from "@/components/wallet/network-picker"
import { GRADE_TEXT } from "@/components/wallet/score-card"
import { EVM_ALL, doneOutcomes, recordScan, runNets, walletStore } from "@/components/wallet/use-scan"

const MAX = 20
const ADD_ERROR = {
  duplicate: "Already in your watchlist",
  full: "20 wallets is the limit",
  empty: "Paste a wallet address.",
}
const netName = (net: string) => (net === EVM_ALL ? "All EVM" : networkOf(net).name)
const keyOf = (w: Wallet) => `${w.address.toLowerCase()}|${w.net}`

function NetPick({ value, onChange, evm }: { value: string; onChange: (v: string) => void; evm: boolean }) {
  const items = [
    ...(evm ? [{ value: EVM_ALL, label: "All EVM", icon: <NetworkIcon id="eth" size={16} /> }] : []),
    ...NETWORKS.map((n) => ({ value: n.key, label: n.name, icon: <NetworkIcon id={n.key} size={16} /> })),
  ]
  return <Pick items={items} value={value} onChange={onChange} label="Network" className="h-9" />
}

function AddDialog({ open, onOpenChange, onAdd }: { open: boolean; onOpenChange: (o: boolean) => void; onAdd: (a: { address: string; net: string; label: string }) => string | null }) {
  const [address, setAddress] = useState("")
  const [label, setLabel] = useState("")
  const [net, setNet] = useState("eth")
  const [error, setError] = useState<string | null>(null)
  const d = detectAddress(address)
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!d.ok) return setError(address.trim() ? d.reason : ADD_ERROR.empty)
    const err = onAdd({ address: d.address, net: net === EVM_ALL && d.family !== "evm" ? networkFor(d.family, net) : net, label })
    if (err) return setError(err)
    setAddress("")
    setLabel("")
    setError(null)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add wallet</DialogTitle>
            <DialogDescription>Saved in this browser only.</DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Address"
            placeholder="Address (required)"
            value={address}
            spellCheck={false}
            className="font-mono"
            aria-invalid={!!error}
            onChange={(e) => {
              setAddress(e.target.value)
              setError(null)
              const x = detectAddress(e.target.value)
              if (x.family) setNet((k) => (k === EVM_ALL && x.family === "evm" ? k : networkFor(x.family!, k)))
            }}
          />
          <Input aria-label="Label" placeholder="Label (optional)" maxLength={24} value={label} onChange={(e) => setLabel(e.target.value)} />
          <NetPick value={net} onChange={setNet} evm={!address.trim() || d.family === "evm"} />
          {error && <p className="text-xs text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit">Add</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function WatchlistTable({ onOpen }: { onOpen: (address: string, net: string) => void }) {
  const store = useMemo(() => walletStore(), [])
  const saving = useMemo(() => storageWorks(browserStore()), [])
  const [list, setList] = useState<Array<Wallet>>(() => readWallets(store))
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set())
  const [partial, setPartial] = useState<ReadonlySet<string>>(new Set())
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set())
  const [adding, setAdding] = useState(false)
  const [dlg, setDlg] = useState<{ kind: "rename" | "remove"; w: Wallet } | null>(null)
  const [name, setName] = useState("")

  const save = (next: Array<Wallet>) => {
    setList(next)
    writeWallets(store, next)
  }
  const flag = (set: (f: (s: ReadonlySet<string>) => ReadonlySet<string>) => void, k: string, on: boolean) =>
    set((s) => {
      const n = new Set(s)
      if (on) n.add(k)
      else n.delete(k)
      return n
    })
  const scanOne = async (w: Wallet) => {
    const k = keyOf(w)
    flag(setBusy, k, true)
    try {
      const rows = await runNets(w.address, w.net)
      const outs = doneOutcomes(rows)
      const part = scanIsPartial(rows)
      if (outs.length) recordScan(store, w.address, w.net, outs, part)
      flag(setFailed, k, outs.length === 0)
      flag(setPartial, k, outs.length > 0 && part)
      setList(readWallets(store))
    } catch {
      flag(setFailed, k, true)
    } finally {
      flag(setBusy, k, false)
    }
  }
  const full = list.length >= MAX
  const addButton = (
    <Button size="sm" disabled={full} onClick={() => setAdding(true)}>
      <HugeiconsIcon icon={Add01Icon} />
      Add wallet
    </Button>
  )

  return (
    <section aria-label="Watchlist" className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        {full ? (
          <Tooltip>
            <TooltipTrigger render={<span tabIndex={0} />}>{addButton}</TooltipTrigger>
            <TooltipContent>20 wallets is the limit</TooltipContent>
          </Tooltip>
        ) : (
          addButton
        )}
        <Button size="sm" variant="outline" className="ml-auto" disabled={list.length === 0 || busy.size > 0} onClick={() => void pool(list, 2, scanOne)}>
          Re-scan all
        </Button>
      </div>
      {!saving && <p className="text-xs text-muted-foreground">Your browser is not saving data; this list will be gone when you close the tab.</p>}
      {list.length === 0 ? (
        <p className="text-sm text-muted-foreground">No saved wallets yet. Add one to re-check it later.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                {["Label", "Address", "Network", "Grade", "Score", "At risk", "New since last", "Scanned"].map((h) => (
                  <th key={h} scope="col" className="py-1 pr-3 font-normal whitespace-nowrap">
                    {h}
                  </th>
                ))}
                <th scope="col" className="w-8">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.map((w) => {
                const k = keyOf(w)
                const last = w.snaps.at(-1)
                const diff = last ? diffSnaps(w.snaps.at(-2), last, sevFromSnap(last)) : null
                return (
                  <tr key={k} className="border-t border-border">
                    <td className="py-1.5 pr-3">{w.label}</td>
                    <td className="pr-3 font-mono text-xs">{`${w.address.slice(0, 6)}…${w.address.slice(-4)}`}</td>
                    <td className="pr-3 whitespace-nowrap">{netName(w.net)}</td>
                    <td className={`pr-3 font-heading ${last?.grade ? GRADE_TEXT[last.grade] : ""}`}>{last?.grade ?? "—"}</td>
                    <td className="pr-3 tabular-nums">{last?.score ?? "—"}</td>
                    <td className="pr-3 tabular-nums">{last?.usd === undefined ? "—" : money(last.usd)}</td>
                    <td className="pr-3">
                      {diff && (diff.newHigh.length || diff.newOther.length || diff.removed.length) ? (
                        <button type="button" onClick={() => onOpen(w.address, w.net)} className="flex gap-2 text-xs underline-offset-4 hover:underline">
                          {diff.newHigh.length > 0 && <span className="text-sev-high">+{diff.newHigh.length} HIGH</span>}
                          {diff.newOther.length > 0 && <span className="text-muted-foreground">+{diff.newOther.length}</span>}
                          {diff.removed.length > 0 && <span className="text-pass">−{diff.removed.length}</span>}
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="pr-3 whitespace-nowrap text-muted-foreground">
                      {busy.has(k) ? (
                        <HugeiconsIcon icon={Loading03Icon} size={14} aria-label="Scanning" className="animate-spin motion-reduce:animate-none" />
                      ) : failed.has(k) ? (
                        <span className="text-sev-high">could not read</span>
                      ) : partial.has(k) ? (
                        <span className="text-sev-medium">partial</span>
                      ) : last ? (
                        ago(last.at / 1000)
                      ) : (
                        "never"
                      )}
                    </td>
                    <td>
                      <DropdownMenu>
                        <DropdownMenuTrigger render={<Button variant="ghost" size="icon-xs" aria-label={`Actions for ${w.label}`} />}>
                          <HugeiconsIcon icon={MoreHorizontalIcon} />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem disabled={busy.has(k)} onClick={() => void scanOne(w)}>
                            Scan now
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => {
                              setName(w.label)
                              setDlg({ kind: "rename", w })
                            }}
                          >
                            Rename
                          </DropdownMenuItem>
                          <DropdownMenuItem variant="destructive" onClick={() => setDlg({ kind: "remove", w })}>
                            Remove
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <AddDialog
        open={adding}
        onOpenChange={setAdding}
        onAdd={(a) => {
          const r = addWallet(list, a)
          if (!r.ok) return ADD_ERROR[r.error]
          save(r.list)
          setAdding(false)
          return null
        }}
      />
      <Dialog open={dlg?.kind === "rename"} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent showCloseButton={false}>
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (dlg) save(renameWallet(list, dlg.w.address, dlg.w.net, name))
              setDlg(null)
            }}
          >
            <DialogHeader>
              <DialogTitle>Rename wallet</DialogTitle>
            </DialogHeader>
            <Input aria-label="Label" maxLength={24} value={name} onChange={(e) => setName(e.target.value)} />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDlg(null)}>
                Cancel
              </Button>
              <Button type="submit">Save</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={dlg?.kind === "remove"} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Remove {dlg?.w.label}?</DialogTitle>
            <DialogDescription>It leaves this browser&apos;s list. Nothing on-chain changes.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (dlg) save(removeWallet(list, dlg.w.address, dlg.w.net))
                setDlg(null)
              }}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
