# 09 — Lộ trình theo phase

Lập ngày 2026-11-13. Chi tiết hóa [07-ke-hoach-trien-khai.md](07-ke-hoach-trien-khai.md) thành các phase làm được độc lập, theo kiến trúc ở [08-kien-truc.md](08-kien-truc.md). Phase 0 đã xong (commit `c6ae912`); các phase còn lại chưa bắt đầu.

Quy ước:

- **Cỡ:** S (một module nhỏ), M (vài module), L (nhiều module hoặc phải chạy thử dài ngày). Đây là độ lớn tương đối, không phải ước lượng thời gian.
- **Xong khi:** điều kiện kiểm chứng được. Chưa đạt thì chưa sang phase sau.
- Mỗi phase kết thúc bằng một commit với test và ruff đều qua.

## Tổng quan

| Phase | Tên | Cỡ | Phụ thuộc | Kết quả dùng được |
|---|---|---|---|---|
| 0 | Khung dự án | S | — | `rinng check` chạy được (đã xong) |
| 1 | Bộ chuyển đổi sàn | M | 0 | lấy nến, funding, OI từ hai sàn bằng một giao diện |
| 2 | Lớp lưu trữ | M | 0 | ghi/đọc Parquet an toàn, có manifest |
| 3 | Bộ thu realtime | L | 1, 2 | liquidation, OI, long/short được tích lũy liên tục |
| 4 | Tải lịch sử và làm sạch | L | 1, 2 | nến 1 phút sạch từ 2020, đã resample |
| 5 | Lõi phân tích | M | 4 | indicator cổ điển, swing, cấu trúc thị trường |
| 6 | SMC và thanh khoản | M | 5 | BOS, CHoCH, FVG, order block, sweep |
| 7 | Volume profile và order flow | L | 4 | VPOC, value area, delta, CVD, footprint |
| 8 | Phái sinh, Wyckoff, Elliott | M | 3, 5 | feature funding/OI/liquidation; thành phần Wyckoff và Elliott |
| 9 | Chiến lược và backtest | L | 5, tốt nhất sau 6–8 | kết quả backtest có phí, so với baseline |
| 10 | Chart và dashboard | M | 5 trở đi | dựng lại các chart mẫu từ dữ liệu của dự án |
| 11 | Pine Script | S–M | 9 | indicator trên TradingView khớp Python |

Thứ tự làm đề xuất: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11. Phase 3 đi sớm vì mỗi ngày chưa chạy là một ngày liquidation mất hẳn. Phase 10 có thể kéo lên ngay sau phase 5 nếu muốn nhìn kết quả sớm; khi đó làm bản chart tối thiểu trước.

## Phase 0 — Khung dự án (đã xong)

Còn một việc treo: tải một file `metrics` và một file `bookDepth` từ data.binance.vision để xem cột. Việc này phải xong trước phase 2, vì nó quyết định schema bảng `open_interest` và `long_short`.

## Phase 1 — Bộ chuyển đổi sàn

**Mục tiêu:** phần còn lại của hệ thống lấy dữ liệu qua `Exchange` mà không biết sàn nào.

**Việc:**
1. `exchanges/ratelimit.py`: bộ điều tiết. Binance đọc `X-MBX-USED-WEIGHT-1M` và tự hãm ở 50%; OKX đếm request theo cửa sổ 2 giây cho từng endpoint. Gặp 429 thì ngủ theo `Retry-After`; gặp 418 thì dừng hẳn và báo lỗi.
2. `exchanges/binance.py`: `klines`, `funding`, `open_interest`, `long_short`, `taker_volume`, `mark_price_klines` cho USDⓈ-M; `klines` cho Spot. Phân trang bằng `startTime`.
3. `exchanges/okx.py`: cùng các phương thức. Phân trang ngược bằng `after`; kiểm tra `code` trong body; dùng `1Dutc` thay cho `1D`.
4. Chuẩn hóa đầu ra: thời gian UTC mili giây, số dạng float, tên cột chung.
5. Mở rộng `Exchange` trong `base.py` cho đủ các phương thức trên.

**Thư viện thêm:** không.

**Xong khi:**
- Test bằng `httpx.MockTransport` cho: phân trang nhiều trang, trang rỗng, 429 có `Retry-After`, 418, mã `50011` của OKX, nến chưa đóng.
- Test có nhãn `network`: lấy 3 ngày nến 1h của BTC từ cả hai sàn, số nến đúng 72 và không trùng.
- Nến 1h của Binance và OKX cùng khoảng thời gian có cùng mốc mở nến.

**Rủi ro:** weight thực tế cao hơn docs ghi (đã thấy một lần); một số endpoint `/futures/data/*` chưa xác minh được limit.

## Phase 2 — Lớp lưu trữ

