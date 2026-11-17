import { poisoning, tronAddress, tronHex } from "./chains"
import type { Family, Lookalike, Movement } from "./chains"
import type { Severity } from "./scan"
import type { Score, ScoreItem } from "./score"

// Read-only safety checks for the non-EVM addresses a multichain wallet hands out. Each chain is
// drained differently, so each gets the checks that matter there:
// - Tron: account permission hijack (the owner key swapped for an attacker's), TRC-20 approvals
//   re-read on-chain, address poisoning in the TRC-20 history.
// - Solana: an account reassigned away from the System Program, SPL token delegates and foreign
//   close authorities, look-alike addresses in recent transactions.
// - Bitcoin: dust attacks, address reuse, look-alike addresses in recent transactions.
// - Stellar: extra signers and thresholds (the Stellar form of a hijack), airdrop-spam claimable
//   balances, look-alike payment senders.
// Every read is a public GET/POST with no key and no signature. Solana's public RPC refuses browser
// origins, so Solana goes through rinng's own read-only relay (/api/solana) unless VITE_SOLANA_RPC
// names an RPC that accepts the browser.

export type NonEvm = Exclude<Family, "evm">

export type ChainFinding = {
  severity: Severity
  title: string
  note: string
  /** Shown on the right of the row: an amount, a count. */
  amount?: string
  /** Score points this finding costs; defaults by severity. */
  points?: number
}

export type ChainSection = {
  title: string
  findings: Array<ChainFinding>
  /** Said when there are no findings, or above them. */
  summary: string
  complete: boolean
}

export type ChainReport = {
  family: NonEvm
  address: string
  sections: Array<ChainSection>
  suspects: Array<Lookalike>
  complete: boolean
}

/** The steps each chain's check walks through, in order, before the score. */
export const PLANS: Record<NonEvm, Array<{ title: string; body: string }>> = {
  tron: [
    {
      title: "Permissions",
      body: "Who can sign for the account: owner and active keys.",
    },
    {
      title: "TRC-20 approvals",
      body: "Allowances the wallet granted, re-read on-chain.",
    },
    {
      title: "Poisoning",
      body: "Look-alike addresses planted in the TRC-20 history.",
    },
  ],
  solana: [
    {
      title: "Account owner",
      body: "Still a wallet owned by the System Program.",
    },
    {
      title: "Token delegates",
      body: "SPL delegates and close authorities on token accounts.",
    },
    {
      title: "Poisoning",
      body: "Look-alike addresses in recent transactions.",
    },
  ],
  bitcoin: [
    {
      title: "Address & reuse",
      body: "Address type and how often it was reused.",
    },
    { title: "Dust", body: "Tiny outputs sent to link and track the wallet." },
    {
      title: "Poisoning",
      body: "Look-alike addresses in recent transactions.",
    },
  ],
  stellar: [
    {
      title: "Signers",
      body: "Who can sign for the account, and the thresholds.",
    },
    {
      title: "Assets & claims",
      body: "Trustlines and unsolicited claimable balances.",
    },
    { title: "Poisoning", body: "Look-alike senders in recent payments." },
  ],
}

type Fetch = typeof fetch
export type ScanOptions = {
  fetch?: Fetch
  onProgress?: (section: number) => void
  solanaRpc?: string
}

const TRONGRID = "https://api.trongrid.io"
const MEMPOOL = "https://mempool.space/api"
const HORIZON = "https://horizon.stellar.org"
const SOLANA_RPC =
  (import.meta.env.VITE_SOLANA_RPC as string | undefined) || "/api/solana"

