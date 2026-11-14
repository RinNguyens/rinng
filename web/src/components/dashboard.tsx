import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { ArrowDownRight01Icon, ArrowUpRight01Icon, Maximize01Icon } from "@hugeicons/core-free-icons"
import { ChartView } from "@/components/chart-view"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import type { Summary, WeekProfile } from "@/lib/api"
import { SyncGroup } from "@/lib/chart-sync"
import { fmtVol } from "@/lib/overlay"
import { PRESETS, fromPreset } from "@/lib/workspaces"
import type { PanelCfg } from "@/lib/workspaces"
import { cn } from "@/lib/utils"

// ----------------------------------------------------------------- định dạng

const num = (v: number, d = 0) =>
  v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
const price = (v: number | null | undefined) =>
  v == null ? "—" : num(v, v >= 1000 ? 1 : v >= 1 ? 2 : 5)
const pct = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : `${v >= 0 ? "+" : "−"}${num(Math.abs(v), d)}%`

function ago(t: number) {
  const s = Date.now() / 1000 - t
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} phút trước`
  if (s < 86400) return `${Math.round(s / 3600)} giờ trước`
  return `${Math.round(s / 86400)} ngày trước`
}

const tone = (v: number | null | undefined) =>
  v == null ? "text-muted-foreground" : v >= 0 ? "text-up" : "text-down"

// ----------------------------------------------------------------- khối dùng chung

function Delta({ v, label }: { v: number | null; label: string }) {
  return (
    <span className={cn("inline-flex items-center gap-0.5 font-heading text-xs", tone(v))}>
      <HugeiconsIcon
        icon={v != null && v < 0 ? ArrowDownRight01Icon : ArrowUpRight01Icon}
        className="size-3.5"
      />
      {pct(v)}
      <span className="ml-1 text-muted-foreground">{label}</span>
    </span>
  )
}

function Stat({ label, value, sub, className }: { label: string; value: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <Card size="sm" className={cn("gap-1.5", className)}>
      <CardContent className="space-y-1.5">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="font-heading text-xl font-medium tabular-nums">{value}</div>
        {sub ? <div className="space-y-0.5 text-xs text-muted-foreground">{sub}</div> : null}
      </CardContent>
    </Card>
  )
}

function Sparkline({ values }: { values: Array<number> }) {
  if (values.length < 2) return null
  const w = 320
  const h = 64
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const k = hi > lo ? h / (hi - lo) : 0
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - (v - lo) * k])
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("")
  const up = values[values.length - 1] >= values[0]
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={cn("h-16 w-full", up ? "text-up" : "text-down")}>
      <defs>
        <linearGradient id="spark" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.25" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d}L${w},${h}L0,${h}Z`} fill="url(#spark)" />
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

// Thanh vị trí: giá đang ở đâu giữa hai mốc.
function RangeBar({
  lo,
  hi,
  value,
  mid,
  loLabel,
  hiLabel,
}: {
  lo: number
  hi: number
  value: number
  mid?: number | null
  loLabel: string
  hiLabel: string
}) {
  const span = hi - lo || 1
  const at = Math.min(1, Math.max(0, (value - lo) / span))
  const outside = value < lo || value > hi
  return (
    <div className="space-y-1.5">
      <div className="relative h-2 rounded-full bg-gradient-to-r from-up/35 via-muted to-down/35">
        {mid != null ? (
          <span
            className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-foreground/40"
            style={{ left: `${((mid - lo) / span) * 100}%` }}
          />
        ) : null}
        <span
          className={cn(
            "absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card",
            outside ? "bg-primary" : "bg-foreground",
          )}
          style={{ left: `${at * 100}%` }}
        />
      </div>
      <div className="flex justify-between font-heading text-[11px] text-muted-foreground">
        <span>{loLabel}</span>
        <span>{hiLabel}</span>
      </div>
    </div>
  )
}

function Row({ k, v, className }: { k: string; v: ReactNode; className?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{k}</span>
      <span className={cn("font-heading tabular-nums", className)}>{v}</span>
    </div>
  )
}