**Mục tiêu:** ghi và đọc dữ liệu theo bố cục đã định, không hỏng file khi nhiều tiến trình cùng chạy.

**Việc:**
1. `store/schemas.py`: schema các bảng curated (`ohlcv`, `trades`, `funding`, `open_interest`, `long_short`, `liquidations`, `mark_index`).
2. `store/writer.py`: ghi file tạm rồi đổi tên; từ chối ghi đè trong `raw/`; khử trùng theo khóa khi ghi `curated/`.
3. `store/reader.py`: đọc theo instrument, khung thời gian, khoảng thời gian.
4. `store/catalog.py`: `manifest` (nguồn, khoảng thời gian, số dòng, checksum, thời điểm tải) và `gaps`.
5. View DuckDB trỏ vào Parquet.

**Thư viện thêm:** `polars`, `duckdb`.

**Xong khi:**
- Test: ghi rồi đọc lại ra đúng dữ liệu; ghi hai lần cùng khóa không sinh dòng trùng; ghi đè `raw/` bị từ chối; tiến trình chết giữa chừng không để lại file dở ở đường dẫn chính thức.
- Truy vấn DuckDB đếm đúng số dòng đã ghi.

**Quyết định cần trước:** kết quả mở file `metrics` (phase 0).

## Phase 3 — Bộ thu realtime

**Mục tiêu:** tích lũy liên tục các chuỗi không lấy lại được.

**Việc:**
1. `ingest/collector/ws.py`: kết nối WebSocket Binance (`@forceOrder`, `@markPrice`, `@aggTrade`) và OKX (`liquidation-orders`, mark price, trades). Kết nối lại có giãn cách; Binance chủ động nối lại trước mốc 24 giờ; OKX gửi `ping` khi im lặng.
2. `ingest/collector/poller.py`: mỗi 5 phút gọi OI, long/short ratio, taker volume qua phase 1.
3. `ingest/collector/gaps.py`: ghi mọi khoảng mất kết nối vào `meta/gaps`.
4. Gom bản ghi trong bộ nhớ, xả ra Parquet theo lô (theo thời gian hoặc số dòng), xả sạch khi nhận tín hiệu dừng.
5. Lệnh `rinng collect` và file dịch vụ để tự khởi động lại (launchd trên macOS hoặc systemd trên VPS).

**Thư viện thêm:** `websockets`, `APScheduler`.

**Xong khi:**
- Test với server WebSocket giả: mất kết nối giữa chừng thì nối lại và ghi đúng một khoảng trống; tín hiệu dừng không làm mất bản ghi đang giữ.
- Chạy thật 72 giờ liên tục, qua ít nhất một lần Binance ngắt 24 giờ; bảng `gaps` khớp với log.
- Số bản ghi OI trong 72 giờ bằng 864 mỗi instrument mỗi sàn (72 × 12), trừ các khoảng trống đã ghi nhận.

**Quyết định cần trước:** chạy trên máy Mac này hay VPS. Nếu VPS, chạy `rinng check` trên đó trước và thêm bước đồng bộ `raw/` về máy phân tích.

**Rủi ro:** luồng liquidation vốn không đầy đủ ở cả hai sàn; dung lượng aggTrades chưa ước lượng, có thể phải tắt luồng này và chỉ lấy aggTrades từ dump.

## Phase 4 — Tải lịch sử và làm sạch

**Mục tiêu:** có bộ nến 1 phút sạch, dài, đã resample; là đầu vào cho mọi phân tích.

**Việc:**
1. `ingest/dumps.py`: liệt kê và tải file từ data.binance.vision theo khoảng ngày, kiểm `.CHECKSUM`, lưu nguyên file zip vào `raw/`.
2. `ingest/backfill.py`: lấp phần dump chưa có (vài ngày gần nhất) bằng REST; tải OKX để đối chiếu.
3. `pipeline/curate.py`: raw → curated. Xử lý timestamp micro giây của dump Spot từ 2025-01-01.
4. `store/resample.py`: 1 phút → 15m, 1h, 4h, 1d, 1w theo UTC; tuần bắt đầu thứ Hai.
5. `pipeline/validate.py`: báo cáo nến thiếu, trùng, giá bất thường, lệch giữa hai sàn.
6. Lệnh `rinng backfill` và `rinng validate`.

**Thư viện thêm:** không.

**Xong khi:**
- Không có nến thiếu hay trùng trong khoảng đã tải, hoặc mọi khoảng thiếu đều được liệt kê kèm lý do (sàn bảo trì).
- Nến 1h và 1d tự resample khớp từng giá trị với nến sàn trả về trên một tháng mẫu.
- Phần giao nhau giữa dump và REST khớp nhau.

