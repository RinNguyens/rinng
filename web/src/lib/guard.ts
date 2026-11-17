// Signature lock. rinng is read-only: it must never be able to ask the wallet to sign, send,
// delegate (EIP-7702), batch calls or switch chains. Every request goes through an ALLOWLIST of
// read methods; anything else, including methods invented after this file was written, is
// rejected with EIP-1193 code 4100 before it reaches the wallet.
//
// Scope, honestly: this covers rinng's own code and every script that reaches the wallet through
// window.ethereum. It is not a sandbox. A script could still find the raw provider through EIP-6963
// announcements, and the wallet's own confirmation screen remains the last line of defence.

export type Eip1193 = {
  request: (a: {
    method: string
    params?: ReadonlyArray<unknown> | object
  }) => Promise<unknown>
  on?: (e: string, f: (...a: Array<any>) => void) => void
  removeListener?: (e: string, f: (...a: Array<any>) => void) => void
}

export const ALLOWED_METHODS: ReadonlySet<string> = new Set([
  "eth_accounts",
  "eth_requestAccounts", // shows the address; grants no spending power
  "eth_chainId",
  "net_version",
  "eth_blockNumber",
  "eth_getBalance",
  "eth_getCode",
  "eth_getStorageAt",
  "eth_getBlockByNumber",
  "eth_getLogs",
  "eth_call", // executes nothing on-chain
])

export type BlockedRequest = { method: string; at: number }

const GUARDED = Symbol.for("rinng.guarded")

export const isGuarded = (p: Eip1193): boolean =>
  (p as { [GUARDED]?: true })[GUARDED] === true

export function guardProvider(
  raw: Eip1193,
  onBlock?: (b: BlockedRequest) => void
): Eip1193 {
  if (isGuarded(raw)) return raw
  const request: Eip1193["request"] = (a) => {
    if (!ALLOWED_METHODS.has(a.method)) {
      onBlock?.({ method: a.method, at: Date.now() })
      const err = Object.assign(
        new Error(`rinng is read-only: "${a.method}" blocked`),
        { code: 4100 }
      )
      return Promise.reject(err)
    }
    return raw.request(a)
  }
  // The raw provider lives only in these closures, never as a property.
  return Object.freeze({
    [GUARDED]: true as const,
    request,
    on: (e: string, f: (...a: Array<any>) => void) => raw.on?.(e, f),
    removeListener: (e: string, f: (...a: Array<any>) => void) =>
      raw.removeListener?.(e, f),
  })
}

export type LockResult =
  | { status: "absent"; provider: null }
  // window.ethereum itself now points at the guard and cannot be reassigned.
  | { status: "locked"; provider: Eip1193 }
  // The wallet pinned window.ethereum; rinng's own calls are guarded, other scripts are not.
  | { status: "wrapped"; provider: Eip1193 }

export function lockInjectedProvider(
  g: object = globalThis,
  onBlock?: (b: BlockedRequest) => void
): LockResult {
  const raw = (g as { ethereum?: Eip1193 }).ethereum
  if (!raw || typeof raw.request !== "function")
    return { status: "absent", provider: null }
  const provider = guardProvider(raw, onBlock)
  try {
    Object.defineProperty(g, "ethereum", {
      value: provider,
      writable: false,
      configurable: false,
      enumerable: true,
    })
    return { status: "locked", provider }
  } catch {
    return { status: "wrapped", provider }
  }
}

// One lock per page, shared by every hook. Blocked attempts are kept so the UI can show them.
// A new array on every block, so useSyncExternalStore sees the change.
let blocked: ReadonlyArray<BlockedRequest> = []
const listeners = new Set<() => void>()
let lock: LockResult | null = null

export function pageLock(): LockResult {
  // Retry while absent: some wallets inject after the first render.
  if (!lock || lock.status === "absent") {
    lock = lockInjectedProvider(globalThis, (b) => {
      blocked = [b, ...blocked].slice(0, 50)
      listeners.forEach((f) => f())
    })
  }
  return lock
}

export const blockedRequests = (): ReadonlyArray<BlockedRequest> => blocked

export function onBlocked(f: () => void): () => void {
  listeners.add(f)
  return () => listeners.delete(f)
}
