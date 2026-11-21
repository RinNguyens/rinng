import { useEffect, useMemo, useRef, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import {
  Loading03Icon,
  Search01Icon,
  Wallet01Icon,
} from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Pick } from "@/components/workspace-grid"
import { NETWORKS, detectAddress, networkFor, networkOf } from "@/lib/chains"
import { liveFps, scanIsPartial } from "@/lib/wallet-scan"
import { readWallets, savedDiff } from "@/lib/wallet-store"
import {
  STATUS_WORD,
  chainVerdicts,
  planFor,
  verdicts,
} from "@/lib/wallet-steps"
import { NetworkIcon } from "@/components/wallet/network-picker"
import { WalletRoute } from "@/components/wallet/wallet-route"
import type { RouteStatus } from "@/components/wallet/wallet-route"
import {
  ChainSections,
  FindingsTable,
} from "@/components/wallet/findings-table"
import { RevokePlan } from "@/components/wallet/revoke-plan"
import { GRADE_TEXT, ScoreCard } from "@/components/wallet/score-card"
import {
  EVM_ALL,
  combine,
  doneOutcomes,
  recordScan,
  rowsOf,
  useReduced,
  useScan,
  walletStore,
} from "@/components/wallet/use-scan"
import type { Row } from "@/components/wallet/use-scan"

const HINT = "0x… address (ENS names are not resolved yet)"
const UNSUPPORTED =
  "Not a wallet address rinng can read. Paste a 0x…, T…, Solana, bc1/1/3… or G… address."
const GRADE_CHIP = "rounded px-1.5 font-heading text-xs"

const shortSp = (a: string) =>
  a.length > 16 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a
const describeFp = (fp: string) => {
  const [, kind, , ...sp] = fp.split(":")
  return `${kind} → ${shortSp(sp.join(":"))}`
}