**Quyết định cần trước:** độ sâu lịch sử (đề xuất nến từ 2020; aggTrades 12 tháng gần nhất).

## Phase 5 — Lõi phân tích

**Mục tiêu:** dựng hai kiểu đầu ra Feature và Event, cùng các khối mà mọi module sau dùng lại.

**Việc:**
1. `analysis/types.py`: kiểu `Features`, `Events`, `Params` và cách băm tham số.
2. `analysis/indicators.py`: RSI, MACD, ROC, Stochastic, Williams %R, ATR, Bollinger, EMA/SMA, ADX, OBV, VWAP và anchored VWAP.
3. `analysis/structure.py`: swing high/low với độ dài cấu hình được; nhãn HH/HL/LH/LL; mỗi swing có `event_time` và `known_at`.
4. `pipeline/run.py`: chạy một module trên một instrument và một khung thời gian, ghi vào `features/` hoặc `events/`.

**Thư viện thêm:** TA-Lib (cần cài thư viện C qua Homebrew), `numpy`.

**Xong khi:**
- Mỗi indicator có test trên chuỗi dựng tay với giá trị kỳ vọng tính độc lập.
- Test chống nhìn trước: cắt dữ liệu tại thời điểm T, mọi dòng có `known_at` ≤ T phải giống hệt kết quả khi chạy trên toàn bộ dữ liệu.
- So bằng mắt RSI, MACD và các swing với TradingView trên ba đoạn giá.

**Rủi ro:** TA-Lib có thể chưa có bản dựng sẵn cho môi trường này; phương án dự phòng là tự viết các indicator bằng numpy.

## Phase 6 — SMC và thanh khoản

**Mục tiêu:** các khái niệm SMC thành sự kiện có định nghĩa rõ, kiểm định được.

**Việc:**
1. `analysis/smc.py`: BOS, CHoCH (phá bằng giá đóng hay wick là tham số), FVG kèm trạng thái đã lấp, order block kèm mitigation và breaker, premium/discount, displacement theo bội số ATR.
2. `analysis/liquidity.py`: equal highs/lows với dung sai theo ATR, liquidity sweep, vùng thanh khoản dưới đáy và trên đỉnh cũ.
3. Ghi định nghĩa đã chọn cho từng khái niệm vào tài liệu, vì SMC không có định nghĩa chuẩn.

**Thư viện thêm:** không.

**Xong khi:**
- Mỗi loại sự kiện có test trên chuỗi nến dựng tay, gồm cả trường hợp không được sinh sự kiện.
- Test chống nhìn trước như phase 5 qua cho mọi loại sự kiện, kể cả `invalidated_at`.
- So bằng mắt với một indicator SMC trên TradingView trên ba đoạn giá; ghi lại chỗ khác và lý do.

**Rủi ro:** giả mã trong [03-pine-script-va-smc.md](03-pine-script-va-smc.md) chưa từng chạy, chỉ dùng làm điểm xuất phát.

## Phase 7 — Volume profile và order flow

**Mục tiêu:** dựng lại được chart volume profile tuần có VPOC và delta.

**Việc:**
1. `analysis/volume_profile.py` bản gần đúng: rải volume của nến 1 phút theo khoảng giá; VPOC, VAH/VAL (70%), HVN/LVN, naked POC; profile theo phiên, tuần, tháng và theo khoảng neo tùy ý.
2. Bản chính xác từ aggTrades; so sai lệch với bản gần đúng.
3. `analysis/orderflow.py`: delta theo nến từ `taker_buy_volume`, CVD; footprint theo mức giá, imbalance và absorption từ aggTrades.
4. Bổ sung tải aggTrades vào phase 4 cho khoảng thời gian cần.

**Thư viện thêm:** không.

**Xong khi:**
- Test trên dữ liệu dựng tay: VPOC, VAH, VAL đúng với phép tính tay; tổng volume của profile bằng tổng volume nến.
- Delta theo nến tính từ nến khớp với delta gộp từ aggTrades trên một ngày mẫu.
- VPOC tuần lệch không quá một bin so với TradingView trên ba tuần mẫu.

**Quyết định cần trước:** kích thước bin giá và định nghĩa tuần (đề xuất thứ Hai 00:00 UTC).

**Rủi ro:** biến thể value area của TradingView chưa xác minh; aggTrades rất nặng, có thể chỉ lưu dạng đã gộp theo mức giá.

## Phase 8 — Phái sinh, Wyckoff, Elliott

**Mục tiêu:** feature từ dữ liệu phái sinh, và các thành phần đo được của Wyckoff và Elliott.

