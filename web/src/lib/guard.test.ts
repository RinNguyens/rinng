import { readdirSync, readFileSync } from "node:fs"
import { join, relative } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it, vi } from "vitest"
import {
  ALLOWED_METHODS,
  guardProvider,
  isGuarded,
  lockInjectedProvider,
} from "./guard"
import type { Eip1193 } from "./guard"

const fakeProvider = () => {
  const request = vi.fn(
    async ({ method }: { method: string }) => `ok:${method}`
  )
  return { request, on: vi.fn(), removeListener: vi.fn() } satisfies Eip1193
}

const SIGN_OR_SEND = [
  "eth_sign",
  "personal_sign",
  "eth_signTypedData",
  "eth_signTypedData_v3",
  "eth_signTypedData_v4",
  "eth_sendTransaction",
  "eth_sendRawTransaction",
  "eth_signTransaction",
  "wallet_sendCalls",
  "wallet_grantPermissions",
  "wallet_switchEthereumChain",
  "wallet_addEthereumChain",
  "wallet_watchAsset",
  "eth_sendUserOperation",
]

describe("guardProvider", () => {
  it("forwards read-only methods to the wallet", async () => {
    const raw = fakeProvider()
    const g = guardProvider(raw)
    for (const method of ALLOWED_METHODS) {
      await expect(g.request({ method })).resolves.toBe(`ok:${method}`)
    }
    expect(raw.request).toHaveBeenCalledTimes(ALLOWED_METHODS.size)
  })

  it.each(SIGN_OR_SEND)(
    "blocks %s before it reaches the wallet",
    async (method) => {
      const raw = fakeProvider()
      const onBlock = vi.fn()
      const g = guardProvider(raw, onBlock)
      await expect(
        g.request({ method, params: ["0xdead"] })
      ).rejects.toMatchObject({ code: 4100 })
      expect(raw.request).not.toHaveBeenCalled()
      expect(onBlock).toHaveBeenCalledWith(expect.objectContaining({ method }))
    }
  )

  it("blocks methods it has never heard of (allowlist, not denylist)", async () => {
    const raw = fakeProvider()
    const g = guardProvider(raw)
    await expect(
      g.request({ method: "eth_signSomethingNew" })
    ).rejects.toMatchObject({ code: 4100 })
    await expect(g.request({ method: "ETH_CALL" })).rejects.toMatchObject({
      code: 4100,
    })
    expect(raw.request).not.toHaveBeenCalled()
  })

  it("is idempotent and exposes no way back to the raw provider", () => {
    const raw = fakeProvider()
    const g = guardProvider(raw)
    expect(guardProvider(g)).toBe(g)
    expect(isGuarded(g)).toBe(true)
    expect(isGuarded(raw)).toBe(false)
    expect(Object.values(g)).not.toContain(raw)
    expect(Object.isFrozen(g)).toBe(true)
  })

  it("passes event subscriptions through", () => {
    const raw = fakeProvider()
    const g = guardProvider(raw)
    const f = () => {}
    g.on?.("accountsChanged", f)
    g.removeListener?.("accountsChanged", f)
    expect(raw.on).toHaveBeenCalledWith("accountsChanged", f)
    expect(raw.removeListener).toHaveBeenCalledWith("accountsChanged", f)
  })
})

describe("lockInjectedProvider", () => {
  it("reports absent when no wallet is injected", () => {
    expect(lockInjectedProvider({}).status).toBe("absent")
  })

  it("replaces window.ethereum with a guarded, non-writable provider", async () => {
    const raw = fakeProvider()
    const g: { ethereum?: unknown } = { ethereum: raw }
    const res = lockInjectedProvider(g)
    expect(res.status).toBe("locked")
    expect(isGuarded(g.ethereum as Eip1193)).toBe(true)
    expect(() => {
      g.ethereum = raw
    }).toThrow()
    await expect(
      (g.ethereum as Eip1193).request({ method: "personal_sign" })
    ).rejects.toMatchObject({
      code: 4100,
    })
  })

  it("falls back to wrapped-only when the wallet made the property non-configurable", () => {
    const raw = fakeProvider()
    const g = {}
    Object.defineProperty(g, "ethereum", {
      value: raw,
      configurable: false,
      writable: false,
    })
    const res = lockInjectedProvider(g)
    expect(res.status).toBe("wrapped")
    expect(isGuarded(res.provider!)).toBe(true)
  })
})

// Source sweep: no code under web/src may ask a wallet for a method outside the allowlist.
const methodsIn = (source: string): Array<string> =>
  [...source.matchAll(/\bmethod\s*:\s*["'`]([^"'`]+)["'`]/g)].map((m) => m[1])

const SRC = fileURLToPath(new URL("..", import.meta.url))

const sourceFiles = (dir: string): Array<string> =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name)
    if (e.isDirectory()) return e.name === "node_modules" ? [] : sourceFiles(p)
    return /\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name) ? [p] : []
  })

describe("allowlist sweep", () => {
  it("the sweep catches a method outside the allowlist in a sample source", () => {
    const sample = `await p.request({ method: "eth_chainId" })\nawait p.request({ method: "eth_sendTransaction", params: [tx] })`
    const found = methodsIn(sample)
    expect(found).toEqual(["eth_chainId", "eth_sendTransaction"])
    expect(found.filter((m) => !ALLOWED_METHODS.has(m))).toEqual(["eth_sendTransaction"])
  })

  it("no source file asks the wallet for a method outside the allowlist", () => {
    const files = sourceFiles(SRC).filter((f) => relative(SRC, f) !== join("lib", "guard.ts"))
    expect(files.length).toBeGreaterThan(10)
    const offenders: Array<string> = []
    let seen = 0
    for (const f of files) {
      for (const m of methodsIn(readFileSync(f, "utf8"))) {
        seen++
        if (!ALLOWED_METHODS.has(m)) offenders.push(`${relative(SRC, f)}: ${m}`)
      }
    }
    expect(seen).toBeGreaterThan(0)
    expect(offenders).toEqual([])
  })
})
