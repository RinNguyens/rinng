# 08 — Kiến trúc dự án rinng

Lập ngày 2026-11-13. Phạm vi: crypto, chưa có LLM, chưa đặt lệnh thật. Đây là bản thiết kế; chưa có dòng code nào. Kiến trúc dùng các mặc định ở [07-ke-hoach-trien-khai.md](07-ke-hoach-trien-khai.md) mục 1 (BTCUSDT và ETHUSDT perpetual, Binance là chính, nến gốc 1 phút, UTC); các mặc định đó chưa được xác nhận.

## 1. Nguyên tắc thiết kế

1. **Dữ liệu thô bất biến.** Thứ tải về được ghi một lần và không sửa. Mọi lớp sau tính lại được từ nó.
2. **Phụ thuộc một chiều.** Lớp sau chỉ đọc đầu ra của lớp trước qua file Parquet, không gọi ngược.
3. **Hai mốc thời gian.** Mỗi bản ghi phân tích có `event_time` (sự việc xảy ra lúc nào) và `known_at` (lúc nào mới biết chắc). Backtest chỉ được dùng `known_at`.
4. **Phân tích là hàm thuần.** Cùng dữ liệu và cùng tham số thì cùng kết quả; không gọi mạng, không đọc đồng hồ.
5. **Tham số nằm trong cấu hình**, không nằm trong code. Mỗi kết quả ghi lại mã băm của bộ tham số đã dùng.
6. **Sàn nằm sau một giao diện chung.** Phần còn lại của hệ thống không biết đang nói chuyện với Binance hay OKX.

## 2. Sơ đồ tổng thể

```
        Binance REST/WS      OKX REST/WS      data.binance.vision      (FRED, tùy chọn)
               │                  │                    │                     │
┌──────────────▼──────────────────▼────────────────────▼─────────────────────▼───────┐
│ L1  INGEST                                                                         │
│   exchanges/   bộ chuyển đổi từng sàn (giới hạn tốc độ, phân trang, chuẩn hóa tên) │
│   backfill     tải lịch sử theo lô            collector   thu realtime 24/7        │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ ghi
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L2  STORE                                                                          │
│   data/raw       đúng như sàn trả về, bất biến                                     │
│   data/curated   schema chung, UTC, đã khử trùng, đã resample                      │
│   data/meta      manifest, danh mục instrument, nhật ký khoảng trống               │
│   DuckDB         chỉ chứa view trỏ vào Parquet                                     │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ đọc curated
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L3  ANALYSIS (hàm thuần, không I/O mạng)                                           │
│   indicators → structure (swing) → smc · liquidity · wyckoff · elliott             │
│   volume_profile · orderflow · derivatives · (macro)                               │
│   Đầu ra: bảng feature (một dòng mỗi nến) và bảng event (một dòng mỗi sự kiện)     │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ ghi data/features, data/events
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L4  STRATEGY + BACKTEST                                                            │
│   strategy    feature + event → tín hiệu vào/ra, stop, take-profit                 │
│   engine      mô phỏng lệnh: phí, slippage, funding, thanh lý                      │
│   metrics     Sharpe, drawdown, so với baseline                                    │
└──────────────────────────────────────┬─────────────────────────────────────────────┘
                                       │ ghi data/results
┌──────────────────────────────────────▼─────────────────────────────────────────────┐
│ L5  PRESENTATION                                                                   │
│   chart có lớp phủ · dashboard · báo cáo backtest · indicator Pine Script          │
└────────────────────────────────────────────────────────────────────────────────────┘

   (hoãn)  L6  LLM diễn giải: chỉ đọc features, events, results; không ghi ngược
```

## 3. Các tiến trình chạy

Hệ thống không phải một chương trình duy nhất mà là năm kiểu chạy, dùng chung thư mục `data/`.

