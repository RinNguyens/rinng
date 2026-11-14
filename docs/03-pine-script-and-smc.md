# 03 — Pine Script và Smart Money Concepts (SMC)

> Ngày tra cứu: **2026-11-13**. Mọi số liệu về giới hạn, tên hàm và release notes đều lấy từ tài liệu TradingView đọc trong ngày này; TradingView thay đổi thường xuyên nên cần tra lại trước khi dựa vào.
>
> Quy ước đánh dấu:
> - **[đã tra]** — đọc trực tiếp từ nguồn kèm URL trong phiên tra cứu này.
> - **[trí nhớ]** — kiến thức nền của người viết, không mở lại trang nguồn trong phiên này; coi như cần kiểm tra lại khi dùng.
> - **[chưa xác minh]** — không tìm được nguồn xác nhận, hoặc nguồn đọc được không nói rõ.
>
> Tài liệu này không phải lời khuyên đầu tư.

## Mục lục

- [Phần A — Pine Script v6](#phần-a--pine-script-v6)
- [Phần B — Smart Money Concepts dưới dạng thuật toán](#phần-b--smart-money-concepts-dưới-dạng-thuật-toán)
- [Phần C — Indicator "Dynamic SMC & Market Structure PRO"](#phần-c--indicator-dynamic-smc--market-structure-pro)
- [Phần D — Đánh giá trung thực về SMC/ICT](#phần-d--đánh-giá-trung-thực-về-smcict)
- [Danh sách điều chưa xác minh](#danh-sách-điều-chưa-xác-minh)
- [Nguồn](#nguồn)

---

# Phần A — Pine Script v6

## A0. Phiên bản

Phiên bản mới nhất là **Pine Script v6**. Trang release notes ghi rõ các cập nhật tương lai chỉ áp dụng cho v6 **[đã tra]**. Mỗi script khai báo phiên bản ở dòng đầu: `//@version=6`.

Các thay đổi đáng chú ý trong 2025–2026 (theo release notes **[đã tra]**):

| Thời điểm | Thay đổi |
|---|---|
| 02/2025 | Bỏ giới hạn 550 scope; thêm biến `bid`, `ask` (chỉ có trên timeframe `"1T"`) |
| 03/2025 | `box.set_xloc()`; vòng `for` đánh giá lại biên `to_num` trước mỗi lần lặp |
| 06/2025 | Library được export hằng `const` |
| 07/2025 | Tham số `active` cho mọi `input*()`; `syminfo.current_contract` |
| 08/2025 | Giới hạn độ dài string tăng từ 4.096 lên 40.960 ký tự |
| 09/2025 | Tham số `linestyle` cho `plot()` (`plot.linestyle_solid/dashed/dotted`) |
| 10/2025 | Tham số `timeframe_bars_back` cho `time()` và `time_close()` |
| 01/2026 | `request.footprint()` và hai kiểu `footprint`, `volume_row` (xem A9) |
| 04/2026 | Multiline string với `"""` hoặc `'''`; sắp xếp collection chứa UDT bằng `sort_field` |
| 07/2026 | `strategy()` có thêm `calc_on_every_history_tick`; giao diện Strategy Tester đổi tên nhiều mục (xem A8) |
| 08/2026 | Từ khoá `once` (cấu trúc điều kiện chạy một lần); Pine Screener mở rộng |
| 09/2026 | Table có thể chuyển xuống bottom panel |

Điểm khác biệt lõi của v6 so với v5:
- **Dynamic requests** bật mặc định: `request.*()` nhận tham số "series", gọi được trong `if`/vòng lặp/hàm export. Tắt bằng `dynamic_requests = false` trong khai báo **[đã tra]**.
- `bool` không bao giờ là `na`; `int`/`float` không tự ép sang `bool`, phải dùng `bool()` **[đã tra]**.
- `and`/`or` đánh giá lười (short-circuit) **[trí nhớ]** — có hệ quả thực tế: một lời gọi `ta.*` nằm sau `and` có thể không chạy trên mọi bar (xem A1.5 và Phần C).
- Strategy: margin mặc định 100%, tham số `when` bị bỏ, vượt 9.000 trade thì cắt bớt trade cũ thay vì báo lỗi **[trí nhớ, phần 9.000 trade đã tra]**.

## A1. Mô hình thực thi

Nguồn: https://www.tradingview.com/pine-script-docs/language/execution-model/ **[đã tra]**

### A1.1 Chạy theo từng bar

Script không chạy một lần trên cả mảng dữ liệu. Nó chạy **lặp lại từ bar đầu tiên đến bar cuối**, mỗi bar đã đóng (historical) chạy đúng một lần. Sau mỗi lần chạy, giá trị của mọi biến được "commit" vào một time series đánh chỉ số theo `bar_index`.

Hệ quả: gần như mọi biểu thức là một **series**. `close` không phải một số mà là "giá đóng cửa của bar đang xét".

### A1.2 History referencing bằng `[]`

- `x[0]` là bar hiện tại, `x[1]` là bar trước, `x[n]` là n bar trước. Không có dữ liệu thì trả `na`.
- Biểu thức cũng có lịch sử: `(high - low)[1]` hợp lệ.
- Không tham chiếu được tương lai (không có offset âm).
- Historical buffer: tối đa **5.000** giá trị quá khứ cho phần lớn series, **10.000** cho `open/high/low/close/time` **[đã tra — trang limitations]**. Buffer tự co giãn theo offset lớn nhất script dùng; khi Pine đoán sai thì dùng `max_bars_back` (tham số của `indicator()`/`strategy()` hoặc hàm `max_bars_back(var, num)`) **[trí nhớ]**.

### A1.3 `var` và `varip`

- Không có từ khoá: biến được khởi tạo lại ở mỗi bar.
- `var`: khởi tạo một lần, giữ giá trị qua các bar. Trên bar đang mở, mỗi tick nó quay về giá trị đã commit ở bar trước.
- `varip`: giữ giá trị qua cả các tick trong cùng một bar. Chỉ có ý nghĩa trên realtime; gây repaint, không backtest được.

### A1.4 Historical bar và realtime bar

| | Historical bar | Realtime bar |
|---|---|---|
| Số lần chạy | 1 lần, dùng OHLC cuối cùng | Indicator: mỗi tick một lần. Strategy: mặc định một lần lúc đóng bar |
| `high/low/close` | Cố định | Thay đổi cho tới khi bar đóng |
| Rollback | Không | Trước mỗi tick, trạng thái script quay về lần commit gần nhất |

Rollback không hoàn tác: biến `varip`, Pine Logs, lệnh strategy đã gửi, alert đã bắn, runtime error.

Các `barstate.*` hay dùng: `barstate.ishistory`, `barstate.isrealtime`, `barstate.isnew`, `barstate.isconfirmed` (lần chạy cuối của bar), `barstate.islast`, `barstate.isfirst`, `barstate.islastconfirmedhistory` **[4 cái đầu đã tra, còn lại trí nhớ]**.

Script chạy lại toàn bộ khi: thêm/lưu script, refresh chart, đổi input, đổi symbol/timeframe, tạo lại alert... Sau khi chạy lại, các bar từng là realtime trở thành historical, nên kết quả có thể khác — đây là gốc rễ của repaint.

### A1.5 Tính nhất quán của lời gọi hàm

Các hàm có trạng thái lịch sử (`ta.*`, và mọi hàm dùng `[]` bên trong) nên được gọi ở **global scope, trên mọi bar**. Gọi trong `if`, trong nhánh `?:`, hoặc sau `and`/`or` thì lịch sử nội bộ của hàm bị thủng và kết quả sai lệch. Compiler có cảnh báo cho trường hợp này **[đã tra]**. Cách viết an toàn:

```pine
bool crossUp = ta.crossover(close, level)   // luôn tính ở global scope
if showStructure and crossUp
    // ...
```

### A1.6 Repainting và cách tránh

Nguồn: https://www.tradingview.com/pine-script-docs/concepts/repainting/ **[đã tra]**

Repainting là khi hành vi trên historical khác realtime. Ba nhóm:

**1. Tính toán historical khác realtime**

| Nguyên nhân | Cách tránh |
|---|---|
| Dùng `close/high/low` của bar chưa đóng | Thêm `and barstate.isconfirmed`, hoặc dùng giá trị `[1]`. Đổi lại: tín hiệu trễ một bar |
| `request.security()` lấy higher timeframe trả giá trị chưa chốt | `request.security(sym, tf, expr[1], lookahead = barmerge.lookahead_on)` — phải có **cả hai** phần |
| `request.security()` lấy timeframe thấp hơn chart | Dùng `request.security_lower_tf()` |
| `lookahead_on` mà không có `[1]` | Rò rỉ tương lai. Không bao giờ dùng. Script kiểu này bị cấm publish |
| `varip` | Không dùng cho logic cần backtest |
| `barstate.isnew` | Dùng `barstate.isconfirmed` |
| `timenow` | Không có cách sửa — bản chất là repaint |
| Strategy với `calc_on_every_tick = true` | Tránh; chạy lúc đóng bar thì khớp với backtest |

**2. Vẽ vào quá khứ.** `ta.pivothigh(high, 5, 5)` chỉ biết pivot sau 5 bar, nhưng nếu vẽ tại `bar_index - 5` thì trên chart trông như biết ngay lúc đó. Mọi indicator SMC đều dính điểm này. Vẽ vào quá khứ để nhìn thì được, nhưng **logic giao dịch phải tính tại bar xác nhận**, không phải bar pivot.

**3. Dataset thay đổi.** Bar đầu tiên được nạp phụ thuộc gói tài khoản và timeframe, nên `ta.ema()`, `ta.barssince()`, `ta.valuewhen()` có thể ra khác nhau. Sàn cũng có thể sửa dữ liệu lịch sử.

## A2. Kiểu dữ liệu và qualifier

Nguồn: https://www.tradingview.com/pine-script-docs/language/type-system/ **[đã tra]**

**Qualifier** (yếu đến mạnh): `const` < `input` < `simple` < `series`.

- `const`: biết lúc compile.
- `input`: biết lúc người dùng chỉnh Settings.
- `simple`: biết ở bar đầu tiên, sau đó không đổi (ví dụ `syminfo.mintick`).
- `series`: có thể đổi theo từng bar.

Biểu thức thừa hưởng qualifier mạnh nhất trong các thành phần; không hạ qualifier được. Nhiều tham số yêu cầu qualifier yếu, ví dụ `length` của `ta.ema()` phải là "simple int", còn `ta.sma()` nhận "series int" **[trí nhớ]**.

**Kiểu:**
- Giá trị cơ bản: `int`, `float`, `bool`, `color`, `string`.
- `enum` (khai báo bằng `enum`, dùng với `input.enum()`).
- Kiểu tham chiếu (luôn là `series`): `plot`, `hline`, `line`, `linefill`, `box`, `polyline`, `label`, `table`, `chart.point`, `footprint`, `volume_row`.
- Collection: `array<T>`, `matrix<T>`, `map<K, V>`.
- UDT khai báo bằng `type`.
- `void` cho hàm không trả giá trị; tuple chỉ dùng làm giá trị trả về của hàm/`request.security` **[trí nhớ]**.
- `na` là "không có giá trị"; kiểm tra bằng `na(x)`, không so sánh `x == na`. `bool` không bao giờ `na`.

## A3. Khai báo script

Một script có đúng một trong ba lời khai báo **[trí nhớ, tên tham số đối chiếu với mã nguồn đã đọc]**:

```pine
//@version=6
indicator("Tên", shorttitle = "Ngắn", overlay = true,
     max_lines_count = 500, max_boxes_count = 500, max_labels_count = 500,
     max_bars_back = 2000)
```

- `indicator()` — tính toán và vẽ, không đặt lệnh. Có alert.
- `strategy()` — thêm các hàm `strategy.*` và broker emulator để backtest (A8).
- `library()` — chỉ chứa hàm/type/hằng được `export`, dùng lại qua `import user/LibName/version as alias`. Library không tự vẽ khi được import.

## A4. Input

Các hàm: `input()`, `input.int()`, `input.float()`, `input.bool()`, `input.string()`, `input.color()`, `input.source()`, `input.timeframe()`, `input.session()`, `input.symbol()`, `input.time()`, `input.price()`, `input.text_area()`, `input.enum()` **[trí nhớ; `input.int/float/bool/color/string/timeframe` thấy trong mã nguồn đã đọc]**.

Tham số chung thường gặp: `defval`, `title`, `minval`, `maxval`, `step`, `options`, `tooltip`, `inline`, `group`, `confirm`, `display`, và `active` (từ 07/2025 **[đã tra]**).

Giá trị trả về có qualifier `input`, trừ `input.source()` trả series.

## A5. Output: plot và drawing

| Nhóm | Hàm | Ghi chú |
|---|---|---|
| Plot | `plot()`, `plotshape()`, `plotchar()`, `plotarrow()`, `plotcandle()`, `plotbar()`, `hline()`, `fill()`, `bgcolor()`, `barcolor()` | Tối đa **64 plot count** mỗi script; một lời gọi có thể tốn tới 7 **[đã tra]**. Phải gọi ở global scope |
| Line | `line.new(x1, y1, x2, y2, xloc, extend, color, style, width)` | Mặc định giữ 50, tối đa 500 |
| Box | `box.new(left, top, right, bottom, ...)` | Mặc định 50, tối đa 500 |
| Label | `label.new(x, y, text, xloc, yloc, color, style, textcolor, size, ...)` | Mặc định 50, tối đa 500 |
| Polyline | `polyline.new(points, curved, closed, xloc, line_color, fill_color, line_style, line_width)` nhận `array<chart.point>` | Mặc định 50, tối đa **100** |
| Linefill | `linefill.new(line1, line2, color)` | |
| Table | `table.new(position, columns, rows, ...)` + `table.cell()` | Tối đa 9 table (mỗi vị trí một cái) |

Số liệu giới hạn **[đã tra]**; chữ ký hàm **[trí nhớ]**. Khi vượt giới hạn, Pine tự xoá drawing cũ nhất (garbage collection), nên không thể giữ toàn bộ lịch sử FVG/OB trên chart dài.

Toạ độ x: `xloc.bar_index` (mặc định) hoặc `xloc.bar_time`. Với `xloc.bar_index`, vẽ được tối đa 10.000 bar về quá khứ và 500 bar về tương lai **[đã tra]**.

Mẹo hiệu năng: tạo drawing một lần với `var` rồi cập nhật bằng `*.set_*()`; chỉ cập nhật table trong `if barstate.islast`.

## A6. `request.security` và lookahead

Nguồn: https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/ **[đã tra]**

```
request.security(symbol, timeframe, expression, gaps, lookahead,
                 ignore_invalid_symbol, currency, calc_bars_count) → series <type>
```

- `expression` có thể là số, bool, string, tuple, collection, UDT, hoặc lời gọi hàm.
- `gaps`: mặc định `barmerge.gaps_off` (lấp bằng giá trị đã chốt gần nhất).
- `lookahead`: mặc định `barmerge.lookahead_off`.
  - Với higher timeframe, `lookahead_on` trên historical bar trả giá trị của HTF bar **chưa kết thúc** — tức là nhìn tương lai.
  - Mẫu chuẩn không repaint:

```pine
float htfClose = request.security(syminfo.tickerid, "240", close[1], lookahead = barmerge.lookahead_on)
// Previous Day High/Low:
[pdh, pdl] = request.security(syminfo.tickerid, "D", [high[1], low[1]], lookahead = barmerge.lookahead_on)
```

- Dynamic requests (v6): trên realtime bar chỉ lấy được dataset đã từng request trên historical.
- Giới hạn: **40** lời gọi `request.*()` duy nhất mỗi script, **64** với gói Ultimate. Lời gọi trùng tham số được dùng lại và không tính thêm; lời gọi nằm trong library được import **có** tính. Tổng số phần tử tuple qua mọi `request.*()` tối đa 127 **[đã tra]**.

Các hàm cùng họ: `request.security_lower_tf()`, `request.footprint()`, `request.currency_rate()`, `request.dividends()`, `request.splits()`, `request.earnings()`, `request.financial()`, `request.economic()`, `request.seed()` **[đã tra]**.

## A7. `ta.*`, collection, UDT, method

### A7.1 `ta.*` hay dùng **[trí nhớ; các hàm có dấu * thấy trong mã nguồn đã đọc]**

| Mục đích | Hàm |
|---|---|
| Trung bình | `ta.sma`, `ta.ema`, `ta.rma`, `ta.wma`, `ta.vwma`, `ta.hma`, `ta.vwap` |
| Biến động | `ta.atr`*, `ta.tr`*, `ta.stdev`, `ta.bb`, `ta.kc` |
| Dao động | `ta.rsi`, `ta.macd`, `ta.stoch`, `ta.cci`, `ta.mfi` |
| Cực trị | `ta.highest`*, `ta.lowest`*, `ta.highestbars`, `ta.lowestbars` |
| Pivot | `ta.pivothigh(source, leftbars, rightbars)`*, `ta.pivotlow(...)`* — trả giá pivot tại bar xác nhận, còn lại là `na` |
| Sự kiện | `ta.crossover`*, `ta.crossunder`*, `ta.cross`, `ta.change`*, `ta.barssince`, `ta.valuewhen` |
| Tích luỹ | `ta.cum`* |
| Xu hướng | `ta.supertrend`, `ta.dmi`, `ta.sar`, `ta.linreg` |

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

Giới hạn: 100.000 phần tử cho array/matrix; map tối đa 50.000 cặp key-value **[đã tra]**. Collection không chứa được collection khác trực tiếp — bọc trong UDT nếu cần. Vòng lặp: `for i = 0 to arr.size() - 1`, hoặc `for [i, v] in arr`. Mỗi vòng lặp không được chạy quá **500 ms** trên một bar **[đã tra]**.

### A7.3 UDT và method

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

UDT là kiểu tham chiếu: gán `b = a` không sao chép, dùng `a.copy()` **[trí nhớ]**. Field của UDT dùng `[]` để lấy lịch sử có hạn chế — nên lưu lịch sử vào array thay vì dựa vào `obj.field[1]` **[trí nhớ]**.

## A8. Strategy tester

Nguồn: https://www.tradingview.com/pine-script-docs/concepts/strategies/ **[đã tra một phần — trang bị cắt, xem ghi chú]**

```pine
//@version=6
strategy("Demo", overlay = true,
     initial_capital = 10000,
     default_qty_type = strategy.percent_of_equity, default_qty_value = 10,
     commission_type = strategy.commission.percent, commission_value = 0.05,
     slippage = 2,                // đơn vị: tick
     pyramiding = 0,
     process_orders_on_close = false)
```

**Lệnh** **[đã tra]**:
- `strategy.entry()` — tuân theo `pyramiding`, tự đảo vị thế.
- `strategy.order()` — bỏ qua pyramiding, không tự đảo.
- `strategy.exit()` — take-profit/stop-loss theo tick (`profit`, `loss`) hoặc giá (`limit`, `stop`), trailing (`trail_price`/`trail_points` + `trail_offset`).
- `strategy.close()`, `strategy.close_all()`, `strategy.cancel()`, `strategy.cancel_all()`.
- `strategy.risk.allow_entry_in()` và các hàm `strategy.risk.*` khác.

**Broker emulator** **[đã tra]**:
- Lệnh tạo lúc đóng bar được khớp ở **open của bar kế tiếp** (mặc định).
- Đường đi giá trong bar được giả định: nếu open gần high hơn thì open→high→low→close, ngược lại open→low→high→close.
- Không có gap trong bar; gap giữa hai bar thì khớp tại open bar sau.
- Bar Magnifier (nay gọi là "Bar detalization", gói Premium/Ultimate) dùng dữ liệu timeframe thấp hơn để khớp chính xác hơn, tối đa 200.000 bar LTF.
- Giữ chi tiết tối đa **9.000** trade gần nhất; Deep Backtesting giữ 1.000.000.

**Mặc định cần biết** **[trí nhớ — trang đọc được không tới phần này]**: `initial_capital = 1000000`, `default_qty_type = strategy.fixed` với số lượng 1, commission = 0, `slippage = 0`, `pyramiding = 1` (**[đã tra]**: trang docs ghi mặc định là 1), `margin_long = margin_short = 100`.

**Cập nhật 07/2026** **[đã tra]**: `calc_on_every_history_tick` (chạy script trên từng tick lịch sử, Premium/Ultimate); giao diện có menu "Script execution", "Bar detalization", "Heikin Ashi mode" (ứng với `fill_orders_on_standard_ohlc`), "Limit order execution" (`backtest_fill_limits_assumption`), và "Long/Short leverage" thay cho ô margin.

### Các bẫy backtest

1. **Commission và slippage bằng 0 theo mặc định.** Với crypto perp phải đặt phí taker thật và slippage; funding rate **không** được mô phỏng **[trí nhớ]**.
2. **Lookahead qua `request.security`** (A6) và qua việc vẽ pivot vào quá khứ rồi dùng luôn bar pivot làm tín hiệu.
3. **`process_orders_on_close = true`** khớp ngay tại close của bar tín hiệu — lạc quan, ngoài đời không khớp được đúng giá đó.
4. **TP và SL cùng nằm trong một bar**: kết quả phụ thuộc giả định đường đi giá ở trên. Bar càng lớn sai càng nhiều.
5. **Limit order khớp ngay khi giá chạm**: ngoài đời cần giá đi xuyên qua. Dùng `backtest_fill_limits_assumption`.
6. **Chart không chuẩn** (Heikin Ashi, Renko, Kagi, Range...): giá tổng hợp, kết quả thường phi thực tế **[đã tra]**.
7. **Số bar lịch sử có hạn** (A10) → mẫu nhỏ trên timeframe thấp.
8. **Mặc định dùng 100% equity hoặc số lượng cố định** làm méo đường equity.
9. **Tối ưu tham số trên cùng một đoạn dữ liệu** — TradingView không có walk-forward sẵn **[trí nhớ]**.
10. **`calc_on_every_tick`** làm realtime khác historical.

## A9. Volume profile trong Pine

**Không có hàm `ta.*` trả về volume profile.** Các indicator Volume Profile có sẵn của TradingView (Visible Range, Session, Fixed Range...) là built-in đóng; script không đọc được giá trị của chúng **[trí nhớ; trang FAQ đã tra không nhắc tới hàm nào như vậy]**. Có ba hướng:

### (1) `request.footprint()` — mới từ 01/2026 **[đã tra]**

```
request.footprint(ticks_per_row, va_percent, imbalance_percent) → series footprint
```

- `ticks_per_row`: "simple int", mỗi hàng cao `ticks_per_row * syminfo.mintick`.
- `va_percent`: mặc định 70. `imbalance_percent`: mặc định 300.
- Trả ID `footprint` của bar hiện tại, hoặc `na` — phải kiểm tra `na` trước khi dùng.
- Hàm của `footprint`: `total_volume()`, `buy_volume()`, `sell_volume()`, `delta()`, `poc()`, `vah()`, `val()` (ba hàm cuối trả `volume_row`), `rows()` (trả `array<volume_row>` theo giá tăng dần).
- Hàm của `volume_row`: `up_price()`, `down_price()`, `buy_volume()`, `sell_volume()`, `delta()`, `total_volume()`, `has_buy_imbalance()`, `has_sell_imbalance()`.
- Hạn chế: chỉ gói **Premium/Ultimate**; **một** lời gọi duy nhất mỗi script; trên timeframe ≥ 1D tổng volume có thể lệch so với `volume`.
- Đây là profile **theo từng bar** (footprint), không phải profile cho một khoảng tuỳ ý. Muốn profile cho cả session thì phải tự cộng dồn các hàng. Độ sâu lịch sử: **[chưa xác minh]**.

### (2) `request.security_lower_tf()` — tự xây profile **[đã tra chữ ký]**

```
request.security_lower_tf(symbol, timeframe, expression, ignore_invalid_symbol,
                          currency, ignore_invalid_timeframe, calc_bars_count) → array<type>
```

Trả về **một array cho mỗi chart bar**, mỗi phần tử ứng với một intrabar. Cách làm thông dụng: lấy `close` và `volume` của intrabar (ví dụ 1 phút), chia khoảng giá thành N bin, cộng volume vào bin tương ứng.

```pine
//@version=6
indicator("LTF volume theo bar", overlay = false)
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
plot(upVol - dnVol, "Delta xấp xỉ", style = plot.style_columns)
```

### Giới hạn dữ liệu intrabar **[đã tra]**

- Tổng intrabar lấy được: **100.000** (Basic/Essential/Plus/Premium), **125.000** (Expert), **200.000** (Ultimate).
- Hệ quả: chart 1H lấy intrabar 1 phút thì chỉ có khoảng 100.000 / 60 ≈ 1.666 bar có dữ liệu. Các bar cũ hơn trả array rỗng.
- Volume gán cho mức giá chỉ là **xấp xỉ**: ta biết volume của intrabar, không biết nó phân bố thế nào trong khoảng high–low của intrabar đó. Phân loại mua/bán theo chiều nến cũng là xấp xỉ, không phải aggressor thật.
- Với crypto, volume là của **một sàn** theo symbol đang chọn, không phải toàn thị trường.

### (3) Tính ở ngoài bằng Python

Với dữ liệu trade/aggTrade từ sàn, volume profile và delta tính chính xác hơn nhiều. Đây là lựa chọn nên dùng cho nghiên cứu nghiêm túc.

## A10. Giới hạn

Nguồn: https://www.tradingview.com/pine-script-docs/writing/limitations/ **[đã tra]**

| Hạng mục | Giới hạn |
|---|---|
| Thời gian compile | 2 phút; 3 cảnh báo liên tiếp thì bị khoá compile 1 giờ |
| Thời gian chạy script | Tuỳ gói; trang docs không nêu số, trỏ sang trang pricing — **[chưa xác minh con số]** |
| Một vòng lặp trên một bar | 500 ms |
| Plot | 64 plot count |
| Line / box / label | Mặc định 50, tối đa 500 mỗi loại |
| Polyline | Mặc định 50, tối đa 100 |
| Table | 9 |
| `request.*()` duy nhất | 40 (Ultimate: 64) |
| `request.footprint()` | 1 lời gọi; cần Premium/Ultimate |
| Intrabar | 100K / 125K (Expert) / 200K (Ultimate) |
| Phần tử tuple qua `request.*()` | 127 |
| Compiled token | 100.256 mỗi script; tổng library import 1 triệu |
| Biến mỗi scope | 1.000 |
| Collection | 100.000 phần tử; map 50.000 cặp |
| Historical buffer (`max_bars_back`) | 5.000; riêng OHLC và `time` là 10.000 |
| Drawing với `xloc.bar_index` | 10.000 bar quá khứ, 500 bar tương lai |
| Số chart bar | Ultimate 40.000; Expert 25.000; Premium 20.000; Essential/Plus 10.000; còn lại 5.000 |
| Lệnh strategy | 9.000 (Deep Backtesting: 1.000.000) |
| Độ dài string | 40.960 ký tự |

## A11. Code mẫu (tự viết, cú pháp v6)

> Ba đoạn dưới đây do người viết tài liệu tự soạn theo cú pháp v6, **chưa được compile trên TradingView trong phiên này** — cần dán vào Pine Editor để kiểm tra trước khi dùng.

### A11.1 Pivot swing high/low có nhãn HH/HL/LH/LL

```pine
//@version=6
indicator("Swing pivots", overlay = true, max_labels_count = 500)

int len = input.int(5, "Pivot length", minval = 1)

float ph = ta.pivothigh(high, len, len)
float pl = ta.pivotlow(low, len, len)

var float lastPh = na
var float lastPl = na

// Lưu ý: pivot chỉ được biết tại bar hiện tại, tức là trễ `len` bar.
// Nhãn được vẽ lùi về bar pivot để dễ nhìn; logic giao dịch phải dùng bar hiện tại.
if not na(ph)
    string tagH = na(lastPh) ? "H" : ph > lastPh ? "HH" : "LH"
    label.new(bar_index - len, ph, tagH, style = label.style_label_down, size = size.tiny)
    lastPh := ph

if not na(pl)
    string tagL = na(lastPl) ? "L" : pl > lastPl ? "HL" : "LL"
    label.new(bar_index - len, pl, tagL, style = label.style_label_up, size = size.tiny)
    lastPl := pl
```

### A11.2 Phát hiện Fair Value Gap

```pine
//@version=6
indicator("FVG", overlay = true, max_boxes_count = 500)

float minAtrMult = input.float(0.25, "Kích thước tối thiểu (x ATR)", minval = 0.0, step = 0.05)
int   extendBars = input.int(20, "Kéo dài (bar)", minval = 1)

float atr = ta.atr(14)

// Mẫu 3 nến: nến [2], nến [1] (nến giữa), nến [0].
// Chỉ đánh giá khi bar đã đóng để không repaint.
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

### A11.3 BOS/CHoCH đơn giản, kèm alert JSON cho webhook

```pine
//@version=6
indicator("BOS / CHoCH đơn giản", overlay = true, max_lines_count = 500, max_labels_count = 500)

int len = input.int(5, "Pivot length", minval = 1)

float ph = ta.pivothigh(high, len, len)
float pl = ta.pivotlow(low, len, len)

var float swingHigh    = na
var int   swingHighBar = na
var bool  highBroken   = true
var float swingLow     = na
var int   swingLowBar  = na
var bool  lowBroken    = true
var int   trend        = 0      // 1 = bullish, -1 = bearish, 0 = chưa xác định

if not na(ph)
    swingHigh    := ph
    swingHighBar := bar_index - len
    highBroken   := false

if not na(pl)
    swingLow    := pl
    swingLowBar := bar_index - len
    lowBroken   := false

// Phá vỡ xác nhận bằng giá đóng cửa của bar đã đóng.
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

Hạn chế cố ý của mẫu này: chỉ theo dõi một swing high và một swing low gần nhất, không phân biệt internal/swing structure, không yêu cầu displacement. Lần phá vỡ đầu tiên (khi `trend == 0`) được gắn nhãn BOS.

## A12. Alert và webhook

Nguồn: https://www.tradingview.com/pine-script-docs/concepts/alerts/ và https://www.tradingview.com/support/solutions/43000529348-about-webhooks/ **[đã tra]**

**Ba cách phát alert:**

| Cách | Dùng ở đâu | Nội dung message |
|---|---|---|
| `alert(message, freq)` | Indicator và strategy | "series string" — tự dựng được JSON động |
| `alertcondition(condition, title, message)` | Chỉ indicator; phải gọi ở global scope | "const string" + placeholder: `{{ticker}}`, `{{exchange}}`, `{{interval}}`, `{{time}}`, `{{timenow}}`, `{{open}}`, `{{high}}`, `{{low}}`, `{{close}}`, `{{volume}}`, `{{plot_0}}`…`{{plot_19}}`, `{{plot("tên")}}` |
| Order fill của strategy | Strategy | Tham số `alert_message` của `strategy.entry/order/exit/close`, lấy ra bằng placeholder `{{strategy.order.alert_message}}` trong ô Message |

`freq`: `alert.freq_once_per_bar` (mặc định), `alert.freq_once_per_bar_close`, `alert.freq_all`.

Điểm cần nhớ:
- Code chỉ tạo **alert event**. Người dùng phải tự bấm "Create Alert" trên giao diện; script không tự tạo alert được.
- Alert chỉ bắn trên **realtime bar**, chạy trên server TradingView.
- Alert lưu **bản chụp** script + input + symbol + timeframe tại lúc tạo. Sửa script xong phải tạo lại alert.

**Webhook:**
- TradingView gửi **HTTP POST**, body là message của alert.
- Message là JSON hợp lệ thì header là `application/json`, còn lại là `text/plain`.
- Chỉ chấp nhận cổng **80 và 443**.
- Server phải trả lời trong **3 giây**, quá thì request bị huỷ.
- IP nguồn (để allowlist): `52.89.214.238`, `34.212.75.30`, `54.218.53.128`, `52.32.178.7`.
- Không hỗ trợ IPv6.
- Tài khoản phải bật **2FA**.
- Trang webhook không nêu yêu cầu gói trả phí và không mô tả cơ chế tự gửi lại — **[chưa xác minh]** cả hai. Nên giả định là **không có retry**.

## A13. Điều Pine không làm được, và cách nối với Python

**Không làm được** **[trí nhớ, trừ mục có ghi chú]**:
- Không gọi HTTP/API bên ngoài, không socket, không đọc/ghi file, không database. Dữ liệu ngoài duy nhất đưa vào được là qua `request.seed()` (repo GitHub do người dùng duy trì **[đã tra tên hàm]**) hoặc dán tay vào input.
- Không đặt lệnh thật trực tiếp; chỉ phát alert.
- Không truy cập order book, không có tick lịch sử đầy đủ (ngoài footprint và timeframe `"1T"`).
- Không lưu trạng thái giữa các lần chạy; mỗi lần reload là tính lại từ đầu.
- Không import thư viện ngoài hệ sinh thái Pine, không machine learning ngoài những gì tự viết bằng Pine.
- Không đọc giá trị của indicator built-in đóng (ví dụ Volume Profile); không đọc drawing người dùng vẽ tay.
- Không tự tạo alert, không tự đổi symbol/timeframe của chart.
- Bị chặn bởi các giới hạn ở A10 — không phù hợp cho nghiên cứu trên dữ liệu lớn.

**Nối với Python — kiến trúc khuyến nghị:**

```
TradingView (Pine: alert() tạo JSON)
        │  HTTP POST, cổng 443, phải trả lời < 3 giây
        ▼
Webhook receiver (FastAPI / Cloudflare Worker)
   1. Kiểm tra secret trong body  2. Ghi vào queue  3. Trả 200 ngay
        ▼
Worker Python: kiểm tra lại tín hiệu bằng dữ liệu sàn → quản lý rủi ro → đặt lệnh qua API sàn
```

```python
# Giả mã receiver — không phải code production
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
    await queue.put(data)          # xử lý nặng làm ở worker khác
    return {"ok": True}            # trả lời ngay, tránh timeout 3 giây
```

Lưu ý thiết kế:
- TradingView không ký request. Xác thực bằng secret trong body cộng allowlist IP. Trang webhook khuyên không đưa thông tin nhạy cảm vào body — nên secret này chỉ là mã nhận diện tín hiệu, **không phải API key của sàn**.
- Làm **idempotent**: dùng `symbol + tf + time + event` làm khoá để chống tín hiệu trùng.
- Phía Python phải **tự kiểm tra lại** tín hiệu bằng dữ liệu của sàn; coi alert là gợi ý, không phải lệnh.
- Webhook có thể rớt. Cần cơ chế đối soát (ví dụ Python tự tính lại tín hiệu theo chu kỳ).
- Cách vững hơn về lâu dài: tính toàn bộ tín hiệu bằng Python trên dữ liệu sàn, chỉ dùng Pine để trực quan hoá và đối chiếu.

---

# Phần B — Smart Money Concepts dưới dạng thuật toán

**Lời dẫn quan trọng.** SMC/ICT là hệ thuật ngữ của giới trader, không có định nghĩa chuẩn. Cùng một tên gọi nhưng mỗi tác giả và mỗi indicator cài một quy tắc khác. Tài liệu này chọn định nghĩa **tính được bằng code**, nêu tham số và các biến thể. Hai cài đặt mã nguồn mở dùng làm mốc đối chiếu:

- **LuxAlgo — Smart Money Concepts [LuxAlgo]** (Pine v5, bản cập nhật 2025-09-23, giấy phép **CC BY-NC-SA 4.0** ghi trong mã nguồn — không dùng cho mục đích thương mại) **[đã tra mã nguồn]**: https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/
- **`smartmoneyconcepts`** (Python, PyPI bản 0.0.27 phát hành 2026-04-03) **[đã tra README và PyPI]**: https://github.com/joshyattridge/smart-money-concepts — giấy phép: PyPI để trống trường license, repo có file LICENSE nhưng loại giấy phép **[chưa xác minh]**.

Ký hiệu chung cho giả mã: `df` là pandas DataFrame có cột `open, high, low, close, volume`, index là thời gian UTC tăng dần. Các hàm dưới đây là **giả mã minh hoạ**, chưa được chạy kiểm thử.

```python
import numpy as np
import pandas as pd

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()      # Wilder (tương đương ta.rma)
```

## B1. Market structure

### B1.1 Swing high / swing low

**Định nghĩa (fractal/pivot):** bar `i` là swing high nếu `high[i]` là lớn nhất trong cửa sổ `[i-L, i+R]`. Swing low tương tự với `low`. Swing chỉ **được biết tại bar `i+R`**.

**Tham số:** `L`, `R` (thường bằng nhau).

**Biến thể:**
- `ta.pivothigh(high, L, R)` của Pine.
- LuxAlgo dùng "leg": tại bar `t`, nếu `high[t-size]` lớn hơn giá cao nhất của `size` bar sau nó thì bắt đầu một leg giảm và `high[t-size]` là swing high. Chỉ xét phía phải, và chỉ ghi nhận khi leg đổi chiều **[đã tra mã nguồn]**.
- `smartmoneyconcepts`: `swing_highs_lows(ohlc, swing_length=50)`, cao/thấp nhất trong `swing_length` nến trước và sau **[đã tra]**.
- ZigZag theo ngưỡng % hoặc theo bội số ATR (không phụ thuộc số bar).
- Xử lý hoà (hai bar cùng high) khác nhau giữa các cài đặt.

```python
def swings(df, n=5):
    w = 2 * n + 1
    is_sh = df.high.eq(df.high.rolling(w, center=True).max())
    is_sl = df.low.eq(df.low.rolling(w, center=True).min())
    out = pd.DataFrame(index=df.index)
    out["swing_high"] = df.high.where(is_sh)
    out["swing_low"] = df.low.where(is_sl)
    # CHỐNG LOOKAHEAD: swing tại vị trí i chỉ dùng được từ vị trí i + n
    out["sh_known"] = out.swing_high.shift(n)
    out["sl_known"] = out.swing_low.shift(n)
    return out
```

### B1.2 Phân loại HH / HL / LH / LL

So mỗi swing với swing **cùng loại** liền trước: swing high cao hơn → HH, thấp hơn → LH; swing low cao hơn → HL, thấp hơn → LL.

- Uptrend: chuỗi HH + HL. Downtrend: chuỗi LH + LL.
- Biến thể: bắt buộc swing high và low xen kẽ (nếu hai swing high liên tiếp thì giữ cái cao hơn); dùng ngưỡng bằng nhau để tách riêng equal high/low (B5).

```python
def classify(sw):
    sh = sw.swing_high.dropna()
    sl = sw.swing_low.dropna()
    lab_h = np.where(sh.diff() > 0, "HH", "LH")[1:]
    lab_l = np.where(sl.diff() > 0, "HL", "LL")[1:]
    return pd.Series(lab_h, index=sh.index[1:]), pd.Series(lab_l, index=sl.index[1:])
```

### B1.3 Internal structure và swing structure

Cùng một thuật toán, chạy với hai độ dài:
- **Swing structure**: độ dài lớn. LuxAlgo mặc định **50**, tối thiểu 10 **[đã tra]**.
- **Internal structure**: độ dài nhỏ. LuxAlgo dùng hằng số **5**, không chỉnh được **[đã tra mã nguồn]**.

LuxAlgo còn thêm điều kiện: internal pivot chỉ tính khi mức của nó **khác** mức swing pivot hiện tại, và có "Confluence Filter" tuỳ chọn để lọc phá vỡ internal kém ý nghĩa **[đã tra]**.

Biến thể khác: dùng timeframe thấp hơn làm internal, timeframe hiện tại làm swing.

## B2. Break of Structure (BOS)

**Định nghĩa:** giá phá qua swing gần nhất **theo chiều xu hướng hiện tại**.
- Bullish BOS: đang bullish, `close > swing_high` gần nhất chưa bị phá.
- Bearish BOS: đang bearish, `close < swing_low` gần nhất chưa bị phá.

**Tham số và biến thể:**
- Xác nhận bằng **close** (chặt) hay **wick** (`high > level`, lỏng). `smartmoneyconcepts` có `close_break=True` **[đã tra]**; LuxAlgo dùng `ta.crossover(close, level)` **[đã tra]**.
- Mỗi swing chỉ được phá một lần (cờ `crossed`).
- Yêu cầu thêm displacement (B8) để lọc phá vỡ yếu.
- Đệm tối thiểu: `close > level + k * ATR`.

## B3. Change of Character (CHoCH) / Market Structure Shift (MSS)

**Định nghĩa:** giá phá qua swing gần nhất **ngược chiều xu hướng hiện tại**.
- Bullish CHoCH: đang bearish, `close > swing_high` gần nhất.
- Bearish CHoCH: đang bullish, `close < swing_low` gần nhất.

Như vậy BOS và CHoCH là **cùng một sự kiện phá vỡ**, chỉ khác nhãn tuỳ trạng thái xu hướng trước đó. Sau sự kiện, xu hướng đặt theo chiều phá vỡ.

**Biến thể:**
- **MSS**: nhiều người dùng đồng nghĩa với CHoCH. Một số phân biệt: CHoCH là phá vỡ ngược chiều đầu tiên (kể cả ở internal structure), MSS đòi hỏi phá vỡ có displacement và/hoặc xảy ra sau một liquidity sweep. Không có chuẩn chung.
- Phá vỡ đầu tiên khi chưa có xu hướng: gọi là BOS (LuxAlgo và indicator ở Phần C đều làm vậy **[đã tra]**).
- Bản chặt: CHoCH bullish yêu cầu swing bị phá phải là **LH tạo ra LL gần nhất**, không phải swing high bất kỳ.

```python
def bos_choch(df, sw, close_break=True):
    """Trả về list sự kiện. Dùng sh_known/sl_known nên không lookahead."""
    events, trend = [], 0
    hi_lvl = lo_lvl = None
    hi_idx = lo_idx = None
    up_src = df.close if close_break else df.high
    dn_src = df.close if close_break else df.low
    for i in range(len(df)):
        if not np.isnan(sw.sh_known.iat[i]):
            hi_lvl, hi_idx = sw.sh_known.iat[i], i     # i là bar XÁC NHẬN swing
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

**Định nghĩa phổ biến:** nến ngược chiều cuối cùng trước một đợt giá mạnh gây ra BOS/CHoCH.
- Bullish OB: nến giảm (`close < open`) cuối cùng trước đợt tăng phá swing high. Vùng = `[low, high]` của nến đó.
- Bearish OB: nến tăng cuối cùng trước đợt giảm phá swing low.

**Tham số và biến thể:**
- Vùng lấy theo **toàn bộ nến** (wick–wick), theo **thân nến**, hay từ open tới wick.
- Cách chọn nến:
  - "Nến ngược chiều cuối cùng" (định nghĩa sách vở).
  - **LuxAlgo**: khi có phá vỡ, lấy bar có **low thấp nhất** (bullish) hoặc **high cao nhất** (bearish) trong đoạn từ swing pivot tới bar phá vỡ, không quan tâm màu nến. Kèm bộ lọc biến động: bar có `high - low >= 2 × ATR(200)` (hoặc 2 × trung bình cộng dồn của true range) bị coi là bar biến động lớn và đảo high/low khi xét, để không bị chọn làm OB **[đã tra mã nguồn]**.
  - **`smartmoneyconcepts`**: `ob(ohlc, swing_highs_lows, close_mitigation=False)`, trả thêm `OBVolume` (volume nến đó cộng hai nến trước) và `Percentage` **[đã tra]**.
- Điều kiện kèm theo tuỳ chọn: phải có displacement, phải để lại FVG, phải nằm trong discount (bullish) hay premium (bearish), phải quét liquidity trước đó.
- Giới hạn số OB còn hiệu lực (LuxAlgo hiển thị 5 mỗi loại, lưu tối đa 100 **[đã tra]**).

### B4.2 Mitigation

Hai nghĩa khác nhau, cần ghi rõ đang dùng nghĩa nào:
1. **Chạm/quay lại (tap):** giá quay về chạm vùng OB — bullish OB: `low <= ob.top`. Thường là điều kiện vào lệnh.
2. **Vô hiệu (invalidation):** giá xuyên hẳn qua vùng — bullish OB: `low < ob.bottom` (theo wick) hoặc `close < ob.bottom` (theo close). LuxAlgo gọi cái này là mitigation và **xoá** OB; tuỳ chọn nguồn là `High/Low` (mặc định) hoặc `Close` **[đã tra]**.

Biến thể: mitigation một phần (chạm 50% vùng), số lần chạm tối đa trước khi coi vùng là "đã dùng".

### B4.3 Breaker block

**Định nghĩa:** một OB đã bị **vô hiệu** (giá đóng cửa xuyên qua) thì đổi vai trò: bullish OB bị phá trở thành vùng kháng cự (bearish breaker), và ngược lại. Tín hiệu là khi giá quay lại test vùng đó từ phía bên kia.

**Biến thể:** bản ICT chặt yêu cầu OB gốc phải nằm trong một cấu trúc đã quét liquidity trước khi bị phá (khác với "mitigation block" là trường hợp không có quét liquidity) — định nghĩa này khó mã hoá và không thống nhất **[trí nhớ]**.

```python
def order_blocks(df, events, max_lookback=50):
    obs = []
    for e in events.itertuples():
        lo = max(0, e.i - max_lookback)
        seg = df.iloc[lo:e.i]                         # các bar TRƯỚC bar phá vỡ
        opp = seg[seg.close < seg.open] if e.side == 1 else seg[seg.close > seg.open]
        if opp.empty:
            continue
        j = df.index.get_loc(opp.index[-1])           # nến ngược chiều cuối cùng
        obs.append(dict(side=e.side, top=df.high.iat[j], bottom=df.low.iat[j],
                        bar=j, active_from=e.i))      # chỉ dùng được SAU bar phá vỡ
    return pd.DataFrame(obs)

def track_ob(df, ob, close_invalidation=True):
    """Trả về (vị trí chạm đầu tiên, vị trí bị vô hiệu) sau khi OB có hiệu lực."""
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
# Breaker: OB có invalid != None → đổi side = -side, có hiệu lực từ bar invalid.
```

## B5. Fair Value Gap (FVG) / imbalance

**Định nghĩa (mẫu 3 nến, chỉ số t là nến mới nhất):**
- Bullish FVG: `low[t] > high[t-2]`. Vùng = `[high[t-2], low[t]]`.
- Bearish FVG: `high[t] < low[t-2]`. Vùng = `[high[t], low[t-2]]`.

Biết được tại lúc **đóng nến t**.

**Tham số và biến thể:**
- Điều kiện thêm cho nến giữa: `close[t-1] > high[t-2]` (LuxAlgo **[đã tra]**), hoặc nến giữa phải cùng chiều (`smartmoneyconcepts` **[đã tra]**).
- Kích thước tối thiểu: theo ATR, theo % giá, hoặc ngưỡng tự động. LuxAlgo "Auto Threshold": biến động % của nến giữa phải lớn hơn 2 lần trung bình cộng dồn của trị tuyệt đối biến động % **[đã tra]**.
- Tính trên timeframe khác (LuxAlgo có input `Timeframe`).
- Gộp các FVG liền nhau (`join_consecutive` của `smartmoneyconcepts`).
- **Lấp (fill/mitigation):** chạm mép, lấp 50% ("consequent encroachment" theo cách gọi ICT), hay lấp toàn bộ.
- **Inverse FVG (IFVG):** FVG bị giá đóng cửa xuyên qua thì đổi vai trò, tương tự breaker.
- Thuật ngữ liên quan: "imbalance", "inefficiency", "liquidity void" (khoảng trống lớn gồm nhiều nến). Một số người gọi riêng "volume imbalance" là khoảng hở giữa thân hai nến liền nhau — định nghĩa khác, đừng trộn.

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
    return out   # dòng tại t: FVG được biết khi nến t đóng

def fvg_fill_index(df, t, side, top, bottom, mode="full"):
    level = {"touch": top if side == 1 else bottom,
             "half": (top + bottom) / 2,
             "full": bottom if side == 1 else top}[mode]
    after = df.iloc[t + 1:]
    hit = after.index[after.low <= level] if side == 1 else after.index[after.high >= level]
    return hit[0] if len(hit) else None
```

## B6. Liquidity

Giả thuyết nền: lệnh dừng lỗ tập trung phía trên các đỉnh và phía dưới các đáy dễ thấy; giá có xu hướng tìm đến các vùng này.

### B6.1 Buy-side và sell-side liquidity

- **Buy-side liquidity (BSL):** vùng phía **trên** các đỉnh (swing high, equal highs, đỉnh ngày/tuần trước, đỉnh session) — nơi có buy stop.
- **Sell-side liquidity (SSL):** vùng phía **dưới** các đáy — nơi có sell stop.

Về mặt thuật toán, đây chỉ là **danh sách mức giá** kèm cờ "đã bị quét chưa". Nguồn mức giá: swing (B1), equal highs/lows, previous day/week/month high/low, session high/low.

### B6.2 Equal highs / equal lows (EQH / EQL)

**Định nghĩa:** hai (hoặc nhiều) swing high có giá chênh nhau dưới một ngưỡng.

**Tham số và biến thể:**
- Ngưỡng theo ATR: LuxAlgo dùng `|level1 - level2| < 0.1 × ATR(200)`, với pivot độ dài 3 ("Bars Confirmation") **[đã tra]**.
- Ngưỡng theo %: `smartmoneyconcepts.liquidity(..., range_percent=0.01)` **[đã tra]**.
- Số lần chạm tối thiểu (2, 3...), khoảng cách tối thiểu/tối đa giữa các lần chạm.
- Yêu cầu giá ở giữa chưa vượt qua mức đó.

### B6.3 Liquidity sweep / stop hunt

**Định nghĩa:** giá vượt qua một mức liquidity rồi quay lại.
- Quét BSL: `high[t] > level` **và** `close[t] < level`.
- Quét SSL: `low[t] < level` **và** `close[t] > level`.

**Biến thể:**
- Cho phép quay lại trong `k` nến thay vì ngay trong một nến.
- Giới hạn độ xuyên tối đa (`high - level <= m × ATR`) để phân biệt với breakout thật.
- Nếu **close** vượt hẳn qua mức thì đó là BOS/breakout, không phải sweep.
- "Liquidity grab" / "stop hunt" / "raid" / "Judas swing": cùng ý, khác tên.

```python
def equal_levels(sw, a, thr_atr=0.1, kind="high"):
    s = (sw.swing_high if kind == "high" else sw.swing_low).dropna()
    rows = []
    for k in range(1, len(s)):
        if abs(s.iat[k] - s.iat[k - 1]) < thr_atr * a.loc[s.index[k]]:
            level = max(s.iat[k], s.iat[k - 1]) if kind == "high" else min(s.iat[k], s.iat[k - 1])
            rows.append(dict(level=level, first=s.index[k - 1], second=s.index[k]))
    return pd.DataFrame(rows)   # nhớ cộng độ trễ xác nhận pivot trước khi dùng làm tín hiệu

def sweeps(df, level, known_pos, side, max_pen_atr=None, a=None):
    """side=+1: quét buy-side (trên đỉnh). side=-1: quét sell-side (dưới đáy)."""
    out = []
    for i in range(known_pos + 1, len(df)):
        h, l, c = df.high.iat[i], df.low.iat[i], df.close.iat[i]
        if side == 1 and c > level:   # close vượt hẳn → breakout, mức hết hiệu lực
            break
        if side == -1 and c < level:
            break
        pierced = h > level if side == 1 else l < level
        if pierced:
            pen = (h - level) if side == 1 else (level - l)
            if max_pen_atr is None or pen <= max_pen_atr * a.iat[i]:
                out.append(i)
            break                      # mỗi mức chỉ tính lần quét đầu tiên
    return out
```

## B7. Premium / discount zone và equilibrium

**Định nghĩa:** chọn một **dealing range** `[L, H]`. Equilibrium `EQ = (H + L) / 2`. Trên EQ là premium (ưu tiên bán), dưới EQ là discount (ưu tiên mua).

Vị trí chuẩn hoá: `pos = (close - L) / (H - L)`, nằm trong 0..1.

**Tham số và biến thể — phần chủ quan nhất là chọn range:**
- Swing high và swing low gần nhất của swing structure, có cập nhật khi giá tạo cực trị mới (LuxAlgo: "trailing" top/bottom **[đã tra]**).
- Cao nhất/thấp nhất trong N bar gần nhất (indicator ở Phần C dùng cách này với N = 35 **[đã tra]**).
- Range của ngày/tuần trước, hoặc của session.
- Chia vùng: LuxAlgo vẽ premium là 5% trên cùng của range, equilibrium là dải 47,5%–52,5%, discount là 5% dưới cùng **[đã tra mã nguồn]**. Biến thể ICT "Optimal Trade Entry" (OTE) dùng vùng hồi 62%–79% **[trí nhớ]**.

```python
def premium_discount(df, sw):
    H = sw.sh_known.ffill()
    L = sw.sl_known.ffill()
    # tuỳ chọn: nới range khi giá vượt ra ngoài (trailing extremes)
    rng = (H - L).where(H > L)
    pos = (df.close - L) / rng
    eq = (H + L) / 2
    zone = pd.Series(np.where(pos > 0.5, "premium", "discount"), index=df.index).where(pos.notna())
    return pd.DataFrame(dict(H=H, L=L, eq=eq, pos=pos, zone=zone))
```

## B8. Displacement

**Định nghĩa:** một hoặc vài nến liên tiếp cùng chiều, thân lớn, wick nhỏ, thể hiện giá di chuyển mạnh một chiều.

**Quy tắc tính được:**
- `body = |close - open| >= k × ATR(n)` (ví dụ k = 1,5), **và**
- `body / (high - low) >= r` (ví dụ r = 0,7).

**Biến thể:** dùng độ lệch chuẩn của thân nến thay cho ATR; yêu cầu để lại FVG; yêu cầu phá một swing (tức là kèm BOS/CHoCH); tính tổng trên 2–3 nến liên tiếp cùng chiều; thêm điều kiện volume lớn hơn trung bình.

```python
def displacement(df, k=1.5, r=0.7, n=14):
    a = atr(df, n).shift(1)                      # ATR của bar trước, tránh tự tham chiếu
    body = (df.close - df.open).abs()
    rng = (df.high - df.low).replace(0, np.nan)
    ok = (body >= k * a) & (body / rng >= r)
    return np.sign(df.close - df.open).where(ok, 0).astype(int)   # +1 / -1 / 0
```

## B9. Inducement (IDM)

Khái niệm khó mã hoá nhất và ít thống nhất nhất.

**Định nghĩa khả dụng:** trong một xu hướng tăng, sau khi có BOS, **đáy hồi nhỏ gần nhất** (internal swing low) nằm phía trên vùng quan tâm (OB/FVG của swing structure) là inducement. Lý thuyết cho rằng giá sẽ quét đáy nhỏ đó trước rồi mới chạm vùng quan tâm; lệnh chỉ hợp lệ **sau khi inducement đã bị quét**.

**Thuật toán:**
1. Xác định trend và swing gần nhất bằng swing structure (độ dài lớn).
2. Trong leg hiện tại, tìm internal swing gần nhất ngược chiều trend (bullish: internal swing low gần nhất tính từ đỉnh).
3. IDM = mức giá đó.
4. "IDM taken" khi `low < IDM` (bullish) hoặc `high > IDM` (bearish).

**Biến thể:** dùng pullback đầu tiên sau BOS thay vì pullback gần nhất; định nghĩa pullback hợp lệ theo nến (nến phá đáy nến trước) thay vì theo pivot; yêu cầu quét bằng wick hay cho phép close.

```python
def inducement(df, sw_internal, trend, leg_start_pos, now_pos):
    """trend=+1: IDM là internal swing low gần nhất trong leg (đã được xác nhận trước now_pos)."""
    col = "sl_known" if trend == 1 else "sh_known"
    s = sw_internal[col].iloc[leg_start_pos:now_pos + 1].dropna()
    return None if s.empty else float(s.iloc[-1])

def idm_taken(df, idm, trend, from_pos):
    after = df.iloc[from_pos + 1:]
    hit = after.index[after.low < idm] if trend == 1 else after.index[after.high > idm]
    return hit[0] if len(hit) else None
```

## B10. Kill zones / session

**Định nghĩa:** các khung giờ cố định trong ngày, cho là có thanh khoản và biến động cao. Về thuật toán chỉ là bộ lọc thời gian, cộng với việc ghi lại high/low của session để làm mức liquidity.

**Khung giờ thường được trích dẫn (giờ New York)** — **[chưa xác minh: lấy từ trí nhớ, các nguồn đưa khung giờ khác nhau]**:

| Kill zone | Giờ New York (xấp xỉ) |
|---|---|
| Asian | 20:00 – 00:00 |
| London open | 02:00 – 05:00 |
| New York (AM) | 07:00 – 10:00 (có nguồn ghi 08:30 – 11:00) |
| London close | 10:00 – 12:00 |

`smartmoneyconcepts.sessions()` có sẵn các lựa chọn Sydney, Tokyo, London, New York, Asian kill zone, London open kill zone, New York kill zone, London close kill zone và Custom **[đã tra tên]**; giờ cụ thể thư viện dùng **[chưa xác minh]**.

**Lưu ý:**
- Luôn tính theo múi giờ có DST (`America/New_York`, `Europe/London`), không dùng offset UTC cố định.
- Kill zone sinh ra từ forex và chỉ số Mỹ. Crypto giao dịch 24/7; hiệu ứng theo giờ có tồn tại (trùng giờ mở cửa chứng khoán Mỹ, giờ chốt funding...) nhưng phải **đo trên dữ liệu của chính mình**, không mặc định áp khung giờ forex.
- Trong Pine: `time(timeframe.period, "0200-0500", "America/New_York")` trả `na` khi ngoài session **[trí nhớ về tham số timezone]**.

```python
def in_session(df, start="02:00", end="05:00", tz="America/New_York"):
    local = df.index.tz_convert(tz)           # index phải có timezone (UTC)
    t = local.strftime("%H:%M")
    return (t >= start) & (t < end) if start < end else (t >= start) | (t < end)

def session_levels(df, mask, tz="America/New_York"):
    day = df.index.tz_convert(tz).date
    g = df[mask].groupby(day[mask])
    return pd.DataFrame({"sess_high": g.high.max(), "sess_low": g.low.min()})
    # Chỉ được dùng các mức này SAU khi session kết thúc.
```

## B11. Bảng tóm tắt tham số

| Khái niệm | Tham số chính | Điểm mơ hồ cần chốt trước khi test |
|---|---|---|
| Swing | `L`, `R` | Xử lý hoà; độ trễ xác nhận |
| Internal / swing | Hai độ dài (5 / 50) | Có lọc trùng mức không |
| BOS / CHoCH | close hay wick; đệm ATR | Nhãn cho lần phá đầu tiên; swing nào được tính |
| Order block | Cách chọn nến; body hay wick | Bộ lọc displacement/FVG |
| Mitigation | Chạm hay vô hiệu; close hay wick | Số lần chạm cho phép |
| FVG | Kích thước tối thiểu; điều kiện nến giữa | Thế nào là "đã lấp" |
| EQH / EQL | Ngưỡng (ATR hay %); số lần chạm | Khoảng cách giữa hai đỉnh |
| Sweep | Số nến để quay lại; độ xuyên tối đa | Ranh giới sweep và breakout |
| Premium / discount | Cách chọn range | Range tĩnh hay trailing |
| Displacement | `k`, `r`, `n` | Một nến hay nhiều nến |
| Inducement | Độ dài internal | Pullback nào được tính |
| Kill zone | Khung giờ, múi giờ | Có áp cho crypto không |

---

# Phần C — Indicator "Dynamic SMC & Market Structure PRO"

URL: https://www.tradingview.com/script/j5Sp5u7i-Dynamic-SMC-Market-Structure-PRO/

## C1. Thông tin chung **[đã tra — đọc trang và mã nguồn]**

| | |
|---|---|
| Tác giả | ACE_Chart_Logic |
| Ngày publish | 2026-08-03, phiên bản 1.0, chưa có bản cập nhật |
| Loại | Open-source indicator, `overlay = true` |
| Phiên bản Pine | `//@version=6` |
| Giấy phép | Dòng đầu mã nguồn ghi **Mozilla Public License 2.0** |
| Độ dài | Khoảng 240 dòng, một file, không import library |
| Khai báo | `max_lines_count = 500`, `max_boxes_count = 100`, `max_labels_count = 500` |

Chữ "PRO" chỉ là tên gọi; đây là script miễn phí, mã mở. Trang mô tả có ghi rõ mục đích giáo dục và không đưa tín hiệu giao dịch.

## C2. Giấy phép và quy tắc tái sử dụng

- Script open-source trên TradingView mặc định theo **MPL 2.0**; tác giả có thể ghi giấy phép khác trong mã nguồn. Script này dùng mặc định.
- **Script Publishing Rules của TradingView được ưu tiên hơn giấy phép** mà tác giả chọn, kể cả MPL 2.0. Các điểm chính **[đã tra]**:
  - Dùng lại code open-source để **publish** trên TradingView thì script mới phải open-source, trừ khi có sự cho phép rõ ràng của tác giả (và phải chứng minh được), hoặc code đó thuộc public domain và chỉ chiếm một phần script.
  - Phải **ghi công tác giả** trong phần mô tả (hoặc release notes nếu thêm khi cập nhật); khuyến nghị ghi cả trong comment mã nguồn.
  - Phần dùng lại chỉ nên là một phần của script và phải có **cải tiến đáng kể**. Đổi style, đổi input, đổi tên biến, sắp xếp lại code, chuyển phiên bản Pine **không** được tính là cải tiến.
  - Cấm bắt chước script của tác giả khác; đạo code có thể bị cấm vĩnh viễn.
  - Dùng trong sản phẩm trả phí (vendor) phải xin phép tác giả và nói rõ mục đích.
  - Dùng riêng (không publish) thì tự do.
- Áp dụng cho dự án này: đọc để hiểu và tự cài lại bằng Python là an toàn. Nếu sao chép đoạn code Pine vào sản phẩm phân phối thì phải tuân thủ MPL 2.0 (giữ thông báo giấy phép, công bố mã của các file đã sửa); nếu publish lại trên TradingView thì theo Script Publishing Rules ở trên. Đây là tóm tắt, không phải tư vấn pháp lý.
- Vì lý do đó, tài liệu này **không chép nguyên văn** mã nguồn, chỉ mô tả logic.

## C3. Indicator vẽ gì

1. Nhãn hình mũi tên tại **major swing high/low**.
2. Đường nét đứt và chữ **BOS / CHoCH**.
3. Hộp **SUPPLY / DEMAND**, tự xoá khi giá đóng cửa xuyên qua.
4. Đường **PDH / PDL** (đỉnh/đáy ngày hôm trước), tự xoá khi bị quét.
5. Đường **Asia session high/low**, tự xoá khi bị quét.
6. Đường **0.50 EQ**.
7. **Bảng dashboard** 2 cột × 4 dòng ở góc trên phải.

Không có: FVG, equal highs/lows, internal structure, order block theo nghĩa chặt, kill zone London/New York, và **không có alert nào** (không có `alert()` hay `alertcondition()`).

## C4. Input **[đã tra mã nguồn]**

| Nhóm | Input | Mặc định | Ràng buộc |
|---|---|---|---|
| Major Swing Extremes | Show Major Swing High/Low Shapes | true | |
| | Major Swing Lookback Sensitivity | 20 | 5–100 |
| | Màu high / low | đỏ / xanh | |
| Smart Money Structure | Show BOS & CHoCH Lines | true | |
| | Structure Sensitivity (Pivot Length) | 8 | ≥ 3 |
| | Màu bullish / bearish | xanh / đỏ | |
| Supply & Demand | Show Dynamic Supply & Demand Zones | true | |
| | Max Active Zones Per Side | 4 | 1–10 |
| | Zone Transparency | 80 | 0–100 |
| | Màu supply / demand | đỏ / xanh | |
| PDH & PDL | Show Active PDH / PDL | true | |
| | Màu PDH / PDL | cyan / vàng | |
| Session | Show Session High/Low Lines | true | |
| | Màu Asia | xanh nhạt | |
| | Clutter Distance Threshold (Pips / Gold $) | 15.0 | ≥ 1 |
| Fibonacci 0.5 EQ | Show 0.5 Equilibrium Line | true | |
| | Equilibrium Lookback Range | 35 | ≥ 10 |
| | Màu EQ | tím | |
| Dashboard | Show Information Panel | true | |

Các tham số **cứng trong code, không chỉnh được**: độ dài pivot của supply/demand (6/6), giờ Asia session (`0000-0600`, thứ Hai–thứ Sáu), ATR(14), timeframe "D" cho PDH/PDL.

## C5. Logic từng khối

**1. Major swing.** Pivot high/low với cùng độ dài hai bên (mặc định 20). Khi pivot được xác nhận, vẽ nhãn lùi về đúng bar pivot, lệch ra 0,3 × ATR(14). Chỉ để nhìn, không tham gia logic khác.

**2. BOS / CHoCH.** Một bộ pivot riêng (mặc định 8). Script chỉ nhớ **một** pivot high và **một** pivot low gần nhất; pivot mới ghi đè pivot cũ, không phân loại HH/HL/LH/LL. Khi giá đóng cửa cắt lên pivot high đang nhớ: nếu trạng thái xu hướng đang là giảm thì gắn nhãn CHoCH, còn lại (kể cả chưa có xu hướng) gắn BOS; đặt xu hướng thành tăng; xoá mức vừa bị phá. Chiều giảm đối xứng. Đây đúng là định nghĩa tối giản ở B2/B3.

**3. Supply / demand.** Pivot cố định 6/6. Tại mỗi pivot high, vẽ hộp supply từ **high của nến pivot xuống mép trên thân nến** (tức là phần wick trên); tại pivot low, hộp demand từ **mép dưới thân nến xuống low** (wick dưới). Giữ tối đa N hộp mỗi bên theo kiểu FIFO. Mỗi bar: nếu `close` vượt lên trên đỉnh hộp supply thì xoá hộp; nếu `close` xuống dưới đáy hộp demand thì xoá; còn lại kéo dài hộp sang phải 12 bar.

**4. PDH / PDL.** Lấy high và low của ngày hôm trước qua `request.security` trên timeframe "D" với offset `[1]` và `lookahead_on` — đúng mẫu không repaint ở A6. Mỗi ngày mới thì đặt lại. Trong ngày, nếu `high` vượt PDH thì đánh dấu "đã quét" và ẩn đường; tương tự với PDL. Đường được xoá và vẽ lại ở mỗi bar.

**5. Asia session.** Session `0000-0600`, thứ Hai–thứ Sáu, theo **múi giờ của sàn/symbol** (không truyền tham số timezone). Trong session thì cộng dồn high/low. Sau đó, nếu giá vượt qua mức thì xoá đường và bỏ mức. Đường bị ẩn nếu nằm quá gần PDH/PDL; ngưỡng = input × `syminfo.mintick` × 10 (forex) hoặc × 100 (loại khác).

**6. Equilibrium.** Trung điểm của giá cao nhất và thấp nhất trong 35 bar gần nhất. Chỉ vẽ ở bar cuối.

**7. Dashboard.** Bốn dòng: Structure Trend (BULLISH/BEARISH/NEUTRAL), Pricing Zone (PREMIUM nếu `close` > EQ, ngược lại DISCOUNT), PDH/PDL State, và số zone supply/demand đang hoạt động.

## C6. Nhận xét kỹ thuật

Các nhận xét sau rút ra từ **đọc mã nguồn**, chưa chạy script trên chart để kiểm chứng.

1. **Vẽ vào quá khứ.** Nhãn major swing xuất hiện trễ 20 bar nhưng được đặt tại bar pivot; hộp supply/demand trễ 6 bar. Nhìn lại lịch sử sẽ thấy "đẹp" hơn thực tế. Đây là dạng repaint "plotting in the past" (A1.6).
2. **Không chờ đóng bar.** Điều kiện BOS/CHoCH không có `barstate.isconfirmed`, nên trên bar đang chạy nhãn có thể hiện rồi biến mất.
3. **`ta.crossover`/`ta.crossunder` nằm sau `and`.** Với cơ chế đánh giá lười của v6, hàm có thể không được gọi trên mọi bar (khi tắt input hoặc khi chưa có pivot), vi phạm khuyến nghị ở A1.5. Mức độ ảnh hưởng thực tế **[chưa xác minh]**. Ngoài ra, việc cắt qua một mức vừa đổi giá trị (pivot mới ghi đè) có thể bỏ sót phá vỡ khi pivot mới hình thành mà giá đã ở phía trên nó.
4. **Trạng thái xu hướng gắn với công tắc hiển thị.** Tắt "Show BOS & CHoCH Lines" thì xu hướng trên dashboard cũng ngừng cập nhật.
5. **"Supply/demand" không phải order block.** Vùng chỉ là wick của nến pivot, không yêu cầu displacement, không theo dõi mitigation theo nghĩa chạm vùng; chỉ có vô hiệu theo close.
6. **Equilibrium không dựa trên swing.** Mô tả nói "across recent swings" nhưng code dùng cao/thấp nhất của 35 bar — một cửa sổ trượt, nên mức EQ và nhãn premium/discount trôi theo từng bar.
7. **Session cứng, không hợp crypto.** Giờ tính theo múi giờ của symbol; với cặp crypto thường là UTC nên `0000-0600` không trùng "Asia session" theo nghĩa thông dụng. Bộ lọc ngày bỏ qua cuối tuần trong khi crypto chạy 24/7. Ngưỡng "pip" được thiết kế cho forex/vàng, vô nghĩa với phần lớn cặp crypto.
8. **Không có alert**, nên không nối webhook được nếu không sửa code.
9. **Nhãn dashboard "PDH Swept" được ưu tiên** khi cả PDH và PDL đều đã bị quét.
10. **Hiệu năng:** xoá và tạo lại line/label ở mỗi bar thay vì dùng `set_*`; chấp nhận được với script nhỏ.

**Kết luận:** đây là một ví dụ nhập môn gọn và dễ đọc về cách ghép các khối SMC cơ bản bằng Pine v6, phù hợp để tham khảo cấu trúc code. Nó không phải cài đặt SMC đầy đủ và không nên dùng nguyên trạng làm nguồn tín hiệu, nhất là cho crypto. Bản LuxAlgo đầy đủ hơn nhiều về mặt khái niệm, nhưng giấy phép của nó cấm dùng thương mại.

---

# Phần D — Đánh giá trung thực về SMC/ICT

## D1. Bằng chứng thực nghiệm: yếu

- Hai lượt tìm kiếm trong phiên này (từ khoá về nghiên cứu thực nghiệm, arXiv/SSRN cho "order block", "fair value gap", "smart money concepts") **không tìm thấy nghiên cứu bình duyệt nào** kiểm định SMC/ICT như một hệ thống. Kết quả gần như toàn bài của broker, blog, và quảng cáo công cụ. Không tìm thấy khác với không tồn tại, nhưng nếu có thì cũng không dễ thấy.
- Chính trang indicator SMC của LuxAlgo cũng ghi rằng các khái niệm này không bảo đảm phản ánh thanh khoản tổ chức và **không có dữ liệu chứng minh tính hợp lệ** **[đã tra]**.
- Các con số lan truyền kiểu "FVG được lấp 70% số lần" không truy được nguồn gốc **[chưa xác minh]**. Kể cả đúng, tỷ lệ lấp cao không đồng nghĩa có lợi nhuận: giá dao động ngẫu nhiên cũng quay lại lấp phần lớn khoảng trống nhỏ. Phải so với baseline.
- Câu chuyện nền ("tổ chức săn stop của nhỏ lẻ", "nến này là lệnh của ngân hàng") **không kiểm chứng được** bằng dữ liệu OHLCV. Nó không cần đúng để mẫu hình có giá trị, nhưng cũng không được coi là bằng chứng.

## D2. Những gì có nền tảng học thuật gần kề **[trí nhớ — chưa tra lại trong phiên này, cần kiểm tra trích dẫn trước khi dùng]**

- **Lệnh stop tập trung quanh các mức dễ thấy và gây chuỗi phản ứng giá:** Osler (2003, 2005) trên thị trường FX. Đây là phần gần nhất với ý tưởng "liquidity".
- **Mẫu hình kỹ thuật có chứa một ít thông tin:** Lo, Mamaysky & Wang (2000).
- **Lợi nhuận của phân tích kỹ thuật phần lớn biến mất sau khi tính chi phí và hiệu chỉnh data snooping:** Sullivan, Timmermann & White (1999); tổng quan của Park & Irwin (2007).
- **Hiệu ứng theo giờ trong ngày** (biến động và thanh khoản theo session) là có thật và được ghi nhận rộng rãi — nhưng biến động cao không tự tạo ra lợi thế về hướng.
- **Kiểm định nhiều lần và overfitting backtest:** Bailey & López de Prado (Deflated Sharpe Ratio, Probability of Backtest Overfitting); Harvey, Liu & Zhu (2016).

Tóm lại: một số **thành phần** của SMC trùng với hiện tượng vi cấu trúc thị trường đã được nghiên cứu (cụm stop, hiệu ứng session, quán tính sau biến động mạnh). **Hệ thống** SMC như được dạy thì chưa có kiểm định độc lập đáng tin.

## D3. Rủi ro chủ quan và hindsight

1. **Định nghĩa co giãn.** Phần B cho thấy mỗi khái niệm có nhiều biến thể. Người vẽ tay chọn biến thể nào khớp với kết quả đã biết.
2. **Hindsight từ pivot.** Swing chỉ biết sau `R` bar, nhưng trên chart được vẽ tại bar pivot. Mọi ví dụ "đẹp" đều dùng thông tin tương lai.
3. **Không thể bác bỏ.** Setup thất bại thì được giải thích lại ("đó là inducement", "liquidity chưa bị lấy hết", "sai timeframe"). Một lý thuyết giải thích được mọi kết cục thì không dự báo được gì.
4. **Thiên lệch chọn mẫu.** Nội dung giáo dục chỉ trưng ví dụ thắng.
5. **Quá nhiều bậc tự do.** Timeframe × độ dài swing × loại vùng × bộ lọc × session → luôn tìm được tổ hợp có backtest đẹp.
6. **Thị trường khác nhau.** Khái niệm sinh ra từ forex và chỉ số Mỹ. Crypto có cấu trúc khác: 24/7, perp với funding và liquidation cascade, thanh khoản phân mảnh giữa các sàn.
7. **Động cơ thương mại.** Phần lớn nguồn SMC bán khoá học, tín hiệu hoặc indicator.

## D4. Cách kiểm định

1. **Chốt định nghĩa bằng code trước khi nhìn kết quả.** Ghi lại tham số, không sửa sau khi thấy PnL.
2. **Chống lookahead.** Mọi tín hiệu tính tại bar xác nhận (`i + R`), vào lệnh từ open của bar kế tiếp. Viết test tự động: cắt dữ liệu tại `t`, tín hiệu trước `t` không được thay đổi khi thêm dữ liệu sau `t`.
3. **Event study trước, strategy sau.** Với mỗi sự kiện (FVG, sweep, CHoCH...), đo phân phối lợi suất tương lai ở các horizon 1, 5, 20, 50 bar, cùng MFE/MAE. So với:
   - baseline vô điều kiện (mọi bar);
   - baseline khớp điều kiện (cùng giờ trong ngày, cùng mức biến động, cùng chiều trend);
   - sự kiện "giả" (ví dụ vùng ngẫu nhiên cùng kích thước).
4. **Chi phí thực tế:** phí taker/maker, spread, slippage, funding rate với perp. Nhiều lợi thế nhỏ biến mất ở bước này.
5. **Out-of-sample đúng nghĩa:** walk-forward, hoặc purged/combinatorial cross-validation có embargo. Giữ riêng một đoạn dữ liệu cuối, chỉ dùng một lần.
6. **Hiệu chỉnh kiểm định nhiều lần:** ghi lại **tất cả** biến thể đã thử; dùng Deflated Sharpe Ratio hoặc White's Reality Check / SPA; hoặc Bonferroni/FDR cho event study.
7. **Độ vững:** kết quả phải giữ được khi đổi nhẹ tham số, đổi symbol, đổi sàn, đổi giai đoạn (bull/bear/sideway). Lợi thế chỉ tồn tại ở một điểm tham số là overfit.
8. **Kích thước mẫu và phụ thuộc:** các sự kiện chồng lấn không độc lập; dùng block bootstrap để tính khoảng tin cậy.
9. **Phân rã:** kiểm tra xem lợi thế đến từ khái niệm SMC hay từ yếu tố đã biết (trend-following, lọc biến động, hiệu ứng giờ). Nếu bỏ phần SMC mà kết quả không đổi thì SMC không đóng góp gì.
10. **Forward test** bằng paper trading hoặc vốn nhỏ trước khi tin.

**Khuyến nghị cho dự án:** coi các khái niệm SMC là **bộ sinh feature** (khoảng cách tới mức liquidity gần nhất, có FVG chưa lấp không, vị trí trong dealing range, vừa có sweep không...) để đưa vào quy trình kiểm định định lượng — không coi là chiến lược có sẵn lợi thế. Giả thuyết mặc định là **không có lợi thế** cho tới khi dữ liệu out-of-sample sau chi phí chứng minh ngược lại.

---

# Danh sách điều chưa xác minh

1. **Code mẫu Pine (A11, A9) và giả mã Python (Phần B)** chưa được compile/chạy.
2. **Mặc định của `strategy()`** (`initial_capital`, `default_qty_type`, commission, slippage, margin) — viết theo trí nhớ; trang docs đọc được chỉ xác nhận `pyramiding` mặc định là 1.
3. **Thời gian chạy tối đa của script theo từng gói** — trang limitations không nêu con số.
4. **Độ sâu lịch sử của `request.footprint()`**; danh sách đầy đủ các hàm `footprint.*`/`volume_row.*` (chỉ liệt kê những hàm thấy trong docs).
5. **Webhook:** có yêu cầu gói trả phí không; có cơ chế retry không.
6. **Chữ ký đầy đủ** của các hàm drawing, danh sách `input.*`, danh sách `ta.*`, hành vi `and`/`or` lười của v6, tham số timezone của `time()` — viết theo trí nhớ, chưa đối chiếu Reference Manual trong phiên này.
7. **Pine không có hàm đọc Volume Profile built-in** — kết luận dựa trên trí nhớ và việc không thấy hàm nào trong các trang đã đọc; chưa rà toàn bộ Reference Manual.
8. **Khung giờ kill zone ICT** và giờ cụ thể mà `smartmoneyconcepts.sessions()` dùng.
9. **Giấy phép của `smartmoneyconcepts`** (PyPI để trống).
10. **Ảnh hưởng thực tế của `ta.crossover` sau `and`** trong indicator ở Phần C — suy luận từ đọc code, chưa chạy.
11. **Các trích dẫn học thuật ở D2** — theo trí nhớ, chưa tra lại.
12. **Con số "FVG lấp ~70%"** và mọi tỷ lệ thắng SMC lan truyền trên mạng — không truy được nguồn.
13. Định nghĩa ICT "chặt" của breaker block, OTE 62–79%, MSS so với CHoCH — theo trí nhớ, các nguồn không thống nhất.
14. Các trang docs dài bị công cụ đọc cắt bớt (release notes, strategies, execution model, type system, other timeframes) — có thể sót thay đổi nằm ở phần chưa đọc.

---

# Nguồn

**Pine Script (TradingView)**
- Trang chủ docs: https://www.tradingview.com/pine-script-docs/welcome/
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
- Reference Manual v6: https://www.tradingview.com/pine-script-reference/v6/ (không đọc trực tiếp trong phiên này)
- About webhooks: https://www.tradingview.com/support/solutions/43000529348-about-webhooks/
- Script publishing rules: https://www.tradingview.com/support/solutions/43000590599-script-publishing-rules/
- Vendor requirements: https://www.tradingview.com/support/solutions/43000549951-vendor-requirements/
- Mozilla Public License 2.0: https://mozilla.org/MPL/2.0/

**Indicator và thư viện SMC**
- Dynamic SMC & Market Structure PRO (ACE_Chart_Logic): https://www.tradingview.com/script/j5Sp5u7i-Dynamic-SMC-Market-Structure-PRO/
- Smart Money Concepts (SMC) [LuxAlgo]: https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/
- CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/
- `smartmoneyconcepts` (GitHub): https://github.com/joshyattridge/smart-money-concepts
- `smartmoneyconcepts` (PyPI): https://pypi.org/project/smartmoneyconcepts/

**Kết quả tìm kiếm về bằng chứng (không phải nguồn học thuật)**
- XS.com — bài giải thích SMC, nêu chưa có nghiên cứu bình duyệt: https://www.xs.com/en/test-blog/smc-smart-money-concepts-explained/
- MQL5 blog — khó khăn khi biến order block thành quy tắc cho EA: https://www.mql5.com/en/blogs/post/779413
