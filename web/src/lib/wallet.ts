import { useCallback, useEffect, useState } from "react"
import { createPublicClient, custom, formatEther } from "viem"
import type { Address } from "viem"
import { pageLock } from "./guard"

// Read-only wallet over the injected EIP-1193 provider (MetaMask, Rabby, OKX Wallet...).
// rinng never asks for a signature or sends a transaction: every call goes through the signature
// lock in guard.ts, which only lets read methods reach the wallet.

const provider = () => pageLock().provider

/** viem client over the guarded wallet: reads on whatever chain the wallet is on. */
export const publicClient = () => {
  const p = provider()
  return p ? createPublicClient({ transport: custom(p) }) : null
}

export const CHAINS: Record<number, string> = {
  1: "Ethereum",
  10: "Optimism",
  56: "BNB Chain",
  137: "Polygon",
  8453: "Base",
  42161: "Arbitrum",
  43114: "Avalanche",
  59144: "Linea",
  534352: "Scroll",
}

export type Wallet = {
  installed: boolean
  address: Address | null
  chainId: number | null
  balance: number | null // native coin
  connecting: boolean
  error: string | null
  connect: () => void
  disconnect: () => void
}

export function useWallet(): Wallet {
  const [address, setAddress] = useState<Address | null>(null)
  const [chainId, setChainId] = useState<number | null>(null)
  const [balance, setBalance] = useState<number | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eth = provider()

  const refresh = useCallback(async (addr: Address | null) => {
    const p = provider()
    if (!p || !addr) return setBalance(null)
    const [cid, wei] = (await Promise.all([
      p.request({ method: "eth_chainId" }),
      p.request({ method: "eth_getBalance", params: [addr, "latest"] }),
    ])) as [string, string]
    setChainId(parseInt(cid, 16))
    setBalance(Number(formatEther(BigInt(wei))))
  }, [])

  // Pick up an already-authorised account silently, and follow account/chain switches.
  useEffect(() => {
    if (!eth) return
    const onAccounts = (a: Array<Address>) => {
      setAddress(a[0] ?? null)
      void refresh(a[0] ?? null).catch(() => {})
    }
    const onChain = () => void refresh(address).catch(() => {})
    eth
      .request({ method: "eth_accounts" })
      .then((a) => onAccounts(a as Array<Address>))
      .catch(() => {})
    eth.on?.("accountsChanged", onAccounts)
    eth.on?.("chainChanged", onChain)
    return () => {
      eth.removeListener?.("accountsChanged", onAccounts)
      eth.removeListener?.("chainChanged", onChain)
    }
  }, [eth, refresh, address])

  const connect = useCallback(() => {
    const p = provider()
    if (!p) return setError("No wallet extension found")
    setConnecting(true)
    setError(null)
    p.request({ method: "eth_requestAccounts" })
      .then(async (a) => {
        const addr = (a as Array<Address>)[0] ?? null
        setAddress(addr)
        await refresh(addr)
      })
      .catch((e: { message?: string }) => setError(e.message ?? "Rejected"))
      .finally(() => setConnecting(false))
  }, [refresh])

  const disconnect = useCallback(() => {
    setAddress(null)
    setBalance(null)
    setChainId(null)
  }, [])

  return {
    installed: !!eth,
    address,
    chainId,
    balance,
    connecting,
    error,
    connect,
    disconnect,
  }
}

export const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`
