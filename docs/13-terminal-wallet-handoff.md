# 13 — Handoff spec: Terminal sections and Security Wallet

Written 2026-11-17. Scope: the `/terminal` app in `web/` (React 19, TanStack Router, Tailwind 4,
shadcn on Base UI, lightweight-charts). The landing page (`/`) is done and out of scope except where
the wallet check is shared.

No Figma file exists for this; the spec is written from the shipped code. Where this document names a
class (`gap-3`, `text-up`), it is the token to use; pixel values are given only to make intent clear.

---

## 0. Where things stand

| Area | Today | Gap |
|---|---|---|
| Terminal shell | `routes/terminal.tsx`: one `Pick` dropdown mixes "Dashboard" with N chart workspaces; `active` tab lives in React state only | Tabs are not in the URL (no deep link, no back button). Dashboard and chart tabs are different *kinds* of page squeezed into one list |
| Dashboard | `components/dashboard.tsx`: one coin — stats row, live desk, news, projection, 2 quick charts | No market-wide view ("what is moving?"). The 2 quick charts duplicate what chart tabs do |
| Chart tabs | `lib/workspaces.ts` + `workspace-grid.tsx` + `chart-library.tsx` + `lib/combos.ts` | Fine. Needs a real tab strip instead of the dropdown |
| Wallet check | Only on the landing page: `components/landing/wallet-section.tsx`, engine in `lib/scan.ts`, `lib/score.ts`, `lib/multichain.ts`, `lib/address.ts`, `lib/guard.ts` | One address, one network at a time, nothing saved, no revoke plan, `checkAddress()` (pre-send check) and `blockedRequests()` (signature lock log) have no UI at all |

What we keep: every analysis engine and the read-only rule. **rinng never signs, sends or holds a key.**
Every wallet feature below is read-only; "fixing" a finding always hands off to the user's wallet via an
external link (revoke.cash or the chain explorer).

---

## 1. Information architecture

### 1.1 The four sections

Split by the question the user is asking, not by data source:

| Section | Question | Scope | Context bar |
|---|---|---|---|
| **Market** | "What is moving across all perps right now?" | All instruments on one exchange | Exchange only |
| **Coin** | "What is the state of *this* coin?" | One instrument | Coin + exchange + live |
| **Charts** | "Let me read this coin through my own chart layouts." | One instrument, user tabs | Coin + exchange + live + layout tools |
| **Wallet** | "Is my wallet safe, and is this address safe to send to?" | Wallet addresses | Wallet / lock status (no coin) |

Why four and not more: Derivatives, news and projection are *about one coin*, so they live inside Coin
rather than as their own sections. Revoking is an action *on a scan result*, so it lives inside Scan,
not as a fifth section. Market → Coin → Charts is the natural drill-down (wide → one coin → deep), and the
order of the nav follows it. Wallet is separate because it shares no context with the other three.

### 1.2 Sub-tabs

| Section | Sub-tabs | Notes |
|---|---|---|
| Market | none (one page; filters are chips) | |
| Coin | none | |
| Charts | the user's workspaces (`Overview`, `Top-down structure`, …) | Editable: add, rename, close, restore defaults |
| Wallet | `Scan` · `Watchlist` · `Send check` · `Lock` | Fixed |

### 1.3 Routes

All state that changes what is on screen goes in the URL, so a link reproduces the view and the browser
back button works.

| Route | Page | Search params |
|---|---|---|
| `/terminal` | redirects to last section visited (default `/terminal/coin`) | — |
| `/terminal/market` | Market | `ex`, `seg` (`all` \| `watch` \| `top`), `sort`, `dir` |
| `/terminal/coin` | Coin | `symbol`, `ex` |
| `/terminal/charts/$tabId` | one chart workspace | `symbol`, `ex` |
| `/terminal/wallet/scan` | Scan | `address`, `net` (network key or `evm-all`) |
| `/terminal/wallet/watch` | Watchlist | — |
| `/terminal/wallet/check` | Send check | `to`, `from` |
| `/terminal/wallet/lock` | Lock | — |

- `symbol` / `ex` are shared by Market (`ex` only), Coin and Charts. Switching section keeps them.
  When absent, fall back to `localStorage["rinng.instrument.v1"]` (existing), then `meta.instruments[0]`.
- `address` and `to` in the URL are acceptable: wallet addresses are public, and the page never sends them
  anywhere except the read-only providers already listed in `SOURCE` (`wallet-section.tsx:28`).
  Do **not** put labels, notes or anything the user typed about the address in the URL.
- Unknown `$tabId` → redirect to the first workspace (see the Slice 1 note below).
- File layout: `routes/terminal.tsx` becomes the layout route (shell + `<Outlet/>`); one file per
  section under `routes/terminal/`.