| Tiến trình | Kiểu | Làm gì | Ghi vào |
|---|---|---|---|
| `collector` | chạy liên tục 24/7 | WebSocket: liquidation, mark price, aggTrades. Định kỳ 5 phút: OI, long/short ratio, taker volume | `raw/` |
| `backfill` | lệnh chạy tay | tải dump và REST cho một khoảng thời gian, kiểm checksum | `raw/` |
| `pipeline` | chạy theo lịch (ví dụ mỗi giờ) hoặc tay | raw → curated → features → events | `curated/`, `features/`, `events/` |
| `backtest` | lệnh chạy tay | chạy một chiến lược với một bộ tham số | `results/` |
| `dashboard` | chạy khi cần xem | đọc và hiển thị | không ghi |

Chỉ `collector` cần máy luôn bật. Bốn tiến trình còn lại chạy trên máy cá nhân được. Nếu `collector` chạy trên VPS, thư mục `raw/` của nó được đồng bộ về máy phân tích; hai bên không cần kết nối trực tiếp.

Vì nhiều tiến trình ghi cùng `data/`, quy tắc là: mỗi tiến trình chỉ ghi vào vùng của mình, ghi file tạm rồi đổi tên, và không bao giờ sửa file đã có trong `raw/`.

## 4. Module và trách nhiệm

```
src/rinng/
  config/          đọc cấu hình, kiểm tra hợp lệ
  exchanges/       base.py (giao diện chung), binance.py, okx.py, ratelimit.py
  ingest/          backfill.py, dumps.py, collector/ (ws.py, poller.py, gaps.py)
  store/           paths.py, writer.py, reader.py, schemas.py, resample.py, catalog.py
  analysis/
    indicators.py      bọc TA-Lib
    structure.py       swing, HH/HL/LH/LL
    smc.py             BOS, CHoCH, order block, FVG, premium/discount
    liquidity.py       equal highs/lows, sweep
    volume_profile.py  VPOC, VAH/VAL, HVN/LVN, naked POC
    orderflow.py       delta, CVD, footprint
    derivatives.py     funding, OI, long/short, liquidation
    wyckoff.py         climax, range, spring/upthrust
    elliott.py         zigzag, quy tắc cứng, Fibonacci
    macro.py           tùy chọn
  pipeline/        sắp thứ tự chạy các bước phân tích, tính tăng dần
  strategy/        base.py, các chiến lược mẫu, baseline (buy-and-hold, hồi quy tuyến tính)
  backtest/        engine.py, costs.py, metrics.py, report.py
  viz/             chart.py, overlays.py, dashboard/
  cli.py           điểm vào dòng lệnh
pine/              indicator Pine Script v6
tests/             cùng cấu trúc với src/
data/              không đưa vào git
configs/           file cấu hình YAML
```

Quy tắc phụ thuộc giữa các gói:

| Gói | Được dùng | Không được dùng |
|---|---|---|
| `exchanges` | `config` | mọi gói khác |
| `ingest` | `exchanges`, `store`, `config` | `analysis` trở đi |
| `store` | `config` | `exchanges`, `analysis` |
| `analysis` | chỉ numpy, polars, TA-Lib | `store`, `exchanges`, mạng |
| `pipeline` | `store`, `analysis`, `config` | `exchanges` |
| `strategy` | kiểu dữ liệu của `analysis` | `store`, `exchanges` |
| `backtest` | `strategy`, `store` | `exchanges`, `ingest` |
| `viz` | `store` | `exchanges`, `ingest` |

Điểm quan trọng nhất: `analysis` nhận bảng dữ liệu trong bộ nhớ và trả bảng dữ liệu. Nó không biết file nằm ở đâu. Nhờ vậy test không cần dữ liệu thật, và cùng một hàm dùng được cho cả backtest lẫn realtime.

Trong `analysis`, thứ tự phụ thuộc là: `indicators` và `structure` đứng độc lập; `smc`, `liquidity`, `wyckoff`, `elliott` dùng `structure`; `volume_profile`, `orderflow`, `derivatives` đứng độc lập.

## 5. Mô hình dữ liệu

### 5.1 Các vùng

