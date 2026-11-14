# 10. Kế hoạch đưa web rinng sang dữ liệu realtime

Ngày lập: 2026-11-14. Phạm vi: crypto, Binance + OKX perp, chỉ phân tích (không đặt lệnh).

## Hiện trạng (đã kiểm trong code)

| Phần | Đang có | Thiếu cho realtime |
|---|---|---|
| Collector (`rinng collect`) | WS Binance: `aggTrade`, `markPrice@1s`, `forceOrder`; WS OKX tương ứng; poller REST 5 phút cho OI, long/short, taker volume, funding | Không có stream nến (kline); chưa chạy liên tục (chưa qua bài 72h); chưa cài dịch vụ |
| Store | raw → curated bằng lệnh `curate` + `resample` chạy tay, xử lý lại toàn bộ | Không cập nhật tăng dần; curated cũ đi vài giờ là dashboard cũ theo |
| Web API | Đọc curated, thiếu thì gọi REST; cache 60 giây | Không đẩy dữ liệu xuống trình duyệt; cache theo thời gian chứ không theo nến đóng |
| Web UI | Chart vẽ một lần lúc tải | Không có giá chạy, nến đang hình thành, trạng thái kết nối |
| Coin | `configs/instruments.yaml` chỉ có id + mã sàn (BTC, ETH) | Không có tên coin, base asset, icon |

Nguyên tắc giữ nguyên: **phân tích (SMC, profile, Wyckoff…) chỉ chạy trên nến đã đóng**, nên realtime
chỉ làm hai việc: (1) cập nhật giá và nến đang chạy ngay lập tức, (2) tính lại lens đúng lúc một nến
của khung đó đóng. Không vẽ tín hiệu từ nến chưa đóng → không lookahead.

## Kiến trúc đích

```
Binance WS ─┐                          ┌─ Parquet raw/curated (lưu bền)
OKX WS ─────┼─► rinng live (1 tiến trình) ─┤
REST poller ┘   • LiveHub: ring buffer     └─ FastAPI ─► /api/* (lens, summary)
                  nến 1m + giá + mark                 └─► WS /ws/live ─► trình duyệt
                • Updater: nến 1m đóng →                  (tick, nến đang chạy,
                  gộp vào curated, resample đuôi           nến đóng, funding, thanh lý)
```

Một tiến trình `rinng live` chạy cả collector lẫn web (asyncio), để tick đi thẳng từ WS sàn sang
WS trình duyệt mà không phải đọc lại đĩa. `rinng web` cũ vẫn giữ để xem dữ liệu tĩnh.

## Các bước

### Bước 0. Bắt kịp dữ liệu (làm ngay, ~vài phút)
- `rinng backfill` + `rinng curate` + `rinng resample` để curated tới hiện tại.
- Kiểm: dashboard ghi "1H candle closed < 1h ago".

### Bước 1. Coin metadata và icon đúng
- `instruments.yaml`: thêm `base` (BTC, ETH), `quote` (USDT), `name` (Bitcoin, Ethereum).
- `/api/meta` trả về danh sách instrument dạng object thay vì chuỗi.
- Icon: gói **`@web3icons/react`** (MIT, cập nhật 2026-11, hàng nghìn token, SVG đóng gói sẵn — không
  gọi mạng, không lộ dữ liệu, không bị rate limit). Hiện ở ô chọn cặp, thẻ giá dashboard, đầu mỗi chart.
  Coin không có icon → huy hiệu chữ cái đầu.
- Phương án dự phòng đã cân nhắc: `cryptocurrency-icons` (CC0) — ngừng cập nhật từ 2022, thiếu coin mới;
  ảnh CoinGecko — phải gọi API ngoài và tôn trọng giới hạn của họ.
- Test: mỗi instrument trong config có icon hoặc fallback.

### Bước 2. Stream nến 1m từ sàn
- Binance: thêm `<symbol>@kline_1m` vào combined stream đang có.
- OKX: kênh `candle1m` nằm ở endpoint **business** (`/ws/v5/business`), khác endpoint public đang dùng →
  thêm một feed thứ hai; vẫn ping mỗi < 30 giây như feed hiện tại.
- Chỉ ghi nến khi sàn báo đã đóng (`x=true` ở Binance, `confirm=1` ở OKX) vào raw `ohlcv_1m`;
  nến đang chạy chỉ giữ trong bộ nhớ.
- Khi kết nối lại: lấp phút bị hụt bằng REST klines (đã có trong adapter), ghi gap như hiện tại.
- Test: phát lại tin nhắn WS đã ghi sẵn → đúng số nến, đúng `is_closed`.

### Bước 3. Cập nhật curated tăng dần
- Hàm mới `curate_tail(exchange, symbol, since)`: gộp nến 1m mới vào curated (dùng `merge_into`
  hiện có) và resample lại **chỉ bucket cuối** của 15m/1h/4h/1d/1w.
