# 04 — Phương pháp phân tích: từ chart sang code

> Tài liệu nền cho dự án quant (Python). Mục tiêu: biến các phương pháp đang dùng trên chart thành quy tắc lập trình được, kèm đánh giá trung thực về bằng chứng.
> Cập nhật: 2026-11-13.

## 0. Cách đọc tài liệu này

**Phạm vi.** Tài liệu mô tả phương pháp và cách đo. Không có khuyến nghị mua/bán; mọi ngưỡng số trong giả mã là tham số khởi điểm để kiểm định, không phải giá trị đã được chứng minh.

**Mức độ xác minh.** Nguồn được đối chiếu bằng web search trong một phiên làm việc, chủ yếu qua trích đoạn (snippet) chứ không đọc toàn văn. Ba nhãn dùng xuyên suốt:

| Nhãn | Nghĩa |
|---|---|
| (đã đối chiếu) | Khớp với trích đoạn từ nguồn có URL kèm theo, tra trong phiên này |
| (theo trí nhớ) | Kiến thức phổ biến hoặc bài báo quen thuộc, không tra lại trong phiên này; cần mở nguồn gốc trước khi dựa vào |
| **chưa xác minh** | Đã tìm nhưng không xác nhận được, hoặc nguồn chỉ là blog/bên bán sản phẩm |

**Ánh xạ bốn chart của chủ dự án sang các mục:**

| Chart | Mục liên quan |
|---|---|
| (1) Volume profile tuần: VPOC, value area, vùng mỏng, delta | §1, §2 |
| (2) BTC tháng, "vùng thanh khoản" dưới đáy cũ | §6, §3.4 |
| (3) Wyckoff accumulation + Elliott 1-5 / A-B-C | §4, §5 |
| (4) XAUUSD – FEDFUNDS – BTCUSDT | §8 |

**Bốn bẫy chung, áp dụng cho mọi mục:**

1. **Lookahead.** Swing, zigzag, POC của tuần đang chạy, nhãn Wyckoff/Elliott đều chỉ "chốt" sau khi có thêm dữ liệu. Mọi feature phải gắn timestamp *thời điểm biết được*, không phải thời điểm xảy ra.
2. **Data snooping.** Thử nhiều tham số rồi chọn cái đẹp nhất sẽ luôn ra kết quả đẹp. Cần out-of-sample, walk-forward, và hiệu chỉnh số lần thử (Sullivan–Timmermann–White 1999; deflated Sharpe ratio của Bailey & López de Prado — theo trí nhớ).
3. **Chi phí.** Phí, spread, slippage, funding. Nhiều kết quả kỹ thuật biến mất sau chi phí.
4. **Mẫu nhỏ.** Chart tuần/tháng của BTC chỉ có vài trăm nến; số chu kỳ độc lập còn ít hơn nhiều.