async function request<T>(
  f: Fetch,
  url: string,
  body?: unknown
): Promise<T | null> {
  for (let attempt = 0; ; attempt++) {
    const r = await f(url, {
      method: body === undefined ? "GET" : "POST",
      headers:
        body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    // keyless public APIs throttle hard: back off and retry before giving up
    if (r.status === 429 && attempt < 4) {
      await new Promise((ok) => setTimeout(ok, 1500 * (attempt + 1)))
      continue
    }
    if (r.status === 404) return null
    if (!r.ok) {
      // JSON-RPC relays explain refusals (data allowance, oversized wallet) in the body
      const said = (await r.json().catch(() => null)) as {
        error?: { message?: string }
        detail?: string
      } | null
      throw new Error(
        said?.error?.message ??
          said?.detail ??
          `${new URL(url, "http://localhost").host} answered ${r.status}`
      )
    }
    return (await r.json()) as T
  }
}

/** Run `work` over `items` with at most `n` in flight. */
async function pool<T, TResult>(
  items: Array<T>,
  n: number,
  work: (t: T) => Promise<TResult>
): Promise<Array<TResult>> {
  const out = new Array<TResult>(items.length)
  let next = 0
  await Promise.all(
    Array.from({ length: Math.min(n, items.length) }, async () => {
      while (next < items.length) {
        const i = next++
        out[i] = await work(items[i])
      }
    })
  )
  return out
}

const plural = (n: number, word: string) =>
  `${n} ${n === 1 ? word : word.endsWith("y") ? `${word.slice(0, -1)}ies` : `${word}s`}`
const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`
const fmt = (units: bigint, decimals: number) => {
  const n = Number(units) / 10 ** decimals
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 })
}

function poisonSection(
  moves: Array<Movement>,
  owner: string,
  read: string,
  complete: boolean
) {
  const p = poisoning(moves, owner)
  const section: ChainSection = {
    title: "Poisoning",
    complete,
    summary: p.suspects.length
      ? `${plural(p.suspects.length, "look-alike address")} planted in ${read}. Never copy an address from your history.`
      : `No look-alike addresses in ${read} (${plural(p.counterparties, "real counterparty")} checked).`,
    findings: p.suspects.map((s) => ({
      severity: "high" as const,
      title: `${short(s.address)} imitates ${short(s.imitates)}`,
      note: `Same start and end as an address you paid, planted ${s.planted}×${s.zeroValue ? `, ${s.zeroValue} zero-value` : ""}. Do not send to it.`,
      points: 5,
    })),
  }
  return { section, suspects: p.suspects }
}

/** Keys and weights of one permission: can someone else sign alone, can the owner? */
export function judgeKeys(
  name: string,
  self: string,
  threshold: number,
  keys: Array<{ address: string; weight: number }>
): ChainFinding | null {
  const t = Math.max(1, threshold)
  const own = keys
    .filter((k) => k.address === self)
    .reduce((s, k) => s + k.weight, 0)
  const others = keys.filter((k) => k.address !== self && k.weight > 0)
  const theirs = others.reduce((s, k) => s + k.weight, 0)
  const who = others.map((k) => short(k.address)).join(", ")
  const strongest = others.find((k) => k.weight >= t)
  if (strongest)
    return {
      severity: "high",
      title: `${name}: another key can sign alone`,
      note:
        own >= t
          ? `${short(strongest.address)} can sign for this account without you (threshold ${t}). Unless you added it yourself, the account is compromised: move funds to a fresh wallet.`
          : `Your own key can no longer sign; ${short(strongest.address)} controls the account (threshold ${t}). This is how permission-hijack scams take wallets. Do not deposit here.`,
      points: 60,
    }
  if (theirs >= t)
    return own >= t
      ? {
          severity: "high",
          title: `${name}: other keys can sign without you`,
          note: `${who} together reach the threshold of ${t} without your key. Unless you set up this multisig yourself, move funds to a fresh wallet.`,
          points: 30,
        }
      : {
          severity: "medium",
          title: `${name}: run by other keys`,
          note: `${others.length} other keys (${who}) sign together; ${own ? "your key alone is not enough" : "your own key has no weight"}. Normal for an organisation's multisig; if this is your personal wallet, it is no longer yours.`,
          points: 15,
        }
  if (!others.length)
    return own >= t
      ? null
      : {
          severity: "high",
          title: `${name}: no key can sign`,
          note: `Weights never reach the threshold of ${t}: the account is locked.`,
          points: 30,
        }
  if (own < t)
    return {
      severity: "medium",
      title: `${name}: multisig`,
      note: `You need co-signers (${who}) to reach the threshold of ${t}. Fine if you set this up yourself.`,
      points: 5,
    }
  return {
    severity: "medium",
    title: `${name}: extra key`,
    note: `${who} was added but cannot sign alone. Remove it if you don't know it.`,
    points: 10,
  }
}