- Chạy mỗi khi có nến 1m đóng (≈ mỗi phút), thay cho curate toàn bộ.
- Test bắt buộc: kết quả `curate_tail` lặp nhiều lần == `curate` + `resample` toàn bộ trên cùng dữ liệu.

### Bước 4. `rinng live`: LiveHub trong một tiến trình
- LiveHub giữ: giá cuối (aggTrade), mark price + funding kế tiếp, nến 1m đang chạy, nến đang chạy
  của từng khung (gộp từ 1m), 50 lệnh thanh lý gần nhất.
- Phát sự kiện nội bộ: `tick`, `bar_update(tf)`, `bar_close(tf)`, `funding`, `liquidation`.
- Lệnh `rinng live` = collector + updater + FastAPI trên cùng event loop.
- Cache lens đổi sang khóa theo **thời điểm nến đóng cuối cùng** của khung đó, bỏ TTL 60 giây.

### Bước 5. WebSocket xuống trình duyệt
- `WS /ws/live?symbol=&exchange=` gửi JSON gọn:
  - `tick` (giới hạn tối đa ~4 lần/giây), `bar` (nến đang chạy cho các tf mà client đăng ký),
  - `close` (tf + thời gian nến vừa đóng), `funding`, `liq`.
- Trình duyệt:
  - Chart: `series.update()` cho nến đang chạy (vẽ mờ hơn để phân biệt); khi nhận `close` đúng tf
    của chart → gọi lại `/api/chart` để vẽ lại lens.
  - Dashboard: giá, % 24h, mark/funding + đếm ngược tới kỳ funding chạy theo tick; thẻ bối cảnh tính
    lại khi nến 1H đóng.
  - Một kết nối WS dùng chung cho cả tab, không mở một kết nối cho mỗi chart.

### Bước 6. Độ tin cậy và hiển thị trạng thái
- Chấm trạng thái ở thanh trên: **Live** (tick < 5s), **Delayed** (5–60s), **Offline**; kèm tuổi dữ liệu.
- Kết nối lại có backoff ở cả hai chiều (sàn → server, server → trình duyệt).
- Giới hạn phía sàn cần tôn trọng: Binance ngắt mỗi kết nối WS sau 24 giờ (đã xử lý reconnect),
  tối đa 1024 stream mỗi kết nối; OKX cần ping khi im lặng 30 giây. REST vẫn qua `WeightLimiter` có sẵn.
- Ghi log số tin nhắn, độ trễ, số lần reconnect; `rinng check` thêm mục "live".

### Bước 7. Chạy liên tục
- Bài chạy thử 72 giờ (tiêu chí còn nợ từ Phase 1): không mất nến, gap được lấp, RAM ổn định.
- Cài dịch vụ launchd từ `deploy/` (cần bạn đồng ý vì là thay đổi hệ thống).

### Bước 8 (tùy chọn). Thêm coin
- Thêm instrument vào config (ví dụ SOL, BNB, XRP), chạy backfill; icon có sẵn từ Bước 1.
- Lưu ý dung lượng: mỗi coin thêm aggTrade lưu raw khá nặng; có thể tắt lưu trade cho coin phụ.

## Trạng thái (2026-11-14)

| Bước | Trạng thái |
|---|---|
| 0 | Xong: backfill 2026-11-01 → hiện tại cho Binance + OKX, resample lại |
| 1 | Xong: `base/quote/name` trong config, icon `@web3icons/react` ở ô chọn, dashboard, chart |
| 2 | Xong: `kline_1m` (Binance), `candle1m` qua `/ws/v5/business` (OKX); chỉ ghi nến đã đóng |
| 3 | Xong: `rinng.live.tail.curate_tail`, test tương đương resample toàn bộ |
| 4 | Xong: `LiveHub`, lệnh `rinng live`, lấp gap bằng REST mỗi phút, cache theo nến đóng |
| 5 | Xong: `/ws/live`, nến đang chạy (mờ), lens vẽ lại khi nến đóng, giá/funding chạy trên dashboard, chấm Live/Delayed/Offline |
| 6–7 | Chưa làm |

## Thứ tự đề xuất và tiêu chí xong

| Bước | Xong khi |
|---|---|
| 0 | Dashboard không cũ quá 1 giờ |
| 1 | Icon BTC/ETH đúng ở ô chọn, dashboard, chart |
| 2–3 | Nến 1m vào curated trong < 5 giây sau khi đóng; test tương đương full curate pass |
| 4–5 | Giá trên web nhảy theo tick; nến đang chạy cập nhật; lens tự vẽ lại khi nến đóng |
| 6 | Rút mạng 1 phút rồi cắm lại: UI báo Offline → Live, không thiếu nến |
| 7 | 72 giờ liên tục không lỗi |