const SHAPES: Record<WeekProfile["shape"], { name: string; read: string; cls: string }> = {
  D: { name: "D", read: "Cân bằng: hai bên chấp nhận giá quanh POC", cls: "bg-muted text-foreground" },
  P: { name: "P", read: "Lệch trên: volume dồn ở vùng giá cao", cls: "bg-up/20 text-up" },
  b: { name: "b", read: "Lệch dưới: volume dồn ở vùng giá thấp", cls: "bg-down/20 text-down" },
  DD: { name: "DD", read: "Hai vùng giá trị: thị trường dời chỗ giữa kỳ", cls: "bg-chart-5/25 text-foreground" },
}

function ShapeTile({ p, label }: { p: WeekProfile | null; label: string }) {
  if (!p) return null
  const s = SHAPES[p.shape]
  return (
    <div className="flex items-start gap-3 rounded-xl bg-muted/50 p-2.5">
      <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg font-heading text-sm font-semibold", s.cls)}>
        {s.name}
      </span>
      <div className="min-w-0 space-y-0.5">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-xs leading-snug">{s.read}</div>
        <div className={cn("font-heading text-[11px]", tone(p.delta))}>delta {fmtVol(p.delta)}</div>
      </div>
    </div>
  )
}

// Thẻ bối cảnh: tiêu đề + khung thời gian + nút mở chart lớn.
function Context({
  title,
  tf,
  children,
  onOpen,
  className,
}: {
  title: string
  tf: string
  children: ReactNode
  onOpen: () => void
  className?: string
}) {
  return (
    <Card size="sm" className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          {title}
          <Badge variant="outline" className="font-heading text-[10px]">
            {tf}
          </Badge>
        </CardTitle>
        <CardAction>
          <Button variant="ghost" size="xs" onClick={onOpen}>
            <HugeiconsIcon icon={Maximize01Icon} data-icon="inline-start" />
            Xem chart
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  )
}

// ----------------------------------------------------------------- dashboard

