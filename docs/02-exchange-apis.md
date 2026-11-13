# 02 — Exchange APIs: Binance và OKX

> Ngày tra cứu: **2026-11-13**. Mọi con số dưới đây lấy từ tài liệu chính thức hiện hành hoặc từ lời gọi thật tới API công khai trong ngày này. API sàn thay đổi thường xuyên: trước khi code, mở lại URL nguồn ở từng mục.

## 0. Cách đọc tài liệu này

Ký hiệu độ tin cậy:

| Ký hiệu | Nghĩa |
|---|---|
| **[docs]** | Đọc trực tiếp từ tài liệu chính thức (URL ghi kèm). |
| **[live]** | Đã gọi thử endpoint công khai ngày 2026-11-13 và nhận kết quả đúng như mô tả. |
| **[chưa xác minh]** | Không mở được trang nguồn, trang bị cắt, hoặc chỉ suy ra. Không dựa vào khi chưa tự kiểm. |

Ba thay đổi lớn so với kiến thức cũ (dễ làm hỏng code viết theo trí nhớ):

1. **Binance Futures WebSocket đã tách base URL** thành `/public`, `/market`, `/private`. URL cũ `wss://fstream.binance.com/ws/...` chỉ còn nhận được dữ liệu nhóm public (depth, bookTicker); `markPrice`, `kline`, `aggTrade`, `forceOrder` phải đi qua `/market`. [docs]
2. **OKX đổi REST host sang `https://openapi.okx.com`** và bỏ `checksum` của order book (giá trị cố định 0), thay bằng `seqId`/`prevSeqId`. [docs]
3. **Binance gộp COIN-M vào hạ tầng USDⓈ-M** (hiệu lực dần từ 2026-06-24): `fapi` và `dapi` dùng chung một quỹ rate limit 2400 weight/phút/IP. [docs]

Trang tài liệu Binance cũng đã chuyển sang cấu trúc mới (`/en/docs/products/...` và `/en/docs/catalog/...`); các link kiểu cũ `/docs/derivatives/...` tự chuyển hướng. Bản toàn văn dạng text: <https://developers.binance.com/en/docs/llms-full.txt>, mục lục endpoint: <https://developers.binance.com/en/docs/llms.txt>.

---

## 1. Binance

### 1.1 Base URL và phiên bản

| Sản phẩm | REST mainnet | Tiền tố / phiên bản | WebSocket market data mainnet |
|---|---|---|---|
| Spot | `https://api.binance.com` (dự phòng: `api-gcp`, `api1`–`api4`) | `/api/v3` | `wss://stream.binance.com:9443` hoặc `:443` |
| Spot, chỉ market data công khai | `https://data-api.binance.vision` | `/api/v3` | `wss://data-stream.binance.vision` |
| USDⓈ-M Futures | `https://fapi.binance.com` | `/fapi/v1` (một số `/fapi/v2`, `/fapi/v3`), thống kê ở `/futures/data` | `wss://fstream.binance.com` + `/public`, `/market`, `/private` |
| COIN-M Futures | `https://dapi.binance.com` | `/dapi/v1`, thống kê ở `/futures/data` | `wss://dstream.binance.com` |

| Môi trường thử | REST | WebSocket |
|---|---|---|
| Spot Testnet | `https://testnet.binance.vision/api` (dự phòng `https://api1.testnet.binance.vision/api`) | `wss://stream.testnet.binance.vision` |
| Spot Demo Mode | `https://demo-api.binance.com/api` | `wss://demo-stream.binance.com` (`/ws`, `/stream`), WS API `wss://demo-ws-api.binance.com/ws-api/v3` |
| USDⓈ-M Futures testnet | `https://demo-fapi.binance.com` | `wss://demo-fstream.binance.com` |
| COIN-M Futures testnet | `https://demo-dapi.binance.com` | `wss://demo-dstream.binance.com` |

Nguồn [docs]:
- Spot REST: <https://developers.binance.com/en/docs/products/spot/rest-api>
- Spot testnet: <https://developers.binance.com/en/docs/products/spot/testnet/general-info>
- Spot demo mode: <https://developers.binance.com/en/docs/products/spot/demo-mode/general-info>
- USDⓈ-M: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>
- COIN-M: <https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/general-info>

Ghi chú:
- `api1`–`api4` "có thể nhanh hơn nhưng kém ổn định hơn". [docs]
- `data-api.binance.vision` chỉ phục vụ endpoint có security type `NONE` (klines, depth, aggTrades, ticker, exchangeInfo, ping, time...). Trả về header `X-MBX-USED-WEIGHT-1M` như host chính. [docs][live]
- Các host testnet/demo ở trên đều trả `{}` cho `ping`. [live]
- Timestamp: mili giây theo mặc định. Riêng Spot có thể xin micro giây bằng header `X-MBX-TIME-UNIT: MICROSECOND` (REST) hoặc tham số `timeUnit=MICROSECOND` (WebSocket). Futures chỉ có mili giây. [docs]
- Dữ liệu trả theo thứ tự **tăng dần** (cũ trước, mới sau). [docs]

### 1.2 Spot — endpoint dữ liệu thị trường công khai

Nguồn [docs]: <https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market> (bản cũ: <https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints>)

| Dữ liệu | Endpoint | Weight | Tham số chính | Giới hạn mỗi lần gọi |
|---|---|---|---|---|
| Klines | `GET /api/v3/klines` | 2 | `symbol`*, `interval`*, `startTime`, `endTime`, `timeZone` (mặc định `0` = UTC), `limit` | mặc định 500, tối đa **1000** |
| Klines cho biểu đồ | `GET /api/v3/uiKlines` | 2 | như trên | 500 / 1000 |
| Order book | `GET /api/v3/depth` | 5 (limit 1–100), 25 (101–500), 50 (501–1000), 250 (1001–5000) | `symbol`*, `limit` | mặc định 100, tối đa **5000** |
| Trades gần nhất | `GET /api/v3/trades` | 25 | `symbol`*, `limit` | 500 / 1000 |
| Trades cũ | `GET /api/v3/historicalTrades` | 25 | `symbol`*, `limit`, `fromId` | 500 / 1000 |
| Aggregate trades | `GET /api/v3/aggTrades` | 4 | `symbol`*, `fromId`, `startTime`, `endTime`, `limit` | 500 / 1000 |
| Ticker 24h | `GET /api/v3/ticker/24hr` | 2 (1 symbol) đến 80 (tất cả) | `symbol` hoặc `symbols`, `type` (`FULL`/`MINI`) | `symbols` tối đa 100 |
| Ticker cửa sổ trượt | `GET /api/v3/ticker` | 4 mỗi symbol, trần 200 | `symbol`/`symbols`, `windowSize` (mặc định `1d`) | `symbols` tối đa 100 |
| Ticker theo ngày giao dịch | `GET /api/v3/ticker/tradingDay` | 4 mỗi symbol, trần 200 | `symbol`/`symbols`, `timeZone` | tối đa 100 |
| Giá mới nhất | `GET /api/v3/ticker/price` | 2 (1 symbol) / 4 | `symbol`/`symbols` | — |
| Best bid/ask | `GET /api/v3/ticker/bookTicker` | 2 (1 symbol) / 4 | `symbol`/`symbols` | — |
| Giá trung bình | `GET /api/v3/avgPrice` | 2 | `symbol`* | — |

(* = bắt buộc)

**Interval của klines Spot** (phân biệt hoa thường): `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`. [docs]

**Phân trang để tải lịch sử dài:**
- Klines: đặt `startTime`, lấy tối đa 1000 nến, rồi gọi tiếp với `startTime = openTime của nến cuối + 1`. Không gửi `startTime`/`endTime` thì nhận các nến mới nhất. [docs][live]
- aggTrades: dùng `fromId` (bao gồm cả id đó) để đi tiếp từ `a` của bản ghi cuối + 1; hoặc dùng cửa sổ `startTime`/`endTime`. [docs]
- historicalTrades: dùng `fromId`. [docs]
- Lịch sử nhiều năm: dùng file dump ở mục 1.9 thay vì REST.

### 1.3 USDⓈ-M Futures — endpoint dữ liệu thị trường công khai

Nguồn [docs]: <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data> (bản cũ: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api>)

Base: `https://fapi.binance.com`.