```
data/
  raw/        {exchange}/{dataset}/{symbol}/date=YYYY-MM-DD/*.parquet|zip
  curated/    {dataset}/exchange=…/symbol=…/timeframe=…/year=…/part-*.parquet
  features/   {module}/v{n}/symbol=…/timeframe=…/…
  events/     {module}/v{n}/symbol=…/timeframe=…/…
  results/    {run_id}/trades.parquet, equity.parquet, summary.json, config.yaml
  meta/       manifest.parquet, instruments.parquet, gaps.parquet
```

### 5.2 Bảng chính ở vùng curated

| Bảng | Khóa | Cột |
|---|---|---|
| `ohlcv` | exchange, symbol, timeframe, open_time | open, high, low, close, volume, quote_volume, trades, taker_buy_volume, is_closed |
| `trades` | exchange, symbol, trade_id | time, price, qty, is_buyer_maker |
| `funding` | exchange, symbol, funding_time | rate, mark_price |
| `open_interest` | exchange, symbol, time | oi_contracts, oi_value |
| `long_short` | exchange, symbol, time, kind | ratio, long_pct, short_pct |
| `liquidations` | exchange, symbol, time | side, price, qty |
| `mark_index` | exchange, symbol, time | mark_price, index_price, premium |

Mọi cột thời gian là UTC, độ phân giải mili giây. Tên symbol được chuẩn hóa về một dạng chung (ví dụ `BTC-USDT-PERP`); bảng `instruments` giữ tên gốc của từng sàn.

Cột `taker_buy_volume` chỉ có sẵn ở nến Binance; với OKX phải tính từ `trades`.

### 5.3 Hai dạng đầu ra của phân tích

**Feature** — giá trị liên tục, một dòng mỗi nến:

| Cột | Ý nghĩa |
|---|---|
| symbol, timeframe, open_time | khóa |
| known_at | bằng thời điểm đóng nến |
| các cột giá trị | ví dụ `rsi_14`, `atr_14`, `cvd`, `funding_z` |
| params_hash | mã băm bộ tham số |

**Event** — sự kiện rời rạc, một dòng mỗi sự kiện:

| Cột | Ý nghĩa |
|---|---|
| event_id | định danh |
| symbol, timeframe | |
| kind | `swing_high`, `bos_up`, `choch_down`, `fvg_bull`, `order_block`, `sweep_low`, `vpoc`, `naked_poc`… |
| event_time | nến mà sự kiện gắn vào |
| known_at | nến mà sự kiện được xác nhận |
| price_low, price_high | mức giá hoặc vùng giá |
| invalidated_at | khi vùng bị phá hoặc được lấp, nếu có |
| attrs | thuộc tính riêng theo loại |
| params_hash | |

Ví dụ: một swing high với độ dài 5 có `event_time` là nến tạo đỉnh, còn `known_at` là thời điểm đóng của nến thứ 5 sau đó. Tách hai dạng này ra là quyết định trung tâm của thiết kế: SMC, thanh khoản, Wyckoff và volume profile đều sinh ra sự kiện và vùng giá, không phải một con số mỗi nến.

## 6. Giao diện giữa các lớp

Bốn hợp đồng dưới đây là thứ cần giữ ổn định; phần bên trong đổi thoải mái.

```python
# exchanges/base.py — mọi sàn cài cùng giao diện
class Exchange(Protocol):
    def klines(self, symbol, timeframe, start, end) -> Iterator[DataFrame]: ...
    def funding(self, symbol, start, end) -> Iterator[DataFrame]: ...
    def open_interest(self, symbol, period, start, end) -> Iterator[DataFrame]: ...
    def stream(self, channels: list[Channel]) -> AsyncIterator[Message]: ...

# analysis — mọi module theo cùng một dạng
def compute(ohlcv: DataFrame, params: Params) -> Features | Events: ...

# strategy/base.py
class Strategy(Protocol):
    def signals(self, features: DataFrame, events: DataFrame) -> DataFrame:
        """Trả về: time, side, entry, stop, take_profit, size_hint, reason."""

# backtest/engine.py
def run(signals: DataFrame, ohlcv: DataFrame, costs: CostModel) -> Result: ...
```

