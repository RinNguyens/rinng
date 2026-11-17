import { describe, expect, it } from "vitest"
import { tronAddress, tronHex } from "./chains"
import {
  bitcoinMoves,
  chainScore,
  judgeKeys,
  scanBitcoin,
  scanSolana,
  scanStellar,
  scanTron,
  solanaMoves,
} from "./multichain"

// A fetch that answers from a route table: the first route whose test matches wins.
type Route = [
  test: (url: string, body: any) => boolean,
  reply: unknown,
  status?: number,
]
function fakeFetch(routes: Array<Route>) {
  const calls: Array<string> = []
  const f = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push(body?.method ? `${url} ${body.method}` : url)
    const hit = routes.find(([t]) => t(url, body))
    if (!hit) return new Response("not found", { status: 404 })
    return new Response(JSON.stringify(hit[1]), { status: hit[2] ?? 200 })
  }) as typeof fetch
  return Object.assign(f, { calls })
}

const ME = "TNPeeaaFB7K9cmo4uQpcU32zGK8G1NYqeL"
const THIEF = "TEzherQdni3jF5xBNWXVD7wVBMUSJPUodj"
const USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

describe("judgeKeys", () => {
  it("is quiet when only the owner's key can sign", () => {
    expect(judgeKeys("Owner", ME, 1, [{ address: ME, weight: 1 }])).toBeNull()
  })
  it("flags a hijack: the owner key replaced by someone else's", () => {
    const f = judgeKeys("Owner", ME, 1, [{ address: THIEF, weight: 1 }])
    expect(f?.severity).toBe("high")
    expect(f?.note).toMatch(/no longer sign/)
    expect(f?.points).toBe(60)
  })
  it("flags a second key that can sign alone, even if the owner still can", () => {
    expect(
      judgeKeys("Owner", ME, 1, [
        { address: ME, weight: 1 },
        { address: THIEF, weight: 1 },
      ])?.severity
    ).toBe("high")
  })
  it("calls a 2-of-2 a multisig, not a hijack", () => {
    expect(
      judgeKeys("Owner", ME, 2, [
        { address: ME, weight: 1 },
        { address: THIEF, weight: 1 },
      ])?.severity
    ).toBe("medium")
  })
})

describe("scanTron", () => {
  const spenderHex = tronHex(THIEF)
  const approveData = `095ea7b3${spenderHex.padStart(64, "0")}${"f".repeat(64)}`
  const routes = (owner: unknown): Array<Route> => [
    [
      (u) => u.endsWith("/wallet/getaccount"),
      { address: ME, owner_permission: owner, active_permission: [] },
    ],
    [
      (u) => u.includes("/transactions?only_from"),
      {
        data: [
          {
            raw_data: {
              contract: [
                {
                  type: "TriggerSmartContract",
                  parameter: {
                    value: {
                      owner_address: `41${tronHex(ME)}`,
                      contract_address: `41${tronHex(USDT)}`,
                      data: approveData,
                    },
                  },
                },
              ],
            },
          },
        ],
        meta: {},
      },
    ],
    [
      (u) => u.includes("/transactions/trc20"),
      {
        data: [
          {
            from: ME,
            to: THIEF,
            value: "5",
            token_info: { address: USDT, symbol: "USDT", decimals: 6 },
          },
        ],
        meta: {},
      },
    ],
    [
      (u) => u.endsWith("/wallet/triggerconstantcontract"),
      { constant_result: ["f".repeat(64)] },
    ],
    [(u) => u.endsWith("/wallet/getcontract"), {}],
  ]

  it("finds a hijacked owner permission and an unlimited allowance to a wallet", async () => {
    const f = fakeFetch(
      routes({ threshold: 1, keys: [{ address: THIEF, weight: 1 }] })
    )
    const r = await scanTron(ME, { fetch: f })
    expect(r.sections.map((s) => s.title)).toEqual([
      "Permissions",
      "TRC-20 approvals",
      "Poisoning",
    ])
    expect(r.sections[0].findings[0].severity).toBe("high")
    const a = r.sections[1].findings[0]
    expect(a.severity).toBe("high") // spender has no contract code
    expect(a.amount).toBe("unlimited")
    expect(a.title).toMatch(/^USDT →/)
    expect(chainScore(r).grade).toBe("F")
  })

  it("reads a clean, activated account as clean", async () => {
    const f = fakeFetch(
      routes(undefined).map(
        ([t, v]) =>
          [
            t,
            t("x/wallet/triggerconstantcontract", null)
              ? { constant_result: ["0"] }
              : v,
          ] as Route
      )
    )
    const r = await scanTron(ME, { fetch: f })
    expect(r.sections[0].findings).toEqual([])
    expect(r.sections[1].findings).toEqual([])
    expect(chainScore(r).grade).toBe("A")
  })

  it("converts the approve calldata's spender to a T address", () => {
    expect(tronAddress(approveData.slice(8 + 24, 8 + 64))).toBe(THIEF)
  })
})

