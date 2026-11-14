# 03 — Pine Script and Smart Money Concepts (SMC)

> Research date: **2026-11-13**. All figures on limits, function names and release notes come from TradingView docs read on that day; TradingView changes often, so re-check before relying on them.
>
> Markers:
> - **[checked]** — read directly from a source, with URL, during this research session.
> - **[memory]** — the writer's background knowledge, source page not reopened in this session; treat as needing verification before use.
> - **[unverified]** — no confirming source found, or the source read was not explicit.
>
> This document is not investment advice.

## Contents

- [Part A — Pine Script v6](#part-a--pine-script-v6)
- [Part B — Smart Money Concepts as algorithms](#part-b--smart-money-concepts-as-algorithms)
- [Part C — The "Dynamic SMC & Market Structure PRO" indicator](#part-c--the-dynamic-smc--market-structure-pro-indicator)
- [Part D — An honest assessment of SMC/ICT](#part-d--an-honest-assessment-of-smcict)
- [Unverified items](#unverified-items)
- [Sources](#sources)

---

# Part A — Pine Script v6

## A0. Version

The latest version is **Pine Script v6**. The release notes state that future updates apply only to v6 **[checked]**. Each script declares its version on the first line: `//@version=6`.

Notable changes in 2025–2026 (per release notes **[checked]**):

| When | Change |
|---|---|
| 02/2025 | 550-scope limit removed; `bid`, `ask` variables added (only on the `"1T"` timeframe) |
| 03/2025 | `box.set_xloc()`; `for` loops re-evaluate the `to_num` bound before each iteration |
| 06/2025 | Libraries can export `const` constants |
| 07/2025 | `active` parameter for all `input*()`; `syminfo.current_contract` |
| 08/2025 | String length limit raised from 4,096 to 40,960 characters |
| 09/2025 | `linestyle` parameter for `plot()` (`plot.linestyle_solid/dashed/dotted`) |
| 10/2025 | `timeframe_bars_back` parameter for `time()` and `time_close()` |
| 01/2026 | `request.footprint()` and the two types `footprint`, `volume_row` (see A9) |
| 04/2026 | Multiline strings with `"""` or `'''`; sorting collections of UDTs with `sort_field` |
| 07/2026 | `strategy()` gains `calc_on_every_history_tick`; many Strategy Tester UI items renamed (see A8) |
| 08/2026 | `once` keyword (run-once conditional structure); Pine Screener expanded |
| 09/2026 | Tables can be moved to the bottom panel |

Core differences of v6 vs v5:
- **Dynamic requests** on by default: `request.*()` accepts "series" arguments and can be called inside `if`/loops/exported functions. Disable with `dynamic_requests = false` in the declaration **[checked]**.
- `bool` is never `na`; `int`/`float` no longer implicitly cast to `bool`, use `bool()` **[checked]**.
- `and`/`or` are lazily evaluated (short-circuit) **[memory]** — with a practical consequence: a `ta.*` call placed after `and` may not run on every bar (see A1.5 and Part C).
- Strategy: default margin 100%, the `when` parameter removed, exceeding 9,000 trades trims the oldest trades instead of raising an error **[memory, the 9,000-trade part checked]**.

## A1. Execution model

Source: https://www.tradingview.com/pine-script-docs/language/execution-model/ **[checked]**

### A1.1 Bar-by-bar execution

A script does not run once over the whole data array. It runs **repeatedly from the first bar to the last**; each closed (historical) bar runs exactly once. After each run, the value of every variable is "committed" to a time series indexed by `bar_index`.

Consequence: almost every expression is a **series**. `close` is not a number but "the close of the bar being processed".

### A1.2 History referencing with `[]`

- `x[0]` is the current bar, `x[1]` the previous bar, `x[n]` n bars back. Missing data returns `na`.
- Expressions have history too: `(high - low)[1]` is valid.
- You cannot reference the future (no negative offsets).
- Historical buffer: at most **5,000** past values for most series, **10,000** for `open/high/low/close/time` **[checked — limitations page]**. The buffer auto-sizes to the largest offset the script uses; when Pine guesses wrong, use `max_bars_back` (a parameter of `indicator()`/`strategy()` or the function `max_bars_back(var, num)`) **[memory]**.

### A1.3 `var` and `varip`

- No keyword: the variable is re-initialized on every bar.
- `var`: initialized once, keeps its value across bars. On the open bar, each tick it rolls back to the value committed on the previous bar.
- `varip`: keeps its value across ticks within the same bar too. Only meaningful in realtime; causes repainting and cannot be backtested.

### A1.4 Historical bars and realtime bars

| | Historical bar | Realtime bar |
|---|---|---|
| Executions | Once, using the final OHLC | Indicator: once per tick. Strategy: by default once at bar close |
| `high/low/close` | Fixed | Change until the bar closes |
| Rollback | No | Before each tick, script state rolls back to the last commit |

Rollback does not undo: `varip` variables, Pine Logs, strategy orders already sent, alerts already fired, runtime errors.

Common `barstate.*`: `barstate.ishistory`, `barstate.isrealtime`, `barstate.isnew`, `barstate.isconfirmed` (the bar's last execution), `barstate.islast`, `barstate.isfirst`, `barstate.islastconfirmedhistory` **[first 4 checked, the rest memory]**.

The script re-runs entirely when: adding/saving the script, refreshing the chart, changing inputs, changing symbol/timeframe, re-creating an alert... After a re-run, bars that were realtime become historical, so results can differ — this is the root of repainting.

### A1.5 Function call consistency

Functions with historical state (`ta.*`, and any function using `[]` internally) should be called at **global scope, on every bar**. Calling them inside `if`, in a `?:` branch, or after `and`/`or` punches holes in the function's internal history and skews results. The compiler warns about this **[checked]**. Safe pattern:

```pine
bool crossUp = ta.crossover(close, level)   // always computed at global scope
if showStructure and crossUp
    // ...
```

### A1.6 Repainting and how to avoid it

Source: https://www.tradingview.com/pine-script-docs/concepts/repainting/ **[checked]**

Repainting is when behavior on historical bars differs from realtime. Three groups:

**1. Historical calculations differ from realtime**

| Cause | Avoidance |
|---|---|
| Using `close/high/low` of an unclosed bar | Add `and barstate.isconfirmed`, or use `[1]` values. Trade-off: signals lag one bar |
| `request.security()` on a higher timeframe returns unconfirmed values | `request.security(sym, tf, expr[1], lookahead = barmerge.lookahead_on)` — **both** parts are required |
| `request.security()` on a timeframe lower than the chart | Use `request.security_lower_tf()` |
| `lookahead_on` without `[1]` | Future leak. Never use it. Such scripts are banned from publishing |
| `varip` | Do not use for logic that must be backtested |
| `barstate.isnew` | Use `barstate.isconfirmed` |
| `timenow` | No fix — repaints by nature |
| Strategy with `calc_on_every_tick = true` | Avoid; running at bar close matches the backtest |

**2. Plotting in the past.** `ta.pivothigh(high, 5, 5)` only knows the pivot 5 bars later, but if drawn at `bar_index - 5` the chart makes it look known at that moment. Every SMC indicator has this issue. Drawing in the past is fine for viewing, but **trading logic must be computed at the confirmation bar**, not the pivot bar.

**3. Changing dataset.** The first loaded bar depends on account plan and timeframe, so `ta.ema()`, `ta.barssince()`, `ta.valuewhen()` can produce different results. Exchanges can also revise historical data.

## A2. Types and qualifiers

Source: https://www.tradingview.com/pine-script-docs/language/type-system/ **[checked]**

**Qualifiers** (weakest to strongest): `const` < `input` < `simple` < `series`.

- `const`: known at compile time.
- `input`: known when the user edits Settings.
- `simple`: known on the first bar, then constant (e.g. `syminfo.mintick`).
- `series`: may change bar to bar.

An expression inherits the strongest qualifier among its parts; qualifiers cannot be demoted. Many parameters require a weak qualifier, e.g. `length` of `ta.ema()` must be "simple int", while `ta.sma()` accepts "series int" **[memory]**.

**Types:**
- Fundamental values: `int`, `float`, `bool`, `color`, `string`.
- `enum` (declared with `enum`, used with `input.enum()`).
- Reference types (always `series`): `plot`, `hline`, `line`, `linefill`, `box`, `polyline`, `label`, `table`, `chart.point`, `footprint`, `volume_row`.
- Collections: `array<T>`, `matrix<T>`, `map<K, V>`.
- UDTs declared with `type`.
- `void` for functions returning nothing; tuples only as return values of functions/`request.security` **[memory]**.
- `na` means "no value"; test with `na(x)`, not `x == na`. `bool` is never `na`.

## A3. Script declaration

A script has exactly one of three declarations **[memory, parameter names cross-checked against source code read]**:

```pine
//@version=6
indicator("Name", shorttitle = "Short", overlay = true,
     max_lines_count = 500, max_boxes_count = 500, max_labels_count = 500,
     max_bars_back = 2000)
```

- `indicator()` — computes and plots, places no orders. Supports alerts.
- `strategy()` — adds `strategy.*` functions and a broker emulator for backtesting (A8).
- `library()` — only contains `export`ed functions/types/constants, reused via `import user/LibName/version as alias`. A library does not plot when imported.

## A4. Inputs

Functions: `input()`, `input.int()`, `input.float()`, `input.bool()`, `input.string()`, `input.color()`, `input.source()`, `input.timeframe()`, `input.session()`, `input.symbol()`, `input.time()`, `input.price()`, `input.text_area()`, `input.enum()` **[memory; `input.int/float/bool/color/string/timeframe` seen in source code read]**.

Common parameters: `defval`, `title`, `minval`, `maxval`, `step`, `options`, `tooltip`, `inline`, `group`, `confirm`, `display`, and `active` (since 07/2025 **[checked]**).

Return values have the `input` qualifier, except `input.source()` which returns series.

## A5. Output: plots and drawings

| Group | Function | Notes |
|---|---|---|
| Plot | `plot()`, `plotshape()`, `plotchar()`, `plotarrow()`, `plotcandle()`, `plotbar()`, `hline()`, `fill()`, `bgcolor()`, `barcolor()` | At most **64 plot count** per script; one call can cost up to 7 **[checked]**. Must be called at global scope |
| Line | `line.new(x1, y1, x2, y2, xloc, extend, color, style, width)` | Default keeps 50, max 500 |
| Box | `box.new(left, top, right, bottom, ...)` | Default 50, max 500 |
| Label | `label.new(x, y, text, xloc, yloc, color, style, textcolor, size, ...)` | Default 50, max 500 |
| Polyline | `polyline.new(points, curved, closed, xloc, line_color, fill_color, line_style, line_width)` takes `array<chart.point>` | Default 50, max **100** |
| Linefill | `linefill.new(line1, line2, color)` | |
| Table | `table.new(position, columns, rows, ...)` + `table.cell()` | At most 9 tables (one per position) |

Limit figures **[checked]**; function signatures **[memory]**. When a limit is exceeded, Pine deletes the oldest drawings (garbage collection), so you cannot keep the full FVG/OB history on a long chart.

x coordinate: `xloc.bar_index` (default) or `xloc.bar_time`. With `xloc.bar_index`, you can draw at most 10,000 bars into the past and 500 bars into the future **[checked]**.

Performance tip: create drawings once with `var` and update them with `*.set_*()`; only update tables inside `if barstate.islast`.

## A6. `request.security` and lookahead

Source: https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/ **[checked]**

```
request.security(symbol, timeframe, expression, gaps, lookahead,
                 ignore_invalid_symbol, currency, calc_bars_count) → series <type>
```

- `expression` can be a number, bool, string, tuple, collection, UDT, or a function call.
- `gaps`: default `barmerge.gaps_off` (filled with the last confirmed value).
- `lookahead`: default `barmerge.lookahead_off`.
  - On a higher timeframe, `lookahead_on` on historical bars returns the value of an **unfinished** HTF bar — i.e. looking into the future.
  - Standard non-repainting pattern:

```pine
float htfClose = request.security(syminfo.tickerid, "240", close[1], lookahead = barmerge.lookahead_on)
// Previous Day High/Low:
[pdh, pdl] = request.security(syminfo.tickerid, "D", [high[1], low[1]], lookahead = barmerge.lookahead_on)
```

- Dynamic requests (v6): on realtime bars you can only fetch datasets already requested on historical bars.
- Limits: **40** unique `request.*()` calls per script, **64** on the Ultimate plan. Calls with identical arguments are reused and not counted again; calls inside an imported library **are** counted. Total tuple elements across all `request.*()` at most 127 **[checked]**.

Sibling functions: `request.security_lower_tf()`, `request.footprint()`, `request.currency_rate()`, `request.dividends()`, `request.splits()`, `request.earnings()`, `request.financial()`, `request.economic()`, `request.seed()` **[checked]**.

## A7. `ta.*`, collections, UDTs, methods

### A7.1 Common `ta.*` **[memory; functions marked * seen in source code read]**

| Purpose | Functions |
|---|---|
| Averages | `ta.sma`, `ta.ema`, `ta.rma`, `ta.wma`, `ta.vwma`, `ta.hma`, `ta.vwap` |
| Volatility | `ta.atr`*, `ta.tr`*, `ta.stdev`, `ta.bb`, `ta.kc` |
| Oscillators | `ta.rsi`, `ta.macd`, `ta.stoch`, `ta.cci`, `ta.mfi` |
| Extremes | `ta.highest`*, `ta.lowest`*, `ta.highestbars`, `ta.lowestbars` |
| Pivots | `ta.pivothigh(source, leftbars, rightbars)`*, `ta.pivotlow(...)`* — return the pivot price on the confirmation bar, `na` otherwise |
| Events | `ta.crossover`*, `ta.crossunder`*, `ta.cross`, `ta.change`*, `ta.barssince`, `ta.valuewhen` |
| Cumulative | `ta.cum`* |
| Trend | `ta.supertrend`, `ta.dmi`, `ta.sar`, `ta.linreg` |

### A7.2 Array, matrix, map

```pine
var array<float> levels = array.new<float>()
levels.push(high)
if levels.size() > 50
    levels.shift()

var map<string, float> m = map.new<string, float>()
m.put("pdh", high)

matrix<float> mx = matrix.new<float>(3, 3, 0.0)
```

Limits: 100,000 elements for arrays/matrices; maps at most 50,000 key-value pairs **[checked]**. Collections cannot directly contain other collections — wrap in a UDT if needed. Loops: `for i = 0 to arr.size() - 1`, or `for [i, v] in arr`. Each loop may not run longer than **500 ms** on one bar **[checked]**.

### A7.3 UDTs and methods

```pine
type Zone
    float top
    float bottom
    int   leftBar
    bool  mitigated = false

method isInside(Zone this, float price) =>
    price <= this.top and price >= this.bottom

var array<Zone> zones = array.new<Zone>()
zones.push(Zone.new(high, low, bar_index))
```

UDTs are reference types: `b = a` does not copy, use `a.copy()` **[memory]**. Using `[]` on UDT fields for history is restricted — store history in an array rather than relying on `obj.field[1]` **[memory]**.

## A8. Strategy tester

Source: https://www.tradingview.com/pine-script-docs/concepts/strategies/ **[partially checked — page was truncated, see note]**

```pine
//@version=6
strategy("Demo", overlay = true,
     initial_capital = 10000,
     default_qty_type = strategy.percent_of_equity, default_qty_value = 10,
     commission_type = strategy.commission.percent, commission_value = 0.05,
     slippage = 2,                // unit: ticks
     pyramiding = 0,
     process_orders_on_close = false)
```

**Orders** **[checked]**:
- `strategy.entry()` — respects `pyramiding`, reverses positions automatically.
- `strategy.order()` — ignores pyramiding, does not auto-reverse.
- `strategy.exit()` — take-profit/stop-loss in ticks (`profit`, `loss`) or price (`limit`, `stop`), trailing (`trail_price`/`trail_points` + `trail_offset`).
- `strategy.close()`, `strategy.close_all()`, `strategy.cancel()`, `strategy.cancel_all()`.
- `strategy.risk.allow_entry_in()` and other `strategy.risk.*` functions.

**Broker emulator** **[checked]**:
- Orders created at bar close fill at the **next bar's open** (default).
- The intrabar price path is assumed: if open is closer to high then open→high→low→close, otherwise open→low→high→close.
- No gaps within a bar; a gap between two bars fills at the next bar's open.
- Bar Magnifier (now called "Bar detalization", Premium/Ultimate plans) uses lower-timeframe data for more accurate fills, up to 200,000 LTF bars.
- Keeps details for at most the **9,000** most recent trades; Deep Backtesting keeps 1,000,000.

**Defaults to know** **[memory — the page as read did not reach this part]**: `initial_capital = 1000000`, `default_qty_type = strategy.fixed` with quantity 1, commission = 0, `slippage = 0`, `pyramiding = 1` (**[checked]**: the docs state the default is 1), `margin_long = margin_short = 100`.

**07/2026 update** **[checked]**: `calc_on_every_history_tick` (runs the script on each historical tick, Premium/Ultimate); the UI has "Script execution", "Bar detalization", "Heikin Ashi mode" (maps to `fill_orders_on_standard_ohlc`), "Limit order execution" (`backtest_fill_limits_assumption`), and "Long/Short leverage" replacing the margin field.

### Backtest pitfalls

1. **Commission and slippage are zero by default.** For crypto perps, set real taker fees and slippage; funding rates are **not** simulated **[memory]**.
2. **Lookahead via `request.security`** (A6) and via plotting pivots in the past and then using the pivot bar itself as the signal.
3. **`process_orders_on_close = true`** fills right at the signal bar's close — optimistic; in reality you can't get exactly that price.
4. **TP and SL both inside one bar**: the result depends on the price-path assumption above. The bigger the bar, the larger the error.
5. **Limit orders fill as soon as price touches**: in reality price must trade through. Use `backtest_fill_limits_assumption`.
6. **Non-standard charts** (Heikin Ashi, Renko, Kagi, Range...): synthetic prices, results are usually unrealistic **[checked]**.
7. **Limited historical bars** (A10) → small samples on low timeframes.
8. **Defaulting to 100% equity or a fixed quantity** distorts the equity curve.
9. **Optimizing parameters on the same data segment** — TradingView has no built-in walk-forward **[memory]**.
10. **`calc_on_every_tick`** makes realtime differ from historical.

## A9. Volume profile in Pine

**There is no `ta.*` function that returns a volume profile.** TradingView's built-in Volume Profile indicators (Visible Range, Session, Fixed Range...) are closed built-ins; scripts cannot read their values **[memory; the FAQ page checked mentions no such function]**. Three approaches:

### (1) `request.footprint()` — new since 01/2026 **[checked]**

```
request.footprint(ticks_per_row, va_percent, imbalance_percent) → series footprint
```

- `ticks_per_row`: "simple int", each row is `ticks_per_row * syminfo.mintick` tall.
- `va_percent`: default 70. `imbalance_percent`: default 300.
- Returns the current bar's `footprint` ID, or `na` — check for `na` before use.
- `footprint` functions: `total_volume()`, `buy_volume()`, `sell_volume()`, `delta()`, `poc()`, `vah()`, `val()` (the last three return `volume_row`), `rows()` (returns `array<volume_row>` in ascending price order).
- `volume_row` functions: `up_price()`, `down_price()`, `buy_volume()`, `sell_volume()`, `delta()`, `total_volume()`, `has_buy_imbalance()`, `has_sell_imbalance()`.
- Restrictions: **Premium/Ultimate** plans only; **one** unique call per script; on timeframes ≥ 1D total volume may differ from `volume`.
- This is a **per-bar** profile (footprint), not a profile over an arbitrary range. For a whole-session profile you must aggregate rows yourself. History depth: **[unverified]**.

### (2) `request.security_lower_tf()` — build your own profile **[signature checked]**

```
request.security_lower_tf(symbol, timeframe, expression, ignore_invalid_symbol,
                          currency, ignore_invalid_timeframe, calc_bars_count) → array<type>
```

Returns **one array per chart bar**, each element one intrabar. The usual approach: take intrabar `close` and `volume` (e.g. 1 minute), split the price range into N bins, add volume to the matching bin.

```pine
//@version=6
indicator("LTF volume per bar", overlay = false)
string ltf = input.timeframe("1", "Lower timeframe")
array<float> ltfClose = request.security_lower_tf(syminfo.tickerid, ltf, close)
array<float> ltfVol   = request.security_lower_tf(syminfo.tickerid, ltf, volume)
float upVol = 0.0
float dnVol = 0.0
if ltfClose.size() > 1
    for i = 1 to ltfClose.size() - 1
        if ltfClose.get(i) >= ltfClose.get(i - 1)
            upVol += ltfVol.get(i)
        else
            dnVol += ltfVol.get(i)
plot(upVol - dnVol, "Approx. delta", style = plot.style_columns)
```

### Intrabar data limits **[checked]**

- Total intrabars available: **100,000** (Basic/Essential/Plus/Premium), **125,000** (Expert), **200,000** (Ultimate).
- Consequence: a 1H chart with 1-minute intrabars only has about 100,000 / 60 ≈ 1,666 bars with data. Older bars return empty arrays.
- Volume assigned to price levels is only an **approximation**: we know an intrabar's volume, not how it was distributed across that intrabar's high–low range. Classifying buy/sell by candle direction is also an approximation, not the true aggressor.
- For crypto, volume is from **one exchange** for the selected symbol, not the whole market.

### (3) Compute externally in Python

With trade/aggTrade data from the exchange, volume profile and delta are far more accurate. This is the option to use for serious research.

## A10. Limits

Source: https://www.tradingview.com/pine-script-docs/writing/limitations/ **[checked]**

| Item | Limit |
|---|---|
| Compile time | 2 minutes; 3 consecutive warnings lock compilation for 1 hour |
| Script run time | Depends on plan; docs give no number, point to the pricing page — **[number unverified]** |
| One loop on one bar | 500 ms |
| Plots | 64 plot count |
| Line / box / label | Default 50, max 500 each |
| Polyline | Default 50, max 100 |
| Table | 9 |
| Unique `request.*()` | 40 (Ultimate: 64) |
| `request.footprint()` | 1 call; needs Premium/Ultimate |
| Intrabars | 100K / 125K (Expert) / 200K (Ultimate) |
| Tuple elements via `request.*()` | 127 |
| Compiled tokens | 100,256 per script; total imported libraries 1 million |
| Variables per scope | 1,000 |
| Collections | 100,000 elements; map 50,000 pairs |
| Historical buffer (`max_bars_back`) | 5,000; OHLC and `time` 10,000 |
| Drawing with `xloc.bar_index` | 10,000 bars past, 500 bars future |
| Chart bars | Ultimate 40,000; Expert 25,000; Premium 20,000; Essential/Plus 10,000; others 5,000 |
| Strategy orders | 9,000 (Deep Backtesting: 1,000,000) |
| String length | 40,960 characters |

## A11. Sample code (self-written, v6 syntax)

> The three snippets below were written by the author in v6 syntax and **have not been compiled on TradingView in this session** — paste them into the Pine Editor to check before use.

### A11.1 Swing high/low pivots labeled HH/HL/LH/LL

```pine
//@version=6
indicator("Swing pivots", overlay = true, max_labels_count = 500)

int len = input.int(5, "Pivot length", minval = 1)

float ph = ta.pivothigh(high, len, len)
float pl = ta.pivotlow(low, len, len)

var float lastPh = na
var float lastPl = na

// Note: a pivot is only known at the current bar, i.e. `len` bars late.
// Labels are drawn back at the pivot bar for readability; trading logic must use the current bar.
if not na(ph)
    string tagH = na(lastPh) ? "H" : ph > lastPh ? "HH" : "LH"
    label.new(bar_index - len, ph, tagH, style = label.style_label_down, size = size.tiny)
    lastPh := ph

if not na(pl)
    string tagL = na(lastPl) ? "L" : pl > lastPl ? "HL" : "LL"
    label.new(bar_index - len, pl, tagL, style = label.style_label_up, size = size.tiny)
    lastPl := pl
```

### A11.2 Fair Value Gap detection

```pine
//@version=6
indicator("FVG", overlay = true, max_boxes_count = 500)

float minAtrMult = input.float(0.25, "Minimum size (x ATR)", minval = 0.0, step = 0.05)
int   extendBars = input.int(20, "Extend (bars)", minval = 1)

float atr = ta.atr(14)

// 3-candle pattern: candle [2], candle [1] (middle candle), candle [0].
// Only evaluate on closed bars to avoid repainting.
float bullGap = low - high[2]
float bearGap = low[2] - high

bool bullFvg = barstate.isconfirmed and bullGap > 0 and close[1] > high[2] and bullGap >= minAtrMult * atr
bool bearFvg = barstate.isconfirmed and bearGap > 0 and close[1] < low[2]  and bearGap >= minAtrMult * atr

if bullFvg
    box.new(bar_index - 2, low, bar_index + extendBars, high[2],
         border_color = color.new(color.teal, 40), bgcolor = color.new(color.teal, 85))

if bearFvg
    box.new(bar_index - 2, low[2], bar_index + extendBars, high,
         border_color = color.new(color.red, 40), bgcolor = color.new(color.red, 85))

alertcondition(bullFvg, "Bullish FVG", "Bullish FVG {{ticker}} {{interval}}")
alertcondition(bearFvg, "Bearish FVG", "Bearish FVG {{ticker}} {{interval}}")
```

### A11.3 Simple BOS/CHoCH with JSON alerts for webhooks

```pine
//@version=6
indicator("Simple BOS / CHoCH", overlay = true, max_lines_count = 500, max_labels_count = 500)

int len = input.int(5, "Pivot length", minval = 1)

float ph = ta.pivothigh(high, len, len)
float pl = ta.pivotlow(low, len, len)

var float swingHigh    = na
var int   swingHighBar = na
var bool  highBroken   = true
var float swingLow     = na
var int   swingLowBar  = na
var bool  lowBroken    = true
var int   trend        = 0      // 1 = bullish, -1 = bearish, 0 = undetermined

if not na(ph)
    swingHigh    := ph
    swingHighBar := bar_index - len
    highBroken   := false

if not na(pl)
    swingLow    := pl
    swingLowBar := bar_index - len
    lowBroken   := false

// Break confirmed by the close of a closed bar.
bool breakUp   = barstate.isconfirmed and not highBroken and not na(swingHigh) and close > swingHigh
bool breakDown = barstate.isconfirmed and not lowBroken  and not na(swingLow)  and close < swingLow

if breakUp
    string tagUp = trend == -1 ? "CHoCH" : "BOS"
    line.new(swingHighBar, swingHigh, bar_index, swingHigh, color = color.teal, style = line.style_dashed)
    label.new(math.round(math.avg(swingHighBar, bar_index)), swingHigh, tagUp,
         style = label.style_none, textcolor = color.teal, size = size.small)
    alert('{"event":"' + tagUp + '","side":"bull","symbol":"' + syminfo.ticker + '","tf":"' + timeframe.period +
         '","level":' + str.tostring(swingHigh) + ',"close":' + str.tostring(close) + ',"time":' + str.tostring(time) + '}',
         alert.freq_once_per_bar_close)
    trend      := 1
    highBroken := true

if breakDown
    string tagDn = trend == 1 ? "CHoCH" : "BOS"
    line.new(swingLowBar, swingLow, bar_index, swingLow, color = color.red, style = line.style_dashed)
    label.new(math.round(math.avg(swingLowBar, bar_index)), swingLow, tagDn,
         style = label.style_none, textcolor = color.red, size = size.small)
    alert('{"event":"' + tagDn + '","side":"bear","symbol":"' + syminfo.ticker + '","tf":"' + timeframe.period +
         '","level":' + str.tostring(swingLow) + ',"close":' + str.tostring(close) + ',"time":' + str.tostring(time) + '}',
         alert.freq_once_per_bar_close)
    trend     := -1
    lowBroken := true
```

Deliberate limitations of this sample: it tracks only the most recent swing high and swing low, does not distinguish internal/swing structure, and does not require displacement. The first break (when `trend == 0`) is labeled BOS.

## A12. Alerts and webhooks

Sources: https://www.tradingview.com/pine-script-docs/concepts/alerts/ and https://www.tradingview.com/support/solutions/43000529348-about-webhooks/ **[checked]**

**Three ways to fire alerts:**

| Method | Where | Message content |
|---|---|---|
| `alert(message, freq)` | Indicators and strategies | "series string" — can build dynamic JSON |
| `alertcondition(condition, title, message)` | Indicators only; must be called at global scope | "const string" + placeholders: `{{ticker}}`, `{{exchange}}`, `{{interval}}`, `{{time}}`, `{{timenow}}`, `{{open}}`, `{{high}}`, `{{low}}`, `{{close}}`, `{{volume}}`, `{{plot_0}}`…`{{plot_19}}`, `{{plot("name")}}` |
| Strategy order fills | Strategies | The `alert_message` parameter of `strategy.entry/order/exit/close`, retrieved with the `{{strategy.order.alert_message}}` placeholder in the Message field |

`freq`: `alert.freq_once_per_bar` (default), `alert.freq_once_per_bar_close`, `alert.freq_all`.

Key points:
- Code only creates **alert events**. The user must click "Create Alert" in the UI; a script cannot create alerts by itself.
- Alerts only fire on **realtime bars**, running on TradingView's servers.
- An alert stores a **snapshot** of script + inputs + symbol + timeframe at creation time. After editing the script you must re-create the alert.

**Webhooks:**
- TradingView sends an **HTTP POST** whose body is the alert message.
- If the message is valid JSON the header is `application/json`, otherwise `text/plain`.
- Only ports **80 and 443** are accepted.
- The server must respond within **3 seconds**, otherwise the request is cancelled.
- Source IPs (for allowlisting): `52.89.214.238`, `34.212.75.30`, `54.218.53.128`, `52.32.178.7`.
- No IPv6 support.
- The account must have **2FA** enabled.
- The webhook page does not state a paid-plan requirement nor describe any resend mechanism — both **[unverified]**. Assume **no retry**.

## A13. What Pine cannot do, and how to connect to Python

**Cannot do** **[memory, except items noted]**:
- No external HTTP/API calls, no sockets, no file read/write, no database. The only external data inputs are `request.seed()` (a user-maintained GitHub repo **[function name checked]**) or pasting into inputs by hand.
- No direct live order placement; only alerts.
- No order book access, no full historical ticks (apart from footprint and the `"1T"` timeframe).
- No state persisted between runs; every reload recomputes from scratch.
- No imports outside the Pine ecosystem, no machine learning beyond what you write in Pine yourself.
- Cannot read values of closed built-in indicators (e.g. Volume Profile); cannot read drawings the user made by hand.
- Cannot create alerts or change the chart's symbol/timeframe by itself.
- Bound by the limits in A10 — unsuitable for research on large datasets.

**Connecting to Python — recommended architecture:**

```
TradingView (Pine: alert() builds JSON)
        │  HTTP POST, port 443, must respond < 3 seconds
        ▼
Webhook receiver (FastAPI / Cloudflare Worker)
   1. Check secret in body  2. Write to queue  3. Return 200 immediately
        ▼
Python worker: re-check the signal with exchange data → risk management → place orders via exchange API
```

```python
# Receiver pseudocode — not production code
from fastapi import FastAPI, Request, HTTPException
import asyncio, hmac, os

app = FastAPI()
queue: asyncio.Queue = asyncio.Queue()
SECRET = os.environ["TV_WEBHOOK_SECRET"]

@app.post("/tv")
async def tv(req: Request):
    data = await req.json()
    if not hmac.compare_digest(str(data.get("secret", "")), SECRET):
        raise HTTPException(403)
    await queue.put(data)          # heavy processing happens in another worker
    return {"ok": True}            # respond immediately, avoid the 3-second timeout
```

Design notes:
- TradingView does not sign requests. Authenticate with a secret in the body plus an IP allowlist. The webhook page advises against putting sensitive information in the body — so this secret is just a signal identifier, **not an exchange API key**.
- Make it **idempotent**: use `symbol + tf + time + event` as a key to reject duplicate signals.
- The Python side must **re-check** signals with exchange data; treat alerts as hints, not orders.
- Webhooks can be dropped. A reconciliation mechanism is needed (e.g. Python periodically recomputes signals).
- The more robust long-term approach: compute all signals in Python on exchange data, use Pine only for visualization and cross-checking.

---

# Part B — Smart Money Concepts as algorithms

**Important preface.** SMC/ICT is trader jargon with no standard definitions. The same name is implemented with different rules by each author and indicator. This document picks definitions that are **computable in code**, and lists parameters and variants. Two open-source implementations serve as reference points:

- **LuxAlgo — Smart Money Concepts [LuxAlgo]** (Pine v5, updated 2025-09-23, license **CC BY-NC-SA 4.0** stated in the source — no commercial use) **[source checked]**: https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/
- **`smartmoneyconcepts`** (Python, PyPI version 0.0.27 released 2026-04-03) **[README and PyPI checked]**: https://github.com/joshyattridge/smart-money-concepts — license: PyPI leaves the license field empty, the repo has a LICENSE file but the license type is **[unverified]**.

Common notation for pseudocode: `df` is a pandas DataFrame with columns `open, high, low, close, volume`, indexed by ascending UTC time. The functions below are **illustrative pseudocode**, not run or tested.

```python
import numpy as np
import pandas as pd

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()      # Wilder (equivalent to ta.rma)
```

## B1. Market structure

### B1.1 Swing high / swing low

**Definition (fractal/pivot):** bar `i` is a swing high if `high[i]` is the maximum within the window `[i-L, i+R]`. Swing low likewise with `low`. A swing is only **known at bar `i+R`**.

**Parameters:** `L`, `R` (usually equal).

**Variants:**
- Pine's `ta.pivothigh(high, L, R)`.
- LuxAlgo uses "legs": at bar `t`, if `high[t-size]` is greater than the highest high of the `size` bars after it, a down leg starts and `high[t-size]` is a swing high. Only the right side is considered, and it is recorded only when the leg changes direction **[source checked]**.
- `smartmoneyconcepts`: `swing_highs_lows(ohlc, swing_length=50)`, highest/lowest within `swing_length` candles before and after **[checked]**.
- ZigZag by % threshold or ATR multiple (independent of bar count).
- Tie handling (two bars with the same high) differs between implementations.

```python
def swings(df, n=5):
    w = 2 * n + 1
    is_sh = df.high.eq(df.high.rolling(w, center=True).max())
    is_sl = df.low.eq(df.low.rolling(w, center=True).min())
    out = pd.DataFrame(index=df.index)
    out["swing_high"] = df.high.where(is_sh)
    out["swing_low"] = df.low.where(is_sl)
    # ANTI-LOOKAHEAD: a swing at position i is only usable from position i + n
    out["sh_known"] = out.swing_high.shift(n)
    out["sl_known"] = out.swing_low.shift(n)
    return out
```

### B1.2 HH / HL / LH / LL classification

Compare each swing with the previous swing **of the same type**: higher swing high → HH, lower → LH; higher swing low → HL, lower → LL.

- Uptrend: sequence of HH + HL. Downtrend: sequence of LH + LL.
- Variants: force alternating swing highs and lows (if two swing highs in a row, keep the higher); use an equality threshold to separate equal highs/lows (B5).

```python
def classify(sw):
    sh = sw.swing_high.dropna()
    sl = sw.swing_low.dropna()
    lab_h = np.where(sh.diff() > 0, "HH", "LH")[1:]
    lab_l = np.where(sl.diff() > 0, "HL", "LL")[1:]
    return pd.Series(lab_h, index=sh.index[1:]), pd.Series(lab_l, index=sl.index[1:])
```

### B1.3 Internal structure and swing structure

Same algorithm, run with two lengths:
- **Swing structure**: long length. LuxAlgo default **50**, minimum 10 **[checked]**.
- **Internal structure**: short length. LuxAlgo uses a constant **5**, not adjustable **[source checked]**.

LuxAlgo also adds a condition: an internal pivot only counts when its level **differs** from the current swing pivot level, plus an optional "Confluence Filter" to drop less meaningful internal breaks **[checked]**.

Other variant: use a lower timeframe as internal and the current timeframe as swing.

## B2. Break of Structure (BOS)

**Definition:** price breaks the most recent swing **in the direction of the current trend**.
- Bullish BOS: trend is bullish, `close >` the most recent unbroken `swing_high`.
- Bearish BOS: trend is bearish, `close <` the most recent unbroken `swing_low`.

**Parameters and variants:**
- Confirm by **close** (strict) or **wick** (`high > level`, loose). `smartmoneyconcepts` has `close_break=True` **[checked]**; LuxAlgo uses `ta.crossover(close, level)` **[checked]**.
- Each swing can be broken only once (a `crossed` flag).
- Additionally require displacement (B8) to filter weak breaks.
- Minimum buffer: `close > level + k * ATR`.

## B3. Change of Character (CHoCH) / Market Structure Shift (MSS)

**Definition:** price breaks the most recent swing **against the current trend**.
- Bullish CHoCH: trend is bearish, `close >` the most recent `swing_high`.
- Bearish CHoCH: trend is bullish, `close <` the most recent `swing_low`.

So BOS and CHoCH are **the same break event**, labeled differently depending on the prior trend state. After the event, the trend is set to the direction of the break.

**Variants:**
- **MSS**: many treat it as a synonym of CHoCH. Some distinguish: CHoCH is the first counter-trend break (including in internal structure), MSS requires a break with displacement and/or after a liquidity sweep. No common standard.
- The first break when there is no trend yet: labeled BOS (both LuxAlgo and the Part C indicator do this **[checked]**).
- Strict version: a bullish CHoCH requires the broken swing to be **the LH that produced the most recent LL**, not any swing high.

```python
def bos_choch(df, sw, close_break=True):
    """Returns a list of events. Uses sh_known/sl_known, so no lookahead."""
    events, trend = [], 0
    hi_lvl = lo_lvl = None
    hi_idx = lo_idx = None
    up_src = df.close if close_break else df.high
    dn_src = df.close if close_break else df.low
    for i in range(len(df)):
        if not np.isnan(sw.sh_known.iat[i]):
            hi_lvl, hi_idx = sw.sh_known.iat[i], i     # i is the swing CONFIRMATION bar
        if not np.isnan(sw.sl_known.iat[i]):
            lo_lvl, lo_idx = sw.sl_known.iat[i], i
        if hi_lvl is not None and up_src.iat[i] > hi_lvl:
            events.append(dict(i=i, side=1, kind="CHoCH" if trend == -1 else "BOS",
                               level=hi_lvl, swing_known_at=hi_idx))
            trend, hi_lvl = 1, None
        elif lo_lvl is not None and dn_src.iat[i] < lo_lvl:
            events.append(dict(i=i, side=-1, kind="CHoCH" if trend == 1 else "BOS",
                               level=lo_lvl, swing_known_at=lo_idx))
            trend, lo_lvl = -1, None
    return pd.DataFrame(events)
```

## B4. Order block, mitigation, breaker block

### B4.1 Order block (OB)

**Common definition:** the last opposite-colored candle before a strong move that causes a BOS/CHoCH.
- Bullish OB: the last down candle (`close < open`) before the rally that breaks a swing high. Zone = that candle's `[low, high]`.
- Bearish OB: the last up candle before the drop that breaks a swing low.

**Parameters and variants:**
- Zone taken from the **whole candle** (wick–wick), the **body**, or open to wick.
- Candle selection:
  - "Last opposite candle" (textbook definition).
  - **LuxAlgo**: on a break, take the bar with the **lowest low** (bullish) or **highest high** (bearish) between the swing pivot and the break bar, regardless of candle color. Plus a volatility filter: bars with `high - low >= 2 × ATR(200)` (or 2 × the cumulative mean of true range) are treated as high-volatility bars and have their high/low swapped when evaluated, so they are not picked as OBs **[source checked]**.
  - **`smartmoneyconcepts`**: `ob(ohlc, swing_highs_lows, close_mitigation=False)`, also returns `OBVolume` (that candle's volume plus the two previous candles) and `Percentage` **[checked]**.
- Optional extra conditions: must have displacement, must leave an FVG, must lie in discount (bullish) or premium (bearish), must have swept liquidity first.
- Cap on active OBs (LuxAlgo shows 5 of each type, stores at most 100 **[checked]**).

### B4.2 Mitigation

Two different meanings; state which one you use:
1. **Touch/return (tap):** price returns to touch the OB zone — bullish OB: `low <= ob.top`. Usually the entry condition.
2. **Invalidation:** price trades fully through the zone — bullish OB: `low < ob.bottom` (by wick) or `close < ob.bottom` (by close). LuxAlgo calls this mitigation and **deletes** the OB; the source option is `High/Low` (default) or `Close` **[checked]**.

Variants: partial mitigation (touching 50% of the zone), maximum number of touches before the zone is considered "used".

### B4.3 Breaker block

**Definition:** an OB that has been **invalidated** (closed through) flips roles: a broken bullish OB becomes resistance (bearish breaker), and vice versa. The signal is when price returns to test the zone from the other side.

**Variants:** the strict ICT version requires the original OB to sit in a structure that swept liquidity before being broken (as opposed to a "mitigation block", the case without a liquidity sweep) — this definition is hard to encode and inconsistent **[memory]**.

```python
def order_blocks(df, events, max_lookback=50):
    obs = []
    for e in events.itertuples():
        lo = max(0, e.i - max_lookback)
        seg = df.iloc[lo:e.i]                         # bars BEFORE the break bar
        opp = seg[seg.close < seg.open] if e.side == 1 else seg[seg.close > seg.open]
        if opp.empty:
            continue
        j = df.index.get_loc(opp.index[-1])           # last opposite candle
        obs.append(dict(side=e.side, top=df.high.iat[j], bottom=df.low.iat[j],
                        bar=j, active_from=e.i))      # only usable AFTER the break bar
    return pd.DataFrame(obs)

def track_ob(df, ob, close_invalidation=True):
    """Returns (first touch position, invalidation position) after the OB becomes active."""
    tapped = invalid = None
    for i in range(ob.active_from + 1, len(df)):
        h, l, c = df.high.iat[i], df.low.iat[i], df.close.iat[i]
        if ob.side == 1:
            if tapped is None and l <= ob.top:
                tapped = i
            if (c if close_invalidation else l) < ob.bottom:
                invalid = i
                break
        else:
            if tapped is None and h >= ob.bottom:
                tapped = i
            if (c if close_invalidation else h) > ob.top:
                invalid = i
                break
    return tapped, invalid
# Breaker: OB with invalid != None → flip side = -side, active from the invalid bar.
```

## B5. Fair Value Gap (FVG) / imbalance

**Definition (3-candle pattern, index t is the newest candle):**
- Bullish FVG: `low[t] > high[t-2]`. Zone = `[high[t-2], low[t]]`.
- Bearish FVG: `high[t] < low[t-2]`. Zone = `[high[t], low[t-2]]`.

Known at the **close of candle t**.

**Parameters and variants:**
- Extra condition on the middle candle: `close[t-1] > high[t-2]` (LuxAlgo **[checked]**), or the middle candle must be in the same direction (`smartmoneyconcepts` **[checked]**).
- Minimum size: by ATR, by % of price, or an automatic threshold. LuxAlgo "Auto Threshold": the middle candle's % change must exceed 2 × the cumulative mean of absolute % changes **[checked]**.
- Computed on another timeframe (LuxAlgo has a `Timeframe` input).
- Merge consecutive FVGs (`join_consecutive` in `smartmoneyconcepts`).
- **Fill/mitigation:** touching the edge, filling 50% ("consequent encroachment" in ICT terms), or filling completely.
- **Inverse FVG (IFVG):** an FVG closed through flips roles, like a breaker.
- Related terms: "imbalance", "inefficiency", "liquidity void" (a large gap spanning several candles). Some use "volume imbalance" specifically for the gap between the bodies of two adjacent candles — a different definition, don't mix them.

```python
def fvg(df, min_atr_mult=0.0, atr_n=14):
    a = atr(df, atr_n)
    bull_gap = df.low - df.high.shift(2)
    bear_gap = df.low.shift(2) - df.high
    bull = (bull_gap > 0) & (df.close.shift(1) > df.high.shift(2)) & (bull_gap >= min_atr_mult * a)
    bear = (bear_gap > 0) & (df.close.shift(1) < df.low.shift(2)) & (bear_gap >= min_atr_mult * a)
    out = pd.DataFrame(index=df.index)
    out["fvg"] = np.select([bull, bear], [1, -1], 0)
    out["top"] = np.where(bull, df.low, np.where(bear, df.low.shift(2), np.nan))
    out["bottom"] = np.where(bull, df.high.shift(2), np.where(bear, df.high, np.nan))
    return out   # row at t: the FVG is known when candle t closes

def fvg_fill_index(df, t, side, top, bottom, mode="full"):
    level = {"touch": top if side == 1 else bottom,
             "half": (top + bottom) / 2,
             "full": bottom if side == 1 else top}[mode]
    after = df.iloc[t + 1:]
    hit = after.index[after.low <= level] if side == 1 else after.index[after.high >= level]
    return hit[0] if len(hit) else None
```

## B6. Liquidity

Underlying hypothesis: stop-loss orders cluster above obvious highs and below obvious lows; price tends to seek out these areas.

### B6.1 Buy-side and sell-side liquidity

- **Buy-side liquidity (BSL):** the area **above** highs (swing highs, equal highs, previous day/week highs, session highs) — where buy stops sit.
- **Sell-side liquidity (SSL):** the area **below** lows — where sell stops sit.

Algorithmically, this is just a **list of price levels** with a "swept yet?" flag. Level sources: swings (B1), equal highs/lows, previous day/week/month high/low, session high/low.

### B6.2 Equal highs / equal lows (EQH / EQL)

**Definition:** two (or more) swing highs whose prices differ by less than a threshold.

**Parameters and variants:**
- ATR threshold: LuxAlgo uses `|level1 - level2| < 0.1 × ATR(200)`, with pivot length 3 ("Bars Confirmation") **[checked]**.
- % threshold: `smartmoneyconcepts.liquidity(..., range_percent=0.01)` **[checked]**.
- Minimum number of touches (2, 3...), minimum/maximum distance between touches.
- Require that price in between has not exceeded the level.

### B6.3 Liquidity sweep / stop hunt

**Definition:** price exceeds a liquidity level and then comes back.
- BSL sweep: `high[t] > level` **and** `close[t] < level`.
- SSL sweep: `low[t] < level` **and** `close[t] > level`.

**Variants:**
- Allow the return within `k` candles instead of within one candle.
- Cap the maximum penetration (`high - level <= m × ATR`) to distinguish from a real breakout.
- If the **close** goes fully past the level, it is a BOS/breakout, not a sweep.
- "Liquidity grab" / "stop hunt" / "raid" / "Judas swing": same idea, different names.

```python
def equal_levels(sw, a, thr_atr=0.1, kind="high"):
    s = (sw.swing_high if kind == "high" else sw.swing_low).dropna()
    rows = []
    for k in range(1, len(s)):
        if abs(s.iat[k] - s.iat[k - 1]) < thr_atr * a.loc[s.index[k]]:
            level = max(s.iat[k], s.iat[k - 1]) if kind == "high" else min(s.iat[k], s.iat[k - 1])
            rows.append(dict(level=level, first=s.index[k - 1], second=s.index[k]))
    return pd.DataFrame(rows)   # remember to add the pivot confirmation lag before using as a signal

def sweeps(df, level, known_pos, side, max_pen_atr=None, a=None):
    """side=+1: buy-side sweep (above highs). side=-1: sell-side sweep (below lows)."""
    out = []
    for i in range(known_pos + 1, len(df)):
        h, l, c = df.high.iat[i], df.low.iat[i], df.close.iat[i]
        if side == 1 and c > level:   # close fully past → breakout, level no longer valid
            break
        if side == -1 and c < level:
            break
        pierced = h > level if side == 1 else l < level
        if pierced:
            pen = (h - level) if side == 1 else (level - l)
            if max_pen_atr is None or pen <= max_pen_atr * a.iat[i]:
                out.append(i)
            break                      # each level counts only its first sweep
    return out
```

## B7. Premium / discount zones and equilibrium

**Definition:** pick a **dealing range** `[L, H]`. Equilibrium `EQ = (H + L) / 2`. Above EQ is premium (favor selling), below EQ is discount (favor buying).

Normalized position: `pos = (close - L) / (H - L)`, in 0..1.

**Parameters and variants — the most subjective part is choosing the range:**
- The most recent swing high and swing low of the swing structure, updated as price makes new extremes (LuxAlgo: "trailing" top/bottom **[checked]**).
- Highest/lowest of the last N bars (the Part C indicator does this with N = 35 **[checked]**).
- Previous day/week range, or the session range.
- Zone split: LuxAlgo draws premium as the top 5% of the range, equilibrium as the 47.5%–52.5% band, discount as the bottom 5% **[source checked]**. The ICT "Optimal Trade Entry" (OTE) variant uses the 62%–79% retracement zone **[memory]**.

```python
def premium_discount(df, sw):
    H = sw.sh_known.ffill()
    L = sw.sl_known.ffill()
    # optional: widen the range when price moves outside it (trailing extremes)
    rng = (H - L).where(H > L)
    pos = (df.close - L) / rng
    eq = (H + L) / 2
    zone = pd.Series(np.where(pos > 0.5, "premium", "discount"), index=df.index).where(pos.notna())
    return pd.DataFrame(dict(H=H, L=L, eq=eq, pos=pos, zone=zone))
```

## B8. Displacement

**Definition:** one or a few consecutive same-direction candles with large bodies and small wicks, showing a strong one-directional move.

**Computable rule:**
- `body = |close - open| >= k × ATR(n)` (e.g. k = 1.5), **and**
- `body / (high - low) >= r` (e.g. r = 0.7).

**Variants:** use the standard deviation of bodies instead of ATR; require leaving an FVG; require breaking a swing (i.e. accompanied by BOS/CHoCH); sum over 2–3 consecutive same-direction candles; add an above-average volume condition.

```python
def displacement(df, k=1.5, r=0.7, n=14):
    a = atr(df, n).shift(1)                      # previous bar's ATR, avoids self-reference
    body = (df.close - df.open).abs()
    rng = (df.high - df.low).replace(0, np.nan)
    ok = (body >= k * a) & (body / rng >= r)
    return np.sign(df.close - df.open).where(ok, 0).astype(int)   # +1 / -1 / 0
```

## B9. Inducement (IDM)

The hardest concept to encode and the least consistent.

**Workable definition:** in an uptrend, after a BOS, the **most recent minor pullback low** (internal swing low) lying above the area of interest (swing-structure OB/FVG) is the inducement. The theory says price will sweep that minor low first before reaching the area of interest; an entry is only valid **after the inducement has been swept**.

**Algorithm:**
1. Determine the trend and most recent swing using swing structure (long length).
2. Within the current leg, find the most recent internal swing against the trend (bullish: the most recent internal swing low counting from the high).
3. IDM = that price level.
4. "IDM taken" when `low < IDM` (bullish) or `high > IDM` (bearish).

**Variants:** use the first pullback after the BOS instead of the most recent; define a valid pullback by candles (a candle breaking the previous candle's low) instead of by pivots; require a wick sweep or allow a close.

```python
def inducement(df, sw_internal, trend, leg_start_pos, now_pos):
    """trend=+1: IDM is the most recent internal swing low in the leg (confirmed before now_pos)."""
    col = "sl_known" if trend == 1 else "sh_known"
    s = sw_internal[col].iloc[leg_start_pos:now_pos + 1].dropna()
    return None if s.empty else float(s.iloc[-1])

def idm_taken(df, idm, trend, from_pos):
    after = df.iloc[from_pos + 1:]
    hit = after.index[after.low < idm] if trend == 1 else after.index[after.high > idm]
    return hit[0] if len(hit) else None
```

## B10. Kill zones / sessions

**Definition:** fixed time windows in the day believed to have high liquidity and volatility. Algorithmically it is just a time filter, plus recording session high/low as liquidity levels.

**Commonly cited windows (New York time)** — **[unverified: from memory, sources give different windows]**:

| Kill zone | New York time (approx.) |
|---|---|
| Asian | 20:00 – 00:00 |
| London open | 02:00 – 05:00 |
| New York (AM) | 07:00 – 10:00 (some sources say 08:30 – 11:00) |
| London close | 10:00 – 12:00 |

`smartmoneyconcepts.sessions()` offers Sydney, Tokyo, London, New York, Asian kill zone, London open kill zone, New York kill zone, London close kill zone and Custom **[names checked]**; the exact hours the library uses are **[unverified]**.

**Notes:**
- Always compute in a DST-aware timezone (`America/New_York`, `Europe/London`), not a fixed UTC offset.
- Kill zones come from forex and US indices. Crypto trades 24/7; time-of-day effects exist (US equity open, funding settlement times...) but must be **measured on your own data**, not assumed from forex windows.
- In Pine: `time(timeframe.period, "0200-0500", "America/New_York")` returns `na` outside the session **[memory on the timezone parameter]**.

```python
def in_session(df, start="02:00", end="05:00", tz="America/New_York"):
    local = df.index.tz_convert(tz)           # index must be timezone-aware (UTC)
    t = local.strftime("%H:%M")
    return (t >= start) & (t < end) if start < end else (t >= start) | (t < end)

def session_levels(df, mask, tz="America/New_York"):
    day = df.index.tz_convert(tz).date
    g = df[mask].groupby(day[mask])
    return pd.DataFrame({"sess_high": g.high.max(), "sess_low": g.low.min()})
    # Only use these levels AFTER the session ends.
```

## B11. Parameter summary table

| Concept | Main parameters | Ambiguities to settle before testing |
|---|---|---|
| Swing | `L`, `R` | Tie handling; confirmation lag |
| Internal / swing | Two lengths (5 / 50) | Filter duplicate levels or not |
| BOS / CHoCH | close or wick; ATR buffer | Label of the first break; which swing counts |
| Order block | Candle selection; body or wick | Displacement/FVG filter |
| Mitigation | Touch or invalidation; close or wick | Number of touches allowed |
| FVG | Minimum size; middle-candle condition | What counts as "filled" |
| EQH / EQL | Threshold (ATR or %); number of touches | Distance between the two highs |
| Sweep | Candles allowed to return; max penetration | Boundary between sweep and breakout |
| Premium / discount | Range selection | Static or trailing range |
| Displacement | `k`, `r`, `n` | One candle or several |
| Inducement | Internal length | Which pullback counts |
| Kill zone | Time window, timezone | Apply to crypto or not |

---

# Part C — The "Dynamic SMC & Market Structure PRO" indicator

URL: https://www.tradingview.com/script/j5Sp5u7i-Dynamic-SMC-Market-Structure-PRO/

## C1. Overview **[checked — page and source read]**

| | |
|---|---|
| Author | ACE_Chart_Logic |
| Published | 2026-08-03, version 1.0, no updates yet |
| Type | Open-source indicator, `overlay = true` |
| Pine version | `//@version=6` |
| License | First line of the source says **Mozilla Public License 2.0** |
| Length | About 240 lines, one file, no library imports |
| Declaration | `max_lines_count = 500`, `max_boxes_count = 100`, `max_labels_count = 500` |

"PRO" is just a name; this is a free, open-source script. The description states it is for educational purposes and gives no trading signals.

## C2. License and reuse rules

- Open-source scripts on TradingView default to **MPL 2.0**; authors may state another license in the source. This script uses the default.
- **TradingView's Script Publishing Rules take precedence over the license** the author chooses, including MPL 2.0. Key points **[checked]**:
  - Reusing open-source code to **publish** on TradingView requires the new script to be open-source, unless you have the author's explicit (and provable) permission, or the code is public domain and only part of the script.
  - You must **credit the author** in the description (or release notes if added in an update); crediting in source comments is also recommended.
  - Reused code should only be part of the script and must have **significant improvements**. Changing style, inputs, variable names, rearranging code, or converting Pine versions does **not** count as improvement.
  - Imitating another author's script is banned; plagiarism can lead to a permanent ban.
  - Use in paid (vendor) products requires the author's permission and a clear statement of purpose.
  - Private use (not published) is unrestricted.
- For this project: reading to understand and reimplementing in Python is safe. Copying Pine code into a distributed product requires MPL 2.0 compliance (keep the license notice, publish source of modified files); republishing on TradingView follows the Script Publishing Rules above. This is a summary, not legal advice.
- For that reason, this document **does not copy the source verbatim**, only describes the logic.

## C3. What the indicator draws

1. Arrow labels at **major swing highs/lows**.
2. Dashed lines and **BOS / CHoCH** text.
3. **SUPPLY / DEMAND** boxes, auto-deleted when price closes through them.
4. **PDH / PDL** lines (previous day high/low), auto-deleted when swept.
5. **Asia session high/low** lines, auto-deleted when swept.
6. A **0.50 EQ** line.
7. A 2-column × 4-row **dashboard table** in the top-right corner.

Not included: FVG, equal highs/lows, internal structure, order blocks in the strict sense, London/New York kill zones, and **no alerts at all** (no `alert()` or `alertcondition()`).

## C4. Inputs **[source checked]**

| Group | Input | Default | Constraint |
|---|---|---|---|
| Major Swing Extremes | Show Major Swing High/Low Shapes | true | |
| | Major Swing Lookback Sensitivity | 20 | 5–100 |
| | High / low color | red / green | |
| Smart Money Structure | Show BOS & CHoCH Lines | true | |
| | Structure Sensitivity (Pivot Length) | 8 | ≥ 3 |
| | Bullish / bearish color | green / red | |
| Supply & Demand | Show Dynamic Supply & Demand Zones | true | |
| | Max Active Zones Per Side | 4 | 1–10 |
| | Zone Transparency | 80 | 0–100 |
| | Supply / demand color | red / green | |
| PDH & PDL | Show Active PDH / PDL | true | |
| | PDH / PDL color | cyan / yellow | |
| Session | Show Session High/Low Lines | true | |
| | Asia color | light blue | |
| | Clutter Distance Threshold (Pips / Gold $) | 15.0 | ≥ 1 |
| Fibonacci 0.5 EQ | Show 0.5 Equilibrium Line | true | |
| | Equilibrium Lookback Range | 35 | ≥ 10 |
| | EQ color | purple | |
| Dashboard | Show Information Panel | true | |

Parameters **hard-coded, not adjustable**: supply/demand pivot length (6/6), Asia session hours (`0000-0600`, Monday–Friday), ATR(14), "D" timeframe for PDH/PDL.

## C5. Logic per block

**1. Major swing.** Pivot high/low with equal length on both sides (default 20). When a pivot is confirmed, a label is drawn back at the pivot bar, offset by 0.3 × ATR(14). Visual only, not used by other logic.

**2. BOS / CHoCH.** A separate pivot set (default 8). The script remembers only **one** pivot high and **one** pivot low (the most recent); a new pivot overwrites the old one, no HH/HL/LH/LL classification. When the close crosses above the remembered pivot high: if the trend state is bearish it labels CHoCH, otherwise (including no trend) BOS; sets the trend to bullish; clears the broken level. The bearish side is symmetric. This is exactly the minimal definition in B2/B3.

**3. Supply / demand.** Fixed 6/6 pivot. At each pivot high, draws a supply box from the **pivot candle's high down to the top of its body** (i.e. the upper wick); at a pivot low, a demand box from the **bottom of the body down to the low** (lower wick). Keeps at most N boxes per side, FIFO. Each bar: if `close` goes above the top of a supply box, delete it; if `close` goes below the bottom of a demand box, delete it; otherwise extend the box 12 bars to the right.

**4. PDH / PDL.** Gets the previous day's high and low via `request.security` on the "D" timeframe with offset `[1]` and `lookahead_on` — exactly the non-repainting pattern in A6. Resets each new day. Intraday, if `high` exceeds PDH it is marked "swept" and the line is hidden; same for PDL. Lines are deleted and redrawn every bar.

**5. Asia session.** Session `0000-0600`, Monday–Friday, in the **exchange/symbol timezone** (no timezone argument passed). During the session it accumulates high/low. Afterwards, if price exceeds a level, the line is deleted and the level dropped. A line is hidden if it is too close to PDH/PDL; threshold = input × `syminfo.mintick` × 10 (forex) or × 100 (other).

**6. Equilibrium.** Midpoint of the highest high and lowest low over the last 35 bars. Drawn only on the last bar.

**7. Dashboard.** Four rows: Structure Trend (BULLISH/BEARISH/NEUTRAL), Pricing Zone (PREMIUM if `close` > EQ, otherwise DISCOUNT), PDH/PDL State, and the count of active supply/demand zones.

## C6. Technical observations

The following observations come from **reading the source**; the script was not run on a chart to verify them.

1. **Plotting in the past.** Major swing labels appear 20 bars late but are placed at the pivot bar; supply/demand boxes lag 6 bars. Looking back at history makes it look "better" than reality. This is the "plotting in the past" form of repainting (A1.6).
2. **No wait for bar close.** BOS/CHoCH conditions lack `barstate.isconfirmed`, so on the live bar labels can appear and then disappear.
3. **`ta.crossover`/`ta.crossunder` after `and`.** With v6 lazy evaluation, the function may not be called on every bar (when the input is off or no pivot exists yet), violating the guidance in A1.5. Practical impact **[unverified]**. Also, crossing a level that just changed value (new pivot overwriting) can miss breaks when a new pivot forms while price is already above it.
4. **Trend state tied to a display toggle.** Turning off "Show BOS & CHoCH Lines" also stops the dashboard trend from updating.
5. **"Supply/demand" is not an order block.** The zone is just the pivot candle's wick, requires no displacement, does not track mitigation in the touch sense; only close-based invalidation.
6. **Equilibrium is not swing-based.** The description says "across recent swings" but the code uses the highest/lowest of 35 bars — a sliding window, so the EQ level and premium/discount label drift every bar.
7. **Hard-coded session, unsuited to crypto.** Hours use the symbol's timezone; for crypto pairs that is usually UTC, so `0000-0600` does not match the "Asia session" in the usual sense. The day filter skips weekends although crypto runs 24/7. The "pip" threshold is designed for forex/gold and is meaningless for most crypto pairs.
8. **No alerts**, so it cannot be connected to webhooks without modifying the code.
9. **The dashboard label "PDH Swept" takes priority** when both PDH and PDL have been swept.
10. **Performance:** deletes and recreates lines/labels every bar instead of using `set_*`; acceptable for a small script.

**Conclusion:** this is a compact, readable introductory example of assembling basic SMC blocks in Pine v6, good as a reference for code structure. It is not a complete SMC implementation and should not be used as-is as a signal source, especially for crypto. The LuxAlgo version is far more complete conceptually, but its license forbids commercial use.

---

# Part D — An honest assessment of SMC/ICT

## D1. Empirical evidence: weak

- Two searches in this session (keywords on empirical research, arXiv/SSRN for "order block", "fair value gap", "smart money concepts") **found no peer-reviewed study** testing SMC/ICT as a system. Results were almost entirely broker articles, blogs, and tool advertising. Not finding is not the same as not existing, but if such studies exist they are not easy to find.
- LuxAlgo's own SMC indicator page states that these concepts are not guaranteed to reflect institutional liquidity and that **there is no data proving their validity** **[checked]**.
- Widely circulated figures like "FVGs get filled 70% of the time" cannot be traced to a source **[unverified]**. Even if true, a high fill rate does not imply profit: randomly fluctuating prices also return to fill most small gaps. Compare against a baseline.
- The underlying story ("institutions hunt retail stops", "this candle is a bank order") is **not verifiable** with OHLCV data. It need not be true for a pattern to have value, but it cannot be taken as evidence either.

## D2. Closely related findings with an academic basis **[memory — not re-checked in this session, verify citations before use]**

- **Stop orders cluster around obvious levels and trigger price cascades:** Osler (2003, 2005) on the FX market. This is the closest to the "liquidity" idea.
- **Technical patterns carry a little information:** Lo, Mamaysky & Wang (2000).
- **Technical analysis profits largely vanish after costs and data-snooping adjustment:** Sullivan, Timmermann & White (1999); review by Park & Irwin (2007).
- **Intraday time-of-day effects** (volatility and liquidity by session) are real and widely documented — but high volatility does not by itself create a directional edge.
- **Multiple testing and backtest overfitting:** Bailey & López de Prado (Deflated Sharpe Ratio, Probability of Backtest Overfitting); Harvey, Liu & Zhu (2016).

In short: some **components** of SMC overlap with studied market microstructure phenomena (stop clusters, session effects, momentum after strong moves). The SMC **system** as taught has no credible independent testing.

## D3. Subjectivity and hindsight risks

1. **Elastic definitions.** Part B shows each concept has many variants. A hand-drawer picks whichever variant fits the known outcome.
2. **Pivot hindsight.** A swing is only known after `R` bars, but on the chart it is drawn at the pivot bar. Every "pretty" example uses future information.
3. **Unfalsifiable.** Failed setups are reinterpreted ("that was inducement", "liquidity wasn't fully taken", "wrong timeframe"). A theory that explains every outcome predicts nothing.
4. **Selection bias.** Educational content shows only winning examples.
5. **Too many degrees of freedom.** Timeframe × swing length × zone type × filters × session → you can always find a combination with a nice backtest.
6. **Different markets.** The concepts come from forex and US indices. Crypto is structured differently: 24/7, perps with funding and liquidation cascades, liquidity fragmented across exchanges.
7. **Commercial incentives.** Most SMC sources sell courses, signals or indicators.

## D4. How to test

1. **Fix definitions in code before looking at results.** Record parameters, don't change them after seeing PnL.
2. **Prevent lookahead.** Compute every signal at the confirmation bar (`i + R`), enter at the next bar's open. Write an automated test: truncate data at `t`; signals before `t` must not change when data after `t` is added.
3. **Event study first, strategy later.** For each event (FVG, sweep, CHoCH...), measure the distribution of forward returns at horizons of 1, 5, 20, 50 bars, plus MFE/MAE. Compare against:
   - an unconditional baseline (all bars);
   - a condition-matched baseline (same time of day, same volatility level, same trend direction);
   - "fake" events (e.g. random zones of the same size).
4. **Realistic costs:** taker/maker fees, spread, slippage, funding rate for perps. Many small edges vanish here.
5. **True out-of-sample:** walk-forward, or purged/combinatorial cross-validation with an embargo. Hold out a final data segment and use it only once.
6. **Multiple-testing correction:** record **all** variants tried; use the Deflated Sharpe Ratio or White's Reality Check / SPA; or Bonferroni/FDR for event studies.
7. **Robustness:** results must hold under small parameter changes, other symbols, other exchanges, other regimes (bull/bear/sideways). An edge that exists at only one parameter point is overfit.
8. **Sample size and dependence:** overlapping events are not independent; use block bootstrap for confidence intervals.
9. **Decomposition:** check whether the edge comes from the SMC concept or from known factors (trend-following, volatility filtering, time-of-day effects). If removing the SMC part leaves results unchanged, SMC contributes nothing.
10. **Forward test** with paper trading or small capital before trusting it.

**Recommendation for the project:** treat SMC concepts as **feature generators** (distance to the nearest liquidity level, whether an unfilled FVG exists, position in the dealing range, whether a sweep just occurred...) to feed into a quantitative testing pipeline — not as strategies with a built-in edge. The default hypothesis is **no edge** until out-of-sample, after-cost data proves otherwise.

---

# Unverified items

1. **Pine sample code (A11, A9) and Python pseudocode (Part B)** have not been compiled/run.
2. **`strategy()` defaults** (`initial_capital`, `default_qty_type`, commission, slippage, margin) — written from memory; the docs page as read only confirms `pyramiding` defaults to 1.
3. **Maximum script run time per plan** — the limitations page gives no number.
4. **History depth of `request.footprint()`**; the full list of `footprint.*`/`volume_row.*` functions (only those seen in the docs are listed).
5. **Webhooks:** whether a paid plan is required; whether there is a retry mechanism.
6. **Full signatures** of drawing functions, the `input.*` list, the `ta.*` list, v6 lazy `and`/`or` behavior, the timezone parameter of `time()` — written from memory, not cross-checked against the Reference Manual in this session.
7. **Pine has no function to read the built-in Volume Profile** — conclusion based on memory and not seeing any such function in the pages read; the full Reference Manual was not reviewed.
8. **ICT kill zone hours** and the exact hours `smartmoneyconcepts.sessions()` uses.
9. **License of `smartmoneyconcepts`** (empty on PyPI).
10. **Practical impact of `ta.crossover` after `and`** in the Part C indicator — inferred from reading code, not run.
11. **Academic citations in D2** — from memory, not re-checked.
12. **The "FVG fills ~70%" figure** and all SMC win rates circulating online — no traceable source.
13. The "strict" ICT definition of breaker blocks, OTE 62–79%, MSS vs CHoCH — from memory, sources disagree.
14. Long docs pages were truncated by the reading tool (release notes, strategies, execution model, type system, other timeframes) — changes in unread parts may be missed.

---

# Sources

**Pine Script (TradingView)**
- Docs home: https://www.tradingview.com/pine-script-docs/welcome/
- Release notes: https://www.tradingview.com/pine-script-docs/release-notes/
- Execution model: https://www.tradingview.com/pine-script-docs/language/execution-model/
- Type system: https://www.tradingview.com/pine-script-docs/language/type-system/
- Conditional structures (`once`): https://www.tradingview.com/pine-script-docs/language/conditional-structures/
- Other timeframes and data (`request.*`, footprint): https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/
- Repainting: https://www.tradingview.com/pine-script-docs/concepts/repainting/
- Strategies: https://www.tradingview.com/pine-script-docs/concepts/strategies/
- Alerts: https://www.tradingview.com/pine-script-docs/concepts/alerts/
- Limitations: https://www.tradingview.com/pine-script-docs/writing/limitations/
- Publishing scripts: https://www.tradingview.com/pine-script-docs/writing/publishing/
- Reference Manual v6: https://www.tradingview.com/pine-script-reference/v6/ (not read directly in this session)
- About webhooks: https://www.tradingview.com/support/solutions/43000529348-about-webhooks/
- Script publishing rules: https://www.tradingview.com/support/solutions/43000590599-script-publishing-rules/
- Vendor requirements: https://www.tradingview.com/support/solutions/43000549951-vendor-requirements/
- Mozilla Public License 2.0: https://mozilla.org/MPL/2.0/

**SMC indicators and libraries**
- Dynamic SMC & Market Structure PRO (ACE_Chart_Logic): https://www.tradingview.com/script/j5Sp5u7i-Dynamic-SMC-Market-Structure-PRO/
- Smart Money Concepts (SMC) [LuxAlgo]: https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/
- CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/
- `smartmoneyconcepts` (GitHub): https://github.com/joshyattridge/smart-money-concepts
- `smartmoneyconcepts` (PyPI): https://pypi.org/project/smartmoneyconcepts/

**Search results on evidence (not academic sources)**
- XS.com — SMC explainer, notes there is no peer-reviewed research: https://www.xs.com/en/test-blog/smc-smart-money-concepts-explained/
- MQL5 blog — difficulties turning order blocks into EA rules: https://www.mql5.com/en/blogs/post/779413
