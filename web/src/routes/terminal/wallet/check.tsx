import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { detectAddress } from "@/lib/chains"
import { SendCheck } from "@/components/wallet/send-check"

type CheckSearch = { to?: string; from?: string }

const text = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined)

const toParam = (v: unknown) => {
  const t = text(v)
  return t && detectAddress(t).ok ? t : undefined
}
const fromParam = (v: unknown) => {
  const t = text(v)
  return t && detectAddress(t.split("|")[0]).ok ? t : undefined
}

export const Route = createFileRoute("/terminal/wallet/check")({
  validateSearch: (raw: Record<string, unknown>): CheckSearch => ({
    to: toParam(raw.to),
    from: fromParam(raw.from),
  }),
  component: Check,
})

function Check() {
  const { to, from } = Route.useSearch()
  const navigate = useNavigate()
  return (
    <SendCheck
      to={to}
      from={from}
      onChange={(p) => navigate({ to: ".", search: (s) => ({ ...s, to: p.to, from: p.from }) })}
    />
  )
}