describe("scanSolana", () => {
  const WALLET = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
  const DRAINER = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
  const rpc = (method: string, result: unknown): Route => [
    (_u, b) => b?.method === method,
    { jsonrpc: "2.0", id: 1, result },
  ]

  it("flags a token delegate and a reassigned account", async () => {
    const f = fakeFetch([
      rpc("getAccountInfo", {
        value: {
          owner: "DrainerProgram1111111111111111111111111111",
          lamports: 1,
        },
      }),
      [
        (_u, b) =>
          b?.method === "getTokenAccountsByOwner" &&
          b.params[1].programId.startsWith("Tokenkeg"),
        {
          result: {
            value: [
              {
                pubkey: "acct",
                account: {
                  data: {
                    parsed: {
                      info: {
                        mint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        owner: WALLET,
                        delegate: DRAINER,
                        delegatedAmount: {
                          amount: "18446744073709551615",
                          decimals: 6,
                          uiAmountString: "x",
                        },
                        tokenAmount: {
                          amount: "1000000",
                          decimals: 6,
                          uiAmountString: "1",
                        },
                      },
                    },
                  },
                },
              },
            ],
          },
        },
      ],
      rpc("getTokenAccountsByOwner", { value: [] }),
      rpc("getSignaturesForAddress", []),
    ])
    const r = await scanSolana(WALLET, {
      fetch: f,
      solanaRpc: "https://rpc.test",
    })
    expect(r.sections[0].findings[0].title).toMatch(/reassigned/)
    expect(r.sections[1].findings[0]).toMatchObject({
      severity: "high",
      amount: "unlimited",
    })
    expect(chainScore(r).grade).toBe("F")
  })

  it("surfaces an RPC refusal instead of a clean report", async () => {
    const f = fakeFetch([
      [
        () => true,
        { jsonrpc: "2.0", id: 1, error: { message: "Access forbidden" } },
      ],
    ])
    await expect(
      scanSolana(WALLET, { fetch: f, solanaRpc: "https://rpc.test" })
    ).rejects.toThrow(/forbidden/)
  })

  it("maps SPL transfers to wallet owners", () => {
    const moves = solanaMoves({
      transaction: {
        message: {
          accountKeys: [{ pubkey: "srcAta" }, { pubkey: "dstAta" }],
          instructions: [
            {
              program: "spl-token",
              parsed: {
                type: "transferChecked",
                info: {
                  source: "srcAta",
                  destination: "dstAta",
                  authority: WALLET,
                  tokenAmount: { amount: "0" },
                },
              },
            },
          ],
        },
      },
      meta: { postTokenBalances: [{ accountIndex: 1, owner: DRAINER }] },
    })
    expect(moves).toEqual([{ from: WALLET, to: DRAINER, value: false }])
  })
})