**Slice 1 (built 2026-11-17), where it differs from the table above:**
- `/terminal/charts` (no id) forwards to the first workspace; an unknown `$tabId` does the same. The
  redirect lives in `routes/terminal/charts/$tabId.tsx` (it replaces the old effect in `terminal.tsx`).
- `/terminal/wallet` is one placeholder page until slice 4 adds the sub-routes.
- The section nav is four plain `<Link>`s with the `LayoutPicker` pill look, not `TabsList` (Base UI tabs
  are buttons and need their own state; links keep middle-click and `aria-current`).
- The resolved coin is written back to the URL with `replace`, and saved to `rinng.instrument.v1` even when
  it came from a link. Pure logic is in `lib/terminal-nav.ts`, shared state in `components/terminal/context.tsx`.

---

## 2. Shell

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ NewsTicker (existing, 28px)                                                                  │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ [logo] rinng │ Market  Coin  Charts  Wallet •2 │                [● Live] [BTC ⌘K] [Binance ▾] │  ← primary bar, h-11
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ section toolbar (only Charts and Wallet have one)                                            │  ← h-9
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ <Outlet/>  (p-3, gap-3)                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Primary bar: `flex items-center gap-2 px-3 h-11`, bottom hairline `border-b border-border`.
- Section nav: `TabsList` from `components/ui/tabs.tsx`, rendered as links (`<Link>` from TanStack) so
  middle-click opens a new tab. Active: `bg-background ring-1 ring-foreground/10` on the `bg-muted` pill
  track — the same look as today's `LayoutPicker` (`terminal.tsx:296`), so the app has one segmented style.
- Wallet tab badge `•2`: count of signature requests blocked this session (`blockedRequests().length`),
  `bg-sev-high text-background`, hidden at 0. It is the only badge in the nav; a blocked request is the one
  event worth pulling the user to another section for.
- Right side changes by section:
  - Market: exchange picker only.
  - Coin, Charts: `LiveBadge`, `CoinSearch`, exchange `Pick` (all existing).
  - Wallet: connected wallet chip (`0x12ab…9f3c · Base`) or "Use my wallet" button, and the lock status dot.
- Logo goes to `/` (the landing). Today it goes to the dashboard; with real tabs that job is done by the
  nav, and the logo pointing home is what people expect.

---

## 3. Market (new)

### 3.1 Layout

```
┌ Movers 24h ───────────┐┌ Funding extremes ─────┐┌ Crowding (L/S) ───────┐┌ News outlook ─────────┐
│ ▲ PEPE   +18.2%       ││ +142% / yr   WIF      ││ 3.4  long   ORDI      ││ bullish  0.41  (63)   │
│ ▲ ...  (5 up, 5 down) ││ −88% / yr    TIA      ││ 0.6  short  ...       ││                       │
└───────────────────────┘└───────────────────────┘└───────────────────────┘└───────────────────────┘
[ All 791 ] [ Watchlist 12 ] [ Top volume 50 ]            [ Filter coins…        ]   updated 14s ago
┌───┬──────────────┬──────────┬────────┬───────────┬──────────────┬──────────┬────────┬─────────┐
│ ★ │ Coin         │ Price    │ 24h    │ Vol 24h   │ Funding / 8h │ OI       │ OI 24h │ L/S     │
├───┼──────────────┼──────────┼────────┼───────────┼──────────────┼──────────┼────────┼─────────┤
│ ★ │ ◎ BTC Bitcoin│ 91,204.1 │ +1.24% │ 12.4B     │ 0.0100%  3h  │ 8.1B     │ +2.1%  │ 1.08    │
│ ☆ │ ...          │          │        │           │              │ —        │ —      │ —       │
```

- Summary cards: `grid grid-cols-2 gap-3 xl:grid-cols-4`, each `Card size="sm"`, max 5 rows per side.
  Every row is a button that opens that coin in Coin.
- Table: full width, `font-heading tabular-nums` for every number column, right-aligned; Coin column
  left-aligned with `CoinIcon` (existing). Row height 36px (`h-9`). Header sticky.
- Click a row → `/terminal/coin?symbol=…&ex=…`. ★ toggles watchlist and does **not** navigate
  (`stopPropagation`).

### 3.2 Columns and data tiers

The backend can fetch some columns for all ~790 perps in one request per exchange, and others only per
symbol. Do not fake the second kind.

