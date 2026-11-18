import { describe, expect, it } from "vitest"
import { closeTarget, duplicateAfter, tabKey, tabName } from "./workspaces"
import type { PanelCfg, Workspace } from "./workspaces"

const panel = (id: string): PanelCfg => ({ id, lens: "structure", tf: "4h", days: 90, period: "week" })

const ws = (id: string, name = id, slots: Workspace["slots"] = [panel(`${id}-p0`), null]): Workspace => ({
  id,
  name,
  layout: "2",
  slots,
})

describe("tabName", () => {
  it("trims the new name", () => {
    expect(tabName("  Swing plan  ", "Old")).toBe("Swing plan")
  })

  it("keeps the old name when blank or whitespace only", () => {
    expect(tabName("", "Old")).toBe("Old")
    expect(tabName("   ", "Old")).toBe("Old")
    expect(tabName("\t\n", "Old")).toBe("Old")
  })

  it("caps the name at 32 characters", () => {
    const long = "x".repeat(40)
    expect(tabName(long, "Old")).toBe("x".repeat(32))
    expect(tabName("y".repeat(32), "Old")).toBe("y".repeat(32))
    expect(tabName("z".repeat(33), "Old")).toHaveLength(32)
  })

  it("trims before capping and keeps unicode text", () => {
    expect(tabName("   " + "a".repeat(32) + "b   ", "Old")).toBe("a".repeat(32))
    expect(tabName("  Tổng quan  ", "Old")).toBe("Tổng quan")
  })
})

describe("duplicateAfter", () => {
  it("inserts a copy right after the source and returns its id", () => {
    const all = [ws("a"), ws("b"), ws("c")]
    const out = duplicateAfter(all, "b")
    expect(out).not.toBeNull()
    const { next, id } = out!
    expect(next).toHaveLength(4)
    expect(next.map((w) => w.id).slice(0, 2)).toEqual(["a", "b"])
    expect(next[2].id).toBe(id)
    expect(next[3].id).toBe("c")
    expect(next[2].name).toBe("b copy")
    expect(next[2].layout).toBe("2")
  })

  it("gives the workspace and every non-null slot a fresh id, keeping the config", () => {
    const src = ws("a", "Alpha", [panel("p0"), null, { ...panel("p2"), lens: "liquidity", tf: "1h" }])
    const { next, id } = duplicateAfter([src], "a")!
    const copy = next[1]
    expect(id).not.toBe("a")
    expect(copy.slots).toHaveLength(3)
    expect(copy.slots[1]).toBeNull()
    expect(copy.slots[0]!.id).not.toBe("p0")
    expect(copy.slots[2]!.id).not.toBe("p2")
    expect(copy.slots[0]!.id).not.toBe(copy.slots[2]!.id)
    expect(copy.slots[2]).toMatchObject({ lens: "liquidity", tf: "1h", days: 90, period: "week" })
  })

  it("does not change the source or the list passed in", () => {
    const all = [ws("a"), ws("b")]
    const before = JSON.stringify(all)
    const { next } = duplicateAfter(all, "a")!
    expect(JSON.stringify(all)).toBe(before)
    expect(next[0]).toEqual(all[0])
    expect(next[0].slots[0]!.id).toBe("a-p0")
  })

  it("caps the copy name at 32 characters", () => {
    const { next } = duplicateAfter([ws("a", "n".repeat(32))], "a")!
    expect(next[1].name).toHaveLength(32)
    expect(next[1].name).toBe("n".repeat(32))
    const short = duplicateAfter([ws("a", "n".repeat(20))], "a")!.next[1].name
    expect(short).toBe(`${"n".repeat(20)} copy`)
  })

  it("duplicating the last tab appends it", () => {
    const { next, id } = duplicateAfter([ws("a"), ws("b")], "b")!
    expect(next.map((w) => w.id)).toEqual(["a", "b", id])
  })

  it("returns null for an unknown id or an empty list", () => {
    expect(duplicateAfter([ws("a")], "zzz")).toBeNull()
    expect(duplicateAfter([], "a")).toBeNull()
  })

  it("two copies of the same tab get different ids", () => {
    const first = duplicateAfter([ws("a")], "a")!
    const second = duplicateAfter(first.next, "a")!
    expect(second.id).not.toBe(first.id)
  })
})

describe("closeTarget", () => {
  it("opens the right neighbour when the active tab closes", () => {
    expect(closeTarget(["a", "b", "c"], "a", "a")).toBe("b")
    expect(closeTarget(["a", "b", "c"], "b", "b")).toBe("c")
  })

  it("opens the left neighbour when the closing tab is last", () => {
    expect(closeTarget(["a", "b", "c"], "c", "c")).toBe("b")
    expect(closeTarget(["a", "b"], "b", "b")).toBe("a")
  })

  it("returns null when the closing tab is not the active one", () => {
    expect(closeTarget(["a", "b", "c"], "b", "a")).toBeNull()
    expect(closeTarget(["a", "b", "c"], "a", "c")).toBeNull()
  })

  it("returns null for the only tab", () => {
    expect(closeTarget(["a"], "a", "a")).toBeNull()
  })

  it("returns null for an unknown closing id", () => {
    expect(closeTarget(["a", "b"], "zzz", "zzz")).toBeNull()
  })
})

describe("tabKey", () => {
  const ids = ["a", "b", "c"]

  it("ArrowRight and ArrowLeft move one tab", () => {
    expect(tabKey(ids, "a", "ArrowRight")).toBe("b")
    expect(tabKey(ids, "c", "ArrowLeft")).toBe("b")
  })

  it("wraps around at both ends", () => {
    expect(tabKey(ids, "c", "ArrowRight")).toBe("a")
    expect(tabKey(ids, "a", "ArrowLeft")).toBe("c")
  })

  it("Home and End jump to the first and last tab", () => {
    expect(tabKey(ids, "b", "Home")).toBe("a")
    expect(tabKey(ids, "b", "End")).toBe("c")
    expect(tabKey(ids, "a", "Home")).toBe("a")
    expect(tabKey(ids, "c", "End")).toBe("c")
  })

  it("with a single tab every navigation key stays on it", () => {
    expect(tabKey(["a"], "a", "ArrowRight")).toBe("a")
    expect(tabKey(["a"], "a", "ArrowLeft")).toBe("a")
    expect(tabKey(["a"], "a", "Home")).toBe("a")
    expect(tabKey(["a"], "a", "End")).toBe("a")
  })

  it("returns null for any other key", () => {
    expect(tabKey(ids, "a", "Enter")).toBeNull()
    expect(tabKey(ids, "a", "ArrowDown")).toBeNull()
    expect(tabKey(ids, "a", "a")).toBeNull()
    expect(tabKey(ids, "a", "")).toBeNull()
  })

  it("returns null for an empty list", () => {
    expect(tabKey([], "a", "ArrowRight")).toBeNull()
  })
})
