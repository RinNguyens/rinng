# rinng

Phân tích quant cho crypto: dữ liệu Binance/OKX, indicator, SMC, volume profile, order flow, backtest.

Tài liệu nằm trong [docs/](docs/README.md). Kiến trúc: [docs/08-kien-truc.md](docs/08-kien-truc.md). Kế hoạch: [docs/07-ke-hoach-trien-khai.md](docs/07-ke-hoach-trien-khai.md).

## Trạng thái

Mới có khung dự án: cấu hình, bố cục thư mục dữ liệu, giao diện sàn, lệnh kiểm tra kết nối. Các gói `ingest`, `analysis`, `pipeline`, `strategy`, `backtest`, `viz` còn rỗng.

## Dùng

```bash
uv sync
uv run rinng check     # thử kết nối hai sàn, in giới hạn tốc độ
uv run rinng config    # in cấu hình đã kiểm tra
uv run pytest
uv run ruff check
```