describe("scanBitcoin", () => {
  const ME_BTC = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
  it("flags dust outputs and address reuse", async () => {
    const f = fakeFetch([
      [
        (u) => u.endsWith("/utxo"),
        [{ value: 546 }, { value: 600 }, { value: 50_000 }],
      ],
      [(u) => u.endsWith("/txs"), []],
      [
        (u) => u.includes("/address/"),
        {
          chain_stats: { funded_txo_count: 3, tx_count: 3 },
          mempool_stats: { funded_txo_count: 0, tx_count: 0 },
        },
      ],
    ])
    const r = await scanBitcoin(ME_BTC, { fetch: f })
    expect(r.sections[0].findings[0].title).toBe("Address reused")
    expect(r.sections[1].findings[0]).toMatchObject({
      severity: "medium",
      title: "2 dust outputs",
      amount: "1146 sats",
    })
  })

  it("reads sends and receipts from transactions", () => {
    const moves = bitcoinMoves(
      [
        {
          vin: [{ prevout: { scriptpubkey_address: ME_BTC, value: 10_000 } }],
          vout: [
            { scriptpubkey_address: "bc1qfriend", value: 9_000 },
            { scriptpubkey_address: ME_BTC, value: 500 },
          ],
        },
        {
          vin: [
            { prevout: { scriptpubkey_address: "bc1qstranger", value: 700 } },
          ],
          vout: [{ scriptpubkey_address: ME_BTC, value: 546 }],
        },
      ],
      ME_BTC
    )
    expect(moves).toEqual([
      { from: ME_BTC, to: "bc1qfriend", value: true },
      { from: "bc1qstranger", to: ME_BTC, value: true },
    ])
  })
})

describe("scanStellar", () => {
  const G = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
  const OTHER = "GBRPYHIL2CI3FNQ4BXLFMNDLFJUNPU2HY3ZMFSHONUCEOASW7QC7OX2H"
  it("flags a second signer that can act alone, and airdrop spam", async () => {
    const f = fakeFetch([
      [
        (u) => u.includes("/claimable_balances"),
        { _embedded: { records: [{}, {}] } },
      ],
      [(u) => u.includes("/payments"), { _embedded: { records: [] } }],
      [
        (u) => u.includes(`/accounts/${G}`),
        {
          signers: [
            { key: G, weight: 1, type: "ed25519_public_key" },
            { key: OTHER, weight: 5, type: "ed25519_public_key" },
          ],
          thresholds: { low_threshold: 0, med_threshold: 0, high_threshold: 0 },
          balances: [{ asset_type: "native" }],
        },
      ],
    ])
    const r = await scanStellar(G, { fetch: f })
    expect(r.sections[0].findings[0].severity).toBe("high")
    expect(r.sections[1].findings[0].title).toBe("2 unclaimed airdrops")
  })

  it("treats an unfunded account as nothing to take over", async () => {
    const r = await scanStellar(G, { fetch: fakeFetch([]) })
    expect(r.sections[0].summary).toMatch(/not funded/)
    expect(chainScore(r).grade).toBe("A")
  })
})

describe("judgeKeys, organisation multisig", () => {
  it("does not call a 2-of-4 with the master key disabled a hijack", () => {
    const keys = ["GA", "GB", "GC", "GD"].map((address) => ({
      address,
      weight: 1,
    }))
    const f = judgeKeys("Signers", "GME", 2, [
      ...keys,
      { address: "GME", weight: 0 },
    ])
    expect(f).toMatchObject({
      severity: "medium",
      title: "Signers: run by other keys",
    })
  })
  it("flags other keys that together sign without the owner", () => {
    const f = judgeKeys("Signers", "GME", 2, [
      { address: "GME", weight: 2 },
      { address: "GA", weight: 1 },
      { address: "GB", weight: 1 },
    ])
    expect(f?.severity).toBe("high")
  })
})

describe("request errors", () => {
  it("passes the relay's own explanation through", async () => {
    const f = fakeFetch([
      [
        () => true,
        {
          jsonrpc: "2.0",
          id: 1,
          error: { message: "You have used your data allowance" },
        },
        413,
      ],
    ])
    await expect(
      scanSolana("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", {
        fetch: f,
        solanaRpc: "/api/solana",
      })
    ).rejects.toThrow(/data allowance/)
  })
})

describe("chainScore", () => {
  it("counts many low notes once, capped at 5 points", () => {
    const low = { severity: "low" as const, title: "frozen", note: "" }
    const r = {
      family: "solana" as const,
      address: "x",
      suspects: [],
      complete: true,
      sections: [
        {
          title: "Token delegates",
          summary: "",
          complete: true,
          findings: Array.from({ length: 41 }, () => low),
        },
      ],
    }
    const s = chainScore(r)
    expect(s.score).toBe(95)
    expect(s.items).toHaveLength(1)
  })
})