export function Dashboard({ symbol, exchange }: { symbol: string; exchange: string }) {
  const [s, setS] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<{ title: string; cfg: PanelCfg } | null>(null)
  const [sync] = useState(() => new SyncGroup())

  useEffect(() => {
    let alive = true
    setS(null)
    setError(null)
    api
      .summary({ symbol, exchange })
      .then((d) => alive && setS(d))
      .catch((e: Error) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [symbol, exchange])

  const show = (i: number, over: Partial<PanelCfg> = {}) =>
    setOpen({ title: PRESETS[i].title, cfg: { ...fromPreset(PRESETS[i]), ...over } })

  if (error) {
    return <div className="grid flex-1 place-items-center text-sm text-destructive">{error}</div>
  }
  if (!s) {
    return (
      <div className="grid grid-cols-12 gap-3">
        {Array.from({ length: 10 }, (_, i) => (
          <Skeleton key={i} className={cn("h-36 rounded-2xl", i === 0 ? "col-span-4" : i < 5 ? "col-span-2" : "col-span-4")} />
        ))}
      </div>
    )
  }

  const { price: p, derivatives: d, structure: st, profile: pr, liquidity: lq, wyckoff: wy, momentum: m } = s
  const close = p.close
  const ref = pr.previous ?? pr.current
  const where = { above: "trên", inside: "trong", below: "dưới" } as const

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pb-2">
      {/* ------------------------------------------------ hàng số liệu */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6 xl:grid-cols-12">
        <Card size="sm" className="col-span-2 md:col-span-6 xl:col-span-4">
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{symbol}</span>
              <Badge variant="secondary" className="text-[10px] capitalize">
                {exchange}
              </Badge>
              <span className="ml-auto font-heading">nến 1H đóng {ago(p.time + 3600)}</span>
            </div>
            <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
              <div className="font-heading text-4xl font-medium tracking-tight tabular-nums">{price(close)}</div>
              <div className="flex flex-col gap-0.5 pb-1">
                <Delta v={p.chg_24h} label="24h" />
                <Delta v={p.chg_7d} label="7 ngày" />
              </div>
            </div>
            <Sparkline values={p.spark} />
            <div className="flex justify-between font-heading text-[11px] text-muted-foreground">
              <span>Thấp 24h {price(p.low_24h)}</span>
              <span>Cao 24h {price(p.high_24h)}</span>
            </div>
          </CardContent>
        </Card>

        <Stat
          className="xl:col-span-2 md:col-span-2"
          label="Funding (mỗi 8h)"
          value={<span className={tone(d.funding?.rate_pct)}>{d.funding ? `${num(d.funding.rate_pct, 4)}%` : "—"}</span>}
          sub={
            d.funding ? (
              <>
                <div>≈ {pct(d.funding.annual_pct, 1)} / năm</div>
                <div>TB 7 ngày {num(d.funding.avg_7d_pct, 4)}%</div>
                <div className="pt-1 text-[11px] leading-snug">Dương: bên long trả phí cho bên short.</div>
              </>
            ) : (
              "chưa có dữ liệu"
            )
          }
        />
        <Stat
          className="xl:col-span-2 md:col-span-2"
          label="Open interest"
          value={d.oi ? `${num(d.oi.base)} ${symbol.split("-")[0]}` : "—"}
          sub={
            d.oi ? (
              <>
                {d.oi.value ? <div>≈ ${fmtVol(d.oi.value, false)}</div> : null}
                <Delta v={d.oi.chg_24h} label="24h" />
                <br />
                <Delta v={d.oi.chg_7d} label="7 ngày" />
              </>
            ) : (
              "chưa có dữ liệu"
            )
          }
        />
        <Stat
          className="xl:col-span-2 md:col-span-2"
          label="Tài khoản long / short"
          value={d.ls ? num(d.ls.ratio, 2) : "—"}
          sub={
            d.ls ? (
              <div className="space-y-1.5 pt-0.5">
                <div className="flex h-1.5 overflow-hidden rounded-full">
                  <span className="bg-up" style={{ width: `${d.ls.long_pct}%` }} />
                  <span className="flex-1 bg-down" />
                </div>
                <div className="flex justify-between font-heading text-[11px]">
                  <span className="text-up">long {num(d.ls.long_pct, 1)}%</span>
                  <span className="text-down">short {num(100 - d.ls.long_pct, 1)}%</span>
                </div>
                <div className="text-[11px] leading-snug">Tỷ lệ số tài khoản, không phải khối lượng.</div>
              </div>
            ) : (
              "chưa có dữ liệu"
            )
          }
        />
        <Stat
          className="xl:col-span-2 md:col-span-2 col-span-2"
          label="Delta taker 24h"
          value={<span className={tone(p.delta_24h)}>{fmtVol(p.delta_24h)}</span>}
          sub={
            <>
              <div>Volume 24h {fmtVol(p.volume_24h, false)}</div>
              <div>Mua chủ động − bán chủ động ({num((Math.abs(p.delta_24h) / p.volume_24h) * 100, 1)}% volume)</div>
            </>
          }
        />
      </div>

      {/* ------------------------------------------------ bối cảnh */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Context title="Cấu trúc thị trường" tf="4H" onOpen={() => show(0)}>
          <div className="flex items-center gap-2">
            <Badge className={cn(st.trend === "up" ? "bg-up/20 text-up" : st.trend === "down" ? "bg-down/20 text-down" : "")}>
              {st.trend === "up" ? "Xu hướng tăng" : st.trend === "down" ? "Xu hướng giảm" : "Chưa rõ"}
            </Badge>
            {st.last_break ? (
              <span className="text-xs text-muted-foreground">
                {st.last_break.kind} tại {price(st.last_break.price)} · {ago(st.last_break.time)}
              </span>
            ) : null}
          </div>
          {st.range_low != null && st.range_high != null ? (
            <>
              <RangeBar
                lo={st.range_low}
                hi={st.range_high}
                mid={st.equilibrium}
                value={close}
                loLabel={`discount ${price(st.range_low)}`}
                hiLabel={`premium ${price(st.range_high)}`}
              />
              <p className="text-xs text-muted-foreground">
                {close < st.range_low
                  ? "Giá đang nằm dưới dải swing gần nhất."
                  : close > st.range_high
                    ? "Giá đang nằm trên dải swing gần nhất."
                    : `Giá đang ở nửa ${st.zone === "premium" ? "premium (đắt)" : "discount (rẻ)"} của dải.`}
              </p>
            </>
          ) : null}
          <Row k="Order block còn hiệu lực" v={<><span className="text-up">{st.active_ob.bull} tăng</span> · <span className="text-down">{st.active_ob.bear} giảm</span></>} />
        </Context>

        <Context title="Volume profile tuần" tf="1H" onOpen={() => show(2)}>
          <div className="grid gap-2">
            <ShapeTile p={pr.current} label="Tuần này (đang chạy)" />
            <ShapeTile p={pr.previous} label="Tuần trước" />
          </div>
          {ref ? (
            <>
              <Row k="POC tuần trước" v={price(ref.poc)} className="text-[#ff9800]" />
              <Row k="Value area" v={`${price(ref.val)} – ${price(ref.vah)}`} />
              <Row
                k="Giá so với VA tuần trước"
                v={pr.price_vs_prev_va ? where[pr.price_vs_prev_va] : "—"}
                className={pr.price_vs_prev_va === "above" ? "text-up" : pr.price_vs_prev_va === "below" ? "text-down" : ""}
              />
            </>
          ) : null}
        </Context>

        <Context title="Thanh khoản gần nhất" tf="1H" onOpen={() => show(1)}>
          <div className="space-y-1.5">
            <Ladder label="BSL phía trên" value={lq.bsl} dist={lq.bsl_dist_pct} cls="text-up" />
            <div className="flex items-center gap-2 rounded-lg bg-muted/60 px-2.5 py-1.5">
              <span className="text-xs text-muted-foreground">Giá hiện tại</span>
              <span className="ml-auto font-heading text-sm tabular-nums">{price(close)}</span>
            </div>
            <Ladder label="SSL phía dưới" value={lq.ssl} dist={lq.ssl_dist_pct} cls="text-down" />
          </div>
          <Row
            k="Sweep gần nhất"
            v={lq.last_sweep ? `${lq.last_sweep.kind} · ${ago(lq.last_sweep.time)}` : "—"}
          />
        </Context>

        <Context title="Động lượng" tf="4H" onOpen={() => show(6)}>
          {m.rsi != null ? <Rsi v={m.rsi} /> : null}
          <div className="flex flex-wrap gap-1.5">
            {(["21", "50", "200"] as const).map((k) => {
              const above = m.above_ema.includes(k)
              return (
                <Badge key={k} variant="outline" className={cn("font-heading text-[11px]", above ? "text-up" : "text-down")}>
                  {above ? "trên" : "dưới"} EMA {k} · {price(m.ema[k])}
                </Badge>
              )
            })}
          </div>
          <Row
            k="MACD histogram"
            v={m.macd_hist == null ? "—" : `${m.macd_hist >= 0 ? "dương" : "âm"} (${num(m.macd_hist, 1)})`}
            className={tone(m.macd_hist)}
          />
        </Context>

        <Context title="Wyckoff" tf="1D" onOpen={() => show(4)}>
          <Row
            k="Sự kiện gần nhất"
            v={wy.last_event ? `${wy.last_event.kind} · ${ago(wy.last_event.time)}` : "—"}
          />
          {wy.in_range ? (
            <RangeBar
              lo={wy.in_range.low}
              hi={wy.in_range.high}
              value={close}
              loLabel={price(wy.in_range.low)}
              hiLabel={price(wy.in_range.high)}
            />
          ) : (
            <p className="text-xs text-muted-foreground">Không có trading range nào đang mở trên khung ngày.</p>
          )}
          <p className="text-xs text-muted-foreground">
            SC/BC: cao trào bán/mua. Spring/UT: phá giả đáy/đỉnh range.
          </p>
        </Context>

        <Context title="Phái sinh & CVD" tf="1H" onOpen={() => show(5)}>
          <Row k="Funding" v={d.funding ? `${num(d.funding.rate_pct, 4)}%` : "—"} className={tone(d.funding?.rate_pct)} />
          <Row k="OI 24h" v={pct(d.oi?.chg_24h)} className={tone(d.oi?.chg_24h)} />
          <Row k="Giá 24h" v={pct(p.chg_24h)} className={tone(p.chg_24h)} />
          <p className="text-xs leading-snug text-muted-foreground">{readOiPrice(p.chg_24h, d.oi?.chg_24h)}</p>
        </Context>
      </div>

      {/* ------------------------------------------------ chart nhanh */}
      <div className="grid min-h-[420px] grid-cols-1 gap-3 xl:grid-cols-2">
        <QuickChart title="Cấu trúc SMC · 4H" cfg={fromPreset(PRESETS[0])} symbol={symbol} exchange={exchange} sync={sync} />
        <QuickChart title="Volume profile tuần · 4H" cfg={fromPreset(PRESETS[2])} symbol={symbol} exchange={exchange} sync={sync} />
      </div>

      <p className="px-1 text-[11px] text-muted-foreground">
        Số liệu mô tả trạng thái thị trường từ dữ liệu đã đóng nến; không phải khuyến nghị giao dịch.
      </p>

      <Dialog open={open != null} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="flex h-[85vh] w-[min(1400px,95vw)] max-w-none flex-col sm:max-w-none">
          <DialogHeader>
            <DialogTitle>{open?.title}</DialogTitle>
          </DialogHeader>
          {open ? <ChartView cfg={open.cfg} symbol={symbol} exchange={exchange} /> : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function Ladder({ label, value, dist, cls }: { label: string; value: number | null; dist: number | null; cls: string }) {
  return (
    <div className="flex items-center gap-2 px-2.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("ml-auto font-heading text-sm tabular-nums", cls)}>{price(value)}</span>
      <span className="w-16 text-right font-heading text-[11px] text-muted-foreground">{pct(dist)}</span>
    </div>
  )
}

function Rsi({ v }: { v: number }) {
  const state = v >= 70 ? "quá mua" : v <= 30 ? "quá bán" : "trung tính"
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-muted-foreground">RSI 14</span>
        <span className={cn("font-heading text-lg tabular-nums", v >= 70 ? "text-down" : v <= 30 ? "text-up" : "")}>
          {num(v, 1)} <span className="text-xs text-muted-foreground">{state}</span>
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-muted">
        <span className="absolute inset-y-0 left-0 w-[30%] rounded-l-full bg-up/25" />
        <span className="absolute inset-y-0 right-0 w-[30%] rounded-r-full bg-down/25" />
        <span
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground ring-2 ring-card"
          style={{ left: `${Math.min(100, Math.max(0, v))}%` }}
        />
      </div>
    </div>
  )
}

// Bốn tổ hợp giá/OI quen thuộc, chỉ để đọc nhanh, không kết luận.
function readOiPrice(dp: number | null, doi: number | null | undefined) {
  if (dp == null || doi == null) return "Thiếu dữ liệu OI để đọc tổ hợp giá/OI."
  if (dp >= 0 && doi >= 0) return "Giá tăng, OI tăng: vị thế mới được mở theo chiều tăng."
  if (dp >= 0 && doi < 0) return "Giá tăng, OI giảm: phần lớn là short đóng vị thế (short covering)."
  if (dp < 0 && doi >= 0) return "Giá giảm, OI tăng: vị thế mới được mở theo chiều giảm."
  return "Giá giảm, OI giảm: phần lớn là long đóng vị thế (long liquidation/chốt)."
}

function QuickChart({
  title,
  cfg,
  symbol,
  exchange,
  sync,
}: {
  title: string
  cfg: PanelCfg
  symbol: string
  exchange: string
  sync: SyncGroup
}) {
  const [c] = useState(cfg)
  return (
    <div className="flex min-h-[420px] flex-col overflow-hidden rounded-2xl bg-card ring-1 ring-foreground/10">
      <div className="border-b border-foreground/10 px-3 py-2 text-sm font-medium">{title}</div>
      <ChartView cfg={c} symbol={symbol} exchange={exchange} sync={sync} />
    </div>
  )
}
