# 07 — Kế hoạch triển khai từng bước (crypto, chưa có LLM)

Lập ngày 2026-11-13. Số liệu giới hạn API lấy từ [02-exchange-apis.md](02-exchange-apis.md); chỗ nào file đó ghi "chưa xác minh" thì ở đây cũng ghi lại. Chưa có bước nào được thực hiện.

## 1. Các quyết định mặc định

Đây là giá trị tôi đề xuất để kế hoạch đủ cụ thể. Đổi được, nhưng nên chốt trước bước 1.

| Hạng mục | Mặc định | Lý do |
|---|---|---|
| Cặp giao dịch | BTCUSDT, ETHUSDT | thanh khoản cao nhất, dữ liệu dài nhất; thêm mã sau không đổi kiến trúc |
| Loại hợp đồng | USDT perpetual là chính, spot để đối chiếu | funding, OI, liquidation chỉ có ở perpetual |
| Sàn chính | Binance; OKX là nguồn thứ hai | Binance có kho dump đầy đủ hơn và giữ lịch sử funding dài hơn |
| Nến gốc lưu trữ | 1 phút | mọi khung lớn hơn resample từ đây; volume profile cần 1 phút |
| Khung phân tích | 15m, 1h, 4h, 1D, 1W | khớp các chart mẫu |
| Múi giờ | UTC cho mọi thứ | nến `1D` của OKX mặc định mở theo UTC+8, phải dùng `1Dutc` |
| API key | không dùng | toàn bộ dữ liệu cần thiết là công khai |

## 2. Giới hạn và chặn ở Binance và OKX

### 2.1 Tóm tắt

Dữ liệu thị trường công khai ở cả hai sàn không cần API key và không mất phí. Giới hạn tốc độ rộng hơn nhiều so với nhu cầu của dự án. Rủi ro thật nằm ở ba chỗ: độ sâu lịch sử của một số chuỗi, bị ban IP nếu bỏ qua lỗi 429, và chặn theo khu vực của máy chạy.

### 2.2 Giới hạn tốc độ

| | Binance | OKX |
|---|---|---|
| Cách tính | theo weight, theo IP | theo từng endpoint, "N request / 2 giây", theo IP |
| Mức | Spot 6000 weight/phút; Futures 2400 weight/phút (USDⓈ-M và COIN-M dùng chung) | candles 40/2s; history-candles 20/2s; nhóm thống kê `rubik` 5/2s |
| Biết đã dùng bao nhiêu | header `X-MBX-USED-WEIGHT-1M` | không có header, phải tự đếm |
| Khi vượt | HTTP 429 kèm `Retry-After` | mã `50011` trong body, HTTP vẫn 200 |
| Nếu tiếp tục gửi | HTTP 418, ban IP từ 2 phút đến 3 ngày, tăng dần | docs không mô tả hình phạt (chưa xác minh) |
| Giới hạn riêng | `fundingRate` 500 request/5 phút; nhóm `/futures/data/*` 1000 request/5 phút | funding 10/2s theo IP + instrument |
| Khác | HTTP 403 khi vi phạm WAF | — |

Ước lượng thời gian tải nến 1 phút qua REST, chạy ở một nửa giới hạn:

- Binance Futures: 1500 nến/lần, weight 10, tức khoảng 120 lần/phút = 180.000 nến/phút. Một năm (525.600 nến) mất khoảng 3 phút.
- OKX: 300 nến/lần, khoảng 300 lần/phút = 90.000 nến/phút. Một năm mất khoảng 6 phút.

Đây là phép tính từ số trong docs, chưa đo thực tế. Một lần gọi thử `limit=1500` làm bộ đếm weight tăng nhiều hơn bảng nêu, nên bộ tải phải đọc header chứ không tự cộng.

### 2.3 Độ sâu lịch sử (giới hạn quan trọng nhất)

