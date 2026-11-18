// Pure helpers for Send check: readable address chunks, a character diff, the verdict wording and
// the extra notes that sit beside it. No React.
import { lookalike } from "./address"
import type { Suspect } from "./address"
import type { Family } from "./chains"
import type { Severity } from "./scan"

export function chunks(address: string): Array<string> {
  const prefix = address.startsWith("0x") ? "0x" : ""
  const body = address.slice(prefix.length)
  const groups = body.match(/.{1,4}/g) ?? []
  return prefix ? [prefix, ...groups] : groups
}

export function diffMarks(a: string, b: string): Array<number> {
  const x = a.toLowerCase()
  const y = b.toLowerCase()
  const marks: Array<number> = []
  for (let i = 0; i < Math.max(x.length, y.length); i++) if (x[i] !== y[i]) marks.push(i)
  return marks
}

const VERDICTS = {
  high: { title: "Do not send to this address", tone: "danger" },
  medium: { title: "Review before sending", tone: "warn" },
  low: { title: "Review before sending", tone: "warn" },
  ok: { title: "No problems found", tone: "note" },
} as const

export const verdict = (
  severity: Severity | "ok"
): { title: string; tone: "danger" | "warn" | "note" } => ({ ...VERDICTS[severity] })

export function extraNotes(i: {
  isContract?: boolean
  tokenSymbol?: string
  fromFamily?: Family
  toFamily?: Family
}): Array<string> {
  const notes: Array<string> = []
  if (i.isContract)
    notes.push(
      i.tokenSymbol
        ? `This address is the ${i.tokenSymbol} token contract. Sending funds to it usually loses them.`
        : "This address is a contract, not a personal wallet. Make sure it is meant to receive funds."
    )
  if (i.fromFamily && i.toFamily && i.fromFamily !== i.toFamily)
    notes.push(
      `You are sending from a ${i.fromFamily} wallet to a ${i.toFamily} address. Funds sent across address types are usually lost.`
    )
  return notes
}

/** The verdict plus every note; a check that did not run, or a contract To, can never leave "No problems found". */
export function sendVerdict(i: {
  check: Severity | "ok"
  skipped: Array<string>
  extra: Array<string>
  isContract?: boolean
}): { title: string; tone: "danger" | "warn" | "note"; notes: Array<string> } {
  const v = verdict((i.skipped.length || i.isContract) && i.check === "ok" ? "low" : i.check)
  return { ...v, notes: [...i.extra, ...i.skipped] }
}

/** The address `address` imitates: a suspect's target, else a counterparty with the same ends. */
export function lookalikeOf(
  address: string,
  counterparties: ReadonlyArray<string> = [],
  suspects: ReadonlyArray<Suspect> = []
): string | undefined {
  const s = suspects.find((x) => x.address.toLowerCase() === address.toLowerCase())
  return s?.imitates ?? counterparties.find((c) => lookalike(c, address))
}

/** The From value is "address|net" for a saved wallet, or a bare address. */
export function splitFrom(v: string | undefined): { address?: string; net?: string } {
  if (!v) return { address: undefined, net: undefined }
  const [address, net] = v.split("|")
  return { address, net: net || undefined }
}

/** The option a From value from the URL points at (exact "address|net", else the option holding that address,
 *  e.g. after the connected wallet switched chain); undefined when none. Only ever returns one of the options. */
export function resolveFrom(fromParam: string | undefined, options: ReadonlyArray<{ value: string }>): string | undefined {
  if (!fromParam) return undefined
  const f = fromParam.toLowerCase()
  const address = splitFrom(f).address
  return (
    options.find((o) => o.value.toLowerCase() === f)?.value ??
    options.find((o) => splitFrom(o.value).address?.toLowerCase() === address)?.value
  )
}