// ---- Tron -------------------------------------------------------------------------------------

type TronKey = { address: string; weight: number }
type TronPermission = {
  permission_name?: string
  threshold: number
  keys: Array<TronKey>
}
type TronAccount = {
  address?: string
  owner_permission?: TronPermission
  active_permission?: Array<TronPermission>
}
type TronTx = {
  raw_data: {
    contract: Array<{
      type: string
      parameter: {
        value: {
          owner_address?: string
          contract_address?: string
          data?: string
        }
      }
    }>
  }
}
type Trc20 = {
  from: string
  to: string
  value: string
  token_info: { address: string; symbol: string; decimals: number }
}
type Page<T> = { data?: Array<T>; meta?: { fingerprint?: string } }

const APPROVE = "095ea7b3"
const TRON_UNLIMITED = 2n ** 255n

async function tronPages<T>(f: Fetch, path: string, pages: number) {
  const out: Array<T> = []
  let fingerprint: string | undefined
  for (let i = 0; i < pages; i++) {
    const url = `${TRONGRID}${path}${path.includes("?") ? "&" : "?"}limit=200${fingerprint ? `&fingerprint=${fingerprint}` : ""}`
    const page = await request<Page<T>>(f, url)
    out.push(...(page?.data ?? []))
    fingerprint = page?.meta?.fingerprint
    if (!fingerprint) return { items: out, complete: true }
  }
  return { items: out, complete: false }
}