**Việc:**
1. `analysis/derivatives.py`: funding (mức, z-score, tích lũy), basis và premium, thay đổi OI, bảng trạng thái giá + OI, long/short ratio, cụm liquidation.
2. `analysis/wyckoff.py`: climax volume, biên trading range, spring và upthrust, effort vs result. Không gắn nhãn cả sơ đồ.
3. `analysis/elliott.py`: zigzag pivot, kiểm ba quy tắc cứng cho một dãy pivot, tỷ lệ Fibonacci giữa các sóng. Không tự chọn một cách đếm duy nhất.

**Thư viện thêm:** không.

**Xong khi:**
- Test trên dữ liệu dựng tay cho từng feature và sự kiện.
- Test chống nhìn trước qua.
- Feature OI và liquidation chỉ được tính trên các đoạn không có khoảng trống trong `meta/gaps`.

**Rủi ro:** lịch sử OI và long/short phụ thuộc file `metrics`; liquidation chỉ có từ lúc phase 3 chạy, nên phần này có ít dữ liệu để kiểm định trong thời gian đầu.

## Phase 9 — Chiến lược và backtest

**Mục tiêu:** đo được một ý tưởng có lợi thế hay không, sau chi phí, so với baseline.

**Việc:**
1. `strategy/base.py` và hai baseline: buy-and-hold, hồi quy tuyến tính 40 nến (như trong paper).
2. `backtest/costs.py`: phí maker/taker, slippage, funding theo thời gian giữ lệnh.
3. `backtest/engine.py`: vào lệnh ở nến sau `known_at`; stop và take-profit trong nến; quy ước khi cả hai cùng chạm trong một nến.
4. `backtest/metrics.py` và `report.py`: Sharpe, Sortino, max drawdown, win rate, profit factor, số lệnh; annualize cho thị trường 24/7.
5. Tách in-sample và out-of-sample; ghi số cấu hình đã thử.
6. Lệnh `rinng backtest`.

**Thư viện thêm:** `quantstats`.

**Xong khi:**
- Một chiến lược giao cắt EMA trên dữ liệu dựng tay cho đúng từng lệnh và đúng lãi lỗ so với phép tính tay, kể cả phí và funding.
- Buy-and-hold cho lợi nhuận bằng thay đổi giá trừ chi phí.
- Mỗi lần chạy lưu cấu hình, mã băm tham số và phiên bản code vào `results/`.

**Rủi ro:** thử nhiều tham số sẽ dẫn tới overfitting; cần kỷ luật giữ nguyên tập out-of-sample.

## Phase 10 — Chart và dashboard

**Mục tiêu:** nhìn thấy dữ liệu, sự kiện và kết quả backtest.

**Việc:**
1. `viz/chart.py`: nến kèm lớp phủ (vùng FVG và order block, đường VPOC và value area, nhãn BOS/CHoCH, swing).
2. `viz/overlays.py`: volume profile bên cạnh, bảng dưới cho CVD, funding, OI.
3. Dashboard: chọn instrument, khung thời gian, lớp phủ; trang kết quả backtest.

**Thư viện thêm:** Plotly hoặc `lightweight-charts`, Streamlit.

**Xong khi:** dựng lại được chart volume profile tuần và chart vùng thanh khoản trong bộ ảnh mẫu, từ dữ liệu của dự án.

## Phase 11 — Pine Script

**Mục tiêu:** đưa các tín hiệu đã qua kiểm định lên TradingView.

**Việc:** viết indicator Pine v6 cho từng nhóm tín hiệu đã qua phase 9; dùng cùng tham số với Python.

**Xong khi:** trên cùng một đoạn giá, sự kiện Pine vẽ ra trùng với sự kiện Python, và chỗ lệch được giải thích.

**Rủi ro:** Pine giới hạn 500 line/box/label và có mô hình thực thi khác, nên một số sự kiện chỉ hiển thị được phần gần nhất.

## Hoãn, chưa xếp phase

- Lớp LLM multi-agent.
- Dữ liệu on-chain trả phí.
- Mảng vĩ mô (lãi suất Fed, vàng, DXY), chờ quyết định.
- Đặt lệnh thật.

## Quyết định còn treo

| Quyết định | Cần trước phase | Mặc định nếu không nói gì |
|---|---|---|
| Tải file `metrics` và `bookDepth` để xem cột | 2 | chưa tải |
| Bộ thu chạy trên Mac hay VPS | 3 | Mac này, chấp nhận khoảng trống khi máy ngủ |
| Độ sâu lịch sử | 4 | nến từ 2020; aggTrades 12 tháng |
| Kích thước bin và định nghĩa tuần của volume profile | 7 | tuần bắt đầu thứ Hai 00:00 UTC; bin chọn khi làm |
| Có làm mảng vĩ mô không | 8 | không |
| Dự án có mục đích thương mại không | 9 | coi như có, nên không dùng vectorbt và mã LuxAlgo |
