# rinng

Phân tích quant cho crypto (USDT perpetual trên Binance và OKX): thu dữ liệu, indicator, SMC,
thanh khoản, volume profile, order flow, dữ liệu phái sinh, Wyckoff/Elliott, backtest,
dashboard và indicator Pine Script.

Tài liệu: [docs/](docs/README.md). Kiến trúc: [docs/08-kien-truc.md](docs/08-kien-truc.md).
Lộ trình và trạng thái từng phase: [docs/09-lo-trinh-phase.md](docs/09-lo-trinh-phase.md).

## Cài

```bash
uv sync
```

## Quy trình

```bash
uv run rinng check                      # thử kết nối hai sàn, in giới hạn tốc độ
uv run rinng backfill --start 2020-01-01  # dump Binance + REST, rồi curate
uv run rinng backfill --exchange okx --start 2026-08-01 --dataset klines_1m
uv run rinng resample                   # 1m → 15m, 1h, 4h, 1d, 1w
uv run rinng validate                   # nến thiếu/trùng, so với sàn, so hai sàn
uv run rinng analyze --timeframe 4h     # ghi data/features, data/events
uv run rinng backtest --timeframe 4h --split 2025-01-01
uv run rinng dashboard                  # http://localhost:8501
uv run rinng collect                    # bộ thu realtime, chạy liên tục
uv run rinng curate                     # đưa dữ liệu collector vào curated
```

Bộ thu realtime nên chạy 24/7 vì liquidation, open interest và long/short ratio không lấy lại
được về sau. File dịch vụ (chưa cài) nằm trong [deploy/](deploy/).

## Web rinng (dashboard + nhiều tab chart)

Giao diện React (TanStack Start + shadcn/ui, thư mục `web/`) trên API FastAPI của rinng.

```bash
pnpm --dir web install && pnpm --dir web build   # build một lần
uv run rinng live                                 # dữ liệu realtime, mở http://127.0.0.1:8000
uv run rinng web                                  # hoặc: chỉ xem dữ liệu đã lưu
```

`rinng live` chạy collector (Binance + OKX, gồm nến 1m), cập nhật curated mỗi phút và đẩy giá,
nến đang chạy, nến vừa đóng xuống trình duyệt qua WebSocket `/ws/live`. Phân tích (SMC, profile,
Wyckoff…) chỉ tính lại khi nến của khung đó đóng. Nếu máy tắt lâu hơn 3 ngày, chạy
`rinng backfill --start <ngày>` trước. Chi tiết: [docs/10-ke-hoach-realtime.md](docs/10-ke-hoach-realtime.md).

- Tab **Dashboard**: giá, funding, OI, long/short, delta 24h và bối cảnh cấu trúc 4H,
  volume profile tuần, thanh khoản, động lượng, Wyckoff; nút "Xem chart" mở chart lớn.
- Các tab chart: chọn bố cục (1 đến 6 khung), kéo thẻ từ thư viện vào khung, kéo tay nắm
  trên đầu chart để đổi chỗ, phóng to một khung. Bố cục lưu trong trình duyệt.
- Watchlist mặc định 5 coin (BTC, SOL, ETH, BNB, LINK) có lịch sử lưu sẵn và dữ liệu realtime.
  Ô tìm coin (⌘K hoặc /) mở mọi hợp đồng perp USDT trên Binance/OKX (~790 mã): dữ liệu qua REST,
  `rinng live` mở feed realtime theo yêu cầu (tối đa 8 coin cùng lúc). Thêm coin vào watchlist:
  sửa `configs/instruments.yaml` rồi chạy `rinng backfill --symbol <ID>`.
- **Combos** trong thư viện chart: 7 bộ chart ghép sẵn, mỗi bộ trả lời một câu hỏi (Top-down
  structure, Value vs. liquidity, Trend health, Positioning & squeeze risk, Market cycle, Risk map,
  Intraday plan) kèm thứ tự đọc. Kéo vào lưới để nạp vào tab đang mở, hoặc bấm "New tab".
- Lens **Projection**: hình nón xác suất cho H nến tới, xác suất chạm các mức giá, kèm kết quả
  kiểm chứng walk-forward ngay trên chart. Phương pháp và số liệu: [docs/11-du-bao.md](docs/11-du-bao.md).
- Sửa giao diện: chạy `uv run rinng web` rồi `pnpm --dir web dev` (cổng 3000, /api chuyển sang 8000).
- Giao diện cũ (HTML thuần) vẫn ở `/classic`.

## Thư mục

| Thư mục | Nội dung |
|---|---|
| `src/rinng/exchanges` | bộ chuyển đổi Binance, OKX, điều tiết tốc độ |
| `src/rinng/ingest` | collector (WebSocket, poller), dump data.binance.vision, backfill |
| `src/rinng/store` | schema, ghi/đọc Parquet, manifest, gaps, DuckDB, resample |
| `src/rinng/analysis` | indicators, structure, smc, liquidity, volume_profile, orderflow, derivatives, wyckoff, elliott |
| `src/rinng/pipeline` | curate, validate, chạy module phân tích |
| `src/rinng/strategy`, `src/rinng/backtest` | chiến lược, engine, metric, báo cáo |
| `src/rinng/viz` | chart Plotly, dashboard Streamlit |
| `src/rinng/web` | API web (lens chart, số liệu dashboard) |
| `web/` | giao diện React + shadcn/ui |
| `pine/` | indicator Pine Script v6 |
| `data/` | dữ liệu (không đưa vào git) |

## Kiểm thử

```bash
uv run pytest              # không cần mạng
uv run pytest -m network   # gọi sàn thật
uv run ruff check && uv run ruff format --check
```

Hệ thống chỉ phân tích và backtest; không đặt lệnh.