| Dữ liệu | Binance qua REST | Binance qua dump (data.binance.vision) | OKX qua REST | OKX qua dump |
|---|---|---|---|---|
| Nến | đầy đủ | có, từ 1s đến 1mo | `candles` chỉ 1440 nến mới nhất; `history-candles` "những năm gần đây" | nến 1 phút từ 2023-07 |
| aggTrades / trades | Futures chỉ 48 giờ | có, theo ngày và tháng | 3 tháng | từ 2021-09 |
| Funding rate | đầy đủ, 1000 bản ghi/lần | có, theo tháng | chỉ 3 tháng | từ 2022-03 |
| Open interest | chỉ 30 ngày | có trong file `metrics` (cột chưa xác minh) | 1440 bản ghi mới nhất | không thấy |
| Long/short ratio | chỉ 30 ngày | có thể trong `metrics` (chưa xác minh) | 1440 bản ghi mới nhất | không thấy |
| Taker buy/sell volume | 30 ngày (limit chưa xác minh) | suy được từ cột taker buy của nến | 1440 bản ghi mới nhất | suy từ trades |
| Liquidation | không có REST công khai | không có (đường dẫn thử trả 404) | REST không còn trong docs | không có |
| Order book | chỉ ảnh chụp hiện tại | `bookDepth` (cột chưa xác minh) | chỉ ảnh chụp hiện tại | L2 từ 2023-03 |

Hệ quả:

1. Nến, trades và funding lấy lại được đầy đủ bất cứ lúc nào.
2. Open interest và long/short ratio: quá 30 ngày thì phụ thuộc file `metrics` của Binance. Việc đầu tiên cần làm là tải một file về xem cột.
3. Liquidation không có lịch sử ở đâu cả. Chỉ có từ lúc bộ thu WebSocket bắt đầu chạy, và ngay cả khi chạy cũng không đầy đủ: Binance chỉ đẩy lệnh mới nhất mỗi 1000 ms, OKX ghi rõ là không đầy đủ.

### 2.4 Chặn theo khu vực

- Từ máy này, ngày 2026-11-13, `api.binance.com`, `fapi.binance.com`, `dapi.binance.com` đều trả 200.
- Docs API của Binance không nêu danh sách khu vực bị chặn (chưa xác minh). Theo hiểu biết chung của tôi, không phải từ tài liệu đã tra, Binance chặn IP từ Mỹ. Nếu thuê VPS, chọn khu vực rồi gọi `GET /api/v3/ping` và `GET /fapi/v1/ping` trước khi trả tiền dài hạn.
- OKX: tài khoản đăng ký ở Mỹ, Úc dùng `us.okx.com`; EU dùng `eea.okx.com`; nơi khác dùng `openapi.okx.com`. Danh sách quốc gia bị hạn chế chưa đọc được (chưa xác minh).

### 2.5 WebSocket

- Binance: kết nối sống tối đa 24 giờ, phải tự kết nối lại. Futures đã tách URL thành `/public`, `/market`, `/private`.
- OKX: client phải gửi `ping` nếu im lặng 30 giây; sàn ngắt kết nối khi nâng cấp, báo trước 60 giây.
- Cả hai đều yêu cầu bộ thu có logic kết nối lại và ghi nhận khoảng trống.

### 2.6 Quy tắc viết bộ tải để không bị ban

1. Đọc `rateLimits` từ `exchangeInfo` lúc khởi động, không ghi cứng con số.
2. Tự giới hạn ở 50% mức cho phép.
3. Binance: đọc `X-MBX-USED-WEIGHT-1M` sau mỗi lần gọi; gặp 429 thì ngủ đúng `Retry-After`, không gọi lại ngay.
4. OKX: kiểm tra `code` trong body ở mọi phản hồi, vì lỗi vẫn trả HTTP 200.
5. Lịch sử dài lấy từ dump trước, REST chỉ lấp phần còn thiếu.
6. Realtime dùng WebSocket, không poll REST.

## 3. Mỗi indicator cần thêm gì

Cột "Cần thêm" là thứ ngoài nến OHLCV 1 phút.

### 3.1 Chỉ cần OHLCV

