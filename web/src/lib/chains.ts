import { isAddress, sha256 } from "viem"

// Which chain an address belongs to, checked down to its checksum, so a pasted address is never
// scanned on the wrong chain and a mistyped one is caught before any request. Multichain wallets
// (MetaMask, Phantom, Trust, OKX...) now hand out one address per family: an EVM 0x address, a
// Bitcoin bc1/1/3 address, a Solana base58 key, a Tron T address and a Stellar G key.

export type Family = "evm" | "tron" | "solana" | "bitcoin" | "stellar"

export type Network = {
  key: string
  family: Family
  name: string
  /** EVM only. */
  chainId?: number
  /** EVM only: the public dRPC node the scan reads through. */
  rpc?: string
  /** Where the user can see (and, for EVM, revoke) what the scan found. */
  explorer: { name: string; url: (address: string) => string }
}

const revoke = (chainId: number) => ({
  name: "revoke.cash",
  url: (a: string) => `https://revoke.cash/address/${a}?chainId=${chainId}`,
})

export const NETWORKS: ReadonlyArray<Network> = [
  {
    key: "eth",
    family: "evm",
    name: "Ethereum",
    chainId: 1,
    rpc: "https://eth.drpc.org",
    explorer: revoke(1),
  },
  {
    key: "base",
    family: "evm",
    name: "Base",
    chainId: 8453,
    rpc: "https://base.drpc.org",
    explorer: revoke(8453),
  },
  {
    key: "arb",
    family: "evm",
    name: "Arbitrum",
    chainId: 42161,
    rpc: "https://arbitrum.drpc.org",
    explorer: revoke(42161),
  },
  {
    key: "bsc",
    family: "evm",
    name: "BNB Chain",
    chainId: 56,
    rpc: "https://bsc.drpc.org",
    explorer: revoke(56),
  },
  {
    key: "op",
    family: "evm",
    name: "Optimism",
    chainId: 10,
    rpc: "https://optimism.drpc.org",
    explorer: revoke(10),
  },
  {
    key: "polygon",
    family: "evm",
    name: "Polygon",
    chainId: 137,
    rpc: "https://polygon.drpc.org",
    explorer: revoke(137),
  },
  {
    key: "tron",
    family: "tron",
    name: "Tron",
    explorer: {
      name: "Tronscan",
      url: (a) => `https://tronscan.org/#/address/${a}`,
    },
  },
  {
    key: "solana",
    family: "solana",
    name: "Solana",
    explorer: {
      name: "Solscan",
      url: (a) => `https://solscan.io/account/${a}`,
    },
  },
  {
    key: "bitcoin",
    family: "bitcoin",
    name: "Bitcoin",
    explorer: {
      name: "mempool.space",
      url: (a) => `https://mempool.space/address/${a}`,
    },
  },
  {
    key: "stellar",
    family: "stellar",
    name: "Stellar",
    explorer: {
      name: "StellarExpert",
      url: (a) => `https://stellar.expert/explorer/public/account/${a}`,
    },
  },
]

export const networkOf = (key: string): Network =>
  NETWORKS.find((n) => n.key === key) ?? NETWORKS[0]

/** The network to scan on when an address of `family` is pasted while `current` is selected. */
export function networkFor(family: Family, current: string): string {
  if (networkOf(current).family === family) return current
  return NETWORKS.find((n) => n.family === family)!.key
}

// ---- encodings ------------------------------------------------------------------------------

const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

export function base58Decode(s: string): Uint8Array | null {
  if (!s) return null
  let n = 0n
  for (const c of s) {
    const i = B58.indexOf(c)
    if (i < 0) return null
    n = n * 58n + BigInt(i)
  }
  const out: Array<number> = []
  while (n > 0n) {
    out.unshift(Number(n & 255n))
    n >>= 8n
  }
  for (const c of s) {
    if (c !== "1") break
    out.unshift(0)
  }
  return Uint8Array.from(out)
}

export function base58Encode(bytes: Uint8Array): string {
  let n = 0n
  for (const b of bytes) n = n * 256n + BigInt(b)
  let s = ""
  while (n > 0n) {
    s = B58[Number(n % 58n)] + s
    n /= 58n
  }
  for (const b of bytes) {
    if (b !== 0) break
    s = `1${s}`
  }
  return s
}

const doubleSha = (b: Uint8Array) => sha256(sha256(b, "bytes"), "bytes")

