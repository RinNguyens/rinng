import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { ScanPanel } from "@/components/wallet/scan-panel"
import { parseWalletSearch } from "@/lib/wallet-scan"

// `address` and `net` are public data; labels and notes never go in the URL.
export const Route = createFileRoute("/terminal/wallet/scan")({
  validateSearch: parseWalletSearch,
  component: Scan,
})

function Scan() {
  const { address, net, hl } = Route.useSearch()
  const navigate = useNavigate()
  return (
    <ScanPanel
      address={address}
      net={net}
      hl={hl}
      onChange={(p) =>
        navigate({ to: ".", search: (s) => ({ ...s, address: p.address, net: p.net, hl: undefined }) })
      }
    />
  )
}
