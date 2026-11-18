import { describe, expect, it } from "vitest"
import { chunks, resolveFrom, diffMarks, extraNotes, lookalikeOf, sendVerdict, splitFrom, verdict } from "./send-check"

/* Signatures chosen by the tests (the coder implements to these):

   chunks(address: string): Array<string>
     "0x" + 40 hex -> ["0x", ...ten groups of 4]; joined it gives back the input unchanged.
     No 0x prefix -> plain groups of 4 (last group may be shorter). "" -> [].
   diffMarks(a: string, b: string): Array<number>
     Character indexes (into the full string, 0x included) where a and b differ, case-insensitive.
     Where one string is longer, every index past the shorter one counts as differing.
   verdict(severity: Severity | "ok"): { title: string; tone: "danger" | "warn" | "note" }
     high -> "Do not send" / danger, medium -> warn, low and ok -> note. No title ever says "safe".
   extraNotes(i: { isContract?: boolean; tokenSymbol?: string; fromFamily?: Family; toFamily?: Family }): Array<string>
     Plain sentences; [] when nothing to add.
*/

const A = "0x1234567890abcdef1234567890ABCDEF12345678"

describe("chunks", () => {
  it("groups by 4 after 0x", () => {
    const out = chunks(A)
    expect(out[0]).toBe("0x")
    expect(out.slice(1)).toHaveLength(10)
    expect(out.slice(1).every((g) => g.length === 4)).toBe(true)
    expect(out.slice(1, 3)).toEqual(["1234", "5678"])
  })

  it("loses nothing: joined, it is the address again, case kept", () => {
    expect(chunks(A).join("")).toBe(A)
  })

  it("handles input without a prefix, short input and empty", () => {
    expect(chunks("abcdefghij")).toEqual(["abcd", "efgh", "ij"])
    expect(chunks("0xab")).toEqual(["0x", "ab"])
    expect(chunks("")).toEqual([])
  })
})

describe("diffMarks", () => {
  it("marks every position that differs", () => {
    const b = A.slice(0, 5) + "9" + A.slice(6, -1) + "0"
    expect(diffMarks(A, b)).toEqual([5, A.length - 1])
  })

  it("ignores case", () => {
    expect(diffMarks(A, A.toUpperCase().replace("0X", "0x"))).toEqual([])
    expect(diffMarks(A, A.toLowerCase())).toEqual([])
  })

  it("is empty for identical strings and symmetrical", () => {
    expect(diffMarks(A, A)).toEqual([])
    const b = "0x1234567890abcdef1234567890abcdef12340000"
    expect(diffMarks(A, b)).toEqual(diffMarks(b, A))
  })

  it("counts the extra length of the longer string as differences", () => {
    expect(diffMarks("0xabc", "0xabcde")).toEqual([5, 6])
    expect(diffMarks("0xabcde", "0xabc")).toEqual([5, 6])
    expect(diffMarks("", "ab")).toEqual([0, 1])
  })
})

describe("verdict", () => {
  // docs/13 §6.3: three banners, never the word "safe".
  it("says do not send for high, with a danger tone", () => {
    expect(verdict("high")).toEqual({ title: "Do not send to this address", tone: "danger" })
  })

  it("asks to review for low and medium", () => {
    expect(verdict("medium")).toEqual({ title: "Review before sending", tone: "warn" })
    expect(verdict("low")).toEqual({ title: "Review before sending", tone: "warn" })
  })

  it("says no problems found when nothing was flagged", () => {
    expect(verdict("ok")).toEqual({ title: "No problems found", tone: "note" })
  })

  it("never says safe, whatever the severity", () => {
    for (const s of ["high", "medium", "low", "ok"] as const) {
      const { title } = verdict(s)
      expect(title.length).toBeGreaterThan(0)
      expect(title).not.toMatch(/safe/i)
    }
  })
})

