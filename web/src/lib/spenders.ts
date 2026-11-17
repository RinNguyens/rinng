import type { Address } from "viem"

// Well-known contracts that commonly hold approvals or EIP-7702 delegations. A label only adds
// context: an unknown spender is not proof of a scam, and a known one can still be hacked.
// Addresses are the projects' published deployments; `chains` limits a label to the chains where
// that address is that contract ("*" = same address everywhere, via CREATE2). A label never
// lowers the risk of an EOA spender, and when in doubt the entry is left out: a missing label
// costs a little context, a wrong one could vouch for a drainer.

export type LabelKind =
  "router" | "nft" | "lending" | "staking" | "infra" | "delegate"
export type Label = { name: string; kind: LabelKind }

const ALL = "*" as const
const KNOWN: Array<[string, string, LabelKind, Array<number> | typeof ALL]> = [
  [
    "0x000000000022D473030F116dDEE9F6B43aC78BA3",
    "Permit2 (Uniswap)",
    "infra",
    ALL,
  ],
  ["0xcA11bde05977b3631167028862bE2a173976CA11", "Multicall3", "infra", ALL],
  [
    "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "Uniswap V2 Router",
    "router",
    [1],
  ],
  [
    "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "Uniswap V3 Router",
    "router",
    [1, 10, 137, 42161],
  ],
  [
    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    "Uniswap V3 Router 02",
    "router",
    [1, 10, 137, 42161],
  ],
  [
    "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD",
    "Uniswap Universal Router",
    "router",
    [1],
  ],
  [
    "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af",
    "Uniswap V4 Universal Router",
    "router",
    [1],
  ],
  [
    "0x1111111254EEB25477B68fb85Ed929f73A960582",
    "1inch Router v5",
    "router",
    ALL,
  ],
  [
    "0x111111125421cA6dc452d289314280a0f8842A65",
    "1inch Router v6",
    "router",
    ALL,
  ],
  [
    "0xDef1C0ded9bec7F1a1670819833240f027b25EfF",
    "0x Exchange Proxy",
    "router",
    [1],
  ],
  [
    "0x6A000F20005980200259B80c5102003040001068",
    "ParaSwap Augustus v6.2",
    "router",
    ALL,
  ],
  [
    "0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57",
    "ParaSwap Augustus v5",
    "router",
    [1],
  ],
  [
    "0xC92E8bdf79f0507f65a392b0ab4667716BFE0110",
    "CoW Protocol Vault Relayer",
    "router",
    [1, 8453, 42161],
  ],
  [
    "0x881D40237659C251811CEC9c364ef91dC08D300C",
    "MetaMask Swap Router",
    "router",
    [1],
  ],
  [
    "0x00000000000000ADc04C56Bf30aC9d3c0aAF14dC",
    "OpenSea Seaport 1.5",
    "nft",
    ALL,
  ],
  [
    "0x0000000000000068F116a894984e2DB1123eB395",
    "OpenSea Seaport 1.6",
    "nft",
    ALL,
  ],
  ["0x1E0049783F008A0085193E00003D00cd54003c71", "OpenSea Conduit", "nft", ALL],
  [
    "0x00000000000111AbE46ff893f3B2fdF1F759a8A8",
    "Blur Execution Delegate",
    "nft",
    [1],
  ],
  [
    "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "Aave V3 Pool",
    "lending",
    [1],
  ],
  [
    "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "Aave V3 Pool",
    "lending",
    [10, 137, 42161, 43114],
  ],
  [
    "0x889edC2eDab5f40e902b864aD4d7AdE8E412F9B1",
    "Lido Withdrawal Queue",
    "staking",
    [1],
  ],
  // EIP-7702 delegates of mainstream smart accounts.
  [
    "0x63c0c19a282a1B52b07dD5a65b58948A07DAE32B",
    "MetaMask Smart Account",
    "delegate",
    ALL,
  ],
  [
    "0x000000009B1D0aF20D8C6d0A44e162d11F9b8f00",
    "Uniswap Wallet (Calibur)",
    "delegate",
    ALL,
  ],
  [
    "0x4Cd241E8d1510e30b2076397afc7508Ae59C66c9",
    "ERC-4337 Simple7702Account",
    "delegate",
    ALL,
  ],
  [
    "0x5A7FC11397E9a8AD41BF10bf13F22B0a63f96f6d",
    "Ambire Smart Account",
    "delegate",
    ALL,
  ],
]

const BY_ADDRESS = new Map(
  KNOWN.map(([a, name, kind, chains]) => [
    a.toLowerCase(),
    { name, kind, chains },
  ])
)

/** The label for `address` on `chainId`, if it is a contract rinng knows. */
export function labelOf(
  address: string | undefined,
  chainId?: number | null
): Label | undefined {
  if (!address) return undefined
  const k = BY_ADDRESS.get(address.toLowerCase())
  if (!k) return undefined
  if (k.chains !== ALL && (chainId == null || !k.chains.includes(chainId)))
    return undefined
  return { name: k.name, kind: k.kind }
}

export const knownAddresses = (): Array<Address> =>
  KNOWN.map(([a]) => a as Address)
