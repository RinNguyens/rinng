import { useEffect, useMemo, useState } from "react"
import { createPublicClient, formatUnits, getAddress, http } from "viem"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowLeft01Icon, ArrowRight01Icon, ArrowUpRight01Icon, Loading03Icon, Search01Icon, Wallet01Icon } from "@hugeicons/core-free-icons"
import { tokenPrices, usd } from "@/lib/defi"
import type { Price } from "@/lib/defi"
import { scanWallet } from "@/lib/scan"
import type { Finding, ScanResult, Severity } from "@/lib/scan"
import { securityScore } from "@/lib/score"
import type { Score } from "@/lib/score"
import { useWallet } from "@/lib/wallet"
import { NETWORKS, detectAddress, networkFor, networkOf } from "@/lib/chains"
import type { Family } from "@/lib/chains"
import { PLANS, chainScore, scanChain } from "@/lib/multichain"
import type { ChainFinding, ChainReport } from "@/lib/multichain"
import { NetworkPicker } from "./network-picker"
import { WalletRoute } from "./wallet-route"
import type { RouteStatus } from "./wallet-route"

/* A read-only check of any wallet address a multichain wallet hands out. EVM addresses: token
   approvals, NFT operators, Permit2 allowances and EIP-7702 delegation, read from a public dRPC
   node (lib/scan.ts, lib/score.ts). Tron, Solana, Bitcoin and Stellar: the checks that matter on
   each chain (lib/multichain.ts). The network follows the pasted address (lib/chains.ts). Nothing
   to connect and nothing to sign; "use my wallet" only reads the connected address through the
   page's signature lock (lib/wallet.ts). */

/** Who serves each chain's reads, as said to the user. */
const SOURCE: Record<Family, (name: string) => string> = {
  evm: (name) => `dRPC\u2019s public ${name} node`,
  tron: () => "TronGrid\u2019s public API",
  solana: () => "rinng\u2019s own read-only relay to Solana\u2019s public RPC",
  bitcoin: () => "mempool.space",
  stellar: () => "the Stellar Development Foundation\u2019s Horizon API",
}

// The seven steps of the EVM check. scanWallet reports progress as free text; each step owns the
// labels it covers (the same map as components/wallet-check.tsx), and gets a verdict at the end.
const STEPS = [
  { title: "Read-only", body: "This page holds no key and asks for no signature.", match: [] as Array<string> },
  { title: "Account & 7702", body: "EOA, Safe or smart account, and any EIP-7702 delegate.", match: ["Reading the account", "Account type and EIP-7702 delegation"] },
  { title: "Approvals", body: "ERC-20 allowances and NFT operators the wallet granted.", match: ["ERC-20 approvals", "NFT approvals"] },
  { title: "Permit2", body: "Off-chain Permit2 signatures still live.", match: ["Permit2 approvals", "Permit2 signatures"] },
  { title: "Poisoning", body: "Look-alike addresses planted in the transfer history.", match: ["Transfers in", "Transfers out"] },
  { title: "Live allowances", body: "Re-read on-chain today, spenders profiled.", match: ["Re-reading live allowances", "Profiling spenders"] },
  { title: "Exposure & score", body: "Dollars reachable now, and a grade.", match: ["Measuring what is at risk", "Pricing what is at risk"] },
]

const SEV_STATUS: Record<Severity, RouteStatus> = { high: "danger", medium: "warn", low: "ok" }

// Other chains: read-only first, the chain's own checks, then the score.
const planFor = (family: Family) =>
  family === "evm"
    ? STEPS
    : [
        STEPS[0],
        ...PLANS[family].map((p) => ({ ...p, match: [] as Array<string> })),
        { title: "Exposure & score", body: "A grade, with every point it lost explained.", match: [] as Array<string> },
      ]

const gradeStatus = (score: Score | null): RouteStatus =>
  !score ? "done" : score.grade === "A" || score.grade === "B" ? "ok" : score.grade === "C" ? "warn" : "danger"