export async function scanTron(
  address: string,
  o: ScanOptions = {}
): Promise<ChainReport> {
  const f = o.fetch ?? fetch
  const ownerHex = tronHex(address)

  o.onProgress?.(0)
  const acct = await request<TronAccount>(f, `${TRONGRID}/wallet/getaccount`, {
    address,
    visible: true,
  })
  const perms: Array<ChainFinding> = []
  const activated = !!acct?.address
  if (activated) {
    const owner = acct.owner_permission
    if (owner) {
      const j = judgeKeys(
        "Owner permission",
        address,
        owner.threshold,
        owner.keys
      )
      if (j) perms.push(j)
    }
    for (const p of acct.active_permission ?? []) {
      const j = judgeKeys(
        `Active permission “${p.permission_name ?? "active"}”`,
        address,
        p.threshold,
        p.keys
      )
      if (j) perms.push(j)
    }
  }
  const permissions: ChainSection = {
    title: "Permissions",
    complete: true,
    findings: perms,
    summary: !activated
      ? "Account not activated on Tron yet: nothing to hijack."
      : perms.length
        ? "Someone other than this address appears in its permissions."
        : "Only this address's own key can sign for it.",
  }

  o.onProgress?.(1)
  const [txs, history] = await Promise.all([
    activated
      ? tronPages<TronTx>(
          f,
          `/v1/accounts/${address}/transactions?only_from=true&only_confirmed=true`,
          3
        )
      : { items: [], complete: true },
    activated
      ? tronPages<Trc20>(
          f,
          `/v1/accounts/${address}/transactions/trc20?only_confirmed=true`,
          2
        )
      : { items: [], complete: true },
  ])
  const tokens = new Map(
    history.items.map((t) => [t.token_info.address, t.token_info])
  )
  const approvals = new Map<string, { token: string; spender: string }>()
  for (const tx of txs.items) {
    const c = tx.raw_data.contract[0]
    const v = c.parameter.value
    if (
      c.type !== "TriggerSmartContract" ||
      !v.data?.startsWith(APPROVE) ||
      !v.contract_address
    )
      continue
    if (v.owner_address?.toLowerCase() !== `41${ownerHex}`) continue
    const token = tronAddress(v.contract_address)
    const spender = tronAddress(v.data.slice(8 + 24, 8 + 64))
    approvals.set(`${token}:${spender}`, { token, spender })
  }
  let unread = 0
  const live = await pool(
    [...approvals.values()].slice(0, 40),
    1,
    async ({ token, spender }) => {
      try {
        const r = await request<{ constant_result?: Array<string> }>(
          f,
          `${TRONGRID}/wallet/triggerconstantcontract`,
          {
            owner_address: address,
            contract_address: token,
            function_selector: "allowance(address,address)",
            parameter:
              ownerHex.padStart(64, "0") + tronHex(spender).padStart(64, "0"),
            visible: true,
          }
        )
        const amount = BigInt(`0x${r?.constant_result?.[0] || "0"}`)
        if (!amount) return null
        const code = await request<{ contract_address?: string }>(
          f,
          `${TRONGRID}/wallet/getcontract`,
          { value: spender, visible: true }
        )
        return { token, spender, amount, contract: !!code?.contract_address }
      } catch {
        unread++
        return null
      }
    }
  )
  const allowances: Array<ChainFinding> = live
    .filter((a) => a !== null)
    .map((a) => {
      const info = tokens.get(a.token)
      const unlimited = a.amount >= TRON_UNLIMITED
      const amount = unlimited
        ? "unlimited"
        : info
          ? `${fmt(a.amount, info.decimals)} ${info.symbol}`
          : "limited"
      const title = `${info?.symbol ?? short(a.token)} → ${short(a.spender)}`
      if (!a.contract)
        return {
          severity: "high",
          title,
          amount,
          note: "Allowance to a plain wallet, not a contract. Drainers use this. Revoke it on Tronscan.",
        }
      if (unlimited)
        return {
          severity: "medium",
          title,
          amount,
          note: "Unlimited allowance to a contract: if it is hacked, the whole balance can go. Revoke it if you no longer use it.",
        }
      return {
        severity: "low",
        title,
        amount,
        note: "Limited allowance to a contract.",
      }
    })
  const approvalSection: ChainSection = {
    title: "TRC-20 approvals",
    complete: txs.complete && approvals.size <= 40 && !unread,
    findings: allowances,
    summary: allowances.length
      ? `${plural(allowances.length, "live allowance")} out of ${plural(approvals.size, "approval")} found in ${plural(txs.items.length, "outgoing transaction")}.`
      : `No live TRC-20 allowances in ${plural(txs.items.length, "outgoing transaction")}.`,
  }

  o.onProgress?.(2)
  const moves = history.items.map((t) => ({
    from: t.from,
    to: t.to,
    value: t.value !== "0",
  }))
  const poison = poisonSection(
    moves,
    address,
    `the last ${plural(history.items.length, "TRC-20 transfer")}`,
    history.complete
  )

  const sections = [permissions, approvalSection, poison.section]
  return {
    family: "tron",
    address,
    sections,
    suspects: poison.suspects,
    complete: sections.every((s) => s.complete),
  }
}

// ---- Solana -----------------------------------------------------------------------------------

const SYSTEM = "11111111111111111111111111111111"
const TOKEN_PROGRAMS = [
  "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
  "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
]
const U64_MAX = 2n ** 64n - 1n

type TokenAccount = {
  pubkey: string
  account: {
    data: {
      parsed: {
        info: {
          mint: string
          owner: string
          state?: string
          delegate?: string
          delegatedAmount?: {
            amount: string
            decimals: number
            uiAmountString: string
          }
          closeAuthority?: string
          tokenAmount: {
            amount: string
            decimals: number
            uiAmountString: string
          }
        }
      }
    }
  }
}
type ParsedIx = {
  program?: string
  parsed?: { type?: string; info?: Record<string, unknown> }
}
type SolTx = {
  transaction: {
    message: {
      accountKeys: Array<{ pubkey: string } | string>
      instructions: Array<ParsedIx>
    }
  }
  meta: {
    postTokenBalances?: Array<{ accountIndex: number; owner?: string }>
    preTokenBalances?: Array<{ accountIndex: number; owner?: string }>
    innerInstructions?: Array<{ instructions: Array<ParsedIx> }>
  } | null
}