/** Payload of a base58check string (version byte included), or null when the checksum fails. */
export function base58Check(s: string): Uint8Array | null {
  const raw = base58Decode(s)
  if (!raw || raw.length < 5) return null
  const payload = raw.slice(0, -4)
  const sum = doubleSha(payload)
  return raw.slice(-4).every((b, i) => b === sum[i]) ? payload : null
}

const hexBytes = (hex: string) =>
  Uint8Array.from(hex.match(/../g)!.map((h) => parseInt(h, 16)))

/** Tron's hex form (41 ‖ 20 bytes, or the bare 20 bytes) to its T… address. */
export function tronAddress(hex: string): string {
  const h = hex.replace(/^0x/, "").toLowerCase()
  const payload = hexBytes(h.length === 40 ? `41${h}` : h)
  return base58Encode(
    Uint8Array.from([...payload, ...doubleSha(payload).slice(0, 4)])
  )
}

/** The 20-byte hex body of a T… address (no 41 prefix, no 0x). */
export function tronHex(address: string): string {
  const p = base58Check(address)
  if (!p) throw new Error(`Not a Tron address: ${address}`)
  return [...p.slice(1)].map((b) => b.toString(16).padStart(2, "0")).join("")
}

const BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]

function polymod(values: Array<number>): number {
  let chk = 1
  for (const v of values) {
    const top = chk >>> 25
    chk = (((chk & 0x1ffffff) << 5) ^ v) >>> 0
    for (let i = 0; i < 5; i++) if ((top >>> i) & 1) chk = (chk ^ GEN[i]) >>> 0
  }
  return chk
}

/** Segwit address check (BIP-173 for v0, BIP-350 bech32m for v1+). */
function segwit(s: string): boolean {
  if (s !== s.toLowerCase() && s !== s.toUpperCase()) return false
  const a = s.toLowerCase()
  const pos = a.lastIndexOf("1")
  if (pos < 1 || a.length > 90) return false
  const hrp = a.slice(0, pos)
  if (hrp !== "bc") return false
  const data = [...a.slice(pos + 1)].map((c) => BECH32.indexOf(c))
  if (data.length < 7 || data.some((d) => d < 0)) return false
  const expand = [...hrp]
    .map((c) => c.charCodeAt(0) >> 5)
    .concat(
      0,
      [...hrp].map((c) => c.charCodeAt(0) & 31)
    )
  const check = polymod(expand.concat(data))
  const version = data[0]
  if (version > 16) return false
  if (check !== (version === 0 ? 1 : 0x2bc830a3)) return false
  const bytes = Math.floor(((data.length - 7) * 5) / 8)
  if (bytes < 2 || bytes > 40) return false
  return version !== 0 || bytes === 20 || bytes === 32
}

const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

function crc16xmodem(bytes: Uint8Array): number {
  let crc = 0
  for (const b of bytes) {
    crc ^= b << 8
    for (let i = 0; i < 8; i++)
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff
  }
  return crc
}

/** Stellar StrKey account id (G…, 56 chars, version byte 6 << 3, CRC16-XModem). */
function stellarKey(s: string): boolean {
  if (!/^G[A-Z2-7]{55}$/.test(s)) return false
  let bits = 0
  let value = 0
  const out: Array<number> = []
  for (const c of s) {
    value = (value << 5) | B32.indexOf(c)
    bits += 5
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 255)
      bits -= 8
    }
  }
  if (out.length !== 35 || out[0] !== 6 << 3) return false
  const crc = crc16xmodem(Uint8Array.from(out.slice(0, 33)))
  return out[33] === (crc & 255) && out[34] === crc >>> 8
}

// ---- detection ------------------------------------------------------------------------------

export type Detected =
  | { ok: true; family: Family; address: string }
  | { ok: false; family?: Family; reason: string }