| Dữ liệu | Endpoint | Weight | Tham số chính | Giới hạn / ghi chú |
|---|---|---|---|---|
| Klines | `GET /fapi/v1/klines` | theo `limit`: 1 (<100), 2 (100–499), 5 (500–1000), 10 (>1000) | `symbol`*, `interval`*, `startTime`, `endTime`, `limit` | mặc định 500, tối đa **1500** |
| Klines hợp đồng liên tục | `GET /fapi/v1/continuousKlines` | như klines | `pair`*, `contractType`* (`PERPETUAL`, `CURRENT_QUARTER`, `NEXT_QUARTER`, `TRADIFI_PERPETUAL`), `interval`* | 500 / 1500 |
| Index price klines | `GET /fapi/v1/indexPriceKlines` | như klines | `pair`*, `interval`* | 500 / 1500 |
| Mark price klines | `GET /fapi/v1/markPriceKlines` | như klines | `symbol`*, `interval`* | 500 / 1500 |
| Premium index klines | `GET /fapi/v1/premiumIndexKlines` | như klines | `symbol`*, `interval`* | 500 / 1500 |
| Order book | `GET /fapi/v1/depth` | 2 (limit 5/10/20/50), 5 (100), 10 (500), 20 (1000) | `symbol`*, `limit` ∈ {5, 10, 20, 50, 100, 500, 1000} | mặc định 500, tối đa **1000**; không gồm lệnh RPI |
| Trades gần nhất | `GET /fapi/v1/trades` | 5 | `symbol`*, `limit` | 500 / 1000 |
| Trades cũ (cần API key) | `GET /fapi/v1/historicalTrades` | 200 | `symbol`*, `limit`, `fromId`, header `X-MBX-APIKEY` | 100 / 500; chỉ dữ liệu 1 tháng gần nhất |
| Aggregate trades | `GET /fapi/v1/aggTrades` | 20 | `symbol`*, `fromId`, `startTime`, `endTime`, `limit` | 500 / 1000; **chỉ truy vấn được 48 giờ gần nhất**; nếu gửi cả `startTime` và `endTime` thì khoảng cách phải < 1 giờ |
| Mark price + funding hiện tại | `GET /fapi/v1/premiumIndex` | 1 (có symbol) / 10 (không) | `symbol` | trả `markPrice`, `indexPrice`, `lastFundingRate`, `nextFundingTime` [live] |
| Funding rate lịch sử | `GET /fapi/v1/fundingRate` | dùng chung giới hạn **500 request / 5 phút / IP** với `fundingInfo` | `symbol`, `startTime`, `endTime`, `limit` | mặc định 100, tối đa **1000**; không gửi thời gian thì trả 200 bản ghi mới nhất; thứ tự tăng dần |
| Thông tin funding (cap/floor, chu kỳ) | `GET /fapi/v1/fundingInfo` | 0 (dùng chung 500/5 phút/IP) | — | — |
| Open interest hiện tại | `GET /fapi/v1/openInterest` | 1 | `symbol`* | — |
| Open interest lịch sử | `GET /futures/data/openInterestHist` | 0; giới hạn riêng **1000 request / 5 phút / IP** | `symbol`*, `period`*, `limit`, `startTime`, `endTime` | 30 / **500**; **chỉ 1 tháng gần nhất**; kỳ không có giao dịch bị bỏ trống, không bù |
| Long/short ratio (toàn bộ tài khoản) | `GET /futures/data/globalLongShortAccountRatio` | 0; 1000 request / 5 phút / IP | `symbol`*, `period`*, `limit`, `startTime`, `endTime` | 30 / 500; chỉ 30 ngày gần nhất |
| Long/short ratio top trader (theo tài khoản) | `GET /futures/data/topLongShortAccountRatio` | [chưa xác minh] | giống trên [chưa xác minh] | [chưa xác minh] |
| Long/short ratio top trader (theo vị thế) | `GET /futures/data/topLongShortPositionRatio` | [chưa xác minh] | `symbol`, `period`, `limit` [live] | [chưa xác minh] |
| Taker buy/sell volume | `GET /futures/data/takerlongshortRatio` | [chưa xác minh] | `symbol`, `period`, `limit` [live] | trả `buySellRatio`, `buyVol`, `sellVol` [live] |
| Basis | `GET /futures/data/basis` | 0 | `pair`*, `contractType`*, `period`*, `limit` | 30 / 500; chỉ 30 ngày gần nhất |
| Ticker 24h | `GET /fapi/v1/ticker/24hr` | [chưa xác minh] | `symbol` [live] | — |
| Giá mới nhất | `GET /fapi/v1/ticker/price`, `GET /fapi/v2/ticker/price` | [chưa xác minh] | `symbol` | — |
| Best bid/ask | `GET /fapi/v1/ticker/bookTicker` | [chưa xác minh] | `symbol` | — |
| Thành phần index | `GET /fapi/v1/constituents` | 2 | `symbol`* | — |
| Thông tin sàn, filter, rate limit | `GET /fapi/v1/exchangeInfo` | 1 | — | — |

