import { describe, expect, it } from "vitest"
import { checkAddress, findPoisoning, lookalike } from "./address"
import type { Transfer } from "./address"

const OWNER = "0x1111111111111111111111111111111111111111"
const FRIEND = "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B" // checksummed
const POISON = "0xab58aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaec9b"
const TOKEN = "0x2222222222222222222222222222222222222222"

const t = (from: string, to: string, value: bigint): Transfer =>
  ({ token: TOKEN, from, to, value }) as Transfer

describe("lookalike", () => {
  it("matches same first and last four hex characters of different addresses", () => {
    expect(lookalike(FRIEND, POISON)).toBe(true)
    expect(lookalike(FRIEND, FRIEND.toLowerCase())).toBe(false)
    expect(lookalike(FRIEND, OWNER)).toBe(false)
  })
})

describe("findPoisoning", () => {
  it("flags a zero-value transfer to a look-alike of an address you really paid", () => {
    const p = findPoisoning(
      [t(OWNER, FRIEND, 100n), t(OWNER, FRIEND, 5n), t(OWNER, POISON, 0n)],
      OWNER
    )
    expect(p.counterparties).toEqual([FRIEND])
    expect(p.suspects).toHaveLength(1)
    expect(p.suspects[0]).toMatchObject({ imitates: FRIEND, zeroValue: 1 })
    expect(p.suspects[0].address.toLowerCase()).toBe(POISON)
  })

  it("flags dust sent to you from a look-alike", () => {
    const p = findPoisoning(
      [t(OWNER, FRIEND, 100n), t(POISON, OWNER, 1n)],
      OWNER
    )
    expect(p.suspects.map((s) => s.zeroValue)).toEqual([0])
  })

  it("keeps the address you used more as the real one when a fake token faked a send", () => {
    const p = findPoisoning(
      [t(OWNER, FRIEND, 1n), t(OWNER, FRIEND, 1n), t(OWNER, POISON, 9n)],
      OWNER
    )
    expect(p.suspects.map((s) => s.address.toLowerCase())).toEqual([POISON])
  })

  it("reports nothing for an ordinary history", () => {
    expect(findPoisoning([t(OWNER, FRIEND, 1n)], OWNER).suspects).toEqual([])
  })
})

describe("checkAddress", () => {
  it("rejects truncated addresses and bad checksums", () => {
    expect(checkAddress("0xab58").valid).toBe(false)
    const bad = checkAddress(
      FRIEND.replace("Ab58", "ab58").replace("8bE1", "8BE1")
    )
    expect(bad.severity).toBe("high")
    expect(bad.notes.join()).toMatch(/checksum/)
  })

  it("warns about a look-alike of an address you have paid", () => {
    const r = checkAddress(POISON, { counterparties: [FRIEND] })
    expect(r.severity).toBe("high")
    expect(r.notes.join()).toMatch(/poisoning/)
  })

  it("recognises an address you have paid before", () => {
    const r = checkAddress(FRIEND, { counterparties: [FRIEND] })
    expect(r.severity).toBe("ok")
    expect(r.notes.join()).toMatch(/sent tokens to this exact address/)
  })

  it("warns that a burn address or a known contract swallows funds", () => {
    expect(
      checkAddress("0x000000000000000000000000000000000000dEaD").severity
    ).toBe("high")
    expect(
      checkAddress("0x000000000022D473030F116dDEE9F6B43aC78BA3", { chainId: 1 })
        .severity
    ).toBe("medium")
  })
})
