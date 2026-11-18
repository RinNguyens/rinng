import type { Severity } from "@/lib/scan"

const STYLE: Record<Severity, string> = {
  high: "bg-sev-high text-background",
  medium: "bg-sev-medium text-background",
  low: "bg-sev-low text-sev-low-foreground",
}

const WORD: Record<Severity, string> = { high: "HIGH", medium: "MED", low: "LOW" }

export function SevPill({ severity }: { severity: Severity }) {
  return (
    <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] tracking-wider ${STYLE[severity]}`}>
      {WORD[severity]}
    </span>
  )
}
