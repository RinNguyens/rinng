import { getAddress, parseAbi, parseAbiItem } from "viem"
import type { Address, Hex, PublicClient } from "viem"
import { findPoisoning } from "./address"
import type { Poisoning, Transfer } from "./address"
import { labelOf } from "./spenders"

// Wallet health scan, read-only: who can move this wallet's funds right now?
// - EIP-7702 delegation (one signature that turned the EOA into someone else's contract)
// - live ERC-20 allowances, NFT operator approvals (setApprovalForAll), Permit2 allowances
// - what kind of account it is (plain EOA, 7702-delegated, Safe multisig) and address poisoning
// Approvals are discovered from logs in the last `lookback` blocks, then re-read on-chain so only
// what is still live is reported. Older approvals are outside the window: the UI says so.
// Each spender is then profiled: EOA or contract (a 7702-delegated EOA is still an EOA: someone
// holds its key), upgradeable proxy or not, known protocol or not, and how much of the token the
// wallet holds right now (what the approval can actually take today).

export const PERMIT2: Address = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
export const MULTICALL3: Address = "0xcA11bde05977b3631167028862bE2a173976CA11"
/** At or above this an ERC-20 allowance is "unlimited" (some tokens decrement max uint). */
export const UNLIMITED = 2n ** 255n
const PERMIT2_UNLIMITED = 2n ** 159n // amount is uint160
const LONG_EXPIRY = 30 * 86_400
/** EIP-7702 delegation designator: code 0xef0100 ‖ delegate address. */
const DELEGATED = /^0xef0100/i
/** EIP-1967 implementation and beacon slots: set on upgradeable proxies. */
const IMPL_SLOT: Hex =
  "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
const BEACON_SLOT: Hex =
  "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"

export type Severity = "high" | "medium" | "low"
export type Kind = "delegation" | "erc20" | "nft" | "permit2"

/** What the chain says, before judgement. */
export type Raw = {
  kind: Kind
  spender: Address // delegate, spender or operator
  /** False for EOAs, including EOAs with EIP-7702 code: a private key controls them. */
  spenderIsContract: boolean
  /** The spender is an EOA running EIP-7702 delegated code. */
  spenderDelegated?: boolean
  /** The spender is an upgradeable proxy: its admin can change what it does. */
  upgradeable?: boolean
  /** Known protocol name, from spenders.ts. */
  label?: string
  /** What the wallet holds now: token units (ERC-20, Permit2) or item count (NFT). */
  balance?: bigint
  token?: Address
  symbol?: string
  decimals?: number
  amount?: bigint
  approved?: boolean
  expiration?: number // unix seconds (Permit2)
}

