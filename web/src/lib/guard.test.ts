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