/** Which chain `input` is an address on, with its checksum verified. */
export function detectAddress(input: string): Detected {
  const s = input.trim()
  if (!s) return { ok: false, reason: "Paste a wallet address to check." }

  if (/^0x/i.test(s)) {
    if (!/^0x[0-9a-fA-F]{40}$/.test(s))
      return {
        ok: false,
        family: "evm",
        reason: /^0x[0-9a-fA-F]*$/.test(s)
          ? `An EVM address has 40 hex characters after 0x; this has ${s.length - 2}. Characters went missing when copying.`
          : "Not an EVM address: 0x and 40 hex characters.",
      }
    return isAddress(s, { strict: true })
      ? { ok: true, family: "evm", address: s }
      : {
          ok: false,
          family: "evm",
          reason:
            "The checksum (the pattern of capital letters) is wrong: a character was changed.",
        }
  }

  if (/^bc1/i.test(s))
    return segwit(s)
      ? { ok: true, family: "bitcoin", address: s.toLowerCase() }
      : {
          ok: false,
          family: "bitcoin",
          reason:
            "Looks like a Bitcoin address, but its checksum fails: a character was changed or lost.",
        }

  if (/^G[A-Z2-7]+$/.test(s) && s.length >= 50)
    return stellarKey(s)
      ? { ok: true, family: "stellar", address: s }
      : {
          ok: false,
          family: "stellar",
          reason:
            "Looks like a Stellar address (G… and 56 characters), but its checksum fails.",
        }
  if (/^M[A-Z2-7]{68}$/.test(s))
    return {
      ok: false,
      family: "stellar",
      reason:
        "This is a muxed Stellar address (M…). Paste the account's G… address instead.",
    }

  const raw = base58Decode(s)
  if (raw) {
    if (s[0] === "T" && s.length === 34 && raw.length === 25) {
      const p = base58Check(s)
      return p && p.length === 21 && p[0] === 0x41
        ? { ok: true, family: "tron", address: s }
        : {
            ok: false,
            family: "tron",
            reason:
              "Looks like a Tron address, but its checksum fails: a character was changed.",
          }
    }
    if (
      (s[0] === "1" || s[0] === "3") &&
      s.length >= 26 &&
      s.length <= 35 &&
      raw.length === 25
    ) {
      const p = base58Check(s)
      return p && (p[0] === 0x00 || p[0] === 0x05)
        ? { ok: true, family: "bitcoin", address: s }
        : {
            ok: false,
            family: "bitcoin",
            reason:
              "Looks like a Bitcoin address, but its checksum fails: a character was changed.",
          }
    }
    if (raw.length === 32 && s.length >= 32 && s.length <= 44)
      return { ok: true, family: "solana", address: s }
  }

  return {
    ok: false,
    reason:
      "Not an address rinng knows: EVM 0x…, Bitcoin bc1…/1…/3…, Solana, Tron T… or Stellar G….",
  }
}

// ---- address poisoning, any chain ---------------------------------------------------------------

const PREFIX = /^(0x|bc1q|bc1p|bc1|T|G|1|3)/i

/** Same first and last `n` characters after the chain prefix, different address. */
export function lookalike(a: string, b: string, n = 4): boolean {
  const evm = /^0x/i.test(a)
  const x = (evm ? a.toLowerCase() : a).replace(PREFIX, "")
  const y = (evm ? b.toLowerCase() : b).replace(PREFIX, "")
  return (
    x !== y &&
    x.length === y.length &&
    x.length > 2 * n &&
    x.slice(0, n) === y.slice(0, n) &&
    x.slice(-n) === y.slice(-n)
  )
}

export type Movement = {
  from: string
  to: string
  /** false for zero-value transfers */ value: boolean
}
export type Lookalike = {
  address: string
  imitates: string
  planted: number
  zeroValue: number
}

/**
 * Address poisoning on any chain: an address that copies the start and end of one you really
 * paid, planted in your history by dust, zero-value or fake-token transfers.
 */
export function poisoning(
  moves: Array<Movement>,
  owner: string
): { counterparties: number; suspects: Array<Lookalike> } {
  const sends = new Map<string, number>()
  for (const m of moves)
    if (m.from === owner && m.to !== owner && m.value)
      sends.set(m.to, (sends.get(m.to) ?? 0) + 1)
  const touched = new Map<string, { planted: number; zeroValue: number }>()
  for (const m of moves) {
    const out = m.from === owner
    const other = out ? m.to : m.from
    if (other === owner) continue
    const t = touched.get(other) ?? { planted: 0, zeroValue: 0 }
    t.planted++
    if (out && !m.value) t.zeroValue++
    touched.set(other, t)
  }
  const suspects: Array<Lookalike> = []
  for (const [address, t] of touched) {
    const target = [...sends.keys()]
      .filter((c) => lookalike(c, address))
      .sort((a, b) => sends.get(b)! - sends.get(a)!)
      .at(0)
    if (!target || (sends.get(address) ?? 0) > sends.get(target)!) continue
    suspects.push({ address, imitates: target, ...t })
  }
  return { counterparties: sends.size, suspects }
}