Bối cảnh học thuật chung: tổng quan của Park & Irwin (2007) ghi nhận đa số nghiên cứu về phân tích kỹ thuật có vấn đề về quy trình kiểm định (data snooping, chọn quy tắc sau khi biết kết quả, ước lượng rủi ro và chi phí) (đã đối chiếu: https://econpapers.repec.org/RePEc:bla:jecsur:v:21:y:2007:i:4:p:786-826). Lo, Mamaysky & Wang (2000) cho thấy một số mẫu hình có nội dung thông tin thống kê nhưng không kết luận là có lợi nhuận vượt trội (đã đối chiếu qua nguồn thứ cấp: https://www.cxoadvisory.com/technical-trading/classic-papers-returns-from-pattern-based-technical-analysis/).

---

## 1. Volume Profile và Market Profile (TPO)

### 1.1 Khái niệm

- **Volume Profile**: histogram khối lượng theo *mức giá* (không theo thời gian) trong một khoảng thời gian chọn trước.
- **Market Profile / TPO** (Time Price Opportunity): histogram theo *thời gian* giá có mặt ở mỗi mức; mỗi khối thời gian (thường 30 phút) đánh một chữ cái vào các mức giá đã chạm. Do J. Peter Steidlmayer phát triển tại CBOT thập niên 1980 (đã đối chiếu qua nguồn thứ cấp: https://www.luxalgo.com/library/concept/tpo-profile/).
- **POC / VPOC**: mức giá (bin) có volume lớn nhất. Với TPO là mức có nhiều TPO nhất.
- **Value Area (VA), VAH, VAL**: dải giá liền kề quanh POC chứa 70% tổng volume (hoặc TPO). 70% là quy ước xấp xỉ một độ lệch chuẩn của phân phối chuẩn (68,2%), không phải tham số ước lượng từ dữ liệu; profile thực tế hiếm khi chuẩn (đã đối chiếu: https://therighttrader.com/learn/volume-and-order-flow/value-area).
- **HVN / LVN**: đỉnh và đáy cục bộ của histogram. "Vùng volume mỏng" trên chart (1) chính là LVN.
- **Naked / virgin POC**: POC của một kỳ đã đóng mà giá các kỳ sau chưa quay lại chạm.
- **Initial Balance**: biên độ giờ giao dịch đầu tiên của phiên (TPO cổ điển). Với crypto 24/7 phải tự quy ước "phiên" (ví dụ 00:00 UTC).

### 1.2 Các loại profile theo phạm vi

| Loại | Phạm vi | Ghi chú lập trình |
|---|---|---|
| Session | Một phiên/ngày | Crypto: cắt theo UTC; cổ phiếu: theo giờ sàn |
| Weekly / Monthly | Tuần ISO / tháng lịch | Chart (1) dùng loại này; `resample("W-MON")` hoặc nhóm theo `isocalendar()` |
| Visible range | Khoảng đang hiển thị | Thuần UI, không có nghĩa trong backtest; thay bằng rolling window N nến |
| Fixed range | Từ t1 đến t2 chọn tay | Tham số hóa t1, t2 |
| Anchored | Từ một mốc đến hiện tại | Mốc phải xác định được tại thời điểm đó (xem bẫy lookahead) |

### 1.3 Thuật toán

**Từ trade/aggTrades (chính xác):** cộng `qty` theo bin giá.

```python
import numpy as np
import pandas as pd

def profile_from_trades(price: np.ndarray, qty: np.ndarray, bin_size: float) -> pd.Series:
    """Trả về Series: index = cạnh dưới của bin, value = volume."""
    b = np.floor(price / bin_size).astype(np.int64)
    s = pd.Series(qty).groupby(b).sum()
    full = np.arange(s.index.min(), s.index.max() + 1)
    s = s.reindex(full, fill_value=0.0)
    s.index = full * bin_size
    return s
```

**Từ OHLCV (xấp xỉ):** không biết volume nằm ở đâu trong nến, nên phải giả định. Cách phổ biến là rải đều volume từ low đến high. Sai số giảm khi dùng nến nhỏ hơn: muốn profile tuần thì dựng từ nến 1 phút hoặc 5 phút, không dựng từ nến ngày.

```python
def profile_from_ohlcv(df: pd.DataFrame, bin_size: float) -> pd.Series:
    lo = np.floor(df["low"].to_numpy() / bin_size).astype(np.int64)
    hi = np.floor(df["high"].to_numpy() / bin_size).astype(np.int64)
    base = lo.min()
    out = np.zeros(hi.max() - base + 1)
    for l, h, v in zip(lo - base, hi - base, df["volume"].to_numpy()):
        out[l:h + 1] += v / (h - l + 1)          # rải đều
    return pd.Series(out, index=(np.arange(len(out)) + base) * bin_size)
```

Biến thể: rải theo tam giác quanh typical price, hoặc dồn toàn bộ vào close. Mỗi giả định cho POC khác nhau; cần ghi rõ giả định trong metadata.

**POC và Value Area.** Quy trình chung (đã đối chiếu: https://www.tradingview.com/wiki/Volume_Profile): tính tổng volume, nhân tỷ lệ (mặc định 70%) ra volume mục tiêu, bắt đầu từ POC và mở rộng đến khi đạt mục tiêu; hàng cao nhất là VAH, thấp nhất là VAL. Bước mở rộng có nhiều biến thể: so sánh tổng *hai hàng* phía trên với hai hàng phía dưới rồi lấy bên lớn hơn (kiểu CBOT cổ điển), hoặc từng hàng một, hoặc luân phiên. Biến thể mà công cụ built-in của TradingView dùng: **chưa xác minh** (mã nguồn đóng).

```python
def value_area(profile: pd.Series, pct: float = 0.70, step: int = 2):
    v = profile.to_numpy()
    n = len(v)
    # POC: nếu hoà, lấy bin gần giữa dải nhất
    cands = np.flatnonzero(v == v.max())
    poc = int(cands[np.abs(cands - (n - 1) / 2).argmin()])
    lo = hi = poc
    acc, target = v[poc], pct * v.sum()
    while acc < target and (lo > 0 or hi < n - 1):
        up = v[hi + 1: hi + 1 + step].sum() if hi < n - 1 else -1.0
        dn = v[max(lo - step, 0): lo].sum() if lo > 0 else -1.0
        if up >= dn:
            hi = min(hi + step, n - 1); acc += up
        else:
            lo = max(lo - step, 0); acc += dn
    bin_size = profile.index[1] - profile.index[0] if n > 1 else 0.0
    return {"poc": profile.index[poc] + bin_size / 2,
            "vah": profile.index[hi] + bin_size,
            "val": profile.index[lo]}
```

**HVN/LVN:** làm mượt profile rồi tìm cực trị có prominence đủ lớn.

```python
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

def nodes(profile: pd.Series, sigma_bins: float = 2.0, prom_frac: float = 0.10):
    sm = gaussian_filter1d(profile.to_numpy(), sigma_bins)
    prom = prom_frac * sm.max()
    hvn, _ = find_peaks(sm, prominence=prom)
    lvn, _ = find_peaks(-sm, prominence=prom)
    return profile.index[hvn], profile.index[lvn]
```

**Naked POC:** với mỗi kỳ đã đóng `k`, POC là naked tại thời điểm `t` nếu không có nến nào trong `(đóng kỳ k, t]` thỏa `low <= POC <= high`. Lưu thêm `touched_at` để backtest không nhìn trước.

### 1.4 Chọn bin size

Không có giá trị "đúng". Các lựa chọn hợp lý:

- Bội số của tick size, cố định theo tài sản (dễ so sánh giữa các kỳ).
- Tỷ lệ theo giá: `bin = price * 0.0005` hoặc bin trên log-price (cần cho chuỗi dài như BTC, vì 100 USD ở 2017 và 2026 không cùng nghĩa).
- Theo biến động: `bin = k * ATR` của khung nền.
- Số hàng cố định (24–100 hàng mỗi profile) như đa số nền tảng chart.

Bin quá nhỏ làm profile răng cưa, POC nhảy lung tung; quá lớn thì mất LVN. Nên kiểm tra độ nhạy: POC/VAH/VAL có ổn định khi đổi bin ±50% hay không.

### 1.5 Dữ liệu cần

- Tốt nhất: aggTrades/tick. Binance công bố file lịch sử tại https://github.com/binance/binance-public-data/ (data.binance.vision).
- Tối thiểu: nến 1 phút.
- Cổ phiếu: volume phân mảnh qua nhiều sàn và dark pool; profile từ một nguồn không đại diện toàn thị trường.

### 1.6 Bẫy thường gặp

- Profile của tuần **đang chạy** thay đổi liên tục; POC "developing" khác POC chốt tuần.
- Crypto: volume mỗi sàn khác nhau, có wash trading ở một số sàn; spot và perp cho profile khác nhau. Phải cố định nguồn.
- Profile từ OHLCV khung lớn chỉ là ước lượng thô; đừng so trực tiếp với hình trên TradingView.
- Split/điều chỉnh giá cổ phiếu làm lệch profile dài hạn.

### 1.7 Bằng chứng thực nghiệm

Yếu. Ý tưởng "giá quay lại vùng volume cao" và "đi nhanh qua vùng volume mỏng" hợp lý về vi cấu trúc (nơi từng có nhiều giao dịch là nơi nhiều người có vị thế), nhưng không tìm thấy nghiên cứu bình duyệt nào kiểm định POC/VA/naked POC như tín hiệu có lợi thế sau chi phí: **chưa xác minh**. Xem đây là *feature mô tả cấu trúc*, cần tự kiểm định.

---

## 2. Order flow

### 2.1 Khái niệm

- **Aggressor / taker side**: bên gửi lệnh khớp ngay (market hoặc marketable limit). Taker buy khớp vào ask; taker sell khớp vào bid.
- **Delta** = volume taker buy − volume taker sell trong một nến/bin. "Số delta" trên chart (1) là delta cộng dồn theo profile tuần.
- **CVD** (cumulative volume delta) = tổng cộng dồn của delta.
- **Footprint**: ma trận (nến × mức giá) chứa volume bid/ask tại từng mức.
- **Imbalance**: tại một mức giá, volume một phía áp đảo phía kia theo một tỷ lệ ngưỡng.
- **Absorption**: taker đánh mạnh một phía nhưng giá không đi; suy ra có lệnh limit thụ động hấp thụ.
- **Order book heatmap**: ảnh chụp độ sâu sổ lệnh theo thời gian (giá × thời gian × khối lượng chờ).

### 2.2 Suy ra từ aggTrades của Binance

Trường `m` trong aggTrades là boolean "buyer là maker". `m = true` nghĩa là người mua đặt lệnh chờ, nên **taker là bên bán**; `m = false` là taker mua (đã đối chiếu: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List và https://dev.binance.vision/t/green-or-red-data/15736). Trường `M` của spot là cờ khác, không liên quan.

```python
def add_delta(trades: pd.DataFrame) -> pd.DataFrame:
    """trades: cột ts (datetime, UTC), price, qty, is_buyer_maker (bool)."""
    t = trades.copy()
    t["signed"] = np.where(t["is_buyer_maker"], -t["qty"], t["qty"])
    return t

def bars_with_delta(t: pd.DataFrame, rule: str = "1min") -> pd.DataFrame:
    g = t.set_index("ts").resample(rule)
    out = g["price"].ohlc()
    out["volume"] = g["qty"].sum()
    out["delta"] = g["signed"].sum()
    out["cvd"] = out["delta"].cumsum()
    return out

def footprint(t: pd.DataFrame, rule: str, bin_size: float) -> pd.DataFrame:
    t = t.assign(bar=t["ts"].dt.floor(rule),
                 px=np.floor(t["price"] / bin_size) * bin_size,
                 side=np.where(t["is_buyer_maker"], "bid", "ask"))  # bid = taker bán khớp vào bid
    return t.pivot_table(index=["bar", "px"], columns="side",
                         values="qty", aggfunc="sum", fill_value=0.0)
```

**Không có aggTrades?** Kline của Binance có sẵn cột "taker buy base asset volume", nên `delta = 2 * taker_buy_base − volume` (theo trí nhớ về cấu trúc kline; kiểm tra lại tại tài liệu API). Với dữ liệu chỉ có OHLCV thuần (cổ phiếu), phải ước lượng: tick rule, Lee–Ready (1991), hoặc bulk volume classification của Easley, López de Prado & O'Hara (theo trí nhớ). Các ước lượng này có sai số đáng kể.

**Imbalance chéo (diagonal)** theo quy ước footprint: so volume ask tại mức `p` với volume bid tại mức `p − tick`.

```python
def diagonal_imbalance(fp_bar: pd.DataFrame, ratio: float = 3.0, min_vol: float = 0.0):
    """fp_bar: footprint của MỘT nến, index = px tăng dần, cột bid/ask."""
    ask = fp_bar["ask"].to_numpy()[1:]
    bid = fp_bar["bid"].to_numpy()[:-1]
    buy_imb = (ask >= ratio * np.maximum(bid, 1e-12)) & (ask > min_vol)
    sell_imb = (bid >= ratio * np.maximum(ask, 1e-12)) & (bid > min_vol)
    return buy_imb, sell_imb     # 3 mức liên tiếp cùng phía = "stacked imbalance"
```

Ngưỡng 3.0 (300%) là quy ước của các nền tảng footprint, không có cơ sở thống kê: **chưa xác minh**.

**Absorption (heuristic):** delta lớn bất thường nhưng giá không dịch chuyển tương ứng.

```python
def absorption_score(bars: pd.DataFrame, win: int = 200) -> pd.Series:
    z_delta = (bars["delta"] - bars["delta"].rolling(win).mean()) / bars["delta"].rolling(win).std()
    ret = bars["close"].diff()
    z_ret = ret / ret.rolling(win).std()
    # delta dương mạnh mà giá không tăng (hoặc ngược lại) -> điểm cao
    return z_delta.abs() - (np.sign(z_delta) * z_ret).clip(lower=0)
```

**CVD divergence:** giá tạo đỉnh cao hơn trong khi CVD tạo đỉnh thấp hơn (xét trên các swing của §6.2, không so từng nến).

**Order book heatmap:** cần ghi lại stream độ sâu (diff depth + snapshot) theo thời gian thực; Binance không cung cấp lịch sử sổ lệnh đầy đủ miễn phí, phải tự thu hoặc mua (ví dụ Tardis: https://docs.tardis.dev/historical-data-details/binance-futures). Lưu dưới dạng mảng `(time, price_bin) -> resting qty`.

### 2.3 Bẫy thường gặp

- **CVD không so sánh được giữa các sàn và giữa spot với perp**; mức tuyệt đối phụ thuộc điểm bắt đầu cộng dồn. Chỉ dùng thay đổi hoặc độ dốc.
- Delta đo *ai trả spread*, không đo ai "thông minh" hơn. Tổ chức lớn thường dùng lệnh limit, nên xuất hiện ở phía thụ động.
- aggTrades gộp các fill cùng giá, cùng phía của một lệnh taker; số lượng "trade" không phải số lệnh.
- Sổ lệnh có spoofing: lệnh lớn trên heatmap có thể bị rút trước khi giá tới.
- Giờ máy và độ trễ: khi ghép trade với sổ lệnh phải dùng timestamp của sàn.

### 2.4 Bằng chứng thực nghiệm

Tương đối tốt ở **khung rất ngắn**, yếu ở khung dài. Order flow imbalance giải thích phần lớn biến động giá đồng thời trong vài giây đến vài phút (Cont, Kukanov & Stoikov 2014, "The price impact of order book events" — theo trí nhớ). Quan hệ *đồng thời* không có nghĩa là *dự báo được*; khả năng dự báo suy giảm rất nhanh và nằm trong vùng cạnh tranh của HFT. Việc dùng delta/CVD tuần như trên chart (1) để suy luận hướng đi nhiều tuần: **chưa xác minh**, không tìm thấy bằng chứng.

---

## 3. Dữ liệu phái sinh crypto

### 3.1 Funding rate

Khoản thanh toán định kỳ giữa long và short của perpetual để neo giá perp về giá spot. Funding dương: long trả short.

Công thức Binance (đã đối chiếu, thông báo hiệu lực 2025-09-18: https://www.binance.com/en-AE/support/announcement/detail/c00588a7e8504b3eb28d02a2da00530b):

```
F = [ P_avg + clamp(I − P_avg, −0.05%, +0.05%) ] / (8 / N)
```

với `P_avg` là premium index trung bình, `I` = 0,01% mỗi 8 giờ (một số hợp đồng là 0%), `N` là chu kỳ funding tính bằng giờ. Hệ quả: khi premium trung bình nằm trong khoảng −0,04% đến +0,06%, funding ra đúng 0,01%, nên funding "đứng yên ở 0,01%" là trạng thái mặc định chứ không phải tín hiệu (đã đối chiếu qua nguồn thứ cấp: https://coincub.com/blog/perpetual-futures-funding-rates-78-of-a-quarter-at-0-01/). Mỗi sàn có công thức và chu kỳ riêng; không gộp thô giữa các sàn.

Feature gợi ý: funding annualized = `F * (24/N) * 365`; z-score rolling; funding cộng dồn 7/30 ngày; chênh lệch funding giữa các sàn.

### 3.2 Open interest (OI)

Tổng số hợp đồng đang mở. Mỗi hợp đồng luôn có một long và một short, nên **OI không có hướng**.

- Endpoint lịch sử `GET /futures/data/openInterestHist` chỉ giữ dữ liệu khoảng 30 ngày gần nhất (đã đối chiếu cho COIN-M: https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/Open-Interest-Statistics; trang USDⓈ-M: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics — giới hạn 30 ngày ở USDⓈ-M **chưa xác minh** trực tiếp). Hệ quả thiết kế: phải có job thu thập định kỳ từ ngày đầu, nếu không sẽ mất lịch sử.
- Lịch sử dài hơn có thể có trong bộ file "metrics" của data.binance.vision: **chưa xác minh**.
- Phân biệt OI tính bằng coin và bằng USD: OI theo USD tăng khi giá tăng dù số hợp đồng không đổi.

### 3.3 Long/short ratio

Binance có nhiều chuỗi khác nhau, dễ nhầm (đã đối chiếu: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio và https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio):

- **Global account ratio**: tỷ lệ số *tài khoản* net long so với net short.
- **Top trader account ratio**: như trên nhưng chỉ nhóm 20% tài khoản có margin lớn nhất, mỗi tài khoản đếm một lần.
- **Top trader position ratio**: theo khối lượng vị thế của nhóm top.
- **Taker buy/sell volume ratio**: thực chất là order flow (§2), không phải vị thế. Tên endpoint chính xác: **chưa xác minh**.

Tỷ lệ theo tài khoản phản ánh số đông tài khoản nhỏ; không mâu thuẫn với việc tổng long bằng tổng short.

### 3.4 Liquidation và liquidation heatmap

- **Liquidation thực tế**: stream `<symbol>@forceOrder` và `!forceOrder@arr`. Stream chỉ đẩy *lệnh thanh lý mới nhất trong mỗi cửa sổ 1000 ms* cho mỗi symbol, nên **dữ liệu bị thiếu** trong các đợt thanh lý dồn dập, đúng lúc cần nhất (đã đối chiếu cho COIN-M: https://developers.binance.com/docs/derivatives/coin-margined-futures/websocket-market-streams/Liquidation-Order-Streams; USDⓈ-M mô tả là "snapshot stream": https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams). Tổng thanh lý tính từ stream này là cận dưới.
- **Liquidation heatmap** (Coinglass và tương tự): **là mô hình, không phải dữ liệu vị thế thật**. Sàn không công bố giá thanh lý từng tài khoản; nhà cung cấp ước lượng từ OI, volume và giả định phân bố đòn bẩy, rồi chiếu ra mức thanh lý cho từng bậc đòn bẩy (đã đối chiếu qua nguồn thứ cấp: https://bitsgap.com/blog/crypto-liquidation-heatmap-explained; tài liệu API Coinglass: https://docs.coinglass.com/v3.0/reference/liquidation-heatmap). Phương pháp chi tiết của Coinglass: **chưa xác minh**.

Tự dựng bản ước lượng (xấp xỉ, bỏ qua phí và bậc margin):

```python
def est_liq_price(entry: float, lev: float, side: str, mmr: float = 0.005) -> float:
    # isolated margin, xấp xỉ bậc nhất
    return entry * (1 - 1/lev + mmr) if side == "long" else entry * (1 + 1/lev - mmr)

def liq_map(bars: pd.DataFrame, bin_size: float,
            levs=(5, 10, 25, 50, 100), weights=(.3, .3, .2, .15, .05)) -> pd.Series:
    """bars cần cột close, d_oi (thay đổi OI, coin). Chỉ tính phần OI TĂNG."""
    acc: dict[float, float] = {}
    for px, d in zip(bars["close"], bars["d_oi"].clip(lower=0)):
        for L, w in zip(levs, weights):
            for side in ("long", "short"):
                lp = np.floor(est_liq_price(px, L, side) / bin_size) * bin_size
                acc[lp] = acc.get(lp, 0.0) + d * w
    return pd.Series(acc).sort_index()
```

Bản này bỏ qua việc vị thế đã đóng, phân bố đòn bẩy `weights` là giả định tùy ý, và cross margin làm giá thanh lý phụ thuộc toàn bộ tài khoản. "Vùng thanh khoản dưới các đáy cũ" trên chart (2) có hai cách hiểu lập trình được: cụm stop dưới swing low (§6) hoặc cụm thanh lý ước lượng (mục này). Cần ghi rõ đang dùng định nghĩa nào.

### 3.5 Basis

- Futures có kỳ hạn: `basis = (F − S) / S`; annualized = `basis * 365 / số ngày đến đáo hạn`.
- Perp: premium index `(mark − index) / index`, chính là đầu vào của funding.

### 3.6 Diễn giải kết hợp giá + OI + funding

| Giá | OI | Diễn giải thường dùng |
|---|---|---|
| Tăng | Tăng | Vị thế mới mở, bên mua chủ động hơn |
| Tăng | Giảm | Short đóng vị thế (short covering) |
| Giảm | Tăng | Vị thế mới mở, bên bán chủ động hơn |
| Giảm | Giảm | Long đóng vị thế / bị thanh lý |

Thêm lớp funding: giá tăng + OI tăng + funding cao bất thường thường được đọc là long đòn bẩy đông; giá giảm + OI tăng + funding âm sâu là short đông.

```python
def oi_regime(df: pd.DataFrame, n: int = 24) -> pd.Series:
    dp = np.sign(df["close"].pct_change(n))
    doi = np.sign(df["oi"].pct_change(n))
    lab = {(1, 1): "new_longs", (1, -1): "short_cover",
           (-1, 1): "new_shorts", (-1, -1): "long_unwind"}
    return pd.Series([lab.get((a, b), "flat") for a, b in zip(dp, doi)], index=df.index)
```

### 3.7 Bẫy và bằng chứng

- Bảng trên là **suy diễn**: "bên chủ động" được đoán từ hướng giá, OI tự nó không nói gì về hướng. Nhãn có thể sai khi hedger (delta-neutral, basis trade) chiếm phần lớn OI.
- Funding cực đoan được nhiều người xem là tín hiệu đảo chiều; bằng chứng chủ yếu từ báo cáo của sàn và blog. Nghiên cứu bình duyệt xác nhận lợi thế sau chi phí: **chưa xác minh**.
- Dữ liệu từng sàn chỉ là một phần thị trường; dữ liệu tổng hợp (aggregated) phụ thuộc cách nhà cung cấp quy đổi.

---

## 4. Wyckoff

Nguồn tham chiếu chính: StockCharts ChartSchool (https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial) và tài liệu Wyckoff Analytics dựng lại từ đó (https://www.wyckoffanalytics.com/wp-content/uploads/2021/05/Wyckoff-Method-Wyckoff-Analytics-English.pdf). Cấu trúc 5 phase A–E và ba định luật đã đối chiếu qua trích đoạn; định nghĩa chi tiết từng sự kiện dưới đây viết theo trí nhớ về tài liệu này, cần đọc lại bản gốc khi cài đặt.

### 4.1 Khái niệm

**Bốn giai đoạn của chu kỳ giá:** Accumulation → Markup → Distribution → Markdown.

**Ba định luật:**

1. **Supply and Demand**: cầu vượt cung thì giá tăng và ngược lại.
2. **Cause and Effect**: thời gian tích lũy/phân phối (cause) quyết định độ dài xu hướng sau đó (effect); truyền thống đo bằng đếm ngang trên Point & Figure.
3. **Effort versus Result**: volume (effort) phải tương xứng với biến động giá (result); lệch pha gợi ý xu hướng sắp đổi.

**Composite Man**: giả định hình dung thị trường như do một tay chơi lớn điều khiển. Đây là công cụ tư duy, không phải thực thể quan sát được.

### 4.2 Sự kiện trong sơ đồ Accumulation

| Ký hiệu | Tên | Mô tả |
|---|---|---|
| PS | Preliminary Support | Lực mua đáng kể đầu tiên sau downtrend dài; volume và spread tăng |
| SC | Selling Climax | Bán tháo: spread rất rộng, volume cực lớn, thường đóng cửa cách xa đáy |
| AR | Automatic Rally | Hồi mạnh sau SC; đỉnh AR xác định cận trên trading range (TR) |
| ST | Secondary Test | Quay lại vùng SC với volume và spread thấp hơn |
| Spring / Shakeout | — | Phá xuống dưới đáy TR rồi quay lại nhanh. Không bắt buộc: Schematic #2 không có spring (đã đối chiếu: https://www.tradingview.com/chart/BTCUSD/GV54T8ZJ-What-is-the-Wyckoff-Method/) |
| Test | — | Kiểm tra lại vùng spring với volume thấp |
| SOS | Sign of Strength | Tăng với spread rộng và volume cao, thường vượt đỉnh TR |
| LPS | Last Point of Support | Điều chỉnh sau SOS với volume thấp, đáy cao hơn |
| BU | Back-Up (còn gọi JAC/BUEC) | Quay lại kiểm tra đỉnh TR vừa bị phá |

"UA" trên chart (3) của chủ dự án là **Upthrust Action**: cú vượt đỉnh TR trong Phase B rồi quay lại vào range (theo trí nhớ; kiểm tra lại trong ChartSchool).

### 4.3 Sự kiện trong sơ đồ Distribution

| Ký hiệu | Tên | Mô tả |
|---|---|---|
| PSY | Preliminary Supply | Lực bán đáng kể đầu tiên sau uptrend |
| BC | Buying Climax | Mua đuổi cao trào, spread rộng, volume cực lớn |
| AR | Automatic Reaction | Giảm mạnh sau BC; đáy AR xác định cận dưới TR |
| ST | Secondary Test | Quay lại vùng BC với volume thấp hơn |
| UT | Upthrust | Vượt đỉnh TR rồi quay lại (đối xứng với spring) |
| UTAD | Upthrust After Distribution | Upthrust muộn ở Phase C |
| SOW | Sign of Weakness | Giảm với spread rộng, volume cao, xuống gần hoặc dưới đáy TR |
| LPSY | Last Point of Supply | Hồi yếu, volume thấp, đỉnh thấp hơn |

### 4.4 Phase A–E

| Phase | Accumulation | Distribution |
|---|---|---|
| A | Dừng downtrend: PS, SC, AR, ST | Dừng uptrend: PSY, BC, AR, ST |
| B | Xây "cause": dao động trong TR, có thể có UA và ST phụ | Xây "cause": UT, SOW nhỏ |
| C | Phép thử: Spring/Shakeout và Test | Phép thử: UTAD |
| D | Xu hướng trong TR: SOS, LPS, BU | SOW, LPSY |
| E | Rời TR, markup | Rời TR, markdown |

### 4.5 Phát hiện tự động: hướng heuristic

Ý tưởng: (i) tìm xu hướng trước đó, (ii) tìm nến cao trào, (iii) dựng TR, (iv) chạy state machine qua các sự kiện.

```python
def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()          # Wilder

def effort_result(df: pd.DataFrame, win: int = 50) -> pd.DataFrame:
    a = atr(df)
    spread = (df["high"] - df["low"]) / a
    vz = (df["volume"] - df["volume"].rolling(win).mean()) / df["volume"].rolling(win).std()
    clv = (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)   # 0=đóng ở đáy, 1=ở đỉnh
    return pd.DataFrame({"spread": spread, "vz": vz, "clv": clv,
                         "er_gap": vz - (spread - spread.rolling(win).mean()) / spread.rolling(win).std()})

def selling_climax(df, f, trend_n=60, min_drop_atr=6.0, vz_min=2.5, spread_min=1.8, clv_min=0.4):
    drop = (df["close"].shift(1) - df["close"].shift(trend_n)) / atr(df)
    return (drop < -min_drop_atr) & (f["vz"] > vz_min) & (f["spread"] > spread_min) \
           & (f["clv"] > clv_min) & (df["low"] == df["low"].rolling(trend_n).min())

def find_spring(df, tr_low: float, start, max_pen_atr=1.5, reclaim_bars=3):
    """Phá đáy TR không quá max_pen_atr rồi đóng cửa lại trong TR trong reclaim_bars nến."""
    a = atr(df)
    seg = df.loc[start:]
    broke = (seg["low"] < tr_low) & (seg["low"] > tr_low - max_pen_atr * a.loc[start:])
    reclaimed = seg["close"].rolling(reclaim_bars).max().shift(-(reclaim_bars - 1)) > tr_low  # NHÌN TRƯỚC
    return seg.index[broke & reclaimed]
```

Dòng đánh dấu `NHÌN TRƯỚC` chỉ dùng khi gán nhãn offline. Khi chạy thật, spring chỉ được xác nhận sau `reclaim_bars` nến; timestamp tín hiệu phải dời tương ứng.

State machine tối thiểu cho accumulation: `DOWNTREND → SC → AR (đỉnh cao nhất trong N nến sau SC) → TR=[low(SC), high(AR)] → ST (chạm vùng đáy, vz thấp hơn SC) → [SPRING → TEST] → SOS (close > TR high, spread và vz cao) → LPS/BU (hồi về, giữ trên TR high hoặc giữa TR, vz thấp) → MARKUP`. Mỗi chuyển trạng thái có timeout; quá hạn thì hủy giả thuyết. Nếu giá đóng cửa dưới TR low quá `max_pen_atr` và không lấy lại, giả thuyết accumulation bị bác bỏ (có thể là redistribution).

### 4.6 Phát hiện tự động: hướng ML

- **Supervised**: gán nhãn tay các TR và sự kiện, huấn luyện CNN/LSTM trên cửa sổ giá-volume chuẩn hóa. Có một preprint arXiv dùng LSTM/CNN nhận dạng accumulation (TR và ST) và báo kết quả tích cực (https://arxiv.org/abs/2403.18839); đây là preprint của tác giả độc lập, phương pháp và dữ liệu **chưa xác minh**.
- **Unsupervised / regime**: HMM hoặc change-point detection để tách "range" và "trend", sau đó chỉ áp heuristic bên trong range.
- **Synthetic data**: sinh sơ đồ lý tưởng có nhiễu để tiền huấn luyện. Rủi ro: mô hình học sơ đồ sách giáo khoa, không học thị trường.

### 4.7 Giới hạn và bằng chứng

- Nhãn Wyckoff **chỉ rõ ràng khi nhìn lại**. Tại thời điểm thực, cùng một TR có thể là accumulation, redistribution hay chỉ là range. Hai chuyên gia gán nhãn cùng một chart thường khác nhau, nên nhãn huấn luyện ML có nhiễu cao.
- Mọi ngưỡng (`vz_min`, `max_pen_atr`...) là tự chọn; càng nhiều ngưỡng càng dễ overfit.
- Volume crypto phụ thuộc sàn; volume cổ phiếu có hiệu ứng lịch (đáo hạn phái sinh, tái cơ cấu chỉ số).
- Bằng chứng học thuật về lợi thế của phương pháp Wyckoff sau chi phí: không tìm thấy nghiên cứu bình duyệt đủ mạnh: **chưa xác minh**. Các indicator "Wyckoff tự động" trên TradingView/LuxAlgo là sản phẩm thương mại dựa trên chấm điểm heuristic, không phải bằng chứng.

Khuyến nghị kỹ thuật: xuất các *thành phần* (climax score, effort-result gap, spring flag, vị trí trong TR) thành feature độc lập và kiểm định từng cái, thay vì kiểm định cả "sơ đồ".

---

## 5. Elliott Wave

### 5.1 Khái niệm

Giá di chuyển theo sóng **motive** 5 bước (1-2-3-4-5) theo hướng xu hướng lớn và sóng **corrective** 3 bước (A-B-C) ngược lại; cấu trúc lồng nhau theo nhiều cấp (degree). Nguồn chuẩn: Frost & Prechter, *Elliott Wave Principle* (theo trí nhớ, không tra lại trong phiên này).

### 5.2 Ba quy tắc cứng (cho impulse)

1. Sóng 2 không hồi quá 100% sóng 1.
2. Sóng 3 không phải là sóng ngắn nhất trong ba sóng 1, 3, 5.
3. Sóng 4 không đi vào vùng giá của sóng 1 (ngoại lệ: diagonal).

```python
def is_valid_impulse(p: list[float]) -> bool:
    """p = [P0..P5] là 6 pivot xen kẽ. Xử lý cả tăng lẫn giảm bằng cách đổi dấu."""
    s = 1.0 if p[1] > p[0] else -1.0
    q = [s * x for x in p]
    w1, w3, w5 = q[1] - q[0], q[3] - q[2], q[5] - q[4]
    if min(w1, w3, w5) <= 0:
        return False
    return (q[2] > q[0]                       # rule 1
            and w3 >= min(w1, w5)             # rule 2: không ngắn nhất
            and q[4] > q[1])                  # rule 3: không chồng lấn
```

Chi tiết cần quyết định khi cài: đo sóng theo giá tuyệt đối hay phần trăm/log (với BTC nên dùng log), dùng high/low hay close, và có cho phép chạm bằng (>=) hay không.

### 5.3 Guideline (mềm, dùng để chấm điểm)

- **Alternation**: sóng 2 và sóng 4 khác dạng (sâu/nông, sharp/sideways).
- **Extension**: thường một trong ba sóng động lực kéo dài, phổ biến nhất là sóng 3.
- **Equality**: hai sóng động lực không kéo dài có xu hướng bằng nhau.
- **Channeling**: nối đáy 2–4 và song song qua đỉnh 3 để ước lượng đích sóng 5.
- Sóng 4 thường kết thúc trong vùng sóng 4 cấp nhỏ hơn của sóng 3.
- Volume thường lớn nhất ở sóng 3.

### 5.4 Tỷ lệ Fibonacci thường dùng

| Quan hệ | Tỷ lệ hay được nêu |
|---|---|
| Sóng 2 hồi sóng 1 | 50%, 61,8% |
| Sóng 3 so sóng 1 | 1,618 (có khi 2,618) |
| Sóng 4 hồi sóng 3 | 23,6%, 38,2% |
| Sóng 5 | bằng sóng 1, hoặc 0,618 × (đầu sóng 1 đến cuối sóng 3) |
| Zigzag: C so A | 1,0 hoặc 1,618 |
| Flat: B hồi A | ≥ 90%; expanded flat: B vượt 100% (hay nêu 123,6–138,2%) |

Đây là guideline, không phải rule. Các con số này là quy ước của giới thực hành (theo trí nhớ).

### 5.5 Mẫu điều chỉnh

| Mẫu | Cấu trúc con | Đặc điểm |
|---|---|---|
| Zigzag | 5-3-5 | Sharp; B hồi ít hơn 61,8% A; C vượt cuối A |
| Flat (regular / expanded / running) | 3-3-5 | Đi ngang; B hồi gần hết hoặc vượt đầu A |
| Triangle (contracting / expanding) | 3-3-3-3-3 (A-B-C-D-E) | Thường ở sóng 4 hoặc sóng B |
| Combination (W-X-Y) | Ghép nhiều mẫu | Nguồn chính gây đa nghiệm |

### 5.6 Thuật toán đếm sóng tự động

**Bước 1 — pivot bằng zigzag.** Ngưỡng theo phần trăm hoặc theo bội số ATR.

```python
def zigzag(high: np.ndarray, low: np.ndarray, thr: float):
    """Pivot xen kẽ. thr = ngưỡng đảo chiều tương đối (vd 0.05).
    Trả về list (idx_pivot, price, kind, idx_confirm). idx_confirm > idx_pivot: chỉ biết pivot tại idx_confirm."""
    piv, trend = [], 0
    hi_i, lo_i = 0, 0
    for i in range(1, len(high)):
        if high[i] > high[hi_i]: hi_i = i
        if low[i] < low[lo_i]: lo_i = i
        if trend >= 0 and low[i] < high[hi_i] * (1 - thr) and hi_i < i:
            piv.append((hi_i, high[hi_i], "H", i)); trend = -1; lo_i = i
        elif trend <= 0 and high[i] > low[lo_i] * (1 + thr) and lo_i < i:
            piv.append((lo_i, low[lo_i], "L", i)); trend = 1; hi_i = i
        if trend == -1 and high[i] >= high[hi_i]: hi_i = i     # theo dõi cực trị mới sau khi đổi chiều
        if trend == 1 and low[i] <= low[lo_i]: lo_i = i
    return piv
```

Đây là giả mã minh họa; bản dùng thật cần test kỹ trường hợp biên (nến vừa tạo đỉnh vừa tạo đáy, pivot đầu chuỗi) và reset cực trị đối diện sau mỗi lần đổi chiều.

**Bước 2 — liệt kê ứng viên.** Chạy zigzag ở nhiều ngưỡng (ví dụ 2%, 5%, 10%, 20%) để có nhiều cấp sóng. Với mỗi cấp, trượt cửa sổ 6 pivot liên tiếp (impulse) và 4 pivot (A-B-C); cho phép bỏ qua pivot nhỏ để ghép sóng.

**Bước 3 — lọc bằng rule cứng** (`is_valid_impulse`), kiểm tra tương tự cho zigzag/flat/triangle.

**Bước 4 — chấm điểm guideline.**

```python
FIB = np.array([0.236, 0.382, 0.5, 0.618, 1.0, 1.618, 2.618])

def fib_closeness(ratio: float, tol: float = 0.08) -> float:
    return float(np.exp(-((np.abs(FIB - ratio).min()) / tol) ** 2))

def score_impulse(p: list[float]) -> float:
    w1, w2, w3, w4, w5 = [abs(p[i + 1] - p[i]) for i in range(5)]
    parts = [fib_closeness(w2 / w1), fib_closeness(w3 / w1), fib_closeness(w4 / w3),
             fib_closeness(w5 / w1), 1.0 if w3 == max(w1, w3, w5) else 0.5,
             1.0 if abs(w2 / w1 - w4 / w3) > 0.15 else 0.5]     # alternation thô
    return float(np.mean(parts))
```

**Bước 5 — kiểm tra đệ quy.** Sóng 1, 3, 5 phải tự chia thành 5 sóng ở cấp nhỏ hơn; sóng 2, 4 thành 3 sóng. Mỗi tầng đệ quy nhân số ứng viên lên.

**Bước 6 — giữ top-k** cách đếm thay vì một đáp án; xuất kèm mức giá *vô hiệu hóa* (invalidation) của từng cách đếm, vì đó là phần duy nhất kiểm chứng được.

### 5.7 Vấn đề đa nghiệm và chủ quan

- Với cùng chuỗi pivot, thường có nhiều cách đếm hợp lệ theo ba rule cứng. Combination W-X-Y và việc cho phép "extension", "truncation" khiến gần như mọi chuỗi giá đều đếm được.
- Kết quả rất nhạy với ngưỡng zigzag và với việc dùng thang log hay tuyến tính.
- Khi cách đếm chính sai, người phân tích chuyển sang "alternate count", nên lý thuyết khó bị bác bỏ. Về mặt kiểm định, phải cố định thuật toán và tham số *trước* rồi mới đo.
- Pivot cuối cùng chưa được xác nhận: cách đếm "hiện tại" luôn thay đổi (repaint).
- Số tổ hợp tăng theo cấp số mũ; cần giới hạn độ sâu đệ quy và beam search.

### 5.8 Bằng chứng thực nghiệm

Yếu. Không tìm thấy nghiên cứu bình duyệt vững chắc nào chứng minh đếm sóng tự động có khả năng dự báo. Một capstone trên dữ liệu forex kết luận Elliott Wave không có khả năng dự báo có ý nghĩa thống kê với tỷ giá ngày (https://nur.nu.edu.kz/handle/123456789/7226; bằng chứng yếu vì là đồ án sinh viên). Batchelor & Ramyar (2006, "Magic numbers in the Dow") thường được dẫn là không tìm thấy tỷ lệ Fibonacci xuất hiện nhiều hơn ngẫu nhiên trong Dow Jones: **chưa xác minh** (chỉ thấy qua nguồn thứ cấp, không mở được bài gốc). Tuyên bố độ chính xác của các phần mềm đếm sóng là quảng cáo, chưa có kiểm chứng độc lập.

Cách dùng hợp lý trong dự án: coi bộ đếm sóng là công cụ *mô tả* và sinh mức invalidation; nếu muốn dùng làm tín hiệu thì phải kiểm định như mọi feature khác, với tham số cố định trước.

---

## 6. Hỗ trợ/kháng cự và thanh khoản

### 6.1 Khái niệm

- **Swing high/low**: cực trị cục bộ.
- **Equal highs/lows**: nhiều swing ở gần cùng một mức.
- **Vùng stop tập trung ("liquidity pool")**: giả định rằng lệnh stop-loss dồn ngay ngoài swing rõ ràng và quanh số tròn.
- **Liquidity sweep / stop hunt**: giá vượt qua mức đó rồi quay lại nhanh. Spring và upthrust của Wyckoff (§4) là cùng hiện tượng, khác tên gọi.

### 6.2 Phát hiện swing

```python
def swings(df: pd.DataFrame, left: int = 5, right: int = 5) -> pd.DataFrame:
    """Fractal: high lớn nhất trong cửa sổ [i-left, i+right].
    Swing tại i chỉ được BIẾT ở i+right -> cột known_at."""
    w = left + right + 1
    is_h = df["high"] == df["high"].rolling(w, center=False).max().shift(-right)
    is_l = df["low"] == df["low"].rolling(w, center=False).min().shift(-right)
    out = pd.DataFrame({"swing_high": df["high"].where(is_h), "swing_low": df["low"].where(is_l)})
    out["known_at"] = df.index.to_series().shift(-right)
    return out
```

Lựa chọn thay thế: zigzag (§5.6) hoặc `scipy.signal.find_peaks` với `prominence` theo ATR.

### 6.3 Cụm equal highs/lows

```python
def cluster_levels(levels: pd.Series, tol: pd.Series, min_touches: int = 2) -> list[dict]:
    """levels: giá swing (index thời gian, đã dropna). tol: dung sai tại thời điểm đó (vd 0.1*ATR)."""
    out, used = [], set()
    vals = levels.sort_values()
    for t0, p0 in vals.items():
        if t0 in used:
            continue
        grp = vals[(vals - p0).abs() <= tol.loc[t0]]
        if len(grp) >= min_touches:
            used.update(grp.index)
            out.append({"level": float(grp.mean()), "touches": len(grp),
                        "first": grp.index.min(), "last": grp.index.max()})
    return out
```

Cho chart tháng BTC (chart 2) nên gom cụm trên log-price với dung sai phần trăm, vì ATR tuyệt đối thay đổi nhiều bậc theo thời gian.

### 6.4 Liquidity sweep

```python
def sweeps_of_low(df: pd.DataFrame, level: float, valid_from, reclaim_bars: int = 1,
                  max_pen: float | None = None) -> pd.Index:
    seg = df.loc[valid_from:]
    pierced = seg["low"] < level
    if max_pen is not None:
        pierced &= seg["low"] > level - max_pen
    if reclaim_bars == 1:
        back = seg["close"] > level                      # cùng nến: biết khi nến đóng
    else:
        back = seg["close"].shift(-(reclaim_bars - 1)) > level   # nhìn trước, phải dời timestamp
    return seg.index[pierced & back]
```

Feature bổ sung: độ sâu xuyên phá tính theo ATR, volume và delta của nến sweep (§2), số lần mức đã được chạm, tuổi của mức, khoảng cách đến số tròn.

### 6.5 Dữ liệu, bẫy, bằng chứng

- Dữ liệu: OHLCV đủ dùng; thêm aggTrades nếu muốn xem delta tại lúc sweep.
- Bẫy: swing chỉ được xác nhận sau `right` nến; mức "đẹp" trên chart khung lớn là kết quả chọn lọc bằng mắt; cùng một cú xuyên phá có thể là sweep hoặc là breakout thật, chỉ phân biệt được sau.
- Bằng chứng: phần **gom cụm lệnh** có cơ sở tốt. Osler (2003, *Journal of Finance* 58(5), 1791–1819) dùng dữ liệu lệnh thực của một ngân hàng ngoại hối lớn, cho thấy lệnh take-profit dồn ở số tròn còn stop-loss dồn ngay bên ngoài số tròn, và xu hướng tăng tốc sau khi phá các mức này (đã đối chiếu: https://ideas.repec.org/a/bla/jfinan/v58y2003i5p1791-1819.html; bản Fed NY Staff Report 125: https://fraser.stlouisfed.org/files/docs/publications/frbnysr/frbny_sr125.pdf). Lưu ý đây là thị trường FX, và kết quả ủng hộ cả *đảo chiều tại mức* lẫn *tăng tốc sau khi phá*, không riêng kịch bản sweep-rồi-đảo-chiều. Lợi thế của việc giao dịch theo sweep ở crypto/cổ phiếu sau chi phí: **chưa xác minh**.

---

## 7. Indicator cổ điển

### 7.1 Công thức và tham số mặc định

Ký hiệu: `C, H, L, V` là close, high, low, volume; `n` là chu kỳ.

| Indicator | Công thức rút gọn | Mặc định phổ biến |
|---|---|---|
| SMA | trung bình cộng `n` giá | 20, 50, 200 |
| EMA | `EMA_t = α·C_t + (1−α)·EMA_{t−1}`, `α = 2/(n+1)` | 12, 26, 50, 200 |
| RSI (Wilder) | `RS = avg_gain / avg_loss` (làm mượt Wilder, `α = 1/n`); `RSI = 100 − 100/(1+RS)` | n=14; ngưỡng 30/70 |
| MACD | `MACD = EMA12 − EMA26`; `signal = EMA9(MACD)`; `hist = MACD − signal` | 12, 26, 9 |
| ROC | `100·(C_t / C_{t−n} − 1)` | n=10 hoặc 12 |
| Stochastic | `%K = 100·(C − LL_n)/(HH_n − LL_n)`; slow %K = SMA(%K, 3); `%D = SMA(slow %K, 3)` | 14, 3, 3 |
| Williams %R | `−100·(HH_n − C)/(HH_n − LL_n)` | n=14; ngưỡng −20/−80 |
| ATR | `TR = max(H−L, |H−C_{t−1}|, |L−C_{t−1}|)`; ATR = Wilder MA của TR | n=14 |
| Bollinger Bands | `mid = SMA_n`; `upper/lower = mid ± k·σ_n` | n=20, k=2 |
| VWAP | `Σ(TP·V) / ΣV`, `TP = (H+L+C)/3`, reset mỗi phiên | reset theo ngày |
| Anchored VWAP | VWAP cộng dồn từ một mốc chọn trước | mốc: swing, sự kiện |
| ADX | `+DM/−DM` → Wilder → `+DI, −DI`; `DX = 100·|+DI − −DI|/(+DI + −DI)`; ADX = Wilder(DX) | n=14; ngưỡng 20–25 |
| OBV | cộng `V` nếu `C_t > C_{t−1}`, trừ nếu nhỏ hơn | không tham số |

```python
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn)

def anchored_vwap(df: pd.DataFrame, anchor) -> pd.Series:
    seg = df.loc[anchor:]
    tp = (seg["high"] + seg["low"] + seg["close"]) / 3
    return (tp * seg["volume"]).cumsum() / seg["volume"].cumsum()

def session_vwap(df: pd.DataFrame) -> pd.Series:          # index là DatetimeIndex UTC
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.floor("D")
    return (tp * df["volume"]).groupby(day).cumsum() / df["volume"].groupby(day).cumsum()
```

### 7.2 Thư viện

- **TA-Lib** (C, wrapper Python): nhanh, là chuẩn tham chiếu thực tế. Wrapper đã có binary wheel kèm thư viện C từ bản 0.6.5, không cần build tay (đã đối chiếu: https://github.com/TA-Lib/ta-lib-python, https://pypi.org/project/TA-Lib).
- **pandas-ta**: bản gốc có thông báo sẽ bị archive nếu không có thêm hỗ trợ trước 2026-07-01; tình trạng hiện tại **chưa xác minh**. Fork cộng đồng `pandas-ta-classic` còn phát hành trong 2026 (đã đối chiếu: https://pypi.org/project/pandas-ta-classic/, https://github.com/TheNeuroDeveloper/pandas-ta-classic). Nên ghim phiên bản và kiểm tra tình trạng bảo trì trước khi chọn.
- Tự viết bằng pandas/numpy cho nhóm indicator cốt lõi là lựa chọn hợp lý: ít phụ thuộc, kiểm soát được warm-up.

### 7.3 Bẫy thường gặp

- **Mặc định của thư viện khác mặc định trên chart.** Theo trí nhớ về TA-Lib: `BBANDS` mặc định `timeperiod=5` (không phải 20), `STOCH` mặc định `fastk_period=5` (không phải 14). Luôn truyền tham số tường minh; kiểm tra lại tại https://ta-lib.org/functions/.
- **Khởi tạo EMA/Wilder khác nhau** giữa TA-Lib (seed bằng SMA), pandas `ewm(adjust=False)` và TradingView, dẫn đến giá trị lệch ở đoạn đầu chuỗi. Cần warm-up dài (ít nhất vài lần `n`) và test đối chiếu với một nguồn chuẩn.
- **VWAP** cần dữ liệu intraday; VWAP tính từ nến ngày không có nghĩa. Với crypto, điểm reset phiên là quy ước tự chọn.
- **Anchored VWAP** neo vào swing: swing phải đã được xác nhận tại thời điểm dùng.
- Đa số indicator là biến đổi của cùng chuỗi giá, tương quan cao với nhau; chồng nhiều indicator không tạo thêm thông tin độc lập.
- OBV và các chỉ báo volume chịu ảnh hưởng chất lượng volume của sàn.

### 7.4 Bằng chứng thực nghiệm

Hỗn hợp. Brock, Lakonishok & LeBaron (1992) báo cáo quy tắc MA và trading-range breakout có khả năng dự báo trên Dow Jones; Sullivan, Timmermann & White (1999) cho thấy sau khi hiệu chỉnh data snooping, hiệu quả không duy trì ngoài mẫu (cả hai theo trí nhớ). Park & Irwin (2007) tổng kết: kết quả tích cực tập trung ở FX và hàng hóa hơn là cổ phiếu, và suy yếu theo thời gian (đã đối chiếu, URL ở §0). Với Bitcoin, có nghiên cứu báo cáo quy tắc MA có khả năng dự báo (Detzel và cộng sự 2021; Hudson & Urquhart 2021 — theo trí nhớ, **chưa xác minh** trong phiên này). Nhóm xu hướng/momentum có bằng chứng tốt hơn nhóm dao động quá mua/quá bán.

---

## 8. Phân tích liên thị trường và vĩ mô

### 8.1 Các quan hệ thường được nêu

| Biến | Lập luận phổ biến | Ghi chú |
|---|---|---|
| Lãi suất Fed (FEDFUNDS) | Lãi suất giảm/nới lỏng hỗ trợ tài sản rủi ro | Biến chính sách dạng bậc thang, đổi rất ít lần |
| DXY | Đô la mạnh đi cùng BTC yếu | DXY là chỉ số của ICE; FRED có chỉ số đô la rộng (DTWEXBGS) là chuỗi khác |
| Vàng (XAUUSD) | "Vàng số", cùng hưởng lợi khi tiền tệ mất giá | Tương quan BTC–vàng thấp và không ổn định |
| Lợi suất trái phiếu (10Y, real yield) | Real yield tăng gây áp lực lên tài sản không sinh dòng tiền | Chuỗi FRED: DGS10, DGS2, DFII10 |
| Thanh khoản toàn cầu / M2 | BTC đi theo M2 với độ trễ vài tuần đến vài tháng | Xem cảnh báo §8.4 |
| Chu kỳ halving | Đỉnh/đáy lặp lại theo chu kỳ ~4 năm | Chỉ có 4 lần halving (2012, 2016, 2020, 2024) |

Bằng chứng về vai trò "trú ẩn": nghiên cứu của Fed Kansas City (2020) kết luận Bitcoin chưa từng thể hiện hành vi safe haven trong mẫu của họ và nhiều lúc hành xử như tài sản rủi ro (đã đối chiếu: https://www.kansascityfed.org/en/publications/research/eb/articles/2020/safe-haven-performance-age-of-bitcoin). Smales & Baur ("Bitcoin as a safe haven: Is it even worth considering?", *Finance Research Letters* 30) và Klein, Hien & Walther ("Bitcoin is not the New Gold", tóm tắt tại https://quantpedia.com/bitcoin-is-not-the-new-gold/) đi cùng hướng (đối chiếu qua nguồn thứ cấp).

### 8.2 Dữ liệu cần

- **FRED** (https://fred.stlouisfed.org): `FEDFUNDS` (trung bình tháng), `DFF` (ngày), `DGS10`, `DGS2`, `DFII10`, `DTWEXBGS`, `M2SL` (tháng), `WALCL` (bảng cân đối Fed, tuần). Mã chuỗi viết theo trí nhớ; kiểm tra từng mã trên FRED.
- **Vàng**: FRED từng có chuỗi giá vàng LBMA nhưng đã gỡ: **chưa xác minh**. Cần nguồn khác (nhà cung cấp dữ liệu FX/hàng hóa, hoặc futures GC).
- **Global M2**: không ngân hàng trung ương nào công bố; đây là chỉ số tự ghép từ M2 các nước quy đổi ra USD, mỗi người dựng một kiểu (đã đối chiếu qua nguồn thứ cấp: https://www.bit.com/knowledge-hub/global-m2-decoupling). Vì quy đổi ra USD, chuỗi này chứa sẵn biến động của đồng đô la.
- **Point-in-time**: dữ liệu vĩ mô có độ trễ công bố và bị sửa. `M2SL` tháng 10 chỉ có vào cuối tháng 11. Dùng ALFRED (vintage) hoặc tự dời chuỗi theo lịch công bố.

### 8.3 Cách đo

**Nguyên tắc số một: đo trên lợi suất (hoặc sai phân), không đo trên mức giá.**

```python
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint

def rolling_corr(a: pd.Series, b: pd.Series, win: int = 90) -> pd.Series:
    ra, rb = np.log(a).diff(), np.log(b).diff()
    return ra.rolling(win).corr(rb)

def lead_lag(a: pd.Series, b: pd.Series, max_lag: int = 26) -> pd.Series:
    """corr(ret_a[t], ret_b[t-k]); k>0 nghĩa là b đi trước a k kỳ."""
    ra, rb = np.log(a).diff(), np.log(b).diff()
    return pd.Series({k: ra.corr(rb.shift(k)) for k in range(-max_lag, max_lag + 1)})

def engle_granger(a: pd.Series, b: pd.Series):
    la, lb = np.log(a).dropna().align(np.log(b).dropna(), join="inner")
    t, p, _ = coint(la, lb)                    # H0: không đồng liên kết
    return {"t": t, "p": p, "adf_a": adfuller(la)[1], "adf_b": adfuller(lb)[1]}

def rate_regime(ff: pd.Series, n: int = 3, eps: float = 0.10) -> pd.Series:
    """FEDFUNDS tháng -> hiking / cutting / hold theo thay đổi n tháng."""
    d = ff.diff(n)
    return pd.Series(np.select([d > eps, d < -eps], ["hiking", "cutting"], "hold"), index=ff.index)
```

Bổ sung:

- **Regime**: so sánh phân phối lợi suất BTC và vàng *có điều kiện* theo regime lãi suất (`rate_regime`) hoặc theo mô hình Markov switching (`statsmodels.tsa.regime_switching`, Hamilton 1989 — theo trí nhớ).
- **Event study**: phản ứng của BTC quanh các cuộc họp FOMC, đo trên cửa sổ ngắn; ít bị nhiễu bởi xu hướng chung hơn tương quan dài hạn.
- **Căn chỉnh thời gian**: BTC giao dịch 24/7, vàng và trái phiếu có giờ đóng cửa và ngày nghỉ. Lấy mẫu BTC tại đúng giờ đóng cửa của tài sản kia, hoặc dùng tần suất tuần để giảm nhiễu lệch giờ.
- **Khoảng tin cậy**: bootstrap theo khối (block bootstrap) cho rolling correlation; với mẫu chồng lấn, độ lệch chuẩn thông thường bị ước lượng thấp.

Áp cho chart (4): tách thành ba phép đo riêng — (a) rolling correlation lợi suất tuần BTC–vàng; (b) lợi suất BTC và vàng theo regime FEDFUNDS; (c) event study quanh ngày FOMC. Chồng ba đường lên một chart chỉ là minh họa, không phải phép đo.

### 8.4 Cảnh báo tương quan giả

- **Hai chuỗi cùng có xu hướng sẽ tương quan cao ở mức giá** dù không liên quan gì (Granger & Newbold 1974, "spurious regression" — theo trí nhớ). Ví dụ cụ thể: một phân tích báo cáo tương quan mức giá BTC–global M2 từ 0,86 đến 0,94 nhưng tương quan thay đổi tháng đồng thời chỉ khoảng 0,04; độ trễ "tốt nhất" trôi từ 1–2 tháng sang 2–3 tháng theo thời gian (https://www.bit.com/knowledge-hub/global-m2-decoupling — nguồn là blog của sàn, số liệu **chưa xác minh** độc lập).
- **Chọn độ trễ sau khi nhìn dữ liệu** là data snooping: dịch chuỗi M2 đi 70–110 ngày cho đến khi khớp chart thì luôn tìm được một độ trễ khớp.
- **Mẫu hiệu dụng rất nhỏ.** Từ khi BTC có thị trường thanh khoản, chỉ có vài chu kỳ lãi suất và 4 lần halving. Bốn quan sát không đủ để phân biệt "chu kỳ halving" với chu kỳ thanh khoản toàn cầu trùng thời điểm.
- **Tương quan không ổn định.** Tương quan BTC với cổ phiếu, vàng, đô la đổi dấu qua các giai đoạn; tương quan BTC–vàng tăng vọt trong đợt bán tháo COVID 2020 rồi trở lại thấp (https://vaneck.com/ch/en/blog/digital-assets/bitcoin-correlation-to-gold-jumps-in-2020 — nguồn thực hành).
- **Biến ẩn chung**: khẩu vị rủi ro toàn cầu và đồng đô la tác động đồng thời lên nhiều tài sản; A và B cùng đi không có nghĩa A dẫn B.
- **Cointegration** giữa BTC và biến vĩ mô: kiểm định dễ cho kết quả dương giả trên mẫu ngắn có đứt gãy cấu trúc; không nên dựng chiến lược mean-reversion trên đó khi chưa kiểm tra ngoài mẫu.

### 8.5 Bằng chứng thực nghiệm

Quan hệ vĩ mô với BTC là có thật ở mức mô tả nhưng không ổn định và mẫu nhỏ. Liu & Tsyvinski (2021, *Review of Financial Studies*) ghi nhận lợi suất crypto ít phơi nhiễm với các nhân tố vĩ mô và cổ phiếu truyền thống, và được giải thích tốt hơn bởi momentum và mức độ chú ý của nhà đầu tư (theo trí nhớ; mẫu của họ kết thúc trước giai đoạn 2020–2022 khi tương quan với cổ phiếu tăng). Nghiên cứu về phản ứng của BTC với thông báo FOMC và phê bình mẫu nhỏ của chu kỳ halving: **chưa xác minh** (tìm kiếm không ra nguồn cụ thể).

---

## 9. On-chain cho crypto

### 9.1 Định nghĩa

| Chỉ số | Định nghĩa |
|---|---|
| Realized Cap | Tổng giá trị nguồn cung, mỗi coin định giá tại thời điểm nó được di chuyển on-chain lần cuối |
| Realized Price | `Realized Cap / nguồn cung lưu hành`; được xem là "giá vốn on-chain" trung bình |
| MVRV | `Market Cap / Realized Cap`; MVRV = 1 nghĩa là giá bằng giá vốn trung bình |
| MVRV Z-Score | `(Market Cap − Realized Cap) / std(Market Cap)` |
| SOPR | Với các output được tiêu trong kỳ: `giá trị khi tiêu / giá trị khi tạo`; > 1 là chốt lời, < 1 là cắt lỗ |
| aSOPR | SOPR loại các output có tuổi dưới 1 giờ |
| NUPL | `(Market Cap − Realized Cap) / Market Cap = 1 − 1/MVRV` |
| Exchange flows | Inflow, outflow, netflow và số dư trên các địa chỉ được gán nhãn là sàn |

Định nghĩa Realized Price, MVRV, SOPR/aSOPR, NUPL đã đối chiếu với Glassnode (https://docs.glassnode.com/guides-and-tutorials/metric-guides, https://studio.glassnode.com/charts/realizedprice-mvrv?a=BTC, https://insights.glassnode.com/dissecting-bitcoins-unrealised-on-chain-profit-loss). Công thức MVRV Z-Score viết theo trí nhớ. Vì NUPL là hàm đơn điệu của MVRV, hai chỉ số này mang cùng một thông tin.

Biến thể theo nhóm: STH/LTH (short/long-term holder, ngưỡng quy ước 155 ngày — theo trí nhớ) cho MVRV, SOPR, realized price riêng từng nhóm.

### 9.2 Tính toán

```python
def onchain_derived(df: pd.DataFrame) -> pd.DataFrame:
    """df ngày: cột price, supply, realized_cap (lấy từ nhà cung cấp)."""
    out = pd.DataFrame(index=df.index)
    mcap = df["price"] * df["supply"]
    out["realized_price"] = df["realized_cap"] / df["supply"]
    out["mvrv"] = mcap / df["realized_cap"]
    out["nupl"] = 1 - 1 / out["mvrv"]
    out["mvrv_z"] = (mcap - df["realized_cap"]) / mcap.expanding(min_periods=365).std()
    return out
```

`expanding()` giữ cho Z-score không nhìn trước; các chart công khai thường dùng std toàn mẫu, tức là nhìn trước.

Tự tính realized cap và SOPR từ đầu cần full node và duyệt toàn bộ UTXO (mỗi output: giá trị, thời điểm tạo, thời điểm tiêu, giá tại hai thời điểm). Làm được nhưng tốn công; nên bắt đầu từ dữ liệu nhà cung cấp.

### 9.3 Nguồn dữ liệu

| Nguồn | Ghi chú |
|---|---|
| Glassnode (https://docs.glassnode.com/quickstart/rest-api) | Đầy đủ; API và độ phân giải cao cần trả phí |
| CryptoQuant | Mạnh về exchange flows; trả phí cho phần lớn dữ liệu (theo trí nhớ) |
| Coin Metrics | Có community API miễn phí với một số chỉ số như realized cap, MVRV (theo trí nhớ; phạm vi miễn phí hiện tại **chưa xác minh**) |
| Tự chạy node | Kiểm soát hoàn toàn định nghĩa; không có nhãn địa chỉ sàn |

### 9.4 Bẫy thường gặp

- **Chỉ áp dụng trực tiếp cho chain kiểu UTXO** (BTC). Với chain account-based (ETH) định nghĩa phải xấp xỉ; với stablecoin và token trên nhiều chain càng phức tạp.
- **Exchange flows phụ thuộc gán nhãn địa chỉ** bằng heuristic riêng của từng nhà cung cấp; số liệu giữa các nguồn lệch nhau và bị sửa hồi tố khi phát hiện ví mới. Chuyển ví nội bộ của sàn có thể bị đếm thành inflow/outflow.
- **Cấu trúc thị trường đã đổi**: ETF giao ngay, lưu ký tập trung, wrapped BTC, giao dịch off-chain khiến "coin di chuyển on-chain" ngày càng ít đại diện cho giao dịch kinh tế thật. Coin mất vĩnh viễn làm lệch realized cap.
- **Ngưỡng lịch sử** (ví dụ NUPL > 0,5 là "hưng phấn" theo Glassnode; MVRV-Z cao là "đỉnh") được rút từ 3–4 chu kỳ và được chọn sau khi biết kết quả. Đỉnh của các chỉ số này thấp dần qua các chu kỳ, nên ngưỡng cố định không ổn định.
- **Độ trễ và sửa số liệu**: dữ liệu ngày, thường chốt theo UTC; một số chỉ số bị tính lại. Cần lưu snapshot theo ngày lấy nếu muốn backtest point-in-time.

### 9.5 Bằng chứng thực nghiệm

MVRV/NUPL/SOPR mô tả tốt trạng thái lãi/lỗ chưa thực hiện của thị trường và về mặt lịch sử có đạt cực trị gần các đỉnh/đáy chu kỳ BTC. Tuy nhiên số chu kỳ độc lập chỉ khoảng 3–4, ngưỡng được khớp trong mẫu, và nguồn chính là các nhà cung cấp dữ liệu có lợi ích thương mại. Nghiên cứu bình duyệt xác nhận khả năng dự báo ngoài mẫu: **chưa xác minh**. Phù hợp làm feature regime khung dài (tuần/tháng), không phù hợp làm tín hiệu ngắn hạn.

---

## 10. Tổng hợp cho thiết kế hệ thống

### 10.1 Bảng đánh giá nhanh

| Phương pháp | Lập trình khách quan được? | Bằng chứng | Dữ liệu tối thiểu |
|---|---|---|---|
| Volume Profile (POC/VA/LVN) | Có, sau khi cố định bin và phạm vi | Yếu, chưa có kiểm định bình duyệt | Nến 1m; tốt nhất aggTrades |
| Order flow (delta, CVD, imbalance) | Có | Tốt ở khung giây–phút; yếu ở khung dài | aggTrades |
| Funding / OI / liquidation | Có | Chủ yếu từ nguồn ngành | API sàn, phải tự thu thập liên tục |
| Liquidation heatmap | Chỉ là mô hình ước lượng | Không kiểm chứng được | OI + giả định đòn bẩy |
| Wyckoff | Một phần (thành phần thì được, sơ đồ thì chủ quan) | Yếu | OHLCV |
| Elliott Wave | Rule cứng thì được; cách đếm đa nghiệm | Yếu | OHLCV |
| Swing / equal lows / sweep | Có | Gom cụm stop có bằng chứng (FX); lợi thế giao dịch chưa rõ | OHLCV |
| Indicator cổ điển | Có | Hỗn hợp; trend/momentum tốt hơn | OHLCV |
| Liên thị trường / vĩ mô | Có | Quan hệ không ổn định, mẫu nhỏ | FRED + giá |
| On-chain | Có (từ dữ liệu nhà cung cấp) | Mô tả tốt, dự báo chưa kiểm chứng | API nhà cung cấp |

### 10.2 Nguyên tắc cài đặt rút ra

1. Mỗi feature có hai timestamp: `event_time` và `known_at`. Backtest chỉ dùng `known_at`.
2. Thu thập ngay từ đầu các dữ liệu không lấy lại được: OI, long/short ratio, liquidation stream, sổ lệnh.
3. Tách phương pháp chủ quan (Wyckoff, Elliott) thành các thành phần đo được và kiểm định riêng từng thành phần.
4. Cố định tham số trước khi kiểm định; ghi lại số cấu hình đã thử.
5. Mọi quan hệ vĩ mô đo trên lợi suất, có khoảng tin cậy, và kiểm tra độ ổn định qua các giai đoạn.
6. Ghi rõ nguồn và giả định của mọi chuỗi dữ liệu (sàn nào, spot hay perp, cách rải volume, định nghĩa "phiên").

### 10.3 Danh sách điều chưa xác minh

1. Biến thể mở rộng value area mà TradingView built-in dùng (hai hàng hay một hàng).
2. Bằng chứng bình duyệt cho POC/VA/naked POC, cho ngưỡng imbalance 300%, và cho delta/CVD ở khung tuần.
3. Giới hạn 30 ngày của `openInterestHist` trên USDⓈ-M (đã thấy ở COIN-M); bộ file "metrics" trên data.binance.vision; tên endpoint taker buy/sell ratio.
4. Quy tắc snapshot 1000 ms của `forceOrder` trên USDⓈ-M (đã thấy ở COIN-M).
5. Phương pháp chi tiết của Coinglass liquidation heatmap.
6. Lợi thế sau chi phí của funding cực đoan, của sweep, của Wyckoff.
7. Định nghĩa chi tiết từng sự kiện Wyckoff và ký hiệu UA: viết theo trí nhớ về ChartSchool, chưa đọc lại bản gốc.
8. Preprint arXiv 2403.18839 về nhận dạng Wyckoff bằng LSTM: chưa đọc phương pháp và dữ liệu.
9. Batchelor & Ramyar (2006) về Fibonacci; các bài Detzel và cộng sự (2021), Hudson & Urquhart (2021), Liu & Tsyvinski (2021), Cont–Kukanov–Stoikov (2014), Brock–Lakonishok–LeBaron (1992), Sullivan–Timmermann–White (1999): dẫn theo trí nhớ, chưa mở bài gốc.
10. Mặc định `BBANDS timeperiod=5`, `STOCH fastk_period=5` của TA-Lib; cột taker buy volume trong kline Binance.
11. Tình trạng archive của pandas-ta gốc sau 2026-07-01.
12. Mã chuỗi FRED và việc FRED đã gỡ chuỗi giá vàng LBMA; phạm vi miễn phí của Coin Metrics.
13. Số liệu tương quan BTC–global M2 (0,86–0,94 và 0,04): từ blog của sàn, chưa kiểm tra độc lập.
14. Nghiên cứu về phản ứng BTC với FOMC và phê bình mẫu nhỏ của chu kỳ halving: chưa tìm được nguồn cụ thể.
15. Công thức MVRV Z-Score và ngưỡng 155 ngày STH/LTH: theo trí nhớ.
16. Toàn bộ giả mã trong tài liệu chưa được chạy thử; cần unit test trước khi dùng.
