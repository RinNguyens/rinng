import { ExchangeIcon, TokenIcon } from "@web3icons/react/dynamic"
import { cn } from "@/lib/utils"

// Letter badge shown while an icon loads or when the package has no icon for the symbol.
function Letter({ text, size, className }: { text: string; size: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-grid shrink-0 place-items-center rounded-full bg-muted font-heading font-semibold text-muted-foreground",
        className,
      )}
      style={{ width: size, height: size, fontSize: size * 0.5 }}
    >
      {text.slice(0, 1).toUpperCase()}
    </span>
  )
}

// Coin icon from @web3icons (SVGs bundled with the app; no network calls).
export function CoinIcon({ symbol, size = 18, className }: { symbol: string; size?: number; className?: string }) {
  // Binance lists some coins per 1000 units (1000PEPE); the icon is the coin's own.
  const plain = symbol.replace(/^(1000000|100000|10000|1000|1M)(?=[A-Z])/, "")
  return (
    <TokenIcon
      key={plain}
      symbol={plain.toLowerCase()}
      variant="branded"
      size={size}
      aria-hidden
      className={cn("shrink-0", className)}
      fallback={<Letter text={plain} size={size} className={className} />}
    />
  )
}

export function VenueIcon({ id, size = 16, className }: { id: string; size?: number; className?: string }) {
  return (
    <ExchangeIcon
      id={id.toLowerCase()}
      // OKX's branded mark is black and disappears on the dark theme.
      variant={id.toLowerCase() === "okx" ? "mono" : "branded"}
      color={id.toLowerCase() === "okx" ? "currentColor" : undefined}
      size={size}
      aria-hidden
      className={cn("shrink-0", className)}
      fallback={<Letter text={id} size={size} className={className} />}
    />
  )
}