export type Finding = Raw & {
  severity: Severity
  unlimited: boolean
  note: string
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

export function classify(r: Raw, now: number): Finding | null {
  const f = (severity: Severity, note: string, unlimited = false): Finding => ({
    ...r,
    severity,
    unlimited,
    note,
  })
  const eoa = r.spenderDelegated
    ? "an EOA running EIP-7702 code (someone's wallet, not a protocol)"
    : "a plain wallet (EOA), not a contract"
  const proxy = r.upgradeable
    ? " It is an upgradeable proxy: whoever controls the upgrade can change what it does with your allowance."
    : ""
  switch (r.kind) {
    case "delegation":
      return r.label
        ? f(
            "medium",
            `Delegated (EIP-7702) to ${r.label}. Fine if you turned on this smart account in its own wallet app; revoke it if you didn't.`
          )
        : f(
            "high",
            "This wallet's code is delegated (EIP-7702) to a contract rinng doesn't recognise. It can act for the wallet and move everything. Revoke it unless you set up this smart account yourself."
          )
    case "erc20": {
      if (!r.amount) return null
      const unlimited = r.amount >= UNLIMITED
      if (!r.spenderIsContract)
        return f(
          "high",
          `Allowance to ${eoa}. Drainers use this. Revoke.`,
          unlimited
        )
      if (same(r.spender, PERMIT2))
        return f(
          "low",
          "Approval to the Permit2 router. What matters are the Permit2 allowances below.",
          unlimited
        )
      if (!unlimited)
        return f("low", `Limited allowance to a contract.${proxy}`)
      if (r.label && !r.upgradeable)
        return f(
          "low",
          `Unlimited allowance to ${r.label}. Normal while you use it; revoke if you don't.`,
          true
        )
      return f(
        "medium",
        `Unlimited allowance${r.label ? ` to ${r.label}` : " to an unrecognised contract"}: if it is hacked or upgraded, the whole balance can go.${proxy}`,
        true
      )
    }
    case "nft":
      if (!r.approved) return null
      if (!r.spenderIsContract)
        return f(
          "high",
          `${eoa[0].toUpperCase()}${eoa.slice(1)} may move every NFT in this collection. Revoke.`,
          true
        )
      return r.label && !r.upgradeable
        ? f(
            "low",
            `${r.label} may move every NFT in this collection. Normal for a marketplace you use.`,
            true
          )
        : f(
            "medium",
            `Operator may move every NFT in this collection. Keep only marketplaces you use.${proxy}`,
            true
          )
    case "permit2": {
      if (!r.amount || (r.expiration ?? 0) <= now) return null
      const unlimited = r.amount >= PERMIT2_UNLIMITED
      if (!r.spenderIsContract)
        return f(
          "high",
          `Permit2 allowance to ${eoa}: typical of a phishing signature. Revoke.`,
          unlimited
        )
      if (unlimited || (r.expiration ?? 0) - now > LONG_EXPIRY)
        return f(
          r.label && !r.upgradeable ? "low" : "medium",
          `Large or long-lived Permit2 allowance${r.label ? ` to ${r.label}` : ""}. It was granted by a signature, not a transaction.${proxy}`,
          unlimited
        )
      return f("low", "Short, limited Permit2 allowance.")
    }
  }
}

/** Units the approval can take today: the smaller of the allowance and what the wallet holds. */
export function exposure(f: Finding): bigint | undefined {
  if (f.balance == null) return undefined
  if (f.kind === "nft") return f.balance
  if (f.kind === "erc20" || f.kind === "permit2")
    return f.amount != null && f.amount < f.balance ? f.amount : f.balance
  return undefined
}

const RANK: Record<Severity, number> = { high: 0, medium: 1, low: 2 }
export const sortFindings = (f: Array<Finding>) =>
  [...f].sort((a, b) => RANK[a.severity] - RANK[b.severity])

/** Consecutive failures at `minChunk` after which the RPC is taken to refuse the query itself. */
const GIVE_UP_AFTER = 3

/**
 * Reads [from, to] in chunks, halving a chunk the RPC refuses (range or result-size limits),
 * down to `minChunk`. It never grows back, so the RPC's range limit is learned once and not
 * retried on every chunk. A range that still fails is reported in `errors` and skipped. If the
 * smallest chunk keeps failing, the RPC refuses the query whatever the range (e.g. it requires
 * an `address`): stop and report the rest once.
 */
export async function logsInChunks<T>(
  fetch: (from: bigint, to: bigint) => Promise<Array<T>>,
  from: bigint,
  to: bigint,
  chunk = 50_000n,
  minChunk = 500n
): Promise<{ items: Array<T>; errors: Array<string>; covered: bigint }> {
  const items: Array<T> = []
  const errors: Array<string> = []
  let covered = 0n // blocks actually read
  let start = from
  let size = chunk
  let strikes = 0
  while (start <= to) {
    const end = start + size - 1n < to ? start + size - 1n : to
    try {
      items.push(...(await fetch(start, end)))
      covered += end - start + 1n
      start = end + 1n
      strikes = 0
    } catch (e) {
      if (size > minChunk) {
        size = size / 2n > minChunk ? size / 2n : minChunk
        continue
      }
      const msg = (e as Error).message.split("\n")[0]
      if (++strikes >= GIVE_UP_AFTER) {
        errors.push(`blocks ${start}–${to}: RPC refused: ${msg}`)
        break
      }
      errors.push(`blocks ${start}–${end}: ${msg}`)
      start = end + 1n
    }
  }
  return { items, errors, covered }
}

const APPROVAL = parseAbiItem(
  "event Approval(address indexed owner, address indexed spender, uint256 value)"
)
const APPROVAL_FOR_ALL = parseAbiItem(
  "event ApprovalForAll(address indexed owner, address indexed operator, bool approved)"
)
const P2_APPROVAL = parseAbiItem(
  "event Approval(address indexed owner, address indexed token, address indexed spender, uint160 amount, uint48 expiration)"
)
const P2_PERMIT = parseAbiItem(
  "event Permit(address indexed owner, address indexed token, address indexed spender, uint160 amount, uint48 expiration, uint48 nonce)"
)
const ERC20 = parseAbi([
  "function allowance(address owner, address spender) view returns (uint256)",
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
])
const ERC721 = parseAbi([
  "function isApprovedForAll(address owner, address operator) view returns (bool)",
])
const P2 = parseAbi([
  "function allowance(address owner, address token, address spender) view returns (uint160 amount, uint48 expiration, uint48 nonce)",
])

const ERC721_BALANCE = parseAbi([
  "function balanceOf(address owner) view returns (uint256)",
])
const SAFE = parseAbi([
  "function getThreshold() view returns (uint256)",
  "function getOwners() view returns (address[])",
])
const TRANSFER = parseAbiItem(
  "event Transfer(address indexed from, address indexed to, uint256 value)"
)

export type ScanClient = Pick<
  PublicClient,
  | "getBlockNumber"
  | "getDelegation"
  | "getCode"
  | "getLogs"
  | "multicall"
  | "getStorageAt"
>

export type Account =
  | { type: "eoa" }
  | { type: "delegated"; delegate: Address }
  | { type: "safe"; threshold: number; owners: Array<Address> }
  | { type: "contract" }
  | { type: "unknown" }

export type ScanResult = {
  findings: Array<Finding>
  account: Account
  poisoning: Poisoning
  fromBlock: bigint
  toBlock: bigint
  errors: Array<string>
  /** Share of the block window each log source actually read, 0..1. */
  coverage: Record<string, number>
  /** False when any source missed blocks: an empty result then proves nothing. */
  complete: boolean
}

type Log = { address: Address; args: Record<string, Address | undefined> }

export async function scanWallet(
  client: ScanClient,
  owner: Address,
  {
    lookback = 200_000n,
    now = Math.floor(Date.now() / 1000),
    chainId,
    onProgress,
  }: {
    lookback?: bigint
    now?: number
    chainId?: number | null
    onProgress?: (step: string) => void
  } = {}
): Promise<ScanResult> {
  owner = getAddress(owner)
  const toBlock = await client.getBlockNumber()
  const fromBlock = toBlock >= lookback ? toBlock - lookback + 1n : 0n
  const errors: Array<string> = []
  const coverage: Record<string, number> = {}
  const span = toBlock - fromBlock + 1n
  let complete = true
  const raws: Array<Raw> = []

  onProgress?.("Account type and EIP-7702 delegation")
  const delegate = await client
    .getDelegation({ address: owner })
    .catch((e: Error) => {
      errors.push(`delegation: ${e.message.split("\n")[0]}`)
      complete = false
      return undefined
    })
  if (delegate)
    raws.push({
      kind: "delegation",
      spender: getAddress(delegate),
      spenderIsContract: true,
      label: labelOf(delegate, chainId)?.name,
    })
  const account = await accountType(client, owner, delegate, errors)

  // `strict` drops ERC-721 Approval logs, which share the topic but index the token id.
  const read = async (
    label: string,
    q: (from: bigint, to: bigint) => Promise<Array<unknown>>
  ) => {
    onProgress?.(label)
    const r = await logsInChunks(q, fromBlock, toBlock)
    errors.push(...r.errors.map((e) => `${label}: ${e}`))
    coverage[label] = Number((r.covered * 10_000n) / span) / 10_000
    if (r.covered < span) complete = false
    return r.items as Array<Log>
  }
  const erc20Logs = await read("ERC-20 approvals", (f, t) =>
    client.getLogs({
      event: APPROVAL,
      args: { owner },
      fromBlock: f,
      toBlock: t,
      strict: true,
    })
  )
  const nftLogs = await read("NFT approvals", (f, t) =>
    client.getLogs({
      event: APPROVAL_FOR_ALL,
      args: { owner },
      fromBlock: f,
      toBlock: t,
      strict: true,
    })
  )
  const p2Logs = [
    ...(await read("Permit2 approvals", (f, t) =>
      client.getLogs({
        address: PERMIT2,
        event: P2_APPROVAL,
        args: { owner },
        fromBlock: f,
        toBlock: t,
        strict: true,
      })
    )),
    ...(await read("Permit2 signatures", (f, t) =>
      client.getLogs({
        address: PERMIT2,
        event: P2_PERMIT,
        args: { owner },
        fromBlock: f,
        toBlock: t,
        strict: true,
      })
    )),
  ]

  const transferLogs = [
    ...(await read("Transfers in", (f, t) =>
      client.getLogs({
        event: TRANSFER,
        args: { to: owner },
        fromBlock: f,
        toBlock: t,
        strict: true,
      })
    )),
    ...(await read("Transfers out", (f, t) =>
      client.getLogs({
        event: TRANSFER,
        args: { from: owner },
        fromBlock: f,
        toBlock: t,
        strict: true,
      })
    )),
  ] as unknown as Array<{
    address: Address
    args: { from: Address; to: Address; value: bigint }
  }>
  const poisoning = findPoisoning(
    transferLogs.map((l): Transfer => ({ token: l.address, ...l.args })),
    owner
  )

  const uniq = <T>(xs: Array<T>, key: (x: T) => string) => [
    ...new Map(xs.map((x) => [key(x), x])).values(),
  ]
  const erc20 = uniq(
    erc20Logs.map((l) => ({
      token: getAddress(l.address),
      spender: getAddress(l.args.spender!),
    })),
    (x) => x.token + x.spender
  )
  const nft = uniq(
    nftLogs.map((l) => ({
      token: getAddress(l.address),
      spender: getAddress(l.args.operator!),
    })),
    (x) => x.token + x.spender
  )
  const p2 = uniq(
    p2Logs.map((l) => ({
      token: getAddress(l.args.token!),
      spender: getAddress(l.args.spender!),
    })),
    (x) => x.token + x.spender
  )

  onProgress?.("Re-reading live allowances")
  const mc = (contracts: Array<object>) =>
    contracts.length
      ? client.multicall({
          contracts: contracts as never,
          allowFailure: true,
          multicallAddress: MULTICALL3,
        })
      : Promise.resolve([])
  const [a20, a721, ap2] = (await Promise.all([
    mc(
      erc20.map((x) => ({
        address: x.token,
        abi: ERC20,
        functionName: "allowance",
        args: [owner, x.spender],
      }))
    ),
    mc(
      nft.map((x) => ({
        address: x.token,
        abi: ERC721,
        functionName: "isApprovedForAll",
        args: [owner, x.spender],
      }))
    ),
    mc(
      p2.map((x) => ({
        address: PERMIT2,
        abi: P2,
        functionName: "allowance",
        args: [owner, x.token, x.spender],
      }))
    ),
  ])) as Array<Array<R>>

  erc20.forEach((x, i) => {
    const amount = ok(a20[i]) as bigint | undefined
    if (amount)
      raws.push({ kind: "erc20", ...x, spenderIsContract: true, amount })
  })
  nft.forEach((x, i) => {
    if (ok(a721[i]) === true)
      raws.push({ kind: "nft", ...x, spenderIsContract: true, approved: true })
  })
  p2.forEach((x, i) => {
    const r = ok(ap2[i]) as readonly [bigint, number, number] | undefined
    if (r && r[0] > 0n)
      raws.push({
        kind: "permit2",
        ...x,
        spenderIsContract: true,
        amount: r[0],
        expiration: Number(r[1]),
      })
  })

  // Is each spender a contract? An EOA spender is the strongest drainer signal. An EOA with
  // 7702 code has code too, but a private key still controls it: it counts as an EOA.
  onProgress?.("Profiling spenders")
  const spenders = [
    ...new Set(
      raws.filter((r) => r.kind !== "delegation").map((r) => r.spender)
    ),
  ]
  const isContract = new Map(
    await Promise.all(
      spenders.map(async (s) => {
        try {
          const code = await client.getCode({ address: s })
          return [s, codeKind(code)] as const
        } catch (e) {
          // Unknown: rated as a contract, and the error is shown so the gap is visible.
          errors.push(`code of ${s}: ${(e as Error).message.split("\n")[0]}`)
          return [s, "contract" as const] as const
        }
      })
    )
  )
  // Upgradeable? Only for contracts rinng doesn't know: a known protocol's proxy is expected.
  const proxies = new Set(
    (
      await Promise.all(
        spenders
          .filter(
            (s) => isContract.get(s) === "contract" && !labelOf(s, chainId)
          )
          .map(async (s) => {
            const slots = await Promise.all(
              [IMPL_SLOT, BEACON_SLOT].map((slot) =>
                client.getStorageAt({ address: s, slot }).catch(() => undefined)
              )
            )
            return slots.some((v) => !!v && BigInt(v) !== 0n) ? s : null
          })
      )
    ).filter((s): s is Address => s !== null)
  )
  raws.forEach((r) => {
    if (r.kind === "delegation") return
    const k = isContract.get(r.spender) ?? "contract"
    r.spenderIsContract = k === "contract"
    if (k === "delegated") r.spenderDelegated = true
    if (proxies.has(r.spender)) r.upgradeable = true
    const l = labelOf(r.spender, chainId)
    if (l) r.label = l.name
  })

  // Token labels for the UI. Failure just leaves the address.
  const tokens = [
    ...new Set(
      raws
        .filter((r) => r.kind === "erc20" || r.kind === "permit2")
        .map((r) => r.token!)
    ),
  ]
  const meta = (await mc(
    tokens.flatMap((t) => [
      { address: t, abi: ERC20, functionName: "symbol" },
      { address: t, abi: ERC20, functionName: "decimals" },
    ])
  )) as Array<R>
  const label = new Map(
    tokens.map((t, i) => [
      t,
      { symbol: ok(meta[2 * i]), decimals: ok(meta[2 * i + 1]) },
    ])
  )
  // What each approval can reach today. ERC-20 and ERC-721 share balanceOf(address).
  onProgress?.("Measuring what is at risk")
  const held = [
    ...new Set(
      raws.filter((r) => r.kind !== "delegation").map((r) => r.token!)
    ),
  ]
  const balances = (await mc(
    held.map((t) => ({
      address: t,
      abi: ERC721_BALANCE,
      functionName: "balanceOf",
      args: [owner],
    }))
  )) as Array<R>
  const balance = new Map(held.map((t, i) => [t, ok(balances[i])]))
  raws.forEach((r) => {
    const m = r.token ? label.get(r.token) : undefined
    if (typeof m?.symbol === "string") r.symbol = m.symbol
    if (typeof m?.decimals === "number") r.decimals = m.decimals
    const b = r.token ? balance.get(r.token) : undefined
    if (typeof b === "bigint") r.balance = b
  })

  const findings = sortFindings(
    raws.map((r) => classify(r, now)).filter((f): f is Finding => f !== null)
  )
  return {
    findings,
    account,
    poisoning,
    fromBlock,
    toBlock,
    errors,
    coverage,
    complete,
  }
}

type R =
  { status: "success"; result: unknown } | { status: "failure"; error: Error }
const ok = (r: R | undefined) =>
  r?.status === "success" ? r.result : undefined

async function accountType(
  c: ScanClient,
  addr: Address,
  delegateTo: Address | undefined,
  errs: Array<string>
): Promise<Account> {
  if (delegateTo) return { type: "delegated", delegate: getAddress(delegateTo) }
  const code = await c.getCode({ address: addr }).catch((e: Error) => {
    errs.push(`account code: ${e.message.split("\n")[0]}`)
    return null
  })
  if (code === null) return { type: "unknown" }
  const kind = codeKind(code)
  if (kind === "eoa") return { type: "eoa" }
  if (kind === "delegated")
    return {
      type: "delegated",
      delegate: getAddress(`0x${code!.slice(8, 48)}`),
    }
  const [t, o] = (await c
    .multicall({
      contracts: [
        { address: addr, abi: SAFE, functionName: "getThreshold" },
        { address: addr, abi: SAFE, functionName: "getOwners" },
      ] as never,
      allowFailure: true,
      multicallAddress: MULTICALL3,
    })
    .catch(() => [])) as Array<R>
  const threshold = ok(t)
  const owners = ok(o)
  if (typeof threshold === "bigint" && Array.isArray(owners))
    return {
      type: "safe",
      threshold: Number(threshold),
      owners: owners as Array<Address>,
    }
  return { type: "contract" }
}

/** "eoa" (no code), "delegated" (EOA with EIP-7702 code) or "contract". */
export function codeKind(
  code: Hex | undefined
): "eoa" | "delegated" | "contract" {
  if (!code || code === "0x") return "eoa"
  return DELEGATED.test(code) ? "delegated" : "contract"
}