async function rpc<T>(
  f: Fetch,
  url: string,
  method: string,
  params: Array<unknown>
): Promise<T> {
  const r = await request<{ result?: T; error?: { message: string } }>(f, url, {
    jsonrpc: "2.0",
    id: 1,
    method,
    params,
  })
  if (!r) throw new Error(`Solana RPC has no ${method}`)
  if (r.error) throw new Error(r.error.message)
  return r.result as T
}

/** Transfers in a parsed Solana transaction, as wallet → wallet movements. */
export function solanaMoves(tx: SolTx): Array<Movement> {
  const keys = tx.transaction.message.accountKeys.map((k) =>
    typeof k === "string" ? k : k.pubkey
  )
  const ownerOf = new Map<string, string>()
  for (const b of [
    ...(tx.meta?.preTokenBalances ?? []),
    ...(tx.meta?.postTokenBalances ?? []),
  ])
    if (b.owner) ownerOf.set(keys[b.accountIndex], b.owner)
  const ixs = [
    ...tx.transaction.message.instructions,
    ...(tx.meta?.innerInstructions ?? []).flatMap((i) => i.instructions),
  ]
  const out: Array<Movement> = []
  for (const ix of ixs) {
    const type = ix.parsed?.type
    const info = ix.parsed?.info ?? {}
    if (ix.program === "system" && type === "transfer")
      out.push({
        from: String(info.source),
        to: String(info.destination),
        value: Number(info.lamports) > 0,
      })
    if (
      (ix.program === "spl-token" || ix.program === "spl-token-2022") &&
      (type === "transfer" || type === "transferChecked")
    ) {
      const from = String(
        info.authority ??
          info.multisigAuthority ??
          ownerOf.get(String(info.source)) ??
          info.source
      )
      const to =
        ownerOf.get(String(info.destination)) ?? String(info.destination)
      const amount =
        (info.tokenAmount as { amount?: string } | undefined)?.amount ??
        info.amount
      out.push({ from, to, value: String(amount ?? "0") !== "0" })
    }
  }
  return out
}

