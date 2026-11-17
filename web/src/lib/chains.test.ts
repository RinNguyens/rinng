import { describe, expect, it } from "vitest"
import {
  detectAddress,
  lookalike,
  networkFor,
  poisoning,
  tronAddress,
  tronHex,
} from "./chains"

const family = (s: string) => {
  const d = detectAddress(s)
  return d.ok ? d.family : `invalid:${d.family ?? "?"}`
}

describe("detectAddress", () => {
  it("recognises one valid address per family", () => {
    expect(family("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")).toBe("evm")
    expect(family("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")).toBe("bitcoin")
    expect(
      family("bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0")
    ).toBe("bitcoin")
    expect(family("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")).toBe("bitcoin")
    expect(family("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")).toBe("bitcoin")
    expect(family("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")).toBe("tron")
    expect(family("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")).toBe(
      "solana"
    )
    expect(
      family("GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
    ).toBe("stellar")
  })

  it("catches one changed character through each family's checksum", () => {
    expect(family("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96046")).toBe(
      "invalid:evm"
    )
    expect(family("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlj")).toBe(
      "invalid:bitcoin"
    )
    expect(family("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb")).toBe("invalid:bitcoin")
    expect(family("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6u")).toBe("invalid:tron")
    expect(
      family("GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVM")
    ).toBe("invalid:stellar")
  })

  it("rejects a taproot address checksummed as bech32 instead of bech32m", () => {
    // v1 program with a v0 (bech32) checksum: BIP-350 invalid vector
    expect(
      family("bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vpzk5jj0")
    ).toBe("invalid:bitcoin")
  })

  it("explains a truncated EVM address and unknown input", () => {
    const d = detectAddress("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA9604")
    expect(d.ok).toBe(false)
    expect(!d.ok && d.reason).toMatch(/39/)
    expect(detectAddress("hello").ok).toBe(false)
    expect(detectAddress("  ").ok).toBe(false)
  })
})

describe("tron hex", () => {
  it("round-trips the USDT contract", () => {
    expect(tronHex("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")).toBe(
      "a614f803b6fd780986a42c78ec9c7f77e6ded13c"
    )
    expect(tronAddress("41a614f803b6fd780986a42c78ec9c7f77e6ded13c")).toBe(
      "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    )
    expect(tronAddress("a614f803b6fd780986a42c78ec9c7f77e6ded13c")).toBe(
      "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    )
  })
})

describe("networkFor", () => {
  it("keeps the chosen EVM chain for an EVM address and jumps to the family otherwise", () => {
    expect(networkFor("evm", "base")).toBe("base")
    expect(networkFor("evm", "tron")).toBe("eth")
    expect(networkFor("solana", "eth")).toBe("solana")
  })
})

describe("poisoning (any chain)", () => {
  const OWNER = "TOwnerAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  const FRIEND = "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"
  const FAKE = "TQn9Y2kZZZZZZZZZZZZZZZZZZZZZZcbLSE"

  it("flags a look-alike planted next to a real counterparty", () => {
    expect(lookalike(FRIEND, FAKE)).toBe(true)
    const r = poisoning(
      [
        { from: OWNER, to: FRIEND, value: true },
        { from: OWNER, to: FRIEND, value: true },
        { from: FAKE, to: OWNER, value: true },
        { from: OWNER, to: FAKE, value: false },
      ],
      OWNER
    )
    expect(r.counterparties).toBe(1)
    expect(r.suspects).toEqual([
      { address: FAKE, imitates: FRIEND, planted: 2, zeroValue: 1 },
    ])
  })

  it("is case-sensitive outside EVM (base58 case matters)", () => {
    expect(lookalike(FRIEND, FRIEND.toLowerCase())).toBe(false)
  })
})