export function ScanPanel({
  address,
  net,
  hl,
  onChange,
}: {
  address?: string
  net?: string
  /** "new": show the saved diff of the watchlist wallet instead of scanning. */
  hl?: "new"
  onChange?: (p: { address?: string; net?: string }) => void
}) {
  const reduced = useReduced()
  const [input, setInput] = useState(address ?? "")
  const [netKey, setNetKey] = useState(net ?? "eth")
  const [touched, setTouched] = useState(false)
  const [picked, setPicked] = useState<number | null>(null)
  const [wantWallet, setWantWallet] = useState(false)
  const [verify, setVerify] = useState<Array<Row> | null>(null)
  const [highlight, setHighlight] = useState<Set<string>>()
  const ran = useRef("")

  const s = useScan((r) => {
    const { prev, fps } = recordScan(
      walletStore(),
      r.address,
      r.net,
      doneOutcomes(r.rows),
      scanIsPartial(r.rows)
    )
    setHighlight(
      prev ? new Set(fps.filter((fp) => !prev.fps.includes(fp))) : undefined
    )
  })
  const w = s.wallet
  const running = s.phase === "running"
  const detected = detectAddress(input)
  const fieldError =
    touched && input.trim() && !detected.ok
      ? detected.family
        ? detected.reason
        : UNSUPPORTED
      : null
  const evmOnly = !input.trim() || detected.family === "evm"

  const outs = useMemo(() => doneOutcomes(s.rows), [s.rows])
  const rows = useMemo(() => outs.flatMap(rowsOf), [outs])
  const partial = scanIsPartial(s.rows)
  const pricesFailed = outs.some((o) => o.pricesFailed)
  const score = combine(outs, partial)
  const all = s.net === EVM_ALL
  const report = !all ? outs[0]?.report : undefined

  const go = (addr: string, key: string) => {
    setTouched(true)
    setPicked(null)
    setVerify(null)
    setHighlight(undefined)
    ran.current = `${addr}|${key}`
    void s.scan(addr, key)
  }
  const submit = (e?: React.FormEvent) => {
    e?.preventDefault()
    setTouched(true)
    if (!detected.ok || running) return
    const key =
      netKey === EVM_ALL ? EVM_ALL : networkFor(detected.family, netKey)
    setNetKey(key)
    onChange?.({ address: detected.address, net: key })
    go(detected.address, key)
  }

  const saved = useMemo(() => {
    const d = address ? detectAddress(address) : null
    return hl === "new" && d?.ok
      ? savedDiff(
          readWallets(walletStore()),
          d.address,
          net ?? networkFor(d.family, "eth")
        )
      : null
  }, [hl, address, net])
  // under StrictMode the mount, cleanup, mount cycle drops the first scan: a remount must scan again
  useEffect(
    () => () => {
      ran.current = ""
    },
    []
  )

  // the route's address/net are the source of truth: a link, or a watchlist row, opens a scan
  useEffect(() => {
    if (!address) return
    const d = detectAddress(address)
    if (!d.ok) return
    const key = net ?? networkFor(d.family, "eth")
    setInput(address)
    setNetKey(key)
    if (saved) return
    if (ran.current !== `${d.address}|${key}`) go(d.address, key)
  }, [address, net, saved])

  // "use my wallet": fill the field once the wallet answers
  const fill = (a: string) => {
    setInput(a)
    setNetKey(
      (k) =>
        NETWORKS.find((n) => n.chainId === w.chainId)?.key ??
        networkFor("evm", k)
    )
  }
  useEffect(() => {
    if (!wantWallet || !w.address) return
    fill(w.address)
    setWantWallet(false)
  }, [wantWallet, w.address])

  const items = [
    ...(evmOnly
      ? [
          {
            value: EVM_ALL,
            label: "All EVM",
            icon: <NetworkIcon id="eth" size={16} />,
          },
        ]
      : []),
    ...NETWORKS.map((n) => ({
      value: n.key,
      label: n.name,
      icon: <NetworkIcon id={n.key} size={16} />,
    })),
  ]

  // the route shows the plan of the chain being scanned, else of the chain selected
  const shown = networkOf(
    s.phase === "idle" ? netKey : all ? "eth" : (outs[0]?.net ?? s.net)
  )
  const plan = planFor(shown.family)
  const routeOut = outs.length
    ? outs.reduce((a, b) => (b.score.score < a.score.score ? b : a))
    : null
  const statuses: Array<RouteStatus> = routeOut
    ? routeOut.result
      ? verdicts(routeOut.result, routeOut.score)
      : chainVerdicts(routeOut.report!, routeOut.score)
    : plan.map((_, i) =>
        !running
          ? "idle"
          : i === 0
            ? "ok"
            : i < s.reached
              ? "done"
              : i === s.reached
                ? "active"
                : "idle"
      )
  const sel = Math.min(
    picked ?? (running ? s.reached : plan.length - 1),
    plan.length - 1
  )
  const steps = plan.map((p, i) => ({
    title: p.title,
    body: p.body,
    status: statuses[i],
  }))
  const highCount =
    rows.filter((r) => r.severity === "high").length +
    (report?.sections
      .flatMap((x) => x.findings)
      .filter((f) => f.severity === "high").length ?? 0)
  const announce =
    s.phase === "running"
      ? s.step
        ? `Checking ${s.step}`
        : ""
      : s.phase === "done" && score
        ? `Scan complete: grade ${score.grade}, ${highCount} high-risk finding${highCount === 1 ? "" : "s"}, ${pricesFailed ? "dollar amounts unknown" : `${Math.round(score.usdAtRisk).toLocaleString("en-US")} dollars at risk`}${partial ? ", partial scan" : ""}`
        : ""
  const live = s.phase === "done" ? liveFps(rows, partial) : null
  const planRows = verify ?? rows

  const netList = (
    <ul className="flex flex-col gap-1 rounded-2xl border border-border bg-card p-3 text-sm">
      {s.rows.map((r) => {
        const name = networkOf(r.net).name
        return (
          <li key={r.net} className="flex items-center gap-2">
            <NetworkIcon id={r.net} size={16} />
            <span className="w-24">{name}</span>
            {r.status === "running" && (
              <HugeiconsIcon
                icon={Loading03Icon}
                size={14}
                className="animate-spin motion-reduce:animate-none"
              />
            )}
            {r.outcome && (
              <span
                className={`${GRADE_CHIP} ${GRADE_TEXT[r.outcome.score.grade]}`}
              >
                {r.outcome.score.grade}
              </span>
            )}
            {r.status === "error" && (
              <>
                <span className="text-xs text-sev-high">
                  Could not read {name} ({r.error})
                </span>
                <Button
                  size="xs"
                  variant="outline"
                  disabled={running}
                  onClick={() => void s.retry(r.net)}
                >
                  Retry
                </Button>
              </>
            )}
          </li>
        )
      })}
    </ul>
  )

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={submit} noValidate className="flex flex-col gap-2">
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-64 flex-1">
            <Input
              value={input}
              disabled={running}
              onChange={(e) => {
                setInput(e.target.value)
                const d = detectAddress(e.target.value)
                if (d.family)
                  setNetKey((k) =>
                    k === EVM_ALL && d.family === "evm"
                      ? k
                      : networkFor(d.family!, k)
                  )
              }}
              onBlur={() => input.trim() && setTouched(true)}
              placeholder="0x…, T…, bc1…, G…, Solana…"
              aria-label="Wallet address"
              aria-invalid={!!fieldError}
              spellCheck={false}
              autoComplete="off"
              className="font-mono"
            />
            {fieldError ? (
              <p className="mt-1 text-xs text-destructive">{fieldError}</p>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">{HINT}</p>
            )}
          </div>
          <Pick
            items={items}
            value={netKey}
            onChange={setNetKey}
            label="Network"
            className="h-9"
          />
          {w.installed && (
            <Button
              type="button"
              variant="outline"
              disabled={running}
              onClick={() =>
                w.address ? fill(w.address) : (setWantWallet(true), w.connect())
              }
            >
              <HugeiconsIcon icon={Wallet01Icon} />
              Use my wallet
            </Button>
          )}
          <Button type="submit" disabled={running || !input.trim()}>
            <HugeiconsIcon
              icon={running ? Loading03Icon : Search01Icon}
              className={
                running ? "animate-spin motion-reduce:animate-none" : ""
              }
            />
            {running ? "Scanning…" : "Scan"}
          </Button>
          {running && (
            <button
              type="button"
              onClick={s.cancel}
              className="h-9 text-xs underline underline-offset-4"
            >
              Cancel
            </button>
          )}
        </div>
      </form>

      <p aria-live="polite" className="sr-only">
        {announce}
      </p>
      {s.switched && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-sev-medium p-3 text-sm">
          Your wallet switched account. Scan the new one?
          <Button
            size="sm"
            onClick={() =>
              w.address &&
              (fill(w.address), go(w.address, networkFor("evm", netKey)))
            }
          >
            Scan the new one
          </Button>
        </div>
      )}
      {s.phase === "error" && (
        <p role="alert" className="text-sm text-destructive">
          {s.error}
        </p>
      )}
      {s.phase === "error" && all && s.rows.length > 0 && netList}
      {saved && s.phase === "idle" && (
        <section
          aria-label="Since the last scan"
          className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-4 text-sm"
        >
          <h3 className="font-heading">Since the last scan</h3>
          {saved.newHigh.length +
            saved.newOther.length +
            saved.removed.length ===
            0 && <p className="text-muted-foreground">Nothing changed.</p>}
          {[
            ["New HIGH", saved.newHigh, "text-sev-high"],
            ["New", saved.newOther, "text-muted-foreground"],
            ["Gone", saved.removed, "text-pass"],
          ].map(([title, fps, cls]) =>
            (fps as Array<string>).length ? (
              <div key={title as string}>
                <p className={cls as string}>{title as string}</p>
                <ul className="ml-4 list-disc font-mono text-xs">
                  {(fps as Array<string>).map((fp) => (
                    <li key={fp}>{describeFp(fp)}</li>
                  ))}
                </ul>
              </div>
            ) : null
          )}
          <p className="text-xs text-muted-foreground">
            This is the saved result. Press Scan to read the wallet again.
          </p>
        </section>
      )}

      {s.phase !== "idle" && s.phase !== "error" && (
        <div className="grid items-start gap-4 xl:grid-cols-[18rem_1fr]">
          <div className="xl:w-72">
            <div className="hidden h-96 xl:block">
              <WalletRoute
                steps={steps}
                selected={sel}
                onSelect={setPicked}
                running={running}
                reduced={reduced}
              />
            </div>
            <ol className="sr-only">
              {plan.map((p, i) => (
                <li key={p.title}>
                  {p.title}: {STATUS_WORD[statuses[i]]}
                </li>
              ))}
            </ol>
            <div className="xl:hidden">
              <p className="text-xs text-muted-foreground">
                Step {sel + 1}/{plan.length} · {plan[sel].title}
              </p>
              <div className="mt-1 h-1 rounded bg-muted">
                <div
                  className="h-full rounded bg-progress transition-[width]"
                  style={{
                    width: `${((running ? s.reached : plan.length) / plan.length) * 100}%`,
                  }}
                />
              </div>
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-4">
            {all && netList}
            {score && (
              <ScoreCard
                score={score}
                reduced={reduced}
                title={all ? "Combined score" : undefined}
                pricesFailed={pricesFailed}
              />
            )}
            {s.phase === "done" &&
              score &&
              !partial &&
              rows.length === 0 &&
              !report?.sections.some((x) => x.findings.length) && (
                <p className="text-sm text-muted-foreground">
                  Nothing can move this wallet&apos;s tokens right now.
                </p>
              )}
            {rows.length > 0 && (
              <FindingsTable
                key={s.address + s.net}
                rows={rows}
                highlight={highlight}
                lookback={outs.flatMap((o) =>
                  o.result
                    ? [
                        {
                          name: networkOf(o.net).name,
                          block: o.result.fromBlock,
                        },
                      ]
                    : []
                )}
              />
            )}
            {report && <ChainSections report={report} />}
            {verify && partial && s.phase === "done" && (
              <p className="text-sm text-muted-foreground">
                Some networks could not be fully read, so nothing can be marked
                Verified.
              </p>
            )}
            {(s.phase === "done" || verify) && (
              <RevokePlan
                rows={planRows}
                live={verify ? live : null}
                running={running}
                onVerify={() => {
                  const keep = planRows
                  go(s.address, s.net)
                  setVerify(keep)
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