export async function scanSolana(
  address: string,
  o: ScanOptions = {}
): Promise<ChainReport> {
  const f = o.fetch ?? fetch
  const url = o.solanaRpc ?? SOLANA_RPC

  o.onProgress?.(0)
  const info = await rpc<{ value: { owner: string; lamports: number } | null }>(
    f,
    url,
    "getAccountInfo",
    [address, { encoding: "base64", dataSlice: { offset: 0, length: 0 } }]
  )
  const owner = info.value?.owner
  const ownerFindings: Array<ChainFinding> = []
  if (owner && TOKEN_PROGRAMS.includes(owner))
    ownerFindings.push({
      severity: "medium",
      title: "This is a token account, not a wallet",
      note: "Paste the wallet (owner) address instead: a token account holds one token for a wallet.",
    })
  else if (owner && owner !== SYSTEM)
    ownerFindings.push({
      severity: "high",
      title: "Account reassigned to a program",
      note: `It is owned by ${short(owner)}, not the System Program. Drainers trick wallets into signing an "assign", after which the program, not your key, decides what happens to it. Stop using it.`,
      points: 60,
    })
  const ownerSection: ChainSection = {
    title: "Account owner",
    complete: true,
    findings: ownerFindings,
    summary: !info.value
      ? "No SOL account on-chain yet (never funded)."
      : owner === SYSTEM
        ? "A plain wallet, owned by the System Program: only its key can sign."
        : "",
  }

  o.onProgress?.(1)
  const lists = await Promise.all(
    TOKEN_PROGRAMS.map((programId) =>
      rpc<{ value: Array<TokenAccount> }>(f, url, "getTokenAccountsByOwner", [
        address,
        { programId },
        { encoding: "jsonParsed" },
      ])
    )
  )
  const accounts = lists.flatMap((l) => l.value)
  const tokenFindings: Array<ChainFinding> = []
  for (const a of accounts) {
    const t = a.account.data.parsed.info
    const delegated = BigInt(t.delegatedAmount?.amount ?? "0")
    if (t.delegate && delegated > 0n) {
      const unlimited = delegated >= U64_MAX
      tokenFindings.push({
        severity: "high",
        title: `${short(t.mint)} → delegate ${short(t.delegate)}`,
        amount: unlimited
          ? "unlimited"
          : (t.delegatedAmount?.uiAmountString ?? "some"),
        note: `${short(t.delegate)} can move ${unlimited ? "all" : "this much"} of this token without asking you (balance ${t.tokenAmount.uiAmountString}). Revoke it in your wallet unless an app you trust needs it right now.`,
      })
    }
    if (t.closeAuthority && t.closeAuthority !== address)
      tokenFindings.push({
        severity: "low",
        title: `${short(t.mint)}: close authority ${short(t.closeAuthority)}`,
        note: "Someone else can close this token account once it is empty and keep its rent deposit.",
      })
    if (t.state === "frozen")
      tokenFindings.push({
        severity: "low",
        title: `${short(t.mint)}: frozen`,
        note: "The token's issuer froze this account; it cannot be moved.",
      })
  }
  const tokenSection: ChainSection = {
    title: "Token delegates",
    complete: true,
    findings: tokenFindings,
    summary: tokenFindings.length
      ? `Checked ${plural(accounts.length, "token account")}.`
      : `No delegates or foreign authorities on ${plural(accounts.length, "token account")}.`,
  }

  o.onProgress?.(2)
  const sigs = await rpc<Array<{ signature: string; err: unknown }>>(
    f,
    url,
    "getSignaturesForAddress",
    [address, { limit: 30 }]
  )
  const txs = await pool(sigs, 3, (s) =>
    rpc<SolTx | null>(f, url, "getTransaction", [
      s.signature,
      { encoding: "jsonParsed", maxSupportedTransactionVersion: 0 },
    ]).catch(() => null)
  )
  const moves = txs.flatMap((t) => (t ? solanaMoves(t) : []))
  const poison = poisonSection(
    moves,
    address,
    `the last ${plural(sigs.length, "transaction")}`,
    txs.every((t) => t !== null)
  )

  const sections = [ownerSection, tokenSection, poison.section]
  return {
    family: "solana",
    address,
    sections,
    suspects: poison.suspects,
    complete: sections.every((s) => s.complete),
  }
}

// ---- Bitcoin ----------------------------------------------------------------------------------

type Stats = { funded_txo_count: number; tx_count: number }
type BtcTx = {
  vin: Array<{
    prevout: { scriptpubkey_address?: string; value: number } | null
  }>
  vout: Array<{ scriptpubkey_address?: string; value: number }>
}

const DUST = 1000 // sats; attackers send 546–1000

export function bitcoinMoves(
  txs: Array<BtcTx>,
  owner: string
): Array<Movement> {
  const out: Array<Movement> = []
  for (const tx of txs) {
    const ins = tx.vin
      .map((v) => v.prevout?.scriptpubkey_address)
      .filter((a): a is string => !!a)
    if (ins.includes(owner)) {
      for (const o of tx.vout)
        if (o.scriptpubkey_address && o.scriptpubkey_address !== owner)
          out.push({
            from: owner,
            to: o.scriptpubkey_address,
            value: o.value > DUST,
          })
    } else {
      const got = tx.vout
        .filter((o) => o.scriptpubkey_address === owner)
        .reduce((s, o) => s + o.value, 0)
      for (const from of new Set(ins))
        out.push({ from, to: owner, value: got > 0 })
    }
  }
  return out
}

const BTC_TYPE = (a: string) =>
  a.startsWith("bc1p")
    ? "Taproot (bc1p)"
    : a.startsWith("bc1q")
      ? "Native SegWit (bc1q)"
      : a.startsWith("3")
        ? "Script hash (3…), often a multisig or wrapped SegWit"
        : "Legacy (1…): works, but pays the highest fees"