Lưu ý:
- **Interval klines Futures**: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1M`. Tám giá trị đầu đọc từ docs; phần còn lại bị ẩn trong trang docs nên được xác nhận bằng lời gọi thật (đều trả 200). `1s` trên `/fapi/v1/klines` trả 400; `2m` trả `-1120 Invalid interval`. [live] `continuousKlines` có thêm `1s` theo docs.
- **`period` của nhóm `/futures/data/*`**: `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d` (giá trị `1d` bị ẩn trong docs, đã gọi thử thành công). [docs][live]
- Gọi `limit=1500` cho klines tốn nhiều weight hơn bảng trên cho thấy: một lần gọi thử làm `X-MBX-USED-WEIGHT-1M` tăng lên 50 (gồm cả các lời gọi trước đó trong phút). Luôn đọc header thay vì tự cộng. [live]
- Các dòng **[chưa xác minh]**: trang docs bị cắt ở sau mục "RPI Order Book", nên weight và limit của nhóm endpoint cuối bảng chữ cái chưa đọc được. Tên endpoint có trong mục lục chính thức `llms.txt` và đã gọi thử thành công.
- Sau khi gộp COIN-M, docs ghi các endpoint klines của `fapi` "chấp nhận cả symbol UM và CM". [docs]
- **Liquidation**: mục lục REST hiện hành **không có** endpoint công khai trả liquidation toàn thị trường. `GET /fapi/v1/forceOrders` là `USER_DATA` (chỉ lệnh thanh lý của chính tài khoản). Dữ liệu liquidation công khai chỉ đến qua WebSocket `@forceOrder` (mục 1.5). [docs]

**Phân trang:** klines giống Spot (tịnh tiến `startTime`). `fundingRate`: khi dữ liệu trong khoảng nhiều hơn `limit`, sàn trả từ `startTime` trở đi, nên tịnh tiến `startTime = fundingTime cuối + 1`. Nhóm `/futures/data/*` chỉ giữ khoảng 30 ngày, vì vậy muốn có lịch sử dài phải **tự thu thập định kỳ** hoặc dùng file `metrics` ở mục 1.9.

### 1.4 COIN-M Futures — khác biệt chính

Nguồn [docs]: <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-coin-m-futures/api/rest-api/market-data>, thông báo gộp: <https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/Important-CM-UM-Integration-Notice>

Base: `https://dapi.binance.com`. Symbol dạng `BTCUSD_PERP` (perpetual), `BTCUSD_YYMMDD` (delivery); `pair` là `BTCUSD`.

| Dữ liệu | Endpoint | Weight | Giới hạn / ghi chú |
|---|---|---|---|
| Klines | `GET /dapi/v1/klines` (và `continuousKlines`, `indexPriceKlines`, `markPriceKlines`, `premiumIndexKlines`) | 1 / 2 / 5 / 10 theo `limit` | 500 / **1500**; khoảng `startTime`–`endTime` tối đa **200 ngày** |
| Order book | `GET /dapi/v1/depth` | 2 / 5 / 10 / 20 | 500 / 1000 |
| Trades | `GET /dapi/v1/trades` | 5 | 500 / 1000 |
| Aggregate trades | `GET /dapi/v1/aggTrades` | 20 | 500 / 1000; chỉ 48 giờ gần nhất; cửa sổ < 1 giờ |
| Mark + index price | `GET /dapi/v1/premiumIndex` | 10 | `symbol` hoặc `pair` |
| Funding rate lịch sử | `GET /dapi/v1/fundingRate` | 1 | `symbol`*; 100 / 1000 |
| Open interest | `GET /dapi/v1/openInterest` | 1 | `symbol`* |
| Open interest lịch sử | `GET /futures/data/openInterestHist` | 1 | `pair`*, `period`*, `contractType`; 30 / 500; chỉ 30 ngày |
| Long/short ratio | `GET /futures/data/globalLongShortAccountRatio` | 1 | `pair`*, `period`*; 30 / 500; chỉ 30 ngày |
| Taker buy/sell volume | `GET /futures/data/takerBuySellVol` | [chưa xác minh] | `pair`, `contractType`, `period` [live] |

Chú ý tên endpoint taker volume khác nhau: `takerlongshortRatio` (USDⓈ-M) và `takerBuySellVol` (COIN-M). [docs]

### 1.5 WebSocket market streams

#### Spot

Nguồn [docs]: <https://developers.binance.com/en/docs/products/spot/web-socket-streams>

- Raw stream: `wss://stream.binance.com:9443/ws/<streamName>`. Combined: `/stream?streams=<s1>/<s2>/<s3>`, payload được bọc thành `{"stream":"<streamName>","data":{...}}`.
- Tên symbol trong stream phải **viết thường**.
- Subscribe động:
  ```json
  {"method": "SUBSCRIBE", "params": ["btcusdt@aggTrade", "btcusdt@depth"], "id": 1}
  ```
  Dùng `UNSUBSCRIBE` với cùng cấu trúc để huỷ. `id` là số nguyên 64-bit, chuỗi chữ-số tối đa 36 ký tự, hoặc `null`. Phản hồi `"result": null` nghĩa là thành công.
- Kết nối chỉ sống **24 giờ**. Server gửi sự kiện `serverShutdown` trước khi tắt.
- **Ping/pong**: server gửi ping frame mỗi **20 giây**; không nhận pong trong **1 phút** thì ngắt. Pong phải chép lại payload của ping. Pong tự phát được phép nhưng không giữ được kết nối.
- **Giới hạn**: 5 message gửi lên mỗi giây (tính cả PING, PONG, lệnh JSON); tối đa **1024 stream** mỗi kết nối; **300 kết nối mỗi 5 phút mỗi IP**. Vượt giới hạn thì bị ngắt, tái phạm có thể bị ban IP.

| Stream | Tên | Tần suất |
|---|---|---|
| Aggregate trade | `<symbol>@aggTrade` | real-time |
| Trade | `<symbol>@trade` | real-time |
| Kline (UTC) | `<symbol>@kline_<interval>` | 1000 ms với `1s`, 2000 ms với interval khác |
| Kline lệch múi giờ | `<symbol>@kline_<interval>@+08:00` | như trên |
| Mini ticker | `<symbol>@miniTicker`, `!miniTicker@arr` | 1000 ms |
| Ticker 24h | `<symbol>@ticker` | 1000 ms |
| Ticker cửa sổ trượt | `<symbol>@ticker_<windowSize>` (`1h`, `4h`, `1d`), `!ticker_<windowSize>@arr` | 1000 ms |
| Best bid/ask | `<symbol>@bookTicker` | real-time |
| Giá trung bình | `<symbol>@avgPrice` | 1000 ms |
| Partial depth | `<symbol>@depth<levels>` hoặc `@100ms` (`levels` = 5, 10, 20) | 1000 ms hoặc 100 ms |
| Diff depth | `<symbol>@depth` hoặc `<symbol>@depth@100ms` | 1000 ms hoặc 100 ms |

**Dựng local order book — Spot** (đúng theo docs):

1. Mở kết nối tới `wss://stream.binance.com:9443/ws/bnbbtc@depth`.
2. Đệm (buffer) các event nhận được. Ghi lại `U` của event đầu tiên.
3. Lấy snapshot: `GET https://api.binance.com/api/v3/depth?symbol=BNBBTC&limit=5000`.
4. Nếu `lastUpdateId` của snapshot **nhỏ hơn hẳn** `U` ở bước 2, quay lại bước 3.
5. Trong buffer, bỏ mọi event có `u <= lastUpdateId`. Event đầu tiên còn lại phải có `lastUpdateId` nằm trong `[U; u]`.
6. Gán local book = snapshot, update ID = `lastUpdateId`.
7. Áp dụng lần lượt các event trong buffer rồi các event mới theo quy tắc:
   - `u` < update ID của local book: bỏ qua event.
   - `U` > update ID của local book + 1: đã mất event, **huỷ book và làm lại từ đầu**.
   - Bình thường `U` của event sau = `u` của event trước + 1.
   - Với mỗi mức giá trong `b` và `a`: số lượng là giá trị **tuyệt đối**; bằng 0 thì xoá mức giá; chưa có thì thêm.
   - Đặt update ID của book = `u`.

Snapshot tối đa 5000 mức mỗi bên, nên các mức nằm ngoài snapshot chỉ được biết khi chúng thay đổi.

#### USDⓈ-M Futures

Nguồn [docs]:
- Kết nối: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect>
- Thông báo tách URL: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice>
- Danh mục stream: <https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams>

Ba đường vào:

| Nhóm | Base | Stream thuộc nhóm |
|---|---|---|
| Public (tần suất cao) | `wss://fstream.binance.com/public` | `<symbol>@bookTicker`, `!bookTicker`, `<symbol>@depth<levels>`, `<symbol>@depth` |
| Market | `wss://fstream.binance.com/market` | `<symbol>@aggTrade`, `<symbol>@markPrice`, `!markPrice@arr`, `<symbol>@kline_<interval>`, `<pair>_<contractType>@continuousKline_<interval>`, `<symbol>@miniTicker`, `!miniTicker@arr`, `<symbol>@ticker`, `!ticker@arr`, `<symbol>@forceOrder`, `!forceOrder@arr`, `<symbol>@compositeIndex`, `!contractInfo`, `!assetIndex@arr` |
| Private | `wss://fstream.binance.com/private` | user data (`listenKey` + `events`) |

- Hai kiểu truy cập: `.../market/ws/<streamName>` và `.../market/stream?streams=<s1>/<s2>`.
- Ví dụ: `wss://fstream.binance.com/market/stream?streams=bnbusdt@aggTrade/btcusdt@markPrice`.
- Kết nối **không có** tiền tố `/public`, `/market`, `/private` chỉ nhận được dữ liệu nhóm Public. Docs ghi URL cũ (`/ws`, `/stream`) bị gỡ bỏ sau **2026-04-23**; hãy luôn dùng URL có tiền tố.
- Kết nối sống 24 giờ. Server gửi ping frame mỗi **3 phút**; không nhận pong trong **10 phút** thì ngắt. Pong tự phát được phép.
- Giới hạn: **10 message gửi lên mỗi giây**; tối đa **1024 stream** mỗi kết nối.
- Subscribe động giống Spot (`{"method":"SUBSCRIBE","params":[...],"id":...}`).

| Stream | Tần suất | Ghi chú |
|---|---|---|
| `<symbol>@aggTrade` | 100 ms | chỉ gộp market trade; không gồm insurance fund và ADL |
| `<symbol>@markPrice`, `<symbol>@markPrice@1s` | 3 s hoặc 1 s | mark price, index price, funding rate, next funding time |
| `<symbol>@kline_<interval>` | 250 ms | trường `x` cho biết nến đã đóng chưa |
| `<symbol>@forceOrder`, `!forceOrder@arr` | 1000 ms | **chỉ đẩy lệnh thanh lý mới nhất** trong mỗi cửa sổ 1000 ms, không phải toàn bộ |
| `<symbol>@ticker` / `!ticker@arr` | 2000 ms / 1000 ms | thống kê 24h trượt |
| `<symbol>@depth`, `<symbol>@depth<levels>` (5, 10, 20) | 250 ms mặc định, `@500ms`, `@100ms` | phần mô tả nêu 250 ms nhưng enum tham số chỉ liệt kê 100 ms và 500 ms — mâu thuẫn trong docs, cần tự kiểm |
| `<symbol>@bookTicker` | real-time | — |

**Dựng local order book — Futures** (khác Spot ở trường `pu`):

1. Mở stream `wss://fstream.binance.com/public/stream?streams=btcusdt@depth`.
2. Đệm các event. Cùng mức giá thì event đến sau ghi đè event trước.
3. Lấy snapshot: `GET https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000`.
4. Bỏ mọi event có `u` < `lastUpdateId` của snapshot.
5. Event đầu tiên được xử lý phải thoả `U <= lastUpdateId` **và** `u >= lastUpdateId`.
6. Từ đó, `pu` của mỗi event mới phải bằng `u` của event trước; nếu không, làm lại từ bước 3.
7. Số lượng trong event là giá trị **tuyệt đối** của mức giá.
8. Số lượng bằng 0 thì **xoá** mức giá.
9. Nhận event xoá một mức giá không có trong local book là bình thường.

Nguồn: <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly>

#### COIN-M Futures

Nguồn [docs]: <https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/websocket-market-streams/Connect>

Base `wss://dstream.binance.com`, truy cập `/ws/<streamName>` hoặc `/stream?streams=...`. Quy tắc 24 giờ, ping 3 phút / pong trong 10 phút, 10 message/giây, 1024 stream giống USDⓈ-M. Trang Connect của COIN-M chưa mô tả tiền tố `/public`, `/market`; việc COIN-M có tách URL giống USDⓈ-M hay không là **[chưa xác minh]**.

### 1.6 Rate limit

Nguồn [docs]: <https://developers.binance.com/en/docs/products/spot/rest-api> (mục Limits), <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info>

| Sản phẩm | REQUEST_WEIGHT | ORDERS | Khác |
|---|---|---|---|
| Spot | **6000 / phút / IP** | 100 / 10 giây; 200 000 / ngày (theo tài khoản) | RAW_REQUESTS 300 000 / 5 phút |
| USDⓈ-M + COIN-M (dùng chung) | **2400 / phút / IP** | 1200 / phút; 300 / 10 giây (theo tài khoản) | — |

Các con số trên đọc từ `rateLimits` của `GET /api/v3/exchangeInfo`, `/fapi/v1/exchangeInfo`, `/dapi/v1/exchangeInfo` [live]; đây là nguồn chuẩn, hãy đọc lại lúc khởi động chương trình vì Binance có thể đổi.

- Giới hạn weight tính theo **IP**, không theo API key. Giới hạn lệnh tính theo tài khoản.
- Header phản hồi: `X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)`, ví dụ `X-MBX-USED-WEIGHT-1M`; lệnh: `X-MBX-ORDER-COUNT-10S`, `X-MBX-ORDER-COUNT-1M`. Chữ cái: `S`, `M`, `H`, `D`.
- **HTTP 429**: vượt rate limit. Phải dừng gửi (back off).
- **HTTP 418**: IP bị tự động ban vì tiếp tục gửi sau khi nhận 429. Thời gian ban tăng dần **từ 2 phút đến 3 ngày**.
- Header `Retry-After` (giây) đi kèm 429 và 418: với 429 là thời gian chờ để tránh bị ban; với 418 là thời gian đến khi hết ban.
- **HTTP 403**: vi phạm WAF.
- Một số endpoint có giới hạn riêng ngoài weight: `fundingRate` + `fundingInfo` 500 request / 5 phút / IP; nhóm `/futures/data/*` 1000 request / 5 phút / IP.
- Docs khuyến nghị dùng WebSocket để lấy dữ liệu thay vì poll REST.

### 1.7 Mã lỗi thường gặp

Nguồn [docs]: <https://developers.binance.com/en/docs/products/spot/errors>, <https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/error-code>

Payload lỗi: `{"code": -1121, "msg": "Invalid symbol."}`.

| Mã | Tên | Ý nghĩa |
|---|---|---|
| `-1003` | `TOO_MANY_REQUESTS` | Dùng quá nhiều request weight |
| `-1007` | `TIMEOUT` | Hết thời gian chờ backend; trạng thái thực thi **không xác định** |
| `-1008` | `SERVER_BUSY` | Server quá tải (Futures: bị throttle; lệnh reduce-only được miễn) |
| `-1015` | `TOO_MANY_ORDERS` | Vượt giới hạn số lệnh |
| `-1021` | `INVALID_TIMESTAMP` | Timestamp nằm ngoài `recvWindow` hoặc sớm hơn server quá 1000 ms |
| `-1022` | `INVALID_SIGNATURE` | Chữ ký sai |
| `-1100` | `ILLEGAL_CHARS` | Ký tự không hợp lệ trong tham số |
| `-1120` | — | `Invalid interval.` [live] |
| `-1121` | `BAD_SYMBOL` | Symbol không hợp lệ |
| `-2014` | `BAD_API_KEY_FMT` | Sai định dạng API key |
| `-2015` | `REJECTED_MBX_KEY` | API key, IP hoặc quyền không hợp lệ cho thao tác |

HTTP 5XX và 503 kèm thông báo "Unknown error..." trên Futures nghĩa là trạng thái **không xác định**, không được coi là thất bại; phải kiểm tra lại qua user data stream hoặc truy vấn lệnh. [docs]

### 1.8 Xác thực, quyền API key, bảo mật

Nguồn [docs]: general-info ở mục 1.1; quản lý API key: <https://www.binance.com/en/support/faq/detail/360002502072>

- API key gửi qua header **`X-MBX-APIKEY`**. Key và secret phân biệt hoa thường.
- Security type: `NONE` (công khai), `MARKET_DATA` và `USER_STREAM` (chỉ cần API key), `TRADE` và `USER_DATA` (cần API key **và chữ ký** — gọi là `SIGNED`).
- Chữ ký `SIGNED`: thêm tham số `timestamp` (ms) và `signature`. `signature` = HMAC SHA256 với `secretKey` làm khoá, trên `totalParams` (query string nối với request body); đặt `signature` ở cuối. Không phân biệt hoa thường.
- `recvWindow`: mặc định 5000 ms; Spot tối đa 60000 ms. Server chấp nhận khi `timestamp < serverTime + 1000` và `serverTime - timestamp <= recvWindow`. Đồng bộ đồng hồ với `GET /api/v3/time` hoặc `GET /fapi/v1/time`.
- Loại key: HMAC (sàn sinh, có secret), **Ed25519** và RSA (tự sinh cặp khoá, nộp public key). Docs Spot khuyến nghị Ed25519.
- Quyền và ràng buộc theo trang hỗ trợ của Binance:
  - Key HMAC **không giới hạn IP chỉ có quyền đọc** (áp dụng từ 2023-01-30).
  - Quyền rút tiền yêu cầu giới hạn IP (IPv4).
  - Danh sách đầy đủ tên các quyền và số key tối đa: **[chưa xác minh]** (trang hỗ trợ không liệt kê hết).

Khuyến nghị cho dự án này:
- Nghiên cứu và thu thập dữ liệu: **không cần key**. Nếu cần key (ví dụ `historicalTrades`), tạo key **chỉ đọc**.
- Key giao dịch: bật IP whitelist, chỉ bật đúng quyền cần dùng, **không bật quyền rút tiền**.
- Thử nghiệm đặt lệnh trên testnet/demo trước, bằng key riêng của môi trường đó.
- Không commit key vào git; đọc từ biến môi trường hoặc trình quản lý secret.

Nhóm endpoint giao dịch và tài khoản (chỉ liệt kê, không hướng dẫn chi tiết):

| Nhóm | Spot | USDⓈ-M Futures |
|---|---|---|
| Đặt / huỷ / truy vấn lệnh | `/api/v3/order`, `/api/v3/openOrders`, `/api/v3/allOrders` | `/fapi/v1/order`, `/fapi/v1/batchOrders`, `/fapi/v1/allOrders`, `/fapi/v1/algoOrder` |
| Tài khoản, số dư, vị thế | `/api/v3/account`, `/api/v3/myTrades` | `/fapi/v3/account`, `/fapi/v3/balance`, `/fapi/v3/positionRisk`, `/fapi/v1/userTrades`, `/fapi/v1/income` |
| User data stream | qua WebSocket API (`userDataStream.*`) | `/fapi/v1/listenKey` |
| Ví, nạp rút | `/sapi/v1/capital/...` (ví dụ `/sapi/v1/capital/withdraw/apply`) | — |

Mục lục đầy đủ: <https://developers.binance.com/en/docs/llms.txt>.

### 1.9 Dữ liệu lịch sử tải hàng loạt — data.binance.vision

Nguồn [docs]: <https://github.com/binance/binance-public-data>, trình duyệt file: <https://data.binance.vision>

- Mẫu URL (ví dụ trong README): `https://data.binance.vision/data/spot/monthly/klines/ADABKRW/1h/ADABKRW-1h-2020-08.zip`.
- Mỗi file `.zip` có file `.CHECKSUM` cùng thư mục; kiểm bằng `shasum -a 256 -c <file>.zip.CHECKSUM` (macOS) hoặc `sha256sum -c` (Linux).
- File daily có vào **ngày hôm sau**; file monthly có vào **thứ Hai đầu tiên của tháng**.
- Interval klines: `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, `1mo` (dùng `1mo` thay cho `1M`).
- **Dữ liệu Spot từ 2025-01-01 dùng timestamp micro giây**; Futures vẫn mili giây. Phải xử lý khi nối chuỗi dữ liệu qua mốc này.
- File đã lưu có thể được cập nhật lại về sau.

Cột CSV:

| File | Cột |
|---|---|
| Klines Spot và USDⓈ-M | open time, open, high, low, close, volume, close time, quote asset volume, number of trades, taker buy base asset volume, taker buy quote asset volume, ignore |
| Klines COIN-M | open time, open, high, low, close, volume, close time, base asset volume, number of trades, taker buy volume, taker buy base asset volume, ignore |
| aggTrades Spot | agg tradeId, price, quantity, first tradeId, last tradeId, timestamp, was buyer maker, was best price match |
| aggTrades Futures | như Spot nhưng không có cột cuối |
| trades Spot | trade Id, price, qty, quoteQty, time, isBuyerMaker, isBestMatch |
| trades USDⓈ-M | trade Id, price, qty, quoteQty, time, isBuyerMaker |

Các đường dẫn đã kiểm bằng HTTP HEAD ngày 2026-11-13 (README không liệt kê hết nên đây là [live], không phải [docs]):

| Đường dẫn dưới `https://data.binance.vision/data/` | Kết quả |
|---|---|
| `spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` (+ `.CHECKSUM`) | 200 |
| `spot/daily/trades/BTCUSDT/BTCUSDT-trades-2026-11-10.zip` | 200 |
| `spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-10.zip` | 200 |
| `futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-11-10.zip` | 200 |
| `futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-2026-11-10.zip` | 200 |
| `futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-11-10.zip` | 200 |
| `futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-10.zip` | 200 |
| `futures/cm/daily/klines/BTCUSD_PERP/1m/BTCUSD_PERP-1m-2026-11-10.zip` | 200 |
| `futures/um/daily/bookTicker/...`, `futures/um/daily/liquidationSnapshot/...`, `futures/cm/monthly/fundingRate/...` | 404 cho ngày/tháng đã thử |

File `metrics` là nguồn để bù cho giới hạn 30 ngày của open interest và long/short ratio qua REST; nội dung cột của `metrics` và `bookDepth` là **[chưa xác minh]** (chưa tải file về đọc).

### 1.10 Hạn chế theo khu vực

- Tài liệu API của Binance **không nêu** danh sách khu vực bị hạn chế. Trang "List of Prohibited Countries" (<https://www.binance.com/en/legal/list-of-prohibited-countries>) tồn tại nhưng nội dung không đọc được bằng công cụ tự động: **[chưa xác minh]**.
- Từ máy phát triển của dự án (2026-11-13), `api.binance.com`, `fapi.binance.com`, `dapi.binance.com`, `data-api.binance.vision` đều trả 200. [live] Server đặt ở khu vực khác có thể bị chặn; kiểm tra bằng `GET /api/v3/ping` trước khi triển khai.

---

## 2. OKX

Nguồn [docs] cho toàn bộ mục này: <https://www.okx.com/docs-v5/en/> (một trang duy nhất; các link bên dưới là anchor). Bản tiếng Việt của trang giới thiệu: <https://www.okx.com/vi/okx-api>.

### 2.1 Base URL và phiên bản

Phiên bản API: **v5** (tiền tố `/api/v5`, WebSocket `/ws/v5`).

| Môi trường | REST | WebSocket public | WebSocket private | WebSocket business |
|---|---|---|---|---|
| Production | `https://openapi.okx.com` | `wss://ws.okx.com/ws/v5/public` | `wss://ws.okx.com/ws/v5/private` | `wss://ws.okx.com/ws/v5/business` |
| Demo trading | `https://openapi.okx.com` + header `x-simulated-trading: 1` | `wss://wspap.okx.com/ws/v5/public` | `wss://wspap.okx.com/ws/v5/private` | `wss://wspap.okx.com/ws/v5/business` |

Nguồn: <https://www.okx.com/docs-v5/en/#overview-production-trading-services>, <https://www.okx.com/docs-v5/en/#overview-demo-trading-services>

- Demo trading dùng **API key riêng** tạo trong mục Demo Trading; một số chức năng (nạp, rút...) không hỗ trợ.
- Host cũ `https://www.okx.com/api/v5/...` vẫn trả dữ liệu khi gọi thử [live], nhưng docs hiện chỉ liệt kê `openapi.okx.com`; dùng host mới.
- Docs thông báo cổng WebSocket **8443 sắp bị gỡ**; dùng cổng 443 (mặc định).
- Timestamp trong dữ liệu: Unix **mili giây**, dạng **chuỗi**. Mọi số (giá, khối lượng) cũng là chuỗi.
- Phản hồi REST luôn có dạng `{"code": "0", "msg": "", "data": [...]}`; `code` khác `"0"` là lỗi, kể cả khi HTTP status là 200.

### 2.2 Định danh instrument

Nguồn: <https://www.okx.com/docs-v5/en/#overview-general-info>

| Loại (`instType`) | Ví dụ `instId` |
|---|---|
| `SPOT` | `BTC-USDT` |
| `SWAP` (perpetual) USDT-margined | `BTC-USDT-SWAP` |
| `SWAP` coin-margined | `BTC-USD-SWAP` |
| `FUTURES` (có kỳ hạn) | `BTC-USDT-250808`, `BTC-USD-250808` |
| `OPTION` | theo `instFamily`, ví dụ họ `BTC-USD` |

`uly` là index (ví dụ `BTC-USD`); `instFamily` là họ instrument (ví dụ `BTC-USDT`). Danh sách instrument: `GET /api/v5/public/instruments?instType=SWAP` (20 request / 2 giây, theo IP + instType).

### 2.3 Endpoint dữ liệu thị trường công khai

Rate limit của mọi endpoint dưới đây tính theo **IP** (một số theo IP + instId), không cần API key.

| Dữ liệu | Endpoint | Rate limit | Tham số chính | Giới hạn / ghi chú |
|---|---|---|---|---|
| Candles gần đây | `GET /api/v5/market/candles` | 40 / 2 s | `instId`*, `bar`, `after`, `before`, `limit` | mặc định 100, tối đa **300**; chỉ lấy được **1440 nến mới nhất** |
| Candles lịch sử | `GET /api/v5/market/history-candles` | 20 / 2 s | như trên | 100 / **300** [docs]; dữ liệu "những năm gần đây"; nến `1s` chỉ 3 tháng |
| Mark price candles | `GET /api/v5/market/mark-price-candles`, `.../history-mark-price-candles` | 20 / 2 s | `instId`*, `bar`, `after`, `before`, `limit` | tối đa 100 |
| Index candles | `GET /api/v5/market/index-candles`, `.../history-index-candles` | 20 / 2 s, lịch sử 10 / 2 s | `instId`* (index, ví dụ `BTC-USD`) | tối đa 100 |
| Order book | `GET /api/v5/market/books` | 40 / 2 s | `instId`*, `sz` | `sz` tối đa **400** mỗi bên, mặc định 1; cập nhật mỗi 50 ms |
| Order book đầy đủ | `GET /api/v5/market/books-full` | 10 / 2 s | `instId`*, `sz` | `sz` tối đa **5000** mỗi bên; cập nhật mỗi 1 s |
| Trades gần nhất | `GET /api/v5/market/trades` | 100 / 2 s | `instId`*, `limit` | 100 / **500** |
| Trades lịch sử | `GET /api/v5/market/history-trades` | 20 / 2 s | `instId`*, `type` (1 = tradeId, 2 = timestamp), `after`, `before`, `limit` | tối đa và mặc định **100**; chỉ **3 tháng** gần nhất |
| Ticker một instrument | `GET /api/v5/market/ticker` | 20 / 2 s | `instId`* | — |
| Ticker cả loại | `GET /api/v5/market/tickers` | 20 / 2 s | `instType`*, `instFamily` | — |
| Funding rate hiện tại | `GET /api/v5/public/funding-rate` | 10 / 2 s (IP + instId) | `instId`* (hoặc `ANY`) | — |
| Funding rate lịch sử | `GET /api/v5/public/funding-rate-history` | 10 / 2 s (IP + instId) | `instId`*, `before`, `after`, `limit` | tối đa và mặc định **400**; chỉ **3 tháng** |
| Open interest hiện tại | `GET /api/v5/public/open-interest` | 20 / 2 s | `instType`*, `instFamily`, `instId` | trả `oi`, `oiCcy`, `oiUsd` [live] |
| Open interest lịch sử | `GET /api/v5/rubik/stat/contracts/open-interest-history` | 10 / 2 s | `instId`*, `period`, `begin`, `end`, `limit` | tối đa **100**; 1440 bản ghi mới nhất |
| Long/short ratio theo hợp đồng | `GET /api/v5/rubik/stat/contracts/long-short-account-ratio-contract` | 5 / 2 s | `instId`*, `period`, `begin`, `end`, `limit` | tối đa 100; 1440 bản ghi mới nhất |
| Long/short ratio top trader (tài khoản / vị thế) | `GET /api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader`, `.../long-short-position-ratio-contract-top-trader` | 5 / 2 s | như trên | top 5% trader theo giá trị vị thế |
| Long/short ratio theo đồng coin | `GET /api/v5/rubik/stat/contracts/long-short-account-ratio` | 5 / 2 s | `ccy`*, `begin`, `end`, `period` (`5m`, `1H`, `1D`) | `5m` tối đa 2 ngày, `1H` 30 ngày, `1D` 180 ngày |
| Taker volume theo hợp đồng | `GET /api/v5/rubik/stat/taker-volume-contract` | 5 / 2 s | `instId`*, `period`, `unit` (0 coin, 1 hợp đồng, 2 USD), `begin`, `end`, `limit` | 1440 bản ghi mới nhất |
| Taker volume theo đồng coin | `GET /api/v5/rubik/stat/taker-volume` | 5 / 2 s | `ccy`*, `instType`* (`SPOT`/`CONTRACTS`), `period` | giới hạn thời gian như long/short theo coin |
| Open interest + volume theo coin | `GET /api/v5/rubik/stat/contracts/open-interest-volume` | 5 / 2 s | `ccy`*, `period` | — |
| Mark price | `GET /api/v5/public/mark-price` | 10 / 2 s (IP + instId) | `instType`*, `instFamily`, `instId` | — |
| Index ticker | `GET /api/v5/market/index-tickers` | 20 / 2 s | `instId` hoặc `quoteCcy` | — |
| Premium lịch sử | `GET /api/v5/public/premium-history` | 20 / 2 s | `instId`*, `after`, `before`, `limit` | tối đa 100; 6 tháng |
| Thời gian server | `GET /api/v5/public/time` | 10 / 2 s | — | — |

Anchor nguồn: `#order-book-trading-market-data` (candles, books, trades, ticker), `#public-data-rest-api` (funding, open interest, mark price), `#trading-statistics-rest-api` (nhóm `rubik`). Ví dụ: <https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks-history>, <https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate-history>, <https://www.okx.com/docs-v5/en/#trading-statistics-rest-api-get-contract-open-interest-history>.

**Giá trị `bar` của candles:** `1m`, `3m`, `5m`, `15m`, `30m`, `1H`, `2H`, `4H`; mở nến theo UTC+8: `6H`, `12H`, `1D`, `2D`, `3D`, `1W`, `1M`, `3M`; mở nến theo UTC+0: `6Hutc`, `12Hutc`, `1Dutc`, `2Dutc`, `3Dutc`, `1Wutc`, `1Mutc`, `3Mutc`. `history-candles` có thêm `1s`. Mặc định `1m`. Chữ `H`, `D`, `W`, `M` viết **hoa**.

> Bẫy: `1D` của OKX mở nến lúc 00:00 **UTC+8**, không khớp với nến `1d` của Binance (UTC). Muốn khớp phải dùng `1Dutc`.

**Giá trị `period` của nhóm `rubik` theo hợp đồng:** `5m`, `15m`, `30m`, `1H`, `2H`, `4H`, cộng `6H`…`3M` và biến thể `utc` như trên, thêm `5D`/`5Dutc`. Mặc định `5m`.

**Cấu trúc một nến:** `[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]`. `vol` tính bằng số hợp đồng với phái sinh, bằng đồng base với Spot. `confirm` = `"0"` là nến chưa đóng, `"1"` là đã đóng. [docs][live]

**Phân trang (ngược với Binance):**
- Dữ liệu trả theo thứ tự **mới trước, cũ sau**.
- `after=<ts>`: lấy bản ghi **cũ hơn** `ts`. `before=<ts>`: lấy bản ghi **mới hơn** `ts`.
- Tải lịch sử: bắt đầu từ thời điểm kết thúc, đặt `after` = `ts` của bản ghi cũ nhất trong trang vừa nhận, lặp đến khi trang rỗng hoặc vượt mốc bắt đầu.
- Gửi `limit` lớn hơn tối đa không báo lỗi mà chỉ trả số bản ghi tối đa (thử `limit=301` trên `history-candles`). [live]

**Liquidation:** tài liệu hiện hành **không còn mục REST** cho liquidation orders; chỉ có WebSocket channel `liquidation-orders`. Gọi thử `GET /api/v5/public/liquidation-orders?instType=SWAP&instFamily=BTC-USDT&state=filled` vẫn trả dữ liệu [live], nhưng vì không còn trong docs nên coi là **[chưa xác minh]** và không nên phụ thuộc.

### 2.4 WebSocket

Nguồn: <https://www.okx.com/docs-v5/en/#overview-websocket>

- **Chọn đúng URL theo channel**: channel public ở `/ws/v5/public`; **candlesticks và all-trades ở `/ws/v5/business`**; channel riêng tư ở `/ws/v5/private` (cần login).
- Subscribe:
  ```json
  {"id": "1512", "op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
  ```
  Huỷ bằng `"op": "unsubscribe"`. `id` tuỳ chọn, tối đa 32 ký tự chữ-số. Tổng độ dài các channel trong một request không quá 64 KB.
- **Ping/pong**: kết nối tự ngắt nếu không có subscription hoặc không có dữ liệu đẩy trong hơn **30 giây**. Cách giữ: đặt timer N giây (N < 30) mỗi khi nhận message; hết timer thì gửi **chuỗi văn bản `ping`** và chờ nhận chuỗi `pong`; không nhận được thì reconnect. Đây là text message, không phải ping frame của giao thức.
- **Giới hạn**:
  - Kết nối mới: **3 request / giây** theo IP.
  - `subscribe` / `unsubscribe` / `login`: tổng **480 lần / giờ** mỗi kết nối.
  - Channel riêng tư (orders, account, positions...): tối đa **30 kết nối mỗi channel mỗi sub-account**.
  - Giới hạn tổng số kết nối public mỗi IP: **[chưa xác minh]** (docs không nêu).
- Thông báo `{"event": "notice", "code": "64008", ...}` được gửi 60 giây trước khi server ngắt để nâng cấp; nên mở kết nối mới ngay.

| Dữ liệu | Channel | URL | Tần suất |
|---|---|---|---|
| Ticker | `tickers` | public | nhanh nhất 1 lần / 100 ms |
| Candles | `candle<bar>` ví dụ `candle1m`, `candle1H` | **business** | nhanh nhất 1 lần / giây |
| Trades (có gộp) | `trades` | public | mỗi khi có khớp; một message có thể gộp nhiều trade (trường `count`) |
| Trades từng lệnh | `trades-all` | **business** | mỗi message một trade |
| Order book | `books`, `books5`, `bbo-tbt`, `books50-l2-tbt`, `books-l2-tbt` | public | xem dưới |
| Funding rate | `funding-rate` | public | 30–90 giây |
| Open interest | `open-interest` | public | mỗi 3 giây khi có thay đổi |
| Mark price | `mark-price` | public | 200 ms khi đổi, 10 giây khi không đổi |
| Index ticker | `index-tickers` | public | 100 ms khi đổi, nếu không thì 1 phút |
| Mark price / index candles | `mark-price-candle<bar>`, `index-candle<bar>` | **business** | nhanh nhất 1 lần / giây |
| Liquidation | `liquidation-orders` (tham số `instType`: `SWAP`, `FUTURES`, `MARGIN`, `OPTION`) | public | docs ghi rõ dữ liệu này **không đại diện cho toàn bộ** liquidation trên OKX |

**Các channel order book:**

| Channel | Độ sâu | Kiểu | Tần suất | Điều kiện |
|---|---|---|---|---|
| `books` | 400 mức | snapshot đầu + incremental | 100 ms | — |
| `books5` | 5 mức | snapshot mỗi lần | 100 ms | — |
| `bbo-tbt` | 1 mức | snapshot mỗi lần | 10 ms | — |
| `books50-l2-tbt` | 50 mức | snapshot đầu + incremental | 10 ms | chỉ **VIP4 trở lên**; nếu không nhận lỗi `64003` |
| `books-l2-tbt` | 400 mức | snapshot đầu + incremental | 10 ms | chỉ **VIP4 trở lên**; nếu không nhận lỗi `64003` |

Không thể đồng thời subscribe `books-l2-tbt` và `books50-l2-tbt`/`books` cho cùng một symbol.

**Dựng local order book — OKX** (nguồn: <https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-order-book-channel>):

1. Subscribe `books` (hoặc channel incremental khác). Message đầu tiên có `action: "snapshot"` và `prevSeqId = -1`: dùng nó làm book ban đầu. **Không cần gọi REST** lấy snapshot như Binance.
2. Các message sau có `action: "update"`. Kiểm tra `prevSeqId` của message mới **bằng** `seqId` của message trước. Nếu không khớp: đã mất dữ liệu, huỷ book và subscribe lại.
3. Mỗi phần tử trong `asks`/`bids` là `[giá, số lượng, (trường cũ luôn "0"), số lệnh]`; phần tử thứ ba theo docs là "một phần của tính năng đã bỏ, luôn bằng 0". [docs] Số lượng là giá trị tuyệt đối của mức giá; quy tắc **số lượng "0" thì xoá mức giá** chưa đọc lại được nguyên văn trong docs: **[chưa xác minh]**, kiểm tra với dữ liệu thật khi cài đặt.
4. Trường hợp đặc biệt theo docs:
   - Khoảng 60 giây không có thay đổi: channel incremental gửi message `asks: []`, `bids: []` với `prevSeqId == seqId` (heartbeat, không phải lỗi).
   - Sau bảo trì, sequence có thể bị reset: nhận một message có `seqId` **nhỏ hơn** `prevSeqId`; các message sau trở lại quy tắc thường. Ví dụ của docs: snapshot (−1 → 10), update (10 → 15), không đổi (15 → 15), reset (15 → 3), update (3 → 5).
5. **`checksum` đã bị loại bỏ**: trường vẫn còn trong message của `books`, `books-l2-tbt`, `books50-l2-tbt` nhưng luôn bằng 0; docs yêu cầu dùng `seqId`/`prevSeqId` để kiểm tra tính liên tục. Code cũ kiểm CRC32 phải được gỡ.

### 2.5 Rate limit và mã lỗi

Nguồn: <https://www.okx.com/docs-v5/en/#overview-rate-limits>, <https://www.okx.com/docs-v5/en/#error-code>

- OKX **không dùng weight**. Mỗi endpoint có giới hạn riêng dạng "N request / 2 giây" ghi ngay trong mô tả endpoint.
- REST công khai: tính theo **IP**. REST riêng tư: theo **User ID** (mỗi sub-account có User ID riêng). WebSocket login/subscribe: theo kết nối.
- Bị giới hạn thì nhận mã lỗi **`50011`**. Không có header thông báo lượng đã dùng (kiểm tra header phản hồi không thấy trường rate limit nào [live]); client phải tự đếm.
- Lệnh giao dịch: giới hạn tính theo instrument ID; REST và WebSocket dùng chung; thêm trần **1000 yêu cầu lệnh / 2 giây** mỗi sub-account (lỗi `50061`).
- Hình phạt ban IP kiểu 418 của Binance: docs OKX không mô tả — **[chưa xác minh]**.

| Mã | HTTP | Ý nghĩa |
|---|---|---|
| `0` | 200 | Thành công |
| `50001` | 503 | Dịch vụ tạm thời không khả dụng |
| `50004` | 400 | Endpoint timeout (không cho biết yêu cầu thành công hay thất bại) |
| `50011` | 200 | Chạm rate limit |
| `50013` | 429 | Hệ thống bận, thử lại sau |
| `50014` | 200 | Thiếu tham số bắt buộc |
| `50026` | 500 | Lỗi hệ thống |
| `50061` | 200 | Vượt giới hạn tần suất lệnh của tài khoản |
| `50101` | 401 | API key không khớp môi trường (live / demo) |
| `50102` | 401 | Timestamp hết hạn (lệch quá 30 giây) |
| `50103` | 401 | Thiếu header `OK-ACCESS-KEY` |
| `50104`, `50105` | 401 | Thiếu / sai `OK-ACCESS-PASSPHRASE` |
| `50110` | 401 | IP không nằm trong whitelist của API key |
| `50111` | 401 | `OK-ACCESS-KEY` không hợp lệ |
| `50113` | 401 | Chữ ký không hợp lệ |
| `51000` | 200 | Sai tham số |
| `51001` | 200 | Instrument ID không tồn tại |
| `60012` | WS | Request không hợp lệ |
| `60014` | WS | Gửi request quá thường xuyên |
| `60018` | WS | Sai URL hoặc channel không tồn tại (ví dụ subscribe `candle1m` trên `/public`) |
| `64003` | WS | Bậc phí không đủ để dùng channel |
| `64008` | WS | Kết nối sắp đóng để nâng cấp |

Lưu ý `50011` và `51000` đi kèm **HTTP 200**: phải kiểm tra `code` trong body, không chỉ HTTP status.

### 2.6 Xác thực, quyền API key, bảo mật

Nguồn: <https://www.okx.com/docs-v5/en/#overview-api-key-creation>, <https://www.okx.com/docs-v5/en/#overview-rest-authentication>

Tạo API key nhận ba thứ: **API key**, **Secret key**, **Passphrase** (tự đặt; OKX chỉ lưu hash có salt, mất thì phải tạo key mới).

Header bắt buộc cho request riêng tư:

| Header | Nội dung |
|---|---|
| `OK-ACCESS-KEY` | API key |
| `OK-ACCESS-SIGN` | Chữ ký, Base64 |
| `OK-ACCESS-TIMESTAMP` | ISO 8601 UTC có mili giây, ví dụ `2020-12-08T09:08:57.715Z` |
| `OK-ACCESS-PASSPHRASE` | Passphrase |
| `x-simulated-trading: 1` | chỉ khi dùng demo trading |

Chữ ký: `Base64( HMAC_SHA256( secretKey, timestamp + METHOD + requestPath + body ) )`.
- `METHOD` viết hoa (`GET`, `POST`).
- `requestPath` gồm cả query string với `GET` (ví dụ `/api/v5/account/balance?ccy=BTC`).
- `body` là chuỗi JSON của request, bỏ trống nếu không có.
- Server từ chối khi timestamp lệch quá **30 giây** (lỗi `50102`). Dùng UTC; đồng bộ bằng `GET /api/v5/public/time`.
- Body request phải là `application/json`.

Quyền của API key: **Read** (xem tài khoản, lịch sử), **Trade** (đặt/huỷ lệnh, chuyển tiền nội bộ, thay đổi cài đặt), **Withdraw** (rút tiền).

Bảo mật theo docs:
- Mỗi key gắn được tối đa **20 địa chỉ IP** (IPv4, IPv6, dải mạng).
- Key có quyền `trade` hoặc `withdraw` mà **không gắn IP sẽ hết hạn sau 14 ngày không hoạt động** (key demo không hết hạn).

Khuyến nghị cho dự án: như mục 1.8 — không cần key cho dữ liệu công khai; key chỉ **Read** khi cần đọc tài khoản; key **Trade** phải gắn IP; **không bật Withdraw**; thử trên demo trading trước.

Nhóm endpoint giao dịch và tài khoản (chỉ liệt kê):

| Nhóm | Tiền tố | Ví dụ |
|---|---|---|
| Lệnh | `/api/v5/trade/` | `POST /api/v5/trade/order`, `GET /api/v5/trade/fills` |
| Trading account | `/api/v5/account/` | `GET /api/v5/account/balance`, `GET /api/v5/account/positions` |
| Funding account (nạp, rút, chuyển) | `/api/v5/asset/` | `GET /api/v5/asset/balances`, `POST /api/v5/asset/withdrawal` |
| WebSocket riêng tư | `/ws/v5/private` | channel `account`, `positions`, `orders` |

### 2.7 Dữ liệu lịch sử tải hàng loạt

- Trang tải: <https://www.okx.com/historical-data>. Theo trang này: trade history (từ 2021-09), candlestick (từ 2023-07), funding rate (từ 2022-03), order book L2 (từ 2023-03), borrowing rate (từ 2021-12). Định dạng file và mẫu URL tải: **[chưa xác minh]** (trang chỉ có nút Download).
- Endpoint trả link file: `GET /api/v5/public/market-data-history` (5 request / 2 giây, theo IP). [docs] <https://www.okx.com/docs-v5/en/#public-data-rest-api-get-historical-market-data>
  - `module`*: `1` trade từng tick, `2` nến 1 phút, `3` funding rate, `4` order book 400 mức, `5` order book 5000 mức (từ 2025-11-01), `6` order book 50 mức (sẽ bị loại bỏ dần), `11` borrowing rate.
  - `instType`*: `SPOT`, `FUTURES`, `SWAP`, `OPTION`.
  - `instIdList` (cho SPOT) hoặc `instFamilyList` (cho loại khác): tối đa 10 mục, hoặc `ANY` với một số module.
  - `dateAggrType`*: `daily` hoặc `monthly`.
  - `begin`*, `end`*: Unix ms; khoảng tối đa 10 ngày với `daily`, 10 tháng với `monthly`.
  - Docs ghi việc bổ sung dữ liệu lịch sử vẫn đang tiếp diễn, độ phủ khác nhau theo module và instrument.
  - Gọi thử `module=3&instType=SWAP&instFamilyList=BTC-USDT&dateAggrType=monthly` trả danh sách file kèm `filename`, `sizeMB`, `url`, ví dụ `BTC-USDT-SWAP-fundingrates-2026-10.zip` trên host `static.okx.com`. [live] Nội dung và cột bên trong file zip: **[chưa xác minh]**.

### 2.8 Hạn chế theo khu vực

Nguồn [docs]: <https://www.okx.com/docs-v5/en/#overview>

- Docs có mục "Regional API Domain Requirement": tài khoản đăng ký ở **Mỹ và Úc** (qua `app.okx.com`) phải dùng domain API **`us.okx.com`**; tài khoản **EU** (qua `my.okx.com`) dùng **`eea.okx.com`**. Docs nói `openapi.okx.com` sẽ không hoạt động cho các khu vực này, và mỗi khu vực có bộ tài liệu API riêng.
- Tiếp tục sử dụng API đồng nghĩa chấp nhận "OKX API Agreement".
- Danh sách quốc gia bị hạn chế dịch vụ: nằm trong "Risk and Compliance Disclosure" của OKX, chưa đọc được: **[chưa xác minh]**.

---

## 3. Thư viện Python

| Thư viện | Cài đặt | Tính chất | Ghi chú |
|---|---|---|---|
| `ccxt` | `pip install ccxt` | bên thứ ba, API thống nhất nhiều sàn | bản đã chạy thử: **4.5.92**; id sàn: `binance`, `binanceusdm`, `binancecoinm`, `okx` |
| `binance-connector-python` | `pip install binance-sdk-spot`, `pip install binance-sdk-derivatives-trading-usds-futures` | SDK của Binance, tách thành nhiều gói theo sản phẩm | yêu cầu **Python 3.11+**; gói hợp nhất cũ có hướng dẫn chuyển đổi `MIGRATION.md` |
| `python-binance` | `pip install python-binance` | **không chính thức** | README hiển thị v1.0.37; có `AsyncClient`, cờ `testnet=True`, `demo=True` |
| `python-okx` | `pip install python-okx` | SDK do OKX giới thiệu trong docs | Python ≥ 3.7; module `okx.MarketData`, `okx.PublicData`, `okx.TradingData`; `flag="0"` là live, `"1"` là demo |

Nguồn: <https://github.com/ccxt/ccxt>, <https://github.com/binance/binance-connector-python>, <https://github.com/sammchardy/python-binance>, <https://github.com/okxapi/python-okx>.

- Tài liệu của `ccxt` không đọc được đầy đủ (trang quá dài); hành vi mô tả ở mục 4.3 dựa trên **chạy thật** bản 4.5.92.
- Phiên bản mới nhất của `python-okx`, `python-binance`, và việc các thư viện này đã cập nhật theo thay đổi URL năm 2026 (Binance `/market`, OKX `openapi.okx.com`) hay chưa: **[chưa xác minh]**. Kiểm tra URL thư viện thực sự gọi trước khi tin dùng.

---

## 4. Ví dụ Python

Cả bốn ví dụ đã chạy thành công ngày 2026-11-13 với Python 3.14, `requests` 2.34.2, `ccxt` 4.5.92, `websockets` 17.4. Cài đặt: `pip install requests ccxt websockets`.

### 4.1 Binance klines qua REST thuần

```python
import time
import requests

SPOT = "https://data-api.binance.vision"   # chỉ market data công khai; hoặc https://api.binance.com
FUT = "https://fapi.binance.com"


def binance_klines(symbol, interval, start_ms, end_ms, futures=False):
    """Tải klines [start_ms, end_ms) bằng cách tịnh tiến startTime."""
    url = f"{FUT}/fapi/v1/klines" if futures else f"{SPOT}/api/v3/klines"
    limit = 1500 if futures else 1000
    out = []
    while start_ms < end_ms:
        r = requests.get(url, params={"symbol": symbol, "interval": interval,
                                      "startTime": start_ms, "endTime": end_ms - 1,
                                      "limit": limit}, timeout=10)
        if r.status_code in (418, 429):          # bị rate limit: bắt buộc back off
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out += rows
        start_ms = rows[-1][0] + 1               # open time của nến cuối + 1 ms
        print("used weight 1m:", r.headers.get("X-MBX-USED-WEIGHT-1M"))
    return out


if __name__ == "__main__":
    now = int(time.time() * 1000)
    k = binance_klines("BTCUSDT", "1m", now - 36 * 3600 * 1000, now)
    print(len(k), k[0][:6])                      # [openTime, open, high, low, close, volume]
    k = binance_klines("BTCUSDT", "1h", now - 48 * 3600 * 1000, now, futures=True)
    print(len(k), k[-1][:6])
```

Kết quả chạy thử: 2160 nến 1 phút Spot qua 3 trang, 48 nến 1 giờ Futures. Nến cuối cùng có thể **chưa đóng**; lọc theo `closeTime < now` nếu chỉ muốn nến hoàn chỉnh.

### 4.2 OKX candles qua REST thuần

```python
import time
import requests

OKX = "https://openapi.okx.com"


def okx_candles(inst_id, bar, start_ms, end_ms):
    """Tải nến [start_ms, end_ms) — OKX trả MỚI -> CŨ, lùi dần bằng `after`."""
    out, after = [], end_ms
    while after > start_ms:
        r = requests.get(f"{OKX}/api/v5/market/history-candles",
                         params={"instId": inst_id, "bar": bar,
                                 "after": after, "limit": 300}, timeout=10)
        if r.status_code == 429:
            time.sleep(2)
            continue
        r.raise_for_status()
        body = r.json()
        if body["code"] != "0":                  # lỗi nằm trong body, vd 50011 = rate limit
            raise RuntimeError(f'{body["code"]}: {body["msg"]}')
        rows = body["data"]
        if not rows:
            break
        out += [x for x in rows if int(x[0]) >= start_ms]
        after = int(rows[-1][0])                 # ts của nến cũ nhất trong trang
        time.sleep(0.11)                         # 20 req / 2 s theo IP
    return out[::-1]                             # đảo lại thành CŨ -> MỚI


if __name__ == "__main__":
    now = int(time.time() * 1000)
    c = okx_candles("BTC-USDT-SWAP", "1m", now - 12 * 3600 * 1000, now)
    print(len(c), c[0])   # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
```

Kết quả chạy thử: 720 nến. Mọi giá trị là **chuỗi**; ép kiểu trước khi tính toán. Trường cuối `confirm == "0"` là nến chưa đóng.

### 4.3 Cả hai sàn qua ccxt

```python
import ccxt

binance = ccxt.binance({"enableRateLimit": True})
okx = ccxt.okx({"enableRateLimit": True})

since = binance.parse8601("2026-11-01T00:00:00Z")
for ex, symbol in [(binance, "BTC/USDT"),          # spot
                   (binance, "BTC/USDT:USDT"),     # USDⓈ-M perpetual
                   (okx, "BTC/USDT"),
                   (okx, "BTC/USDT:USDT")]:        # = BTC-USDT-SWAP
    rows, cursor = [], since
    while len(rows) < 2000:
        page = ex.fetch_ohlcv(symbol, "1h", since=cursor, limit=1000)
        if not page:
            break
        rows += page
        cursor = page[-1][0] + 1
    print(ex.id, symbol, ex.market(symbol)["id"], len(rows), rows[0])
    # mỗi dòng: [timestamp_ms, open, high, low, close, volume]
```

Kết quả chạy thử: `BTC/USDT` → `BTCUSDT` / `BTC-USDT`; `BTC/USDT:USDT` → `BTCUSDT` (futures) / `BTC-USDT-SWAP`. ccxt trả dữ liệu **cũ → mới** với kiểu `float` cho cả hai sàn và tự xử lý phân trang ngược của OKX.

### 4.4 WebSocket

```python
import asyncio
import json
import websockets


async def binance_futures(n=3):
    # markPrice và aggTrade thuộc nhóm /market; depth, bookTicker thuộc nhóm /public
    url = "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade/btcusdt@markPrice@1s"
    async with websockets.connect(url) as ws:     # thư viện tự trả pong cho ping frame
        for _ in range(n):
            msg = json.loads(await ws.recv())
            print("binance", msg["stream"], msg["data"]["E"])


async def okx_public(n=3):
    async with websockets.connect("wss://ws.okx.com/ws/v5/public", ping_interval=None) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [
            {"channel": "trades", "instId": "BTC-USDT-SWAP"},
            {"channel": "funding-rate", "instId": "BTC-USDT-SWAP"}]}))
        got = 0
        while got < n:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send("ping")             # OKX: chuỗi 'ping' -> nhận 'pong'
                continue
            if raw == "pong":
                continue
            msg = json.loads(raw)
            if "data" in msg:
                got += 1
                print("okx", msg["arg"]["channel"], msg["data"][0].get("ts"))


async def main():
    await asyncio.gather(binance_futures(), okx_public())

asyncio.run(main())
```

Ghi chú khi chạy:
- Trên macOS với Python cài từ python.org, kết nối `wss://` có thể báo `CERTIFICATE_VERIFY_FAILED`. Cách xử lý đã dùng khi thử: đặt biến môi trường `SSL_CERT_FILE` trỏ tới file của gói `certifi` (`python -c "import certifi; print(certifi.where())"`), hoặc chạy `Install Certificates.command` đi kèm bộ cài Python.
- Trong lúc thử, `requests` thỉnh thoảng gặp `ConnectionError` thoáng qua tới host Binance; chạy lại thì thành công. Code production cần retry có backoff.
- Code production cần thêm: tự reconnect (Binance ngắt sau 24 giờ; OKX ngắt khi nâng cấp), subscribe lại sau reconnect, và phát hiện mất dữ liệu.

---

## 5. Bảng so sánh Binance và OKX

| Tiêu chí | Binance | OKX |
|---|---|---|
| Phiên bản | Spot `/api/v3`; USDⓈ-M `/fapi/v1`; COIN-M `/dapi/v1` | `/api/v5` cho mọi sản phẩm |
| REST host | tách theo sản phẩm: `api`, `fapi`, `dapi` | một host: `openapi.okx.com` |
| Symbol Spot | `BTCUSDT` | `BTC-USDT` |
| Symbol perpetual USDT | `BTCUSDT` (trên `fapi`) | `BTC-USDT-SWAP` |
| Symbol perpetual coin-margined | `BTCUSD_PERP` (trên `dapi`) | `BTC-USD-SWAP` |
| Symbol ccxt | `BTC/USDT`, `BTC/USDT:USDT` | `BTC/USDT`, `BTC/USDT:USDT` |
| Symbol trong WebSocket | viết thường trong tên stream: `btcusdt@aggTrade` | giữ nguyên `instId` trong `args` |
| Interval nến | `1m`, `1h`, `1d`, `1w`, `1M` (chữ thường trừ tháng) | `1m`, `1H`, `1D`, `1W`, `1M` (giờ trở lên viết hoa) |
| Mốc mở nến ngày | UTC (Spot đổi được bằng `timeZone`) | `1D` = UTC+8; `1Dutc` = UTC |
| Limit klines mỗi lần gọi | Spot 1000; Futures 1500 | `candles` 300; `history-candles` 300 |
| Thứ tự dữ liệu | cũ → mới | mới → cũ |
| Phân trang | `startTime` / `endTime` / `fromId` | `after` (cũ hơn) / `before` (mới hơn) |
| Kiểu timestamp | số nguyên ms (Spot tuỳ chọn µs) | chuỗi ms |
| Kiểu giá / khối lượng | chuỗi trong mảng klines | chuỗi |
| Trạng thái nến đóng | suy từ `closeTime`; WebSocket có `k.x` | trường `confirm` (`"0"` / `"1"`) |
| Order book REST tối đa | Spot 5000; Futures 1000 | `books` 400; `books-full` 5000 |
| Local order book | diff stream + REST snapshot; `U`/`u` (Spot), thêm `pu` (Futures) | snapshot đến qua WebSocket; `seqId`/`prevSeqId`; checksum đã bỏ |
| Funding rate lịch sử | `limit` tối đa 1000 | `limit` tối đa 400; chỉ 3 tháng |
| Open interest lịch sử | `/futures/data/openInterestHist`, tối đa 500, chỉ 1 tháng | `rubik/.../open-interest-history`, tối đa 100, 1440 bản ghi mới nhất |
| Liquidation công khai | chỉ WebSocket `@forceOrder` (1 lệnh mới nhất / 1000 ms) | chỉ WebSocket `liquidation-orders` (không đầy đủ) |
| Rate limit | theo weight: Spot 6000/phút, Futures 2400/phút, theo IP | theo từng endpoint, "N request / 2 giây", theo IP |
| Đọc lượng đã dùng | header `X-MBX-USED-WEIGHT-1M` | không có header; tự đếm |
| Khi vượt | HTTP 429 → 418 (ban 2 phút đến 3 ngày), header `Retry-After` | mã `50011` (HTTP 200) hoặc HTTP 429 |
| Báo lỗi | HTTP 4XX + `{"code": -1121, "msg": ...}` | `{"code": "5xxxx", "msg": ...}`, nhiều lỗi vẫn HTTP 200 |
| Xác thực | header `X-MBX-APIKEY` + `signature` (HMAC SHA256 hex, hoặc Ed25519/RSA) trong query | 4 header `OK-ACCESS-*`; chữ ký HMAC SHA256 Base64; có **passphrase** |
| Timestamp xác thực | Unix ms, `recvWindow` mặc định 5000 ms | ISO 8601 UTC, lệch tối đa 30 giây |
| WebSocket ping | server gửi ping frame (Spot 20 s; Futures 3 phút), client trả pong | client gửi chuỗi `ping` trong vòng 30 giây im lặng |
| Thời gian sống kết nối | 24 giờ | không nêu giới hạn cố định; ngắt khi nâng cấp (báo trước 60 giây) |
| Môi trường thử | testnet/demo trên host riêng | cùng REST host + header `x-simulated-trading: 1`; WebSocket `wspap.okx.com` |
| Dump lịch sử | `data.binance.vision` (file zip theo ngày/tháng, có checksum) | trang historical-data + `GET /api/v5/public/market-data-history` |

---

## 6. Danh sách điều chưa xác minh

1. Weight và limit của `topLongShortAccountRatio`, `topLongShortPositionRatio`, `takerlongshortRatio`, `ticker/24hr`, `ticker/price`, `ticker/bookTicker` trên USDⓈ-M, và `takerBuySellVol` trên COIN-M (trang docs bị cắt; endpoint có trong mục lục và gọi được).
2. Danh sách interval đầy đủ của klines Futures trong docs (bị ẩn; đã kiểm bằng lời gọi thật).
3. Tần suất mặc định của depth stream Futures (docs tự mâu thuẫn giữa 250 ms và enum 100/500 ms).
4. COIN-M WebSocket có tách `/public`, `/market` như USDⓈ-M hay không.
5. Danh sách quốc gia/khu vực bị hạn chế của cả Binance và OKX.
6. Danh sách đầy đủ quyền API key của Binance và số key tối đa.
7. REST `GET /api/v5/public/liquidation-orders` của OKX: còn hoạt động nhưng không còn trong docs.
8. Quy tắc "số lượng 0 thì xoá mức giá" trong order book WebSocket của OKX (chưa đọc lại nguyên văn).
9. Giới hạn tổng số kết nối WebSocket public của OKX; hình phạt ban IP của OKX.
10. Định dạng và cột của file tải từ OKX historical data / `market-data-history`.
11. Mẫu đường dẫn Futures trên `data.binance.vision` (kiểm bằng HTTP HEAD, không có trong README); nội dung cột của `metrics` và `bookDepth`; vì sao `bookTicker`, `liquidationSnapshot`, `cm/fundingRate` trả 404.
12. Tài liệu `ccxt` (chỉ xác nhận bằng chạy thật bản 4.5.92); phiên bản mới nhất và mức độ cập nhật URL mới của `python-okx`, `python-binance`.
13. Các sản phẩm ngoài phạm vi chưa tra: Binance Options, Portfolio Margin, Spot WebSocket API, SBE/FIX; OKX Options, spread trading, block trading.
