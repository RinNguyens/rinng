import { useMemo, useRef, useState } from "react"
import { createPublicClient, getAddress, http, parseAbi } from "viem"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { AddressChunks } from "@/components/wallet/address-chunks"
import { walletStore } from "@/components/wallet/use-scan"
import { checkAddress } from "@/lib/address"
import { NETWORKS, detectAddress } from "@/lib/chains"
import type { Network } from "@/lib/chains"
import { scanWallet } from "@/lib/scan"
import { extraNotes, lookalikeOf, resolveFrom, sendVerdict, splitFrom } from "@/lib/send-check"
import { short, useWallet } from "@/lib/wallet"
import { readWallets } from "@/lib/wallet-store"
import { lastScan, rememberScan } from "@/lib/wallet-scan"

type Props = {
  to?: string
  from?: string
  onChange?: (p: { to?: string; from?: string }) => void
}
type Outcome = { title: string; tone: "danger" | "warn" | "note"; notes: Array<string>; address?: string; compare?: string }

const NONE = "none"
const SYMBOL = parseAbi(["function symbol() view returns (string)"])
const BANNER = {
  note: "border-pass",
  warn: "border-sev-medium",
  danger: "border-sev-high bg-sev-high/10",
} as const
const TITLE = { note: "text-pass", warn: "text-sev-medium", danger: "text-sev-high" } as const

const clientFor = (n: Network) =>
  createPublicClient({ transport: http(n.rpc, { retryCount: 2, batch: { batchSize: 20 } }) })