export async function scanBitcoin(
  address: string,
  o: ScanOptions = {}
): Promise<ChainReport> {
  const f = o.fetch ?? fetch

  o.onProgress?.(0)
  const a = await request<{ chain_stats: Stats; mempool_stats: Stats }>(
    f,
    `${MEMPOOL}/address/${address}`
  )
  const funded =
    (a?.chain_stats.funded_txo_count ?? 0) +
    (a?.mempool_stats.funded_txo_count ?? 0)
  const txCount =
    (a?.chain_stats.tx_count ?? 0) + (a?.mempool_stats.tx_count ?? 0)
  const reuse: Array<ChainFinding> =
    funded > 1
      ? [
          {
            severity: "low",
            title: "Address reused",
            amount: `${funded}× received`,
            note: "Every payment to the same address can be linked to you. Most wallets give a fresh receive address each time; use it.",
            points: funded > 20 ? 5 : 2,
          },
        ]
      : []
  const typeSection: ChainSection = {
    title: "Address & reuse",
    complete: !!a,
    findings: reuse,
    summary: `${BTC_TYPE(address)}. ${plural(txCount, "transaction")} on record.`,
  }

  o.onProgress?.(1)
  let utxos: Array<{ value: number }> = []
  let utxoComplete = true
  try {
    utxos =
      (await request<Array<{ value: number }>>(
        f,
        `${MEMPOOL}/address/${address}/utxo`
      )) ?? []
  } catch {
    utxoComplete = false // mempool.space refuses addresses with very many outputs
  }
  const dust = utxos.filter((u) => u.value <= DUST)
  const dustSection: ChainSection = {
    title: "Dust",
    complete: utxoComplete,
    findings: dust.length
      ? [
          {
            severity: "medium",
            title: `${plural(dust.length, "dust output")}`,
            amount: `${dust.reduce((s, u) => s + u.value, 0)} sats`,
            note: "Tiny outputs (≤1,000 sats) are sent so that spending them together with your other coins links your addresses. Freeze them with coin control instead of spending them.",
          },
        ]
      : [],
    summary: utxoComplete
      ? `${plural(utxos.length, "unspent output")}, none of them dust-sized.`
      : "Too many unspent outputs to list from the public node.",
  }
  if (dust.length)
    dustSection.summary = `${plural(utxos.length, "unspent output")} checked.`

  o.onProgress?.(2)
  const txs =
    (await request<Array<BtcTx>>(f, `${MEMPOOL}/address/${address}/txs`)) ?? []
  const poison = poisonSection(
    bitcoinMoves(txs, address),
    address,
    `the last ${plural(txs.length, "transaction")}`,
    true
  )

  const sections = [typeSection, dustSection, poison.section]
  return {
    family: "bitcoin",
    address,
    sections,
    suspects: poison.suspects,
    complete: sections.every((s) => s.complete),
  }
}

// ---- Stellar ----------------------------------------------------------------------------------

type StellarAccount = {
  signers: Array<{ key: string; weight: number; type: string }>
  thresholds: {
    low_threshold: number
    med_threshold: number
    high_threshold: number
  }
  balances: Array<{
    asset_type: string
    asset_code?: string
    asset_issuer?: string
  }>
}
type Payment = {
  type: string
  from?: string
  to?: string
  funder?: string
  account?: string
  amount?: string
  starting_balance?: string
}