function chainVerdicts(r: ChainReport, score: Score | null): Array<RouteStatus> {
  const worstOf = (f: Array<ChainFinding>): RouteStatus =>
    f.some((x) => x.severity === "high") ? "danger" : f.some((x) => x.severity === "medium") ? "warn" : "ok"
  return ["ok", ...r.sections.map((s) => (s.findings.length ? worstOf(s.findings) : s.complete ? "ok" : "warn")), gradeStatus(score)]
}

function worst(r: ScanResult, kinds: Array<string>): RouteStatus {
  const sev = r.findings.filter((f) => kinds.includes(f.kind)).map((f) => f.severity)
  return sev.includes("high") ? "danger" : sev.includes("medium") ? "warn" : "ok"
}

function verdicts(r: ScanResult, score: Score | null): Array<RouteStatus> {
  const delegation = r.findings.find((f) => f.kind === "delegation")
  return [
    "ok",
    delegation ? SEV_STATUS[delegation.severity] : r.account.type === "unknown" ? "warn" : "ok",
    worst(r, ["erc20", "nft"]),
    worst(r, ["permit2"]),
    r.poisoning.suspects.length ? "danger" : "ok",
    r.complete ? "ok" : "warn",
    gradeStatus(score),
  ]
}

const STATUS_WORD: Record<RouteStatus, string> = {
  idle: "waiting",
  active: "checking",
  done: "read",
  ok: "pass",
  warn: "review",
  danger: "risk",
}

const STATUS_TEXT: Record<RouteStatus, string> = {
  idle: "text-[#8a8a8a]",
  active: "text-[#5b7cff]",
  done: "text-[#4ade80]",
  ok: "text-[#4ade80]",
  warn: "text-[#f2c94c]",
  danger: "text-[#ff5c4d]",
}

const ACCOUNT: Record<ScanResult["account"]["type"], string> = {
  eoa: "A plain account (EOA): one private key controls it.",
  delegated: "An account running EIP-7702 delegated code.",
  safe: "A Safe multisig.",
  contract: "A smart contract account.",
  unknown: "The account type could not be read.",
}

const SEV_STYLE: Record<Finding["severity"], string> = {
  high: "bg-[#ff5c4d] text-[#0d0d0d]",
  medium: "bg-[#f2c94c] text-[#0d0d0d]",
  low: "bg-[#2a2a2a] text-[#cfcfcf]",
}

