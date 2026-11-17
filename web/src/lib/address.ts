import { getAddress, isAddress, zeroAddress } from "viem"
import type { Address } from "viem"
import { labelOf } from "./spenders"
import type { Severity } from "./scan"

// Address poisoning: an attacker generates an address with the same first and last characters as
// one you use, then plants it in your history (a zero-value transferFrom of a real token, dust, or a
// fake token). Wallets show addresses as 0x1234…abcd, so copying "the last address" sends to them.

/** Same first and last `n` hex characters, different address. */
export function lookalike(a: string, b: string, n = 4): boolean {
  const x = a.toLowerCase().replace(/^0x/, "")
  const y = b.toLowerCase().replace(/^0x/, "")
  return (
    x !== y &&
    x.length === 40 &&
    y.length === 40 &&
    x.slice(0, n) === y.slice(0, n) &&
    x.slice(-n) === y.slice(-n)
  )
}

export type Transfer = {
  token: Address
  from: Address
  to: Address
  value: bigint
}

export type Suspect = {
  address: Address
  /** The address it imitates: one you really sent to. */
  imitates: Address
  /** Transfers that planted it in your history. */
  planted: number
  /** Zero-value transfers "from you" that you never made: the classic poisoning trick. */
  zeroValue: number
}

export type Poisoning = {
  /** Addresses you sent real value to: the ones worth imitating. */
  counterparties: Array<Address>
  suspects: Array<Suspect>
}

const eq = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

export function findPoisoning(
  transfers: Array<Transfer>,
  owner: string
): Poisoning {
  // How many real (non-zero) sends the owner made to each address.
  const sends = new Map<string, number>()
  for (const t of transfers)
    if (eq(t.from, owner) && t.value > 0n && !eq(t.to, owner))
      sends.set(getAddress(t.to), (sends.get(getAddress(t.to)) ?? 0) + 1)

  const touched = new Map<string, { planted: number; zeroValue: number }>()
  for (const t of transfers) {
    const outgoing = eq(t.from, owner)
    const other = getAddress(outgoing ? t.to : t.from)
    if (eq(other, owner)) continue
    const s = touched.get(other) ?? { planted: 0, zeroValue: 0 }
    s.planted++
    if (outgoing && t.value === 0n) s.zeroValue++
    touched.set(other, s)
  }

  const counterparties = [...sends.keys()] as Array<Address>
  const suspects: Array<Suspect> = []
  for (const [address, s] of touched) {
    // The imitated address is the one with the most real sends; a poisoner can fake an outgoing
    // transfer with a fake token, but rarely outnumbers your own history with the real one.
    const target = counterparties
      .filter((c) => lookalike(c, address))
      .sort((a, b) => sends.get(b)! - sends.get(a)!)
      .at(0)
    if (!target) continue
    if ((sends.get(address) ?? 0) > sends.get(target)!) continue
    suspects.push({
      address: address as Address,
      imitates: target,
      planted: s.planted,
      zeroValue: s.zeroValue,
    })
  }
  return { counterparties, suspects }
}

export type AddressCheck = {
  valid: boolean
  address?: Address
  severity: Severity | "ok"
  notes: Array<string>
}

const BURN = new Set([
  zeroAddress,
  "0x000000000000000000000000000000000000dead",
  "0xdead000000000000000042069420694206942069",
])

/**
 * Offline checks for an address you are about to send to. On-chain facts (contract? token?)
 * are added by the caller, which has a client.
 */
export function checkAddress(
  input: string,
  {
    owner,
    counterparties = [],
    suspects = [],
    chainId,
  }: {
    owner?: string | null
    counterparties?: Array<string>
    suspects?: Array<Suspect>
    chainId?: number | null
  } = {}
): AddressCheck {
  const s = input.trim()
  if (!/^0x[0-9a-fA-F]{40}$/.test(s))
    return {
      valid: false,
      severity: "high",
      notes: [
        s.length && /^0x[0-9a-fA-F]*$/.test(s)
          ? `An address has 40 hex characters after 0x; this has ${s.length - 2}. Characters went missing when copying.`
          : "Not an EVM address (0x followed by 40 hex characters).",
      ],
    }
  const notes: Array<string> = []
  let severity = "ok" as AddressCheck["severity"]
  const bump = (to: Severity) => {
    const rank = { ok: 0, low: 1, medium: 2, high: 3 }
    if (rank[to] > rank[severity]) severity = to
  }
  const mixed = /[a-f]/.test(s) && /[A-F]/.test(s)
  if (mixed && !isAddress(s, { strict: true })) {
    bump("high")
    notes.push(
      "The checksum (the pattern of capital letters) is wrong: a character was changed. Do not send."
    )
  }
  const address = getAddress(s)
  if (BURN.has(address.toLowerCase())) {
    bump("high")
    notes.push("This is a burn address. Anything sent here is gone for good.")
  }
  if (owner && eq(owner, address)) notes.push("This is your own address.")

  const suspect = suspects.find((x) => eq(x.address, address))
  if (suspect) {
    bump("high")
    notes.push(
      `Poisoned address: it was planted in your history to imitate ${suspect.imitates}. Do not send.`
    )
  }
  const twin = counterparties.find((c) => lookalike(c, address))
  if (twin && !counterparties.some((c) => eq(c, address))) {
    bump("high")
    notes.push(
      `Looks like ${twin}, an address you have sent to, but it is a different address. Classic address poisoning.`
    )
  }
  if (counterparties.some((c) => eq(c, address)) && !suspect)
    notes.push("You have sent tokens to this exact address before.")

  const label = labelOf(address, chainId)
  if (label) {
    bump("medium")
    notes.push(
      `This is ${label.name}, a contract. Sending tokens straight to it usually loses them.`
    )
  }
  if (notes.length === 0)
    notes.push(
      "Nothing wrong offline. Compare every character with the source, not just the start and end."
    )
  return { valid: true, address, severity, notes }
}
