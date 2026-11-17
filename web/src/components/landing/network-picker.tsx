import { Select } from "@base-ui/react/select"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowDown01Icon, Tick02Icon } from "@hugeicons/core-free-icons"
import {
  NetworkArbitrumOne,
  NetworkBase,
  NetworkBinanceSmartChain,
  NetworkBitcoin,
  NetworkEthereum,
  NetworkOptimism,
  NetworkPolygon,
  NetworkSolana,
  NetworkStellar,
  NetworkTron,
} from "@web3icons/react"
import { NETWORKS, networkOf } from "@/lib/chains"

/* The wallet check's network picker: every chain with its logo, EVM chains (one 0x address for
   all of them) first, then the chains that have addresses of their own. */

const ICONS = {
  eth: NetworkEthereum,
  base: NetworkBase,
  arb: NetworkArbitrumOne,
  bsc: NetworkBinanceSmartChain,
  op: NetworkOptimism,
  polygon: NetworkPolygon,
  tron: NetworkTron,
  solana: NetworkSolana,
  bitcoin: NetworkBitcoin,
  stellar: NetworkStellar,
} as const

export function NetworkIcon({ id, size = 20 }: { id: string; size?: number }) {
  const Icon = id in ICONS ? ICONS[id as keyof typeof ICONS] : null
  return Icon ? (
    <Icon
      variant="background"
      size={size}
      aria-hidden="true"
      className="shrink-0 rounded-[6px]"
    />
  ) : (
    <span
      className="shrink-0 rounded-[6px] bg-[#e6e6e6]"
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  )
}

const GROUPS = [
  {
    label: "EVM · one 0x address",
    items: NETWORKS.filter((n) => n.family === "evm"),
  },
  { label: "Other chains", items: NETWORKS.filter((n) => n.family !== "evm") },
]

export function NetworkPicker({
  id,
  value,
  onChange,
}: {
  id: string
  value: string
  onChange: (key: string) => void
}) {
  const current = networkOf(value)
  return (
    <Select.Root value={value} onValueChange={(v) => v && onChange(v)}>
      <Select.Trigger
        id={id}
        className="flex h-12 w-full cursor-pointer items-center gap-2.5 rounded-md border border-[#d6d6d6] bg-white pr-3 pl-3 text-left text-[14px] transition-colors duration-150 outline-none hover:border-[#999] focus-visible:border-[#111] focus-visible:ring-2 focus-visible:ring-[#5b7cff]/40 data-popup-open:border-[#999]"
      >
        <NetworkIcon id={current.key} />
        <span className="min-w-0 flex-1 truncate">{current.name}</span>
        <HugeiconsIcon
          icon={ArrowDown01Icon}
          size={16}
          strokeWidth={1.5}
          className="shrink-0 text-[#666]"
          aria-hidden="true"
        />
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner
          side="bottom"
          align="start"
          sideOffset={6}
          alignItemWithTrigger={false}
          className="z-50"
        >
          <Select.Popup className="max-h-(--available-height) w-60 origin-(--transform-origin) overflow-y-auto rounded-xl border border-[#e2e2e2] bg-white p-1.5 text-[#111] shadow-[0_18px_40px_-12px_rgba(0,0,0,0.25)] transition-[opacity,scale] duration-150 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
            <Select.List>
              {GROUPS.map((g, gi) => (
                <Select.Group
                  key={g.label}
                  className={
                    gi ? "mt-1 border-t border-[#eee] pt-1" : undefined
                  }
                >
                  <Select.GroupLabel className="px-2.5 pt-1.5 pb-1 font-mono text-[10px] tracking-widest text-[#888] uppercase">
                    {g.label}
                  </Select.GroupLabel>
                  {g.items.map((n) => (
                    <Select.Item
                      key={n.key}
                      value={n.key}
                      className="flex min-h-10 cursor-pointer items-center gap-3 rounded-lg px-2.5 py-1.5 text-[14px] outline-none select-none data-highlighted:bg-[#f2f2f2]"
                    >
                      <NetworkIcon id={n.key} size={22} />
                      <Select.ItemText className="flex-1">
                        {n.name}
                      </Select.ItemText>
                      <Select.ItemIndicator>
                        <HugeiconsIcon
                          icon={Tick02Icon}
                          size={16}
                          strokeWidth={2}
                          className="text-[#111]"
                          aria-hidden="true"
                        />
                      </Select.ItemIndicator>
                    </Select.Item>
                  ))}
                </Select.Group>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  )
}