| Column | Tier | Source | Format |
|---|---|---|---|
| Price | A (all) | bulk 24h ticker | `price()` from `dashboard.tsx:29` |
| 24h % | A | bulk 24h ticker | `pct()`; `text-up` / `text-down` |
| Vol 24h | A | bulk 24h ticker (quote volume) | `fmtVol(v, false)` |
| Funding / 8h | A | Binance `premiumIndex` (all), OKX funding per inst (cached) | 4 decimals + countdown to next funding; tooltip "≈ X% / year" |
| OI, OI 24h %, L/S | B (configured instruments only) | stored by the collector (`configs/instruments.yaml`) | `—` with tooltip "Not collected for this coin. Add it to configs/instruments.yaml." |

Sort: any column, default `Vol 24h` desc. Tier-B columns sort `—` last in both directions.

### 3.3 Segments

| Chip | Rows |
|---|---|
| All | every perp on the exchange |
| Watchlist | `rinng.watchlist.v1` (shared with Coin's ★) |
| Top volume | top 50 by 24h quote volume |

Chip shows its count. Filter input matches base, name and symbol (same as `CoinSearch`).

### 3.4 Refresh

Poll `/api/market` every 30 s while the page is visible (`document.visibilityState`). Live ticks do not
stream into this table (the live hub follows one symbol); "updated 14s ago" says how fresh it is.

---

## 4. Coin (existing Dashboard, trimmed)

Keep `Dashboard` as is, with three changes:

1. Remove the two `QuickChart`s at the bottom (`dashboard.tsx:344-359`). In their place, one row of
   combo shortcuts: `Card` with the combo title + question, button "Open as chart tab" →
   `insert(comboWorkspace(c))` then navigate to `/terminal/charts/$newId`. Show `top-down`,
   `value-liquidity`, `positioning`.
   Why: the quick charts were the only charts that could not be changed; the same view one click away in
   Charts can be.
2. ★ watchlist toggle next to the coin name in the price card.
3. Order of blocks stays: stats → live desk → news → projection → combo shortcuts → disclaimer.

---

## 5. Charts (existing workspaces, new tab strip)

### 5.1 Toolbar

```
[ Overview ] [ Top-down structure ] [ Risk map ×] [ + ]   ⋯        [layout ▣▣] [⛓ sync] [📚 library]
```

- Workspace tabs: `TabsList` variant `line` (underline), one tab per `Workspace`, `max-w-48 truncate`.
- Close `×` shows on hover/focus of a tab and always on the active tab; hidden when only one tab is left
  (today's rule).
- Double-click a tab (or `F2` while focused) → inline rename `Input` `h-7`, max 32 characters, `Enter`
  saves, `Esc` cancels, empty → keeps old name.
- `+` adds a 2-slot tab (existing `add()`) and navigates to it.
- `⋯` menu (`DropdownMenu`): Rename, Duplicate, Close, separator, "Restore default tabs…". Restore opens a
  `Dialog` (not `window.confirm`): "Restore the 4 default tabs? Your N tabs will be replaced." with
  `Cancel` / destructive `Restore`.
- More tabs than fit: the strip scrolls horizontally (`overflow-x-auto`, no visible scrollbar) and the
  active tab is scrolled into view on change.
- Layout picker, sync switch, library toggle: unchanged, right-aligned.

---

## 6. Wallet (new section) — Security Wallet

Principle shown on every sub-tab, in the toolbar: a lock icon + "Read-only · rinng never asks you to
sign". Clicking it goes to Lock.

### 6.1 Scan

```
┌ address / ENS? ─────────────────────────────────────┐ [Base ▾ | All EVM] [Use my wallet] [ Scan ]
└─────────────────────────────────────────────────────┘
┌ WalletRoute (existing) ──┐┌ Score ─────────────────────────────────────────────────────────────┐
│ ● Read-only        PASS  ││  C   62/100   $4,210 can be taken today      provisional ⓘ          │
│ ● Account & 7702   PASS  ││  −20 2 unlimited approvals to unverified contracts                  │
│ ◌ Approvals    CHECKING  ││  −10 Permit2 allowance expiring in 2y …   (every lost point listed)  │
│ ○ ...                    │└────────────────────────────────────────────────────────────────────┘
│                          │┌ Findings (14) ──── [All] [High 2] [Medium 5] [Low 7]   group: none ▾┐
│                          ││ Sev  Kind    Asset   Spender                 Allowance   At risk  ↗ │
│                          ││ HIGH ERC-20  USDC    0x9a…31 · EOA           unlimited   $3,900  ↗ │
│                          ││ MED  NFT     Pudgy   Blur Pool · proxy       all items   —       ↗ │
│                          │└────────────────────────────────────────────────────────────────────┘
│                          │┌ Revoke plan ───────────────────────────────────────────────────────┐
│                          ││ ☐ 1  Revoke USDC → 0x9a…31 on Base           $3,900   revoke.cash ↗ │
│                          ││ ☑ 2  …                                                              │
│                          ││ [ Re-scan to verify ]        [Copy as Markdown] [Download JSON]     │
└──────────────────────────┘└────────────────────────────────────────────────────────────────────┘
```

**Input**
- One field accepts any family; `detectAddress()` picks the network (`lib/chains.ts:268`), the picker
  follows it (`networkFor`). Unsupported input → inline error under the field, `text-destructive text-xs`:
  "Not a wallet address rinng can read. Paste a 0x…, T…, Solana, bc1/1/3… or G… address."
- ENS names: not resolved in v1 (see §14). The hint text says "0x… address (ENS names are not resolved yet)".
- "All EVM" (new, EVM addresses only): scans the 6 EVM networks in `NETWORKS`, concurrency 2 so public dRPC
  nodes do not rate-limit us. Score becomes one per network plus a combined grade = the worst network's.
- "Use my wallet": reads the address through `useWallet()` (guarded). Never triggers anything but
  `eth_requestAccounts`.

**Progress** — reuse `WalletRoute` unchanged at `w-72` on desktop. In "All EVM" mode, show one compact row
per network above it (name, spinner / grade chip) and let the route follow the network being read.

**Score card** — grade letter `font-heading text-5xl`, colored by grade (A/B `text-pass`, C `text-sev-medium`,
D/F `text-sev-high`), score `/100`, `usdAtRisk` via `usd()`. `provisional` → `Badge variant="outline"`
"provisional" with tooltip "Part of the scan did not finish or approvals older than the lookback window were
not read. The real score can only be lower." Every `ScoreItem` listed, `−delta` in `font-heading`.

**Findings table**
| Column | Content | Rule |
|---|---|---|
| Sev | `HIGH` / `MED` / `LOW` pill (`SEV_STYLE`, re-tokenized §7) | text, never color alone |
| Kind | ERC-20, NFT, Permit2, 7702 delegate (Tron/Solana/…: the chain's own kinds) | |
| Asset | token symbol, max 12 chars then `…`, full in tooltip | |
| Spender | known label from `labelOf()` or `short()` address + copy button; tags `EOA`, `proxy`, `unknown` | an EOA spender is always shown, even with a label |
| Allowance | `amountOf()` (existing) | |
| At risk | `usdAtRisk()` or `—` + tooltip "No price for this token" | sort key in Revoke plan |
| ↗ | explorer / revoke.cash link for the network, `target=_blank rel=noopener noreferrer` | |

Filter chips by severity with counts. "Group by" menu: none / spender / network. Rows > 50 → render the first
50 and a "Show all N" button (no virtualization needed for this size).

**Revoke plan** (new) — the findings the user can act on, ordered: severity (high → low), then USD at risk
(desc), then unlimited before limited. One checkbox per item, saved under the finding's fingerprint
(§12) so the plan survives reloads. Checking an item does not mean it is revoked — label the checkbox
"I revoked this", and the only way to clear an item for real is "Re-scan to verify", which re-runs the scan
and marks items that disappeared as `Verified` (`text-pass`), and items still present but checked as
`Still live` (`text-sev-medium`). Export: "Copy as Markdown" (clipboard) and "Download JSON" (a local Blob,
nothing uploaded).

### 6.2 Watchlist (new)

Saved wallets the user wants to re-check. Stored in the browser only.

```
[ + Add wallet ]                                                              [ Re-scan all ]
┌ Label        Address          Network     Grade  Score  At risk   New since last   Scanned    ┐
│ Main         0x12ab…9f3c      All EVM     B      84     $120      —                2h ago   ⋯ │
│ Cold BTC     bc1q…8k2d        Bitcoin     A      97     —         —                3d ago   ⋯ │
│ Hot Base     0x77…01aa        Base        D      41     $2,310    +2 HIGH          5m ago   ⋯ │
```

- Add: dialog with Address (required), Label (optional, max 24 chars, default `short(address)`), Network
  (auto). Duplicate address+network → inline error "Already in your watchlist".
- "New since last": diff of finding fingerprints between the last two snapshots. `+N HIGH` in
  `text-sev-high`; `+N` (lower severities) in `text-muted-foreground`; removed findings `−N` in `text-pass`.
  Click → opens Scan for that wallet with the new findings highlighted (`bg-sev-high/10` row tint).
- "Re-scan all": sequential per wallet, concurrency 2, row shows a spinner while its scan runs.
- Row `⋯`: Scan now, Rename, Remove (confirm dialog).
- Snapshot kept per wallet: last 2 `{ at, score, grade, usdAtRisk, fingerprints[] }`. Not the full findings.
- Max 20 wallets (public RPC budget); at 20 the Add button is disabled with tooltip "20 wallets is the limit".

### 6.3 Send check (new — UI for `checkAddress()`)

"Before you send: is this the address you mean?"

```
To   ┌───────────────────────────────────────────────────────────┐
     └───────────────────────────────────────────────────────────┘
From [ Main · 0x12ab…9f3c ▾ ]   (saved wallet, connected wallet, or none)        [ Check ]

┌ ⚠ Review before sending ─────────────────────────────────────────────────────────────────────┐
│  0x9a3F 1c22 …  … 77e1 b031                                                                    │
│  0x9a3F 1c22 …  … 77e1 b0E1   ← you sent to this one 3 times; they share the first 4 and      │
│                                   last 3 characters                                           │
│  • This address appears in your history only as an incoming 0-value transfer (poisoning).     │
│  • It is a contract, not a wallet. Sending a token straight to a contract can lose it.        │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Verdict banner, three states (never the word "safe"):
  | `severity` | Title | Token |
  |---|---|---|
  | `ok` | "No problems found" | `border-pass` |
  | `low` / `medium` | "Review before sending" | `border-sev-medium` |
  | `high` | "Do not send to this address" | `border-sev-high bg-sev-high/10` |
- Each `notes[]` entry is one bullet. Add on-chain facts when a client is available: contract or EOA, token
  contract (sending to a token's own address), burn address (`BURN` set), wrong family for the From wallet.
- Address rendering: **full address, never shortened**, in groups of 4, `font-heading text-base
  tracking-wide`. When a look-alike exists, show it on the next line and mark differing characters with
  `bg-sev-high/25 text-foreground rounded-sm`.
- From = none → only offline checks run; the banner says "Pick your wallet to compare against your
  transfer history" as a hint, not an error.

### 6.4 Lock (new — UI for `guard.ts`)

```
┌ Signature lock ───────────────────────────── ● Locked ┐┌ Blocked this session (2) ─────────────┐
│ Wallet: MetaMask (window.ethereum)                    ││ 14:02:11  eth_sendTransaction          │
│ Allowed methods (11): eth_accounts, eth_chainId, …    ││ 14:02:11  wallet_switchEthereumChain   │
│ What this covers / what it does not  ▸                ││                                        │
└───────────────────────────────────────────────────────┘└────────────────────────────────────────┘
```

- Status from `pageLock().status` (`guard.ts:66`):
  | `status` | Label | Token | Explanation line |
  |---|---|---|---|
  | `locked` | Locked | `text-pass` | "window.ethereum points at rinng's lock and cannot be reassigned." |
  | `wrapped` | Partly locked | `text-sev-medium` | "Your wallet pinned window.ethereum. rinng's own requests are locked; other scripts on this page are not." |
  | `absent` | No wallet in this browser | `text-muted-foreground` | "Nothing to lock. Scans read public data." |
- Allowed methods: `ALLOWED_METHODS`, as `Badge variant="secondary"` chips, `font-heading text-[11px]`.
- "What this covers": collapsible, text adapted from the comment at the top of `guard.ts` (rinng's code and
  `window.ethereum` scripts; not a sandbox; EIP-6963; the wallet's own confirmation screen is the last line).
- Blocked list: subscribe with `onBlocked()`; newest first; method in `font-heading`, time `HH:mm:ss`.
  Empty: "Nothing has tried to sign. Requests other than reads would be listed here."

---

## 7. Design tokens

### 7.1 Existing (use as is)

| Token / class | Value | Usage |
|---|---|---|
| `bg-background` | `--background` dark `oklch(0.147 0.004 49.3)` | page |
| `bg-card` + `ring-1 ring-foreground/10` | `--card` | every panel |
| `bg-muted` | `--muted` | segmented track, chips |
| `text-muted-foreground` | `--muted-foreground` | labels, secondary text |
| `text-up` / `text-down` | `--up` / `--down` | **price direction only** |
| `text-destructive` | `--destructive` | input/validation errors |
| `text-chart-1…5` | `--chart-*` | chart series |
| `font-sans` | Space Grotesk Variable | UI text |
| `font-heading` | Geist Mono Variable | every number, address, method name |
| `rounded-xl` | `calc(var(--radius) * 1.4)` ≈ 14px | cards |
| `rounded-4xl` | ≈ 26px | pills, segmented tracks |
| `gap-3` / `p-3` | 12px | between cards / page gutter |
| `text-xs` 12 / `text-sm` 14 / `text-xl` 20 / `text-4xl` 36 | | label / body / stat value / hero price |

### 7.2 New (add to `styles.css`, `:root` and `.dark`, and to `@theme inline`)

The landing's wallet check hard-codes hex values (`wallet-section.tsx:101-121`). Move them to tokens and use
them in both places.

| Token | Dark value | Usage |
|---|---|---|
| `--sev-high` → `text-sev-high`, `bg-sev-high` | `#ff5c4d` | HIGH findings, "Do not send", nav badge |
| `--sev-medium` | `#f2c94c` | MEDIUM findings, "Review", provisional, lock "Partly locked" |
| `--sev-low` | `#2a2a2a` bg / `#cfcfcf` text | LOW pill |
| `--pass` | `#4ade80` | PASS, verified, grade A/B, locked |
| `--progress` | `#5b7cff` | step being checked, spinners in wallet |

Why separate from `--up` / `--down`: red on the Market page means "price fell", red in Wallet means "someone
can take your money". Same hue, different meaning, so a different token; if the palette changes later the
two can drift apart safely. Light values (for the landing `.hub`): darken each ~15% L so text passes 4.5:1
on `oklch(0.993 0.002 30)`; verify with a contrast check when implementing.

---

## 8. Components

| Component | File | Variant / props | Notes |
|---|---|---|---|
| `TerminalShell` | `routes/terminal.tsx` (layout) | — | NewsTicker, primary bar, `<Outlet/>` |
| `SectionNav` | `components/terminal/section-nav.tsx` | `blocked: number` | `TabsList` as links |
| `ContextBar` | `components/terminal/context-bar.tsx` | `section` | right side of primary bar per §2 |
| `MarketPage` | `routes/terminal/market.tsx` | — | |
| `MarketTable` | `components/market/market-table.tsx` | `rows, sort, onSort, watch, onToggleWatch` | `<table>`, sticky header |
| `MoverCard` | `components/market/mover-card.tsx` | `title, rows, format` | 4 instances |
| `ComboShortcuts` | `components/combo-shortcuts.tsx` | `ids: string[]` | replaces QuickCharts in Coin |
| `WorkspaceTabs` | `components/workspace-tabs.tsx` | `workspaces, active, onRename, onClose, onAdd, onReset` | §5 |
| `WalletToolbar` | `components/wallet/toolbar.tsx` | — | sub-tabs + read-only chip |
| `ScanPanel` | `components/wallet/scan-panel.tsx` | `address, net` | owns the scan; reuses `WalletRoute` |
| `ScoreCard` | `components/wallet/score-card.tsx` | `score: Score` | |
| `FindingsTable` | `components/wallet/findings-table.tsx` | `findings, prices, highlight?: Set<string>` | |
| `RevokePlan` | `components/wallet/revoke-plan.tsx` | `findings, network, onRescan` | |
| `WatchlistTable` | `components/wallet/watchlist.tsx` | — | |
| `SendCheck` | `components/wallet/send-check.tsx` | — | |
| `AddressChunks` | `components/wallet/address-chunks.tsx` | `address, compare?: string` | groups of 4, diff marks |
| `LockPanel` | `components/wallet/lock-panel.tsx` | — | |
| `SevPill` | `components/wallet/sev-pill.tsx` | `severity` | shared with landing |

Move shared wallet pieces out of `components/landing/` (`WalletRoute`, `NetworkPicker`, `amountOf`,
`STEPS`, `planFor`, `verdicts`) into `components/wallet/` and import them from the landing, so there is one
scan UI logic. The landing keeps its own visual frame.

---

## 9. States and interactions

| Element | State | Behavior |
|---|---|---|
| Section tab | hover | `bg-background/50` (as `LayoutPicker`) |
| Section tab | active | `bg-background ring-1 ring-foreground/10`, `aria-current="page"` |
| Section tab | focus-visible | `outline-ring/50` 2px (global base style) |
| Market row | hover | `bg-muted/50` |
| Market row | price changed since last poll | 600 ms tint `bg-up/10` or `bg-down/10` |
| Market table | loading (first) | 12 `Skeleton` rows `h-9` + 4 skeleton cards |
| Market table | refresh | keep rows, small spinner next to "updated …" |
| Market table | error | keep last rows, banner above table: "Exchange did not answer. Showing data from 3m ago." + Retry |
| Market table | empty (filter) | "No coin matches “xyz”." + "Clear filter" |
| Watchlist segment | empty | "Star a coin to add it here." |
| Workspace tab | rename | inline input; blur = save |
| Restore defaults | confirm | Dialog, destructive button |
| Scan button | idle / no input | disabled |
| Scan button | running | label "Scanning…", spinner, disabled; input read-only; "Cancel" link appears (AbortController) |
| Scan | partial (one network failed) | that network's row: "Could not read Base (rate limited)" + Retry; others shown |
| Scan | done, 0 findings | Score card + "Nothing can move this wallet's tokens right now." Revoke plan hidden |
| Findings row | new since last scan | `bg-sev-high/10`, `New` badge |
| Revoke item | checked | strike-through text, muted |
| Revoke item | verified after re-scan | `Verified` `text-pass`, moves to bottom |
| Send check | typing | no live verdict; check runs on `Check` or `Enter` |
| Send check | invalid | inline error, banner hidden |
| Lock | new blocked request | row slides in, nav badge increments, `aria-live` announce |
| Copy (address / markdown) | click | icon swaps to check for 1.5 s, tooltip "Copied" |

---

## 10. Responsive

| Breakpoint | Changes |
|---|---|
| ≥1280 (`xl`) | As drawn. Market cards 4 across. Scan: route `w-72` left, results right |
| 768–1279 (`md`) | Market cards 2×2; table hides `L/S` and `OI 24h` (still in the row's tooltip). Scan: route on top as a horizontal step strip (`WalletRoute` replaced by a one-line "Step 3/7 · Approvals" + progress bar), results below |
| <768 | Section nav becomes a bottom bar (4 icons + labels, `h-14`, safe-area padding) because the top bar is full with coin search. Market: cards become one horizontal scroller; table shows Coin, Price, 24h, Funding. Charts: layout forced to `1`, a slot switcher replaces the grid (other slots are one tap away; 4 charts on a phone are unreadable). Wallet: everything stacks; findings table becomes cards (sev pill, asset → spender, at risk, link) |

Wallet must be fully usable on a phone: people check an address on the phone right before sending from a
mobile wallet. Market and Charts are desktop-first.

---

## 11. Edge cases

- **Market, 790 rows**: render all in a plain table with `content-visibility: auto` on `tbody tr` and a
  fixed row height; measure before adding a virtualization library.
- **New listing**: no funding yet → `—`; 24h % with less than 24h of history → value with `*` and tooltip
  "Listed 6h ago".
- **OKX from this machine**: the backend must use the IPv4 transport for OKX (known hang on IPv6), the same
  as the existing clients.
- **Price < 0.0001** (meme coins): `price()` shows 5 decimals; switch to significant digits (`0.0₄1234`
  style is not needed — `toPrecision(4)` is enough).
- **Long coin names**: name column `max-w-40 truncate`, base symbol never truncated.
- **Wallet with 500+ approvals**: group by spender by default when > 50 findings.
- **Approvals older than the lookback window**: always say it under the findings table: "Approvals granted
  before block N (≈ date) were not read. Check on revoke.cash for the full history." (and `provisional`).
- **Token with no price**: at-risk `—`; it sorts after priced items in the Revoke plan, not dropped.
- **Connected wallet on an unsupported chain**: chip shows "Chain 7777 · not supported", Scan falls back to
  the address with the network picker open.
- **Wallet switches account mid-scan** (`accountsChanged`): cancel the scan, show "Your wallet switched
  account. Scan the new one?" with a button.
- **Storage blocked** (private mode): watchlist and revoke plan work for the session; a muted line in the
  Watchlist says "Your browser is not saving data; this list will be gone when you close the tab."
- **Slow RPC**: per-step timeout 20 s → the step becomes `warn` ("did not answer"), the scan continues,
  score is provisional.

---

## 12. Data contracts

### 12.1 New endpoint `GET /api/market`

```
?exchange=binance|okx
→ {
  "time": 1763380800,          // server time of the snapshot
  "exchange": "binance",
  "rows": [{
    "symbol": "BTC-USDT-PERP", "base": "BTC", "name": "Bitcoin",
    "price": 91204.1, "chg_24h": 1.24, "volume_24h": 1.24e10,
    "funding_rate_pct": 0.01, "next_funding": 1763391600,
    "oi_value": 8.1e9 | null, "oi_chg_24h": 2.1 | null, "ls_ratio": 1.08 | null,
    "collected": true          // tier-B columns are real only when true
  }]
}
```

Implement in `rinng.service.Rinng` (so CLI/MCP can use it too, per doc 12) with a 30 s TTL cache; the
FastAPI route stays thin. Two REST calls per exchange for tier A, stored data for tier B.

### 12.2 Browser storage (all wrapped in try/catch, like `workspaces.ts`)

| Key | Shape | Notes |
|---|---|---|
| `rinng.instrument.v1` | existing | |
| `rinng.workspaces.v2` | existing | |
| `rinng.section.v1` | `"market" \| "coin" \| "charts" \| "wallet"` | `/terminal` redirect target |
| `rinng.watchlist.v1` | `string[]` symbols | Market + Coin ★ |
| `rinng.wallets.v1` | `{ id, label, address, net, snaps: Snap[≤2] }[]` | addresses and labels only |
| `rinng.revoke.v1` | `Record<fingerprint, { checkedAt }>` | prune entries older than 90 days |

Finding fingerprint: `${net}:${kind}:${token ?? "-"}:${spender}` lowercased. Stable across scans, so diffing
and the revoke checklist both key on it.

Never stored: private keys, seed phrases, signatures (rinng has none to store). Never sent to rinng's backend:
wallet addresses, except Solana reads through the existing `/api/solana` relay.

---

## 13. Motion

| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Section / sub-tab switch | click | none (instant) — a terminal should feel immediate | 0 | — |
| Market price cell | value changed on poll | background tint fade out | 600 ms | ease-out |
| Score number | scan done | count up from 0 | 600 ms | `cubic-bezier(0.2, 0, 0, 1)` |
| WalletRoute | progress | existing canvas animation | existing | existing |
| New finding / blocked row | appears | existing `.desk-in` (6px rise + fade) | 350 ms | ease-out |
| Copy confirm | click | icon cross-fade | 150 ms | ease |

All of it off under `prefers-reduced-motion: reduce` (WalletRoute already takes `reduced`).

---

## 14. Accessibility

- **Focus order**: news ticker (skippable, existing pause on focus) → section nav → context bar → section
  toolbar → content. Add a "Skip to content" link as the first focusable element.
- **Section nav**: links with `aria-current="page"`; not a `tablist`, because each section is a route.
  Workspace tabs and Wallet sub-tabs: `role="tablist"`, arrow keys move, `Home`/`End`, `Delete` closes a
  workspace tab (with the same confirm rules).
- **Shortcuts**: `Alt+1…4` sections; `/` and `⌘K` coin search (existing); in Charts `Alt+←/→` previous/next
  workspace. Listed in a `?` help dialog.
- **Tables**: real `<table>`, `<th scope="col">`, sortable headers are buttons with `aria-sort`.
- **Severity**: always text (HIGH/MED/LOW, PASS/REVIEW/RISK) plus color; never color alone.
- **Live regions**: scan progress `aria-live="polite"` announcing step names ("Checking approvals");
  completion "Scan complete: grade C, 2 high-risk findings, 4,210 dollars at risk"; Send check verdict
  `role="alert"` only for "Do not send"; blocked signature request `aria-live="assertive"` ("rinng blocked a
  request to send a transaction").
- **Addresses**: `AddressChunks` renders the full address in an `aria-label` without spaces; differing
  characters are announced as "differs from the address you used before".
- **Contrast**: check every new token at 4.5:1 for text on `--card`, both themes.

---

## 15. Build order

Each slice ships on its own; run each through horsemoon (plan → RED → GREEN → review → verify).

1. **Routing + shell**: layout route, 4 sections, URL search params, section nav, logo → `/`. Coin =
   today's Dashboard; Charts = today's workspaces; Market and Wallet = empty placeholders. No new features.
2. **Workspace tab strip**: `WorkspaceTabs`, rename, `⋯` menu, Dialog for restore.
3. **Severity tokens + shared wallet components** moved out of `landing/`; landing still renders the same.
4. **Wallet · Scan** in the terminal, with Revoke plan and export. Then "All EVM".
5. **Wallet · Lock** (small, high value: makes the read-only promise visible).
6. **Wallet · Send check**.
7. **Wallet · Watchlist** + diff + nav badge.
8. **`/api/market`** in the service layer (+ tests), then **Market** page.
9. **Coin** trim: combo shortcuts, ★.

Tests that matter most: fingerprint stability and diff (pure functions), revoke-plan ordering, URL ⇄ state
round-trip, `/api/market` tier-B nulls, and that no new code path calls a non-allowlisted wallet method
(extend `guard.test.ts`).

---

## 16. Open questions

1. **ENS**: resolve `name.eth` in Scan and Send check? It needs a mainnet read, which we already have; the
   risk is a look-alike ENS name, so Send check would have to show the resolved address prominently.
2. **Landing wallet check**: keep the full scanner on `/`, or shorten it to the first result plus "Open in
   terminal" for the revoke plan and watchlist?
3. **Market across exchanges**: one exchange at a time (this spec), or a merged list with a venue column?
4. **Watchlist alerts**: browser notifications when a re-scan finds a new HIGH finding? Needs a re-scan
   while the tab is open (or the collector to do it), so it is left out of v1.