const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`

function amountOf(f: Finding) {
  if (f.kind === "delegation") return "delegated"
  if (f.kind === "nft") return "all items"
  if (f.unlimited) return "unlimited"
  if (f.amount != null && f.decimals != null) {
    const n = Number(formatUnits(f.amount, f.decimals))
    return `${n.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${f.symbol ?? ""}`.trim()
  }
  return "limited"
}

export function WalletSection({
  label,
  h2Class,
  running,
  reduced,
}: {
  label: React.ReactNode
  h2Class: string
  running: boolean
  reduced: boolean
}) {
  const w = useWallet()
  const [netKey, setNetKey] = useState("eth")
  const [input, setInput] = useState("")
  const [touched, setTouched] = useState(false)
  const [step, setStep] = useState<string | null>(null)
  const [result, setResult] = useState<ScanResult | null>(null)
  const [report, setReport] = useState<ChainReport | null>(null)
  const [scanned, setScanned] = useState<{ address: string; net: string } | null>(null)
  const [prices, setPrices] = useState<Map<string, Price>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [wantWallet, setWantWallet] = useState(false)
  const [reached, setReached] = useState(-1)
  const [selected, setSelected] = useState(0)

  const detected = detectAddress(input)
  const fieldError = !touched || detected.ok ? null : detected.reason
  const score = useMemo(
    () => (result ? securityScore(result, prices) : report ? chainScore(report) : null),
    [result, report, prices]
  )
  const net = networkOf(netKey)
  // the route shows the plan of the chain being scanned, else of the chain selected
  const shownNet = networkOf(step || !scanned ? netKey : scanned.net)
  const plan = planFor(shownNet.family)

  // the step the scan is on, from its progress label; the route follows it
  useEffect(() => {
    if (!step) return
    const i = STEPS.findIndex((st) => st.match.includes(step))
    if (net.family !== "evm") return
    if (i > 0) setReached((r) => Math.max(r, i))
  }, [step])
  useEffect(() => {
    if (step && reached >= 0) setSelected(reached)
  }, [reached, step])
  useEffect(() => {
    if (result || report) setSelected(plan.length - 1)
  }, [result, report, plan.length])

  const statuses: Array<RouteStatus> = result
    ? verdicts(result, score)
    : report
      ? chainVerdicts(report, score)
      : plan.map((_, i) => (!step ? "idle" : i === 0 ? "ok" : i < reached ? "done" : i === reached ? "active" : "idle"))
  const routeSteps = plan.map((st, i) => ({ title: st.title, body: st.body, status: statuses[i] }))
  const sel = Math.min(selected, plan.length - 1)

  // "use my wallet": fill the field once the wallet answers
  useEffect(() => {
    if (!wantWallet || !w.address) return
    setInput(w.address)
    const match = NETWORKS.find((n) => n.chainId === w.chainId)
    setNetKey((k) => match?.key ?? networkFor("evm", k))
    setWantWallet(false)
  }, [wantWallet, w.address, w.chainId])

  const run = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setTouched(true)
    if (!detected.ok) {
      document.getElementById("wc-address")?.focus()
      return
    }
    if (step) return
    // the address decides the chain: a Solana key is never scanned on Ethereum
    const key = networkFor(detected.family, netKey)
    const target = networkOf(key)
    setNetKey(key)
    setError(null)
    setResult(null)
    setReport(null)
    setScanned(null)
    setPrices(new Map())
    setReached(1)
    setSelected(1)
    const fam = target.family
    try {
      if (fam === "evm") {
        setStep("Reading the account")
        const owner = getAddress(detected.address)
        const chainId = target.chainId!
        const client = createPublicClient({ transport: http(target.rpc, { retryCount: 2, batch: { batchSize: 20 } }) })
        const r = await scanWallet(client, owner, { lookback: 200_000n, chainId, onProgress: setStep })
        setResult(r)
        setScanned({ address: owner, net: key })
        const tokens = r.findings.filter((f) => f.kind === "erc20" || f.kind === "permit2").map((f) => f.token!)
        setStep("Pricing what is at risk")
        setPrices(await tokenPrices(chainId, tokens).catch(() => new Map()))
      } else {
        setStep(PLANS[fam][0].title)
        const r = await scanChain(fam, detected.address, {
          onProgress: (i) => {
            setStep(PLANS[fam][i].title)
            setReached(i + 1)
          },
        })
        setReport(r)
        setScanned({ address: r.address, net: key })
      }
    } catch (err) {
      setError((err as Error).message.split("\n")[0])
    } finally {
      setStep(null)
    }
  }

  const found: Array<{ severity: Severity }> = result?.findings ?? report?.sections.flatMap((s) => s.findings) ?? []
  const counts = result || report ? found.reduce((m, f) => ({ ...m, [f.severity]: m[f.severity] + 1 }), { high: 0, medium: 0, low: 0 }) : undefined
  const scannedNet = scanned ? networkOf(scanned.net) : null

  return (
    <div className="wrap relative grid items-start gap-12 pt-16 pb-20 md:grid-cols-12 md:gap-x-6 md:pt-20">
      <div className="flex flex-col gap-10 md:col-span-5">
        <div>
          {label}
          <h2 id="wallet-h" className={`mt-6 ${h2Class}`}>
            A read-only check of any wallet, on any of its chains
          </h2>
          <p className="mt-6 max-w-[440px] text-[15px] leading-[1.6] text-[#444]">
            Paste any address your wallet shows: EVM, Tron, Solana, Bitcoin or Stellar. rinng picks the network
            from the address, reads who can move the funds (approvals, delegates, signers, EIP-7702) and the traps
            planted around it (dust, look-alike addresses), then grades the exposure. Nothing to connect, nothing
            to sign.
          </p>
        </div>

        <form onSubmit={run} noValidate className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-[170px_1fr]">
            <div>
              <label htmlFor="wc-chain" className="font-mono text-[10px] tracking-widest text-[#666] uppercase">
                Network
              </label>
              <div className="mt-1.5">
                <NetworkPicker id="wc-chain" value={netKey} onChange={setNetKey} />
              </div>
            </div>
            <div>
              <label htmlFor="wc-address" className="font-mono text-[10px] tracking-widest text-[#666] uppercase">
                Wallet address
              </label>
              <input
                id="wc-address"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value)
                  const d = detectAddress(e.target.value)
                  if (d.ok) setNetKey((k) => networkFor(d.family, k))
                }}
                onBlur={() => input.trim() && setTouched(true)}
                placeholder="0x…, T…, bc1…, G…, Solana…"
                spellCheck={false}
                autoComplete="off"
                aria-invalid={!!fieldError}
                aria-describedby={fieldError ? "wc-address-err" : undefined}
                className={`mt-1.5 h-12 w-full rounded-md border bg-white px-3 font-mono text-[13px] transition-colors duration-150 hover:border-[#999] ${fieldError ? "border-[#d93a2b]" : "border-[#d6d6d6]"}`}
              />
              {fieldError && (
                <p id="wc-address-err" className="mt-1.5 text-[12px] text-[#b3261e]">
                  {fieldError}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:gap-7">
            <button
              type="submit"
              disabled={!!step}
              className="group relative inline-flex min-h-12 cursor-pointer items-center gap-3 overflow-hidden rounded-md border border-[#1a1a1a] bg-[#1a1a1a] px-6 py-3.5 text-white shadow-sm transition-[translate,box-shadow] duration-300 hover:-translate-y-0.5 hover:shadow-[3px_3px_0px_rgba(17,17,17,0.5)] active:translate-y-px active:shadow-sm disabled:pointer-events-none disabled:opacity-70"
            >
              <span className="absolute inset-0 -translate-x-[101%] bg-[#fcfcfc] transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:translate-x-0" aria-hidden="true" />
              <HugeiconsIcon
                icon={step ? Loading03Icon : Search01Icon}
                size={18}
                strokeWidth={1.5}
                className={`relative z-10 transition-colors duration-500 group-hover:text-[#111] ${step ? "animate-spin motion-reduce:animate-none" : ""}`}
                aria-hidden="true"
              />
              <span className="relative z-10 text-[15px] font-medium transition-colors duration-500 group-hover:text-[#111]">
                {step ? "Checking" : "Check this wallet"}
              </span>
            </button>
            {w.installed && (
              <button
                type="button"
                onClick={() => {
                  setWantWallet(true)
                  if (!w.address) w.connect()
                }}
                className="group inline-flex min-h-12 cursor-pointer items-center gap-2 text-[15px] font-medium text-[#111] underline decoration-black/25 decoration-1 underline-offset-[6px] transition-colors duration-300 hover:decoration-black active:scale-[0.985]"
              >
                <HugeiconsIcon icon={Wallet01Icon} size={16} strokeWidth={1.5} aria-hidden="true" />
                {w.address ? `Use ${short(w.address)}` : "Use my wallet, read-only"}
              </button>
            )}
          </div>
          <p className="text-[12px] leading-[1.6] text-[#666]">
            {net.family === "evm"
              ? `The address is read through ${SOURCE.evm(net.name)}; token prices come from DefiLlama, which sees only token contracts. The last 200,000 blocks are scanned.`
              : `The address is read through ${SOURCE[net.family](net.name)}, with no key and no signature.`}
          </p>
        </form>
      </div>

      {/* the result frame: the seven-card deck, then the grade and findings */}
      <div className="flex flex-col overflow-hidden rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] text-[#e6e6e6] shadow-[0_30px_60px_-30px_rgba(0,0,0,0.45)] md:col-span-7" data-visual>
        <div className="flex min-h-11 items-center justify-between gap-4 border-b border-[#222] px-5 py-1 font-mono text-[11px] text-[#9a9a9a]">
          <span>wallet check · {scanned && scannedNet ? `${short(scanned.address)} on ${scannedNet.name}` : net.name}</span>
          {(result || report) && scanned && scannedNet && (
            <a
              href={scannedNet.explorer.url(scanned.address)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center gap-1.5 text-[#cfcfcf] transition-colors duration-150 hover:text-white"
            >
              {scannedNet.family === "evm" ? "Revoke on" : "Open in"} {scannedNet.explorer.name}
              <HugeiconsIcon icon={ArrowUpRight01Icon} size={13} aria-hidden="true" />
            </a>
          )}
        </div>

        {/* the steps, top to bottom: seven on EVM, five elsewhere */}
        <div className="h-[396px] shrink-0 border-b border-[#1f1f1f]">
          <WalletRoute steps={routeSteps} selected={sel} onSelect={setSelected} running={running} reduced={reduced} />
        </div>
        <ol className="sr-only">
          {plan.map((st, i) => (
            <li key={st.title}>
              {st.title}: {STATUS_WORD[statuses[i]]}
            </li>
          ))}
        </ol>

        {/* the selected step: what it found */}
        <div className="flex flex-col">
          <div className="flex items-center gap-3 px-5 pt-3">
            <p className="min-w-0 flex-1 text-[14px]" aria-live="polite">
              <span className="mr-2 font-mono text-[11px] text-[#9a9a9a]">
                {String(sel + 1).padStart(2, "0")} / {String(plan.length).padStart(2, "0")}
              </span>
              <span className="font-medium text-white">{plan[sel].title}</span>
              <span className={`ml-3 font-mono text-[11px] tracking-wider uppercase ${STATUS_TEXT[statuses[sel]]}`}>
                {STATUS_WORD[statuses[sel]]}
              </span>
            </p>
            <button
              type="button"
              onClick={() => setSelected((i) => Math.max(0, i - 1))}
              disabled={sel === 0}
              aria-label="Previous step"
              className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full border border-[#333] text-[#cfcfcf] transition-colors duration-150 hover:border-[#888] hover:text-white disabled:cursor-default disabled:opacity-30"
            >
              <HugeiconsIcon icon={ArrowLeft01Icon} size={16} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => setSelected((i) => Math.min(plan.length - 1, i + 1))}
              disabled={sel === plan.length - 1}
              aria-label="Next step"
              className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full border border-[#333] text-[#cfcfcf] transition-colors duration-150 hover:border-[#888] hover:text-white disabled:cursor-default disabled:opacity-30"
            >
              <HugeiconsIcon icon={ArrowRight01Icon} size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="max-h-[300px] overflow-y-auto px-5 pt-2 pb-5 text-[13px] leading-[1.6] text-[#d6d6d6]">
            {error ? (
              <p className="text-[#ffb4ab]">
                The node refused the scan: {error}.{" "}
                {net.family === "solana"
                  ? "Solana is read through rinng\u2019s server (Solana\u2019s public RPC refuses browsers): make sure `rinng web` is running, then try again."
                  : "Try again in a minute, or pick another network."}
              </p>
            ) : result ? (
              <StepDetail index={sel} result={result} score={score} counts={counts} network={scannedNet?.name ?? net.name} />
            ) : report ? (
              <ChainStepDetail index={sel} report={report} score={score} counts={counts} />
            ) : (
              <p className="text-[#b0b0b0]">
                {plan[sel].body}{" "}
                {statuses[sel] === "active" && step ? <span className="inline-flex items-center gap-1.5 align-middle font-mono text-[11px] text-[#5b7cff]">
                    <HugeiconsIcon icon={Loading03Icon} size={12} strokeWidth={2} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                    {step}
                  </span> : null}
                {!step && "Paste an address and press Check this wallet: the route fills in, step by step."}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function FindingList({ items, empty }: { items: Array<Finding>; empty: string }) {
  if (!items.length) return <p className="text-[#9a9a9a]">{empty}</p>
  return (
    <ul className="divide-y divide-[#1f1f1f]">
      {items.slice(0, 10).map((f, i) => (
        <li key={`${f.kind}-${f.spender}-${f.token ?? ""}-${i}`} className="grid grid-cols-[auto_1fr_auto] items-start gap-x-3 gap-y-1 py-2.5">
          <span className={`mt-0.5 rounded px-1.5 py-0.5 font-mono text-[10px] tracking-wider uppercase ${SEV_STYLE[f.severity]}`}>{f.severity}</span>
          <div className="min-w-0">
            <p className="truncate text-[14px] font-medium text-white">
              {f.kind === "delegation" ? "Delegation" : (f.symbol ?? (f.token ? short(f.token) : f.kind))}
              <span className="ml-2 font-mono text-[11px] text-[#9a9a9a]">→ {f.label ?? short(f.spender)}</span>
            </p>
            <p className="mt-0.5 text-[12px] leading-[1.5] text-[#9a9a9a]">{f.note}</p>
          </div>
          <span className="font-mono text-[11px] text-[#cfcfcf]">{amountOf(f)}</span>
        </li>
      ))}
      {items.length > 10 && <li className="py-2 font-mono text-[11px] text-[#9a9a9a]">+ {items.length - 10} more on revoke.cash</li>}
    </ul>
  )
}

function StepDetail({
  index,
  result,
  score,
  counts,
  network,
}: {
  index: number
  result: ScanResult
  score: Score | null
  counts: Record<Severity, number> | undefined
  network: string
}) {
  const of = (...kinds: Array<Finding["kind"]>) => result.findings.filter((f) => kinds.includes(f.kind))
  switch (index) {
    case 0:
      return <p>No key and no signature: every call was a public read through dRPC&rsquo;s {network} node.</p>
    case 1:
      return (
        <div className="space-y-2">
          <p>{ACCOUNT[result.account.type]}{result.account.type === "safe" ? ` ${result.account.threshold} of ${result.account.owners.length} signers.` : ""}</p>
          <FindingList items={of("delegation")} empty="No EIP-7702 delegation on this account." />
        </div>
      )
    case 2:
      return <FindingList items={of("erc20", "nft")} empty="No open ERC-20 allowances or NFT operators in the scanned window." />
    case 3:
      return <FindingList items={of("permit2")} empty="No live Permit2 allowances." />
    case 4:
      return result.poisoning.suspects.length ? (
        <ul className="divide-y divide-[#1f1f1f]">
          {result.poisoning.suspects.slice(0, 8).map((p) => (
            <li key={p.address} className="py-2.5">
              <span className="font-mono text-white">{short(p.address)}</span> imitates{" "}
              <span className="font-mono text-white">{short(p.imitates)}</span>
              <span className="text-[#9a9a9a]"> · planted {p.planted}×{p.zeroValue ? `, ${p.zeroValue} zero-value` : ""}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>No look-alike addresses in the transfer history ({result.poisoning.counterparties.length} real counterparties checked).</p>
      )
    case 5:
      return (
        <div className="space-y-2">
          <p>
            {result.complete
              ? "Every source was read in full, then each allowance was re-read on-chain today."
              : "Part of the history could not be read from the public node, so the score is provisional."}
          </p>
          <ul className="grid gap-x-6 gap-y-1 font-mono text-[11px] sm:grid-cols-2">
            {Object.entries(result.coverage).map(([k, v]) => (
              <li key={k} className="flex justify-between gap-3">
                <span className="text-[#9a9a9a]">{k}</span>
                <span className={v >= 1 ? "text-[#4ade80]" : "text-[#f2c94c]"}>{Math.round(v * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )
    default:
      return <ScorePanel score={score} counts={counts} />
  }
}

function ScorePanel({ score, counts }: { score: Score | null; counts: Record<Severity, number> | undefined }) {
  if (!score) return <p className="text-[#9a9a9a]">Pricing what is at risk…</p>
  return (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex items-end gap-4">
              <span className="font-serif text-[3.2rem] leading-none font-light text-white">{score.grade}</span>
              <div className="pb-1">
                <p className="text-[20px] font-medium text-white tabular-nums">
                  {score.score}
                  <span className="text-[#777]">/100</span>
                </p>
                <p className="font-mono text-[10px] tracking-widest text-[#9a9a9a] uppercase">
                  {score.provisional ? "Provisional" : "Exposure score"}
                </p>
              </div>
            </div>
            <dl className="flex gap-5 font-mono text-[11px] uppercase">
              {(["high", "medium", "low"] as const).map((sv) => (
                <div key={sv}>
                  <dt className="tracking-widest text-[#9a9a9a]">{sv}</dt>
                  <dd className="mt-1 text-[18px] text-white tabular-nums">{counts?.[sv] ?? 0}</dd>
                </div>
              ))}
              {score.usdAtRisk > 0 && (
                <div>
                  <dt className="tracking-widest text-[#9a9a9a]">at risk</dt>
                  <dd className="mt-1 text-[18px] text-white tabular-nums">{usd(score.usdAtRisk)}</dd>
                </div>
              )}
            </dl>
          </div>
          {score.items.length > 0 && (
            <ul className="space-y-1 border-l border-[#2a2a2a] pl-4">
              {score.items.map((it) => (
                <li key={it.text}>
                  <span className="mr-2 font-mono text-[#9a9a9a] tabular-nums">{it.delta ? it.delta : "·"}</span>
                  {it.text}
                </li>
              ))}
            </ul>
          )}
        </div>
  )
}

function ChainFindings({ items }: { items: Array<ChainFinding> }) {
  return (
    <ul className="divide-y divide-[#1f1f1f]">
      {items.slice(0, 10).map((f, i) => (
        <li key={`${f.title}-${i}`} className="grid grid-cols-[auto_1fr_auto] items-start gap-x-3 gap-y-1 py-2.5">
          <span className={`mt-0.5 rounded px-1.5 py-0.5 font-mono text-[10px] tracking-wider uppercase ${SEV_STYLE[f.severity]}`}>{f.severity}</span>
          <div className="min-w-0">
            <p className="truncate text-[14px] font-medium text-white">{f.title}</p>
            <p className="mt-0.5 text-[12px] leading-[1.5] text-[#9a9a9a]">{f.note}</p>
          </div>
          <span className="font-mono text-[11px] text-[#cfcfcf]">{f.amount ?? ""}</span>
        </li>
      ))}
      {items.length > 10 && <li className="py-2 font-mono text-[11px] text-[#9a9a9a]">+ {items.length - 10} more</li>}
    </ul>
  )
}

function ChainStepDetail({
  index,
  report,
  score,
  counts,
}: {
  index: number
  report: ChainReport
  score: Score | null
  counts: Record<Severity, number> | undefined
}) {
  if (index === 0) return <p>No key and no signature: every call was a public read through {SOURCE[report.family]("")}.</p>
  if (index > report.sections.length) return <ScorePanel score={score} counts={counts} />
  const section = report.sections[index - 1]
  return (
    <div className="space-y-2">
      {section.summary && <p>{section.summary}</p>}
      {!section.complete && <p className="text-[#f2c94c]">Part of this could not be read from the public source, so the score is provisional.</p>}
      {section.findings.length > 0 && <ChainFindings items={section.findings} />}
    </div>
  )
}
