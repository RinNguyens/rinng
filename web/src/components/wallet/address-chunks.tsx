import { chunks, diffMarks } from "@/lib/send-check"

function Line({ address, marks }: { address: string; marks?: ReadonlySet<number> }) {
  let i = 0
  return (
    <p aria-hidden className="font-heading text-base tracking-wide break-all">
      {chunks(address).map((g, n) => {
        const start = i
        i += g.length
        return (
          <span key={n} className="mr-2 inline-block">
            {[...g].map((c, k) =>
              marks?.has(start + k) ? (
                <span key={k} className="rounded-sm bg-sev-high/25 text-foreground">
                  {c}
                </span>
              ) : (
                c
              )
            )}
          </span>
        )
      })}
    </p>
  )
}

export function AddressChunks({ address, compare }: { address: string; compare?: string }) {
  const marks = compare ? new Set(diffMarks(address, compare)) : undefined
  return (
    <div
      role="group"
      aria-label={
        compare
          ? `${address.replace(/\s/g, "")}, differs from the address you used before`
          : address.replace(/\s/g, "")
      }
    >
      <Line address={address} marks={marks} />
      {compare && <Line address={compare} marks={marks} />}
    </div>
  )
}