export function SendCheck({ to = "", from, onChange }: Props) {
  const wallet = useWallet()
  const saved = useMemo(() => readWallets(walletStore()), [])
  const [input, setInput] = useState(to)
  const [error, setError] = useState<string | null>(null)
  const [out, setOut] = useState<Outcome | null>(null)
  const [step, setStep] = useState<string | null>(null)
  const runId = useRef(0)

  const connectedNet = NETWORKS.find((n) => n.chainId === wallet.chainId)
  const options = [
    { value: NONE, label: "None" },
    ...(wallet.address && !saved.some((w) => w.address.toLowerCase() === wallet.address!.toLowerCase())
      ? [
          {
            value: connectedNet ? `${wallet.address}|${connectedNet.key}` : wallet.address,
            label: `Connected ${short(wallet.address)}`,
          },
        ]
      : []),
    ...saved.map((w) => ({ value: `${w.address}|${w.net}`, label: `${w.label} ${short(w.address)}` })),
  ]
  const resolved = resolveFrom(from, options.filter((o) => o.value !== NONE))
  const split = splitFrom(resolved)
  const fromAddr = split.address
  const fromWallet = fromAddr
    ? saved.find(
        (w) =>
          w.address.toLowerCase() === fromAddr.toLowerCase() && (!split.net || w.net === split.net)
      )
    : undefined
  const fromNet = fromWallet
    ? NETWORKS.find((n) => n.key === fromWallet.net)
    : NETWORKS.find((n) => n.key === split.net) ?? NETWORKS.find((n) => n.chainId === wallet.chainId)
  const selected = resolved ?? NONE

  async function run() {
    const id = ++runId.current
    const stale = () => id !== runId.current
    setOut(null)
    setError(null)
    const value = input.trim()
    const detected = detectAddress(value)
    if (!detected.ok) return setError(detected.reason)
    setStep("Checking…")
    const fromDetected = fromAddr ? detectAddress(fromAddr) : undefined
    const fromFamily = fromAddr
      ? fromNet?.family ?? (fromDetected?.ok ? fromDetected.family : undefined)
      : undefined
    const toFamily = detected.family
    const mismatch = !!fromFamily && fromFamily !== toFamily
    const skipped: Array<string> = []
    if (detected.family !== "evm") {
      setStep(null)
      return setOut({
        ...sendVerdict({
          check: mismatch ? "medium" : "ok",
          // With a From wallet the user expects a history comparison; it cannot run here, so it counts as skipped.
          skipped: fromAddr ? ["Your transfer history was not compared: only format checks are available for this network."] : [],
          extra: [...extraNotes({ fromFamily, toFamily }), ...(fromAddr ? [] : ["Only format checks are available for this network."])],
        }),
        address: value,
      })
    }
    const fromEvm = fromFamily === "evm"
    const net = (fromEvm ? fromNet : undefined) ?? NETWORKS.find((n) => n.chainId === 1)!
    let poisoning
    if (fromAddr && !fromEvm && fromFamily)
      skipped.push("Your From wallet is not an EVM wallet, so the history and on-chain reads were skipped.")
    else if (fromAddr) {
      try {
        let scan = lastScan(fromAddr, net.key)
        if (!scan) {
          setStep("Reading your transfer history…")
          scan = await scanWallet(clientFor(net), getAddress(fromAddr), {
            lookback: 200_000n,
            chainId: net.chainId,
          })
          if (stale()) return
          rememberScan(fromAddr, net.key, scan)
        }
        poisoning = scan.poisoning
        if (!scan.complete)
          skipped.push("Your transfer history was incomplete; the look-alike check may have missed something.")
      } catch {
        if (stale()) return
        skipped.push("Could not read your transfer history; the look-alike check did not run.")
      }
    }
    const c = checkAddress(value, {
      owner: fromEvm ? fromAddr : undefined,
      counterparties: poisoning?.counterparties,
      suspects: poisoning?.suspects,
      chainId: net.chainId,
    })
    if (!c.valid) {
      setStep(null)
      return setError(c.notes[0])
    }
    let isContract = false
    let tokenSymbol: string | undefined
    if (!fromAddr || fromEvm) {
      setStep("Reading the address on-chain…")
      const client = clientFor(net)
      try {
        const code = await client.getCode({ address: c.address! })
        isContract = !!code && code !== "0x"
        if (isContract)
          tokenSymbol = await client
            .readContract({ address: c.address!, abi: SYMBOL, functionName: "symbol" })
            // most contracts are not tokens and revert here; the contract note already raises the verdict
            .catch(() => undefined)
      } catch {
        skipped.push("Could not read this address on-chain, so contract and token checks did not run.")
      }
    }
    if (stale()) return
    const v = sendVerdict({
      check: mismatch && c.severity === "ok" ? "medium" : c.severity,
      skipped,
      extra: [...c.notes, ...extraNotes({ isContract, tokenSymbol, fromFamily, toFamily })],
      isContract,
    })
    setStep(null)
    setOut({
      ...v,
      address: c.address,
      compare: lookalikeOf(c.address!, poisoning?.counterparties, poisoning?.suspects),
    })
  }

  const validTo = () => (detectAddress(input.trim()).ok ? input.trim() : undefined)

  const submit = () => {
    if (step) return
    onChange?.({ to: validTo(), from: resolved })
    void run()
  }

  return (
    <section className="flex flex-col gap-4" aria-label="Send check">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <label htmlFor="send-to" className="text-xs text-muted-foreground">
            To
          </label>
          <Input
            id="send-to"
            value={input}
            placeholder="Paste the address you are about to send to"
            aria-invalid={!!error}
            aria-describedby={error ? "send-to-error" : undefined}
            onChange={(e) => {
              runId.current++
              setStep(null)
              setInput(e.target.value)
              setOut(null)
              setError(null)
            }}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          {error && (
            <p id="send-to-error" className="text-xs text-sev-high">
              {error}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1 sm:w-56">
          <span className="text-xs text-muted-foreground">From</span>
          <Select
            items={options}
            value={selected}
            onValueChange={(v) => {
              runId.current++
              setStep(null)
              setOut(null)
              onChange?.({ to: validTo(), from: v && v !== NONE ? String(v) : undefined })
            }}
          >
            <SelectTrigger aria-label="From wallet" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {!resolved && <p className="text-xs text-muted-foreground">Pick your wallet to compare against your transfer history</p>}
      <div className="flex items-center gap-3">
        <Button onClick={submit} disabled={!!step}>
          Check
        </Button>
        {step && (
          <p role="status" className="text-sm text-muted-foreground">
            {step}
          </p>
        )}
      </div>
      {out && (
        <div
          role={out.tone === "danger" ? "alert" : undefined}
          className={`desk-in flex flex-col gap-3 rounded-lg border-2 p-4 ${BANNER[out.tone]}`}
        >
          <p className={`font-heading text-base ${TITLE[out.tone]}`}>
            {out.title}
          </p>
          {out.address && <AddressChunks address={out.address} compare={out.compare} />}
          <ul className="list-disc pl-5 text-sm">
            {out.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