| Nhóm | Indicator | Công cụ | Tham số phải chốt | Cần thêm |
|---|---|---|---|---|
| Momentum | RSI, MACD, ROC, Stochastic, Williams %R | TA-Lib | chu kỳ; số nến khởi động bị bỏ | không |
| Biến động | ATR, Bollinger Bands | TA-Lib | chu kỳ, số độ lệch chuẩn | không |
| Xu hướng | EMA/SMA, ADX, kênh hồi quy OLS | TA-Lib, numpy | chu kỳ, độ dài cửa sổ | không |
| Volume | OBV, VWAP, anchored VWAP | tự viết | điểm neo (đầu tuần, đầu tháng, swing) | không; VWAP chính xác cần nến 1 phút |
| Cấu trúc | swing high/low, HH/HL/LH/LL | tự viết | độ dài swing (số nến mỗi bên) | không |
| SMC | BOS, CHoCH, order block, FVG, premium/discount, displacement | tự viết | độ dài swing; phá bằng giá đóng hay wick; ngưỡng displacement theo ATR | không |
| Thanh khoản | equal highs/lows, liquidity sweep, vùng dưới đáy cũ | tự viết | dung sai "bằng nhau" theo ATR; số nến xác nhận sweep | không |
| Wyckoff (thành phần) | climax volume, biên trading range, spring/upthrust, effort vs result | tự viết | ngưỡng z-score volume; cách xác định range | không |
| Elliott (thành phần) | zigzag pivot, 3 quy tắc cứng, tỷ lệ Fibonacci | tự viết | ngưỡng zigzag (% hoặc ATR) | không |
| Phiên | kill zone, đỉnh/đáy phiên Á–Âu–Mỹ | tự viết | khung giờ UTC của từng phiên | không |

Lưu ý chung cho nhóm này: mọi tín hiệu dựa trên swing chỉ được xác nhận sau N nến. Phải lưu thời điểm xác nhận, nếu không backtest sẽ nhìn trước tương lai.

### 3.2 Cần dữ liệu ngoài nến

| Indicator | Cần thêm | Nguồn | Có lịch sử không |
|---|---|---|---|
| Volume profile gần đúng (VPOC, VAH/VAL, HVN/LVN, naked POC) | không, dùng nến 1 phút rải volume theo khoảng giá | nến | có |
| Volume profile chính xác | từng giao dịch | aggTrades từ dump Binance | có |
| Delta theo nến, CVD | cột taker buy volume có sẵn trong nến Binance (delta = 2 × taker buy − volume) | nến Binance | có |
| Delta theo mức giá, footprint, imbalance, absorption | từng giao dịch kèm chiều taker | aggTrades (trường `m`) | có qua dump; REST Futures chỉ 48 giờ |
| Funding rate, funding cực đoan | funding lịch sử | Binance REST hoặc dump | có |
| Basis, premium | mark price, index price, premium index | `markPriceKlines`, `premiumIndexKlines` | có |
| Open interest, giá + OI | OI theo 5 phút | REST (30 ngày) + file `metrics` + bộ thu | tùy file `metrics` |
| Long/short ratio | tỷ lệ theo 5 phút | như trên | tùy file `metrics` |
| Liquidation, cụm thanh lý | luồng thanh lý | WebSocket `@forceOrder`, `liquidation-orders` | không, chỉ từ lúc tự thu |
| Liquidation heatmap | OI + giả định đòn bẩy | tự mô hình hóa | là ước lượng, không kiểm chứng được |
| Tường lệnh, độ sâu sổ lệnh | order book | WebSocket depth; `bookDepth` dump | một phần |
| Vĩ mô (lãi suất Fed, lợi suất) | chuỗi FRED | FRED API, cần đăng ký key miễn phí | có |
| Vàng, DXY | nguồn ngoài FRED | chưa chọn | chưa xác minh |
| On-chain (MVRV, SOPR, exchange flows) | nhà cung cấp trả phí | Glassnode, CryptoQuant | giá chưa xác minh |

Volume profile có hai tham số quyết định kết quả và phải chốt trước: kích thước bin giá, và định nghĩa "tuần" (đề xuất: thứ Hai 00:00 UTC). Biến thể mở rộng value area mà TradingView dùng chưa xác minh, nên kết quả có thể lệch nhẹ so với chart của bạn.

## 4. Các bước

Mỗi bước có tiêu chí xong. Không sang bước sau khi tiêu chí chưa đạt.

### Bước 0 — Chốt phạm vi
- Việc: xác nhận bảng ở mục 1; quyết định có làm mảng vĩ mô không; quyết định máy nào chạy bộ thu 24/7.
- Xong khi: các ô ở mục 1 và mục 5 có câu trả lời.

### Bước 1 — Khung dự án và kiểm tra kết nối
- Việc: tạo repo git, môi trường `uv`, cấu trúc thư mục, `pytest`, `ruff`. Viết script gọi `ping` và `exchangeInfo` của hai sàn, in ra giới hạn tốc độ đang áp dụng. Tải một file `metrics` và một file `bookDepth` của Binance để xem cột.
- Công cụ: `uv`, `httpx`, `ccxt`.
- Xong khi: script chạy được trên máy sẽ chạy bộ thu; biết chắc `metrics` có OI và long/short ratio hay không.