Đây là phác thảo để thống nhất hình dạng, chưa phải code đã chạy.

## 7. Các mối quan tâm xuyên suốt

| Việc | Cách làm |
|---|---|
| Cấu hình | YAML trong `configs/`, đọc và kiểm tra bằng Pydantic; một file cho instrument, một file cho tham số từng module |
| Giới hạn tốc độ | một bộ điều tiết dùng chung trong `exchanges/ratelimit.py`; Binance đọc header, OKX tự đếm |
| Lỗi mạng | thử lại có giãn cách; gặp 429 thì ngủ theo `Retry-After`; không bao giờ thử lại ngay |
| Khoảng trống dữ liệu | `collector` ghi mọi lần mất kết nối vào `meta/gaps`; `pipeline` từ chối tính trên đoạn có khoảng trống chưa lấp |
| Tái lập | mỗi lần backtest lưu cấu hình, mã băm tham số, phiên bản code và manifest dữ liệu |
| Log | log có cấu trúc (JSON), riêng cho từng tiến trình |
| Kiểm thử | unit test cho `analysis` trên dữ liệu dựng tay; test đối chiếu cho `store` (resample khớp nến sàn); test tích hợp cho `exchanges` chạy riêng vì cần mạng |
| Bí mật | hiện không có API key nào; nếu sau này có thì nằm trong biến môi trường, không nằm trong repo |

## 8. Công nghệ

| Việc | Lựa chọn |
|---|---|
| Ngôn ngữ, môi trường | Python 3.12, `uv` |
| HTTP, WebSocket | `httpx`, `websockets`; `ccxt` làm đường dự phòng và để đối chiếu |
| Bảng dữ liệu | `polars`, `numpy` |
| Lưu trữ | Parquet, DuckDB |
| Indicator | TA-Lib |
| Lịch chạy | `APScheduler` trong `collector`; cron cho `pipeline` |
| Cấu hình | Pydantic, YAML |
| Dòng lệnh | `typer` |
| Metric | `quantstats` |
| Hiển thị | Plotly hoặc `lightweight-charts`, Streamlit |
| Chất lượng | `pytest`, `ruff` |

Tôi chọn viết bộ chuyển đổi sàn bằng `httpx` thay vì dùng hẳn `ccxt` vì cần các endpoint mà `ccxt` không bọc đầy đủ (nhóm `/futures/data/*`, file dump, luồng liquidation) và cần kiểm soát giới hạn tốc độ. Cái giá là phải tự theo dõi khi sàn đổi API.

## 9. Điểm mở rộng

- **Thêm sàn:** viết một file trong `exchanges/` theo giao diện chung.
- **Thêm indicator:** viết một module trong `analysis/` trả về Features hoặc Events, đăng ký vào `pipeline`.
- **On-chain:** là một nguồn mới ở L1 và một bảng mới ở curated.
- **LLM:** là lớp L6 chỉ đọc. Vì features, events và results đã là bảng có cấu trúc kèm `known_at`, lớp này gắn vào mà không phải sửa gì bên dưới.
- **Realtime:** `pipeline` chạy tăng dần trên nến vừa đóng thay vì cả lịch sử; các hàm `analysis` giữ nguyên.

## 10. Chỗ còn mở

1. Các mặc định ở file 07 mục 1 chưa được xác nhận.
2. `collector` chạy ở đâu quyết định có cần cơ chế đồng bộ `raw/` hay không.
3. File `metrics` của Binance chưa được mở; schema bảng `open_interest` và `long_short` có thể phải chỉnh theo.
4. Tính tăng dần cho module dựa trên swing (sự kiện có thể bị vô hiệu về sau) cần thiết kế kỹ hơn khi tới bước đó.
5. Dung lượng aggTrades chưa ước lượng; có thể cần chỉ giữ dạng đã gộp theo mức giá thay vì từng giao dịch.