export async function scanStellar(
  address: string,
  o: ScanOptions = {}
): Promise<ChainReport> {
  const f = o.fetch ?? fetch

  o.onProgress?.(0)
  const acct = await request<StellarAccount>(
    f,
    `${HORIZON}/accounts/${address}`
  )
  const signerFindings: Array<ChainFinding> = []
  if (acct) {
    const keys = acct.signers.map((s) => ({ address: s.key, weight: s.weight }))
    const j = judgeKeys(
      "Signers",
      address,
      acct.thresholds.high_threshold,
      keys
    )
    if (j) signerFindings.push(j)
  }
  const signerSection: ChainSection = {
    title: "Signers",
    complete: true,
    findings: signerFindings,
    summary: !acct
      ? "Account not funded on Stellar yet: nothing to take over."
      : signerFindings.length
        ? ""
        : "Only this account's own key can sign for it.",
  }

  o.onProgress?.(1)
  const claims = acct
    ? await request<{ _embedded: { records: Array<unknown> } }>(
        f,
        `${HORIZON}/claimable_balances?claimant=${address}&limit=50`
      )
    : null
  const pending = claims?._embedded.records.length ?? 0
  const trust =
    acct?.balances.filter((b) => b.asset_type !== "native").length ?? 0
  const assetSection: ChainSection = {
    title: "Assets & claims",
    complete: true,
    findings: pending
      ? [
          {
            severity: "low",
            title: `${plural(pending, "unclaimed airdrop")}`,
            note: "Unsolicited claimable balances are a common scam lure. Don't claim assets you don't know, and never follow links in their memos.",
            points: 2,
          },
        ]
      : [],
    summary: `${plural(trust, "trustline")} besides XLM.`,
  }

  o.onProgress?.(2)
  const payments = acct
    ? await request<{ _embedded: { records: Array<Payment> } }>(
        f,
        `${HORIZON}/accounts/${address}/payments?order=desc&limit=100`
      )
    : null
  const moves: Array<Movement> = (payments?._embedded.records ?? []).flatMap(
    (p) => {
      if (p.type === "create_account")
        return [
          {
            from: p.funder!,
            to: p.account!,
            value: Number(p.starting_balance) > 0,
          },
        ]
      if (p.from && p.to)
        return [
          { from: p.from, to: p.to, value: Number(p.amount ?? 0) > 0.0001 },
        ]
      return []
    }
  )
  const poison = poisonSection(
    moves,
    address,
    `the last ${plural(moves.length, "payment")}`,
    true
  )

  const sections = [signerSection, assetSection, poison.section]
  return {
    family: "stellar",
    address,
    sections,
    suspects: poison.suspects,
    complete: sections.every((s) => s.complete),
  }
}

export function scanChain(
  family: NonEvm,
  address: string,
  o: ScanOptions = {}
): Promise<ChainReport> {
  return {
    tron: scanTron,
    solana: scanSolana,
    bitcoin: scanBitcoin,
    stellar: scanStellar,
  }[family](address, o)
}

// ---- score ------------------------------------------------------------------------------------

const DEFAULT_POINTS: Record<Severity, number> = { high: 20, medium: 8, low: 1 }

/** Same scale and grades as the EVM score (score.ts), from the chain's own findings. */
export function chainScore(r: ChainReport): Score {
  const items: Array<ScoreItem> = []
  // plain low notes (close authorities, frozen spam tokens) are counted, not listed one by one:
  // like the EVM score, only more than five cost anything, and at most 5 points
  let notes = 0
  for (const s of r.sections)
    for (const fd of s.findings) {
      if (s.title === "Poisoning") continue
      if (fd.severity === "low" && fd.points == null) {
        notes++
        continue
      }
      items.push({
        delta: -(fd.points ?? DEFAULT_POINTS[fd.severity]),
        text: fd.title,
      })
    }
  if (notes > 5)
    items.push({
      delta: -Math.min(notes - 5, 5),
      text: `${plural(notes, "low-risk note")}: clean up the ones you no longer need`,
    })
  if (r.suspects.length)
    items.push({
      delta: -5,
      text: `Targeted by address poisoning (${plural(r.suspects.length, "look-alike address")} in your history)`,
    })
  if (!r.complete)
    items.push({
      delta: 0,
      text: "Part of the history could not be read: score is provisional",
    })
  const score = Math.max(0, 100 + items.reduce((s, i) => s + i.delta, 0))
  const grade =
    score >= 90
      ? "A"
      : score >= 75
        ? "B"
        : score >= 60
          ? "C"
          : score >= 40
            ? "D"
            : "F"
  return { score, grade, items, provisional: !r.complete, usdAtRisk: 0 }
}