### Bước 2 — Bộ thu realtime (làm sớm vì dữ liệu không lấy lại được)
- Việc: tiến trình WebSocket ghi liquidation, mark price, aggTrades; tác vụ định kỳ 5 phút ghi OI, long/short ratio, taker volume qua REST. Có kết nối lại, ghi nhận khoảng trống, ghi Parquet theo lô.
- Công cụ: `websockets`, `APScheduler`, `polars`.
- Xong khi: chạy liên tục 72 giờ, qua được ít nhất một lần Binance ngắt kết nối 24 giờ, và báo cáo khoảng trống chính xác.

### Bước 3 — Tải lịch sử
- Việc: tải dump Binance (nến 1 phút, funding, aggTrades cho giai đoạn cần), kiểm checksum; lấp phần mới nhất bằng REST; tải OKX để đối chiếu.
- Lưu ý: dump Spot từ 2025-01-01 dùng timestamp micro giây, Futures vẫn mili giây.
- Xong khi: không có nến thiếu hay trùng trong khoảng đã tải; nến từ dump và từ REST khớp nhau ở phần giao nhau.

### Bước 4 — Lớp lưu trữ
- Việc: chuẩn hóa schema (UTC, kiểu số, tên cột chung cho hai sàn); resample 1 phút lên các khung phân tích; view DuckDB; bảng manifest ghi nguồn và khoảng thời gian.
- Xong khi: nến 1h và 1D tự resample khớp với nến 1h và 1D sàn trả về.

### Bước 5 — Module phân tích, theo thứ tự phụ thuộc
1. Indicator cổ điển (bọc TA-Lib).
2. Swing và cấu trúc thị trường. Mọi thứ ở 3, 4, 7 dựa vào đây.
3. SMC: BOS, CHoCH, FVG, order block, premium/discount.
4. Thanh khoản: equal highs/lows, sweep.
5. Volume profile bản gần đúng, rồi bản chính xác từ aggTrades.
6. Order flow: delta theo nến, CVD, rồi footprint.
7. Thành phần Wyckoff và Elliott.
8. Feature phái sinh: funding, OI, long/short, liquidation.
9. Vĩ mô, nếu giữ.

- Xong khi (cho từng module): có unit test trên dữ liệu dựng tay; mỗi tín hiệu có thời điểm xác nhận; đối chiếu bằng mắt với TradingView trên ít nhất ba đoạn giá.

### Bước 6 — Backtest
- Việc: engine nhận tín hiệu, mô phỏng lệnh có phí maker/taker, slippage, funding; metric; so với buy-and-hold và hồi quy tuyến tính; tách dữ liệu in-sample và out-of-sample.
- Xong khi: một chiến lược tầm thường (ví dụ giao cắt EMA) cho kết quả khớp với phép tính tay.

### Bước 7 — Hiển thị
- Việc: chart nến có lớp phủ (vùng, VPOC, nhãn cấu trúc), dashboard, báo cáo backtest.
- Công cụ: Plotly hoặc `lightweight-charts`, Streamlit.
- Xong khi: dựng lại được các chart mẫu của bạn từ dữ liệu của dự án.

### Bước 8 — Pine Script
- Việc: viết indicator v6 cho những tín hiệu đã qua bước 6.
- Xong khi: tín hiệu trên TradingView trùng với tín hiệu Python trên cùng đoạn giá.

### Hoãn
- Lớp LLM multi-agent.
- On-chain trả phí.
- Đặt lệnh thật.

## 5. Việc cần bạn quyết định

1. Danh sách cặp giao dịch ban đầu (mặc định BTCUSDT, ETHUSDT).
2. Bộ thu 24/7 chạy ở đâu: máy Mac này (mất dữ liệu khi máy ngủ) hay VPS.
3. Có giữ mảng vĩ mô (lãi suất Fed, vàng, DXY) không.
4. Lịch sử cần sâu tới đâu (đề xuất: nến từ 2020, aggTrades 12 tháng gần nhất vì dung lượng lớn).
5. Dự án có mục đích thương mại không. Câu trả lời quyết định có được dùng vectorbt và tham khảo mã LuxAlgo hay không.
