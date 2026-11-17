import { useEffect, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { SearchIcon } from "@hugeicons/core-free-icons"
import { CoinIcon, VenueIcon } from "@/components/coin-icon"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { api } from "@/lib/api"
import type { Instrument } from "@/lib/api"

const RECENT_KEY = "rinng.recent.v1"

function loadRecent(): Array<Instrument> {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? (JSON.parse(raw) as Array<Instrument>) : []
  } catch {
    return []
  }
}

function saveRecent(list: Array<Instrument>) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    /* storage blocked: recent list lives for this session only */
  }
}

function Row({ inst }: { inst: Instrument }) {
  return (
    <>
      <CoinIcon symbol={inst.icon ?? inst.base} size={20} />
      <span className="font-medium">{inst.base}</span>
      <span className="truncate text-muted-foreground">
        {inst.name !== inst.base ? inst.name : "USDT perp"}
      </span>
      <span className="ml-auto flex items-center gap-1">
        {inst.configured ? (
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            watchlist
          </span>
        ) : null}
        {inst.binance ? <VenueIcon id="binance" size={14} /> : null}
        {inst.okx ? <VenueIcon id="okx" size={14} /> : null}
      </span>
    </>
  )
}

// Trigger button + command palette (⌘K or "/") to open any USDT perp on Binance or OKX.
export function CoinSearch({
  value,
  watchlist,
  onSelect,
}: {
  value: Instrument
  watchlist: Array<Instrument>
  onSelect: (inst: Instrument) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<Array<Instrument>>([])
  const [loading, setLoading] = useState(false)
  const [recent, setRecent] = useState<Array<Instrument>>([])

  useEffect(() => setRecent(loadRecent()), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing =
        e.target instanceof HTMLElement &&
        e.target.closest("input, textarea, [contenteditable]")
      if (
        (e.key === "k" && (e.metaKey || e.ctrlKey)) ||
        (e.key === "/" && !typing)
      ) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    const t = setTimeout(() => {
      api
        .instruments(q)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 180)
    return () => clearTimeout(t)
  }, [query])

  const pick = (inst: Instrument) => {
    const next = [inst, ...recent.filter((r) => r.id !== inst.id)].slice(0, 6)
    setRecent(next)
    saveRecent(next)
    onSelect(inst)
    setOpen(false)
    setQuery("")
  }

  const recentOther = recent.filter(
    (r) => !watchlist.some((w) => w.id === r.id)
  )

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Instrument: ${value.base}. Search coins`}
        className="inline-flex h-7 items-center gap-1.5 rounded-4xl border border-input bg-input/30 pr-1.5 pl-2 text-xs font-medium transition-colors hover:bg-input/50"
      >
        <CoinIcon symbol={value.icon ?? value.base} size={16} />
        {value.base}/{value.quote ?? "USDT"} Perp
        <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          <HugeiconsIcon icon={SearchIcon} className="size-3" />
          ⌘K
        </span>
      </button>
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search coins"
        description="Any USDT perpetual listed on Binance or OKX"
      >
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search any coin: XRP, DOGE, PEPE…"
            value={query}
            onValueChange={setQuery}
          />
          <CommandList className="max-h-[420px]">
            {query.trim() ? (
              <>
                <CommandEmpty>
                  {loading ? "Searching…" : "No USDT perpetual matches."}
                </CommandEmpty>
                {results.length ? (
                  <CommandGroup heading="Binance & OKX perpetuals">
                    {results.map((inst) => (
                      <CommandItem
                        key={inst.id}
                        value={inst.id}
                        onSelect={() => pick(inst)}
                      >
                        <Row inst={inst} />
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ) : null}
              </>
            ) : (
              <>
                <CommandGroup heading="Watchlist">
                  {watchlist.map((inst) => (
                    <CommandItem
                      key={inst.id}
                      value={inst.id}
                      onSelect={() => pick(inst)}
                    >
                      <Row inst={inst} />
                    </CommandItem>
                  ))}
                </CommandGroup>
                {recentOther.length ? (
                  <CommandGroup heading="Recent">
                    {recentOther.map((inst) => (
                      <CommandItem
                        key={inst.id}
                        value={`recent-${inst.id}`}
                        onSelect={() => pick(inst)}
                      >
                        <Row inst={inst} />
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ) : null}
              </>
            )}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  )
}