describe("extraNotes", () => {
  it("is empty when there is nothing to add", () => {
    expect(extraNotes({})).toEqual([])
    expect(extraNotes({ isContract: false, fromFamily: "evm", toFamily: "evm" })).toEqual([])
  })

  it("flags a token contract by its symbol", () => {
    const notes = extraNotes({ isContract: true, tokenSymbol: "USDC" })
    expect(notes).toHaveLength(1)
    expect(notes[0]).toContain("USDC")
    expect(notes[0].toLowerCase()).toContain("token")
  })

  it("flags a plain contract without claiming it is a token", () => {
    const notes = extraNotes({ isContract: true })
    expect(notes).toHaveLength(1)
    expect(notes[0].toLowerCase()).toContain("contract")
    expect(notes[0].toLowerCase()).not.toContain("token")
  })

  it("flags a wrong family, naming both", () => {
    const notes = extraNotes({ fromFamily: "evm", toFamily: "tron" })
    expect(notes).toHaveLength(1)
    expect(notes[0].toLowerCase()).toContain("evm")
    expect(notes[0].toLowerCase()).toContain("tron")
  })

  it("adds one note per fact", () => {
    expect(
      extraNotes({ isContract: true, tokenSymbol: "DAI", fromFamily: "evm", toFamily: "solana" })
    ).toHaveLength(2)
  })

  it("ignores a family check when either side is unknown", () => {
    expect(extraNotes({ fromFamily: "evm" })).toEqual([])
    expect(extraNotes({ toFamily: "bitcoin" })).toEqual([])
  })
})

describe("sendVerdict", () => {
  const skip = "Could not read your transfer history; the look-alike check did not run."

  it("keeps the plain verdict when nothing was skipped", () => {
    expect(sendVerdict({ check: "ok", skipped: [], extra: ["x"] })).toEqual({
      title: "No problems found",
      tone: "note",
      notes: ["x"],
    })
  })

  it("never says no problems when a check was skipped, and names it", () => {
    const v = sendVerdict({ check: "ok", skipped: [skip], extra: [] })
    expect(v.title).toBe("Review before sending")
    expect(v.tone).toBe("warn")
    expect(v.notes).toContain(skip)
  })

  it("does not soften a high verdict", () => {
    const v = sendVerdict({ check: "high", skipped: [skip], extra: ["e"] })
    expect(v.tone).toBe("danger")
    expect(v.notes).toEqual(["e", skip])
  })
})

describe("lookalikeOf", () => {
  const real = "0x1234567890abcdef1234567890abcdef12345678"
  const fake = "0x1234000000000000000000000000000000005678"
  it("returns what a suspect imitates", () => {
    expect(lookalikeOf(fake, [], [{ address: fake, imitates: real, planted: 1, zeroValue: 1 }] as never)).toBe(real)
  })
  it("returns a counterparty with the same ends", () => {
    expect(lookalikeOf(fake, [real], [])).toBe(real)
  })
  it("is undefined when there is none, or the address is the counterparty", () => {
    expect(lookalikeOf(real, [real], [])).toBeUndefined()
    expect(lookalikeOf(fake, undefined, undefined)).toBeUndefined()
  })
})

describe("splitFrom", () => {
  it("splits address|net and accepts a bare address", () => {
    expect(splitFrom("0xabc|base")).toEqual({ address: "0xabc", net: "base" })
    expect(splitFrom("0xabc")).toEqual({ address: "0xabc", net: undefined })
    expect(splitFrom(undefined)).toEqual({ address: undefined, net: undefined })
  })
})

describe("resolveFrom", () => {
  const opts = [{ value: "0xAbC|base" }, { value: "0xdef" }]
  it("drops a From that matches no option", () => {
    expect(resolveFrom("0x999", opts)).toBeUndefined()
    expect(resolveFrom(undefined, opts)).toBeUndefined()
    expect(resolveFrom("0x999|base", opts)).toBeUndefined()
  })
  it("matches a bare address to the option holding it", () => {
    expect(resolveFrom("0xabc", opts)).toBe("0xAbC|base")
    expect(resolveFrom("0xDEF", opts)).toBe("0xdef")
  })
  it("matches address|net exactly", () => {
    expect(resolveFrom("0xAbC|base", opts)).toBe("0xAbC|base")
  })
  it("keeps the user's own wallet when only its network changed (connected wallet switched chain)", () => {
    expect(resolveFrom("0xabc|eth", opts)).toBe("0xAbC|base")
  })
})

describe("sendVerdict contract", () => {
  it("raises ok to Review before sending for a contract", () => {
    const v = sendVerdict({ check: "ok", skipped: [], extra: [], isContract: true })
    expect(v.title).toBe("Review before sending")
    expect(v.tone).toBe("warn")
  })
  it("keeps high", () => {
    expect(sendVerdict({ check: "ok", skipped: [], extra: [], isContract: true }).title).toBe(
      "Review before sending"
    )
    expect(sendVerdict({ check: "high", skipped: [], extra: [], isContract: true }).title).toBe("Do not send to this address")
  })
})
