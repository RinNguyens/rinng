# 05 — Quant research, backtest và dữ liệu

> Ngày tra cứu: **2026-11-13**. Phiên bản thư viện lấy từ PyPI JSON API và GitHub API trong ngày; giá và giới hạn gói miễn phí lấy từ trang chính thức khi mở được, còn lại là nguồn thứ cấp và được ghi rõ.
>
> Quy ước:
> - **[chưa xác minh]** = không kiểm tra được bằng nguồn chính thức trong phiên tra cứu này. Hãy mở trang gốc trước khi dựa vào.
> - Công thức, khái niệm và danh sách sách/paper là kiến thức nền, không phụ thuộc ngày tra cứu. URL của paper ghi theo trí nhớ, **chưa mở kiểm tra từng link**.
> - Tài liệu này không đưa khuyến nghị mua/bán. Mọi ví dụ chỉ minh hoạ phương pháp.

## Mục lục

1. [Quy trình nghiên cứu quant](#1-quy-trình-nghiên-cứu-quant)
2. [Backtest đúng cách](#2-backtest-đúng-cách)
3. [Metric và cách annualize](#3-metric-và-cách-annualize)
4. [Quản trị rủi ro và position sizing](#4-quản-trị-rủi-ro-và-position-sizing)
5. [Các họ chiến lược](#5-các-họ-chiến-lược)
6. [Microstructure cơ bản](#6-microstructure-cơ-bản)
7. [So sánh thư viện Python](#7-so-sánh-thư-viện-python)
8. [Nguồn dữ liệu](#8-nguồn-dữ-liệu)
9. [Phân tích cơ bản cho stock analyzer](#9-phân-tích-cơ-bản-cho-stock-analyzer)
10. [Kiến trúc lưu trữ và pipeline đề xuất](#10-kiến-trúc-lưu-trữ-và-pipeline-đề-xuất)
11. [Sách và paper nền tảng](#11-sách-và-paper-nền-tảng)
12. [Danh sách điều chưa xác minh](#12-danh-sách-điều-chưa-xác-minh)

---

## 1. Quy trình nghiên cứu quant

| Bước | Việc cần làm | Sản phẩm đầu ra | Lỗi hay gặp |
|---|---|---|---|
| 1. Giả thuyết | Viết ra *vì sao* edge tồn tại (ai là người trả tiền cho mình: người cần thanh khoản, người bị ép bán, hành vi chậm phản ứng…) và điều kiện làm nó biến mất | 1 đoạn văn + tiêu chí bác bỏ viết **trước** khi nhìn dữ liệu | Đào dữ liệu trước rồi mới bịa lý do |
| 2. Dữ liệu | Thu thập, làm sạch, ghi nguồn và thời điểm dữ liệu *được biết* (point-in-time) | Raw bất biến + bảng đã chuẩn hoá | Dùng dữ liệu đã bị sửa (restated), thiếu mã đã huỷ niêm yết |
| 3. Feature | Biến đổi thành đại lượng có ý nghĩa, chỉ dùng thông tin có tại thời điểm `t` | Feature store có timestamp | Chuẩn hoá bằng mean/std của cả mẫu (leak) |
| 4. Tín hiệu | Ánh xạ feature → vị thế mong muốn (hướng + kích cỡ) | Hàm `signal(t)` thuần, tái lập được | Quá nhiều tham số tự do |
| 5. Backtest | Mô phỏng khớp lệnh với phí, slippage, funding, độ trễ | Equity curve, nhật ký lệnh | Fill ở giá không thể khớp |
| 6. Kiểm định | Out-of-sample, walk-forward, CPCV, DSR, PBO, stress theo regime | Báo cáo kèm **số lần thử** | Chọn bản đẹp nhất rồi báo cáo như thử một lần |
| 7. Paper trading | Chạy code thật với dữ liệu live, tiền ảo, đủ lâu để gặp vài regime | So sánh fill thực tế với giả định backtest | Bỏ qua bước này vì backtest "đẹp" |
| 8. Live | Vốn nhỏ, tăng dần; có kill-switch và giới hạn lỗ | Nhật ký lệnh, đối soát hằng ngày | Tăng size trước khi đủ mẫu |

Nguyên tắc xuyên suốt:

- **Ghi sổ nghiên cứu**: mỗi lần chạy backtest ghi lại tham số, khoảng dữ liệu, commit hash, kết quả. Số lần thử `N` là đầu vào bắt buộc của deflated Sharpe ratio (mục 2.4).
- **Tách dữ liệu ngay từ đầu**: giữ một đoạn hold-out cuối cùng, chỉ mở một lần khi đã chốt chiến lược.
- **Cùng một code cho backtest và live** (hoặc ít nhất cùng hàm signal) để tránh lệch hành vi.
- **Kỳ vọng thực tế**: phần lớn ý tưởng chết ở bước 5–6. Một kết quả âm được ghi lại cẩn thận vẫn có giá trị.

---

## 2. Backtest đúng cách

### 2.1 Vectorized và event-driven

| | Vectorized | Event-driven |
|---|---|---|
| Cách chạy | Tính trên cả mảng (pandas/numpy/polars): `position.shift(1) * returns` | Vòng lặp theo sự kiện (bar, tick, fill), có trạng thái sổ lệnh và tài khoản |
| Tốc độ | Rất nhanh, quét được hàng nghìn tham số | Chậm hơn nhiều lần |
| Độ chân thực | Thấp: khó mô phỏng lệnh limit, khớp một phần, margin, thanh lý | Cao: mô hình hoá được loại lệnh, queue, latency, funding |
| Rủi ro look-ahead | Cao (quên `shift` là dính) | Thấp hơn vì chỉ thấy dữ liệu đến hiện tại |
| Dùng khi | Sàng lọc ý tưởng, nghiên cứu factor, chiến lược tần suất thấp | Xác nhận trước khi live, chiến lược intraday, có đòn bẩy |
| Ví dụ thư viện | vectorbt, tự viết bằng polars | NautilusTrader, backtrader, LEAN, zipline-reloaded, freqtrade |

Cách làm hợp lý: dùng vectorized để loại ý tưởng tồi, rồi viết lại ý tưởng còn sống bằng engine event-driven sẽ dùng cho live. Nếu hai kết quả lệch nhiều, phần lệch chính là chi phí thực thi mà bản vectorized đã bỏ qua.

### 2.2 Các lỗi kinh điển

| Lỗi | Biểu hiện | Cách phòng |
|---|---|---|
| **Look-ahead bias** | Dùng giá close của bar `t` để vào lệnh tại close `t`; dùng báo cáo tài chính theo ngày kết thúc quý thay vì ngày công bố; `fillna(method="bfill")`; resample sai nhãn (`label`/`closed`) | Tín hiệu tính ở `t`, khớp sớm nhất ở open `t+1`. Lưu `available_at` cho mọi dữ liệu. Test: cắt dữ liệu tại `t`, tín hiệu trước `t` không được đổi |
| **Survivorship bias** | Universe chỉ gồm mã đang niêm yết hoặc coin đang còn giao dịch | Dùng danh sách thành phần theo thời gian, gồm cả mã đã huỷ niêm yết. Với crypto: tính cả coin đã delist |
| **Data snooping / multiple testing** | Thử 500 biến thể, báo cáo bản tốt nhất | Đếm số lần thử, dùng DSR/PBO, giữ hold-out |
| **Overfitting** | Nhiều tham số, kết quả sụp khi đổi tham số một chút | Ít tham số, kiểm tra vùng tham số "cao nguyên" thay vì đỉnh nhọn, walk-forward |
| **Bỏ qua chi phí** | Không tính fee maker/taker, spread, slippage, funding (perp), phí vay (short cổ phiếu), thuế | Mô hình hoá tất cả. Chạy thêm kịch bản chi phí ×2 để xem chiến lược còn sống không |
| **Fill không thực tế** | Lệnh limit khớp ngay khi giá chạm; khớp toàn bộ khối lượng lớn hơn volume của bar; khớp ở giá high/low | Limit chỉ khớp khi giá *xuyên qua*. Giới hạn tỷ lệ tham gia (ví dụ ≤ 1–5% volume bar). Thêm độ trễ |
| **Sai lệch dữ liệu** | Giá chưa điều chỉnh split/cổ tức; múi giờ lẫn lộn; nến chưa đóng bị coi là đã đóng | Chuẩn hoá UTC, lưu cả giá raw và adjusted, bỏ bar cuối chưa đóng |
| **Regime đơn** | Backtest chỉ trong một thị trường tăng | Kiểm tra theo từng giai đoạn, gồm cả giai đoạn xấu |
| **Bỏ qua giới hạn thị trường** | Biên độ trần/sàn, T+ (ví dụ thị trường Việt Nam), không short được, lô tối thiểu | Mã hoá ràng buộc vào engine |

### 2.3 Kiểm định theo thời gian

**Walk-forward**: tối ưu trên cửa sổ train, đánh giá trên cửa sổ test liền sau, trượt tới và nối các đoạn test.

- *Rolling* (cửa sổ train cố định độ dài) phù hợp khi quan hệ thay đổi theo thời gian; *anchored/expanding* (train lớn dần) phù hợp khi cần nhiều mẫu.
- Hạn chế: chỉ cho **một** đường lịch sử, kết quả phụ thuộc cách chia cửa sổ.

**Purged & embargoed K-fold** (López de Prado, *AFML* ch. 7): K-fold thường làm rò rỉ thông tin vì nhãn của mẫu train chồng thời gian với mẫu test.

- *Purging*: loại khỏi train mọi mẫu có khoảng nhãn `[t0, t1]` giao với khoảng test.
- *Embargo*: loại thêm một đoạn train ngay **sau** test (thường ~1% số mẫu) để chặn rò rỉ qua tự tương quan.

**Combinatorial purged CV (CPCV)** (*AFML* ch. 12): chia thành `N` nhóm, mỗi lần lấy `k` nhóm làm test, có purge và embargo.

- Số cách chia: `C(N, k)`.
- Số đường backtest tái tạo được: `φ = (k / N) · C(N, k)`. Ví dụ `N = 6, k = 2` → 15 cách chia, 5 đường.
- Lợi ích: có **phân phối** Sharpe thay vì một con số.

### 2.4 Hiệu chỉnh cho multiple testing

**Deflated Sharpe ratio (DSR)** — Bailey & López de Prado (2014). Ý tưởng: thử `N` chiến lược thì Sharpe lớn nhất sẽ dương ngay cả khi tất cả đều vô dụng. DSR hỏi xác suất Sharpe thật > 0 sau khi trừ đi kỳ vọng của "cái lớn nhất trong N lần thử".

```
SR0 = sqrt(V[SR_n]) · [ (1 − γ) · Φ⁻¹(1 − 1/N) + γ · Φ⁻¹(1 − 1/(N·e)) ]

DSR = Φ( (SR − SR0) · sqrt(T − 1) / sqrt(1 − γ3·SR + ((γ4 − 1)/4)·SR²) )
```

- `SR`: Sharpe **chưa annualize** (theo tần suất quan sát); `T`: số quan sát.
- `V[SR_n]`: phương sai của Sharpe giữa các lần thử; `N`: số lần thử *độc lập* (nếu các biến thể tương quan cao, số hiệu dụng nhỏ hơn số đếm được).
- `γ ≈ 0.5772` (hằng số Euler–Mascheroni); `γ3`, `γ4`: skewness và kurtosis của return.
- Đọc kết quả: DSR > 0.95 thường được coi là ngưỡng đáng tin; dưới đó nên coi là chưa chứng minh được.

**Probability of backtest overfitting (PBO)** — Bailey, Borwein, López de Prado & Zhu (2017), dùng CSCV (combinatorially symmetric cross-validation):

1. Lập ma trận return `T × N` (N cấu hình), chia thành `S` khối theo thời gian.
2. Với mỗi cách chọn `S/2` khối làm in-sample: tìm cấu hình tốt nhất IS, xem thứ hạng của nó OOS.
3. PBO = tỷ lệ số lần cấu hình thắng IS rơi xuống **dưới trung vị** OOS.

PBO gần 0.5 nghĩa là việc chọn theo backtest không hơn tung đồng xu.

**Ngưỡng thống kê khi thử nhiều**: Harvey, Liu & Zhu (2016) lập luận một factor mới nên có t-stat > 3.0 thay vì 2.0. Các hiệu chỉnh thông dụng: Bonferroni (chặt), Holm, Benjamini–Hochberg (kiểm soát false discovery rate).

**Kiểm tra thực dụng**, rẻ và hiệu quả:

- Xáo trộn tín hiệu hoặc dịch tín hiệu ngẫu nhiên: Sharpe phải về gần 0.
- Chạy trên dữ liệu ngẫu nhiên (random walk): nếu vẫn "có lãi" thì engine có bug.
- Nhiễu tham số ±10–20%: kết quả không được sụp.
- Đổi sàn/đổi thị trường tương tự: edge có lặp lại không.

### 2.5 Triple-barrier labeling và meta-labeling

**Triple-barrier** (*AFML* ch. 3): thay vì gán nhãn theo return sau `h` bar cố định, đặt ba rào cho mỗi sự kiện vào lệnh:

- Rào trên (profit-taking) và rào dưới (stop-loss), độ rộng tính theo volatility hiện tại (ví dụ bội số của EWM std hoặc ATR).
- Rào dọc (hết thời gian nắm giữ).

Nhãn là rào chạm trước: `+1`, `−1`, hoặc `0`/dấu của return nếu chạm rào dọc. Vì các nhãn chồng thời gian nên phải dùng *sample weights theo uniqueness* và purged CV.

**Meta-labeling**: tách hai quyết định.

1. Mô hình sơ cấp (rule đơn giản hoặc mô hình có recall cao) quyết định **hướng**.
2. Mô hình thứ cấp (classifier) dự đoán xác suất tín hiệu sơ cấp **đúng**; xác suất này dùng để lọc lệnh và quyết định **size**.

Lợi ích: cải thiện precision mà không phá logic gốc, và cho một cách sizing có cơ sở. Rủi ro: thêm một tầng để overfit, nên vẫn phải qua CPCV/DSR.

---

## 3. Metric và cách annualize

Ký hiệu: `r_t` là return mỗi kỳ, `P` là số kỳ mỗi năm, `r_f` là lãi suất phi rủi ro mỗi kỳ, `V_t` là giá trị tài khoản.

| Metric | Công thức | Ghi chú |
|---|---|---|
| **CAGR** | `(V_end / V_start)^(1/years) − 1` | `years` tính theo lịch thực (ngày / 365.25) |
| **Volatility năm** | `std(r) · sqrt(P)` | Giả định return i.i.d.; sai khi có tự tương quan |
| **Sharpe** | `mean(r − r_f) / std(r − r_f) · sqrt(P)` | Nói rõ `r_f` dùng là gì; với crypto nhiều người dùng 0, cần ghi chú |
| **Sortino** | `mean(r − MAR) / DD · sqrt(P)`, `DD = sqrt(mean(min(r − MAR, 0)²))` | Downside deviation chia cho **toàn bộ** số kỳ, không chỉ kỳ âm |
| **Max drawdown** | `min_t (V_t / max_{s≤t} V_s − 1)` | Phụ thuộc tần suất lấy mẫu: dữ liệu daily che drawdown intraday |
| **Calmar** | `CAGR / |MaxDD|` | Thường tính trên 36 tháng gần nhất |
| **Win rate** | `số lệnh lãi / tổng số lệnh` | Vô nghĩa nếu không kèm payoff ratio |
| **Profit factor** | `tổng lãi gộp / |tổng lỗ gộp|` | > 1 là có lãi; rất cao với ít lệnh thường là overfit |
| **Expectancy** | `p · avg_win − (1 − p) · avg_loss` | Có thể chuẩn hoá theo rủi ro mỗi lệnh (R-multiple) |
| **Turnover** | `Σ |Δw_t| / 2` mỗi kỳ, rồi nhân `P` | Nhân với chi phí một chiều để ước tính cost drag |
| **Exposure** | Tỷ lệ thời gian có vị thế; gross = `Σ|w|`, net = `Σw` | Sharpe cao với exposure 5% khác hẳn với 100% |
| **Beta** | `cov(r, r_m) / var(r_m)` | `r_m` là benchmark phù hợp (chỉ số cho cổ phiếu, BTC cho altcoin) |
| **Alpha (Jensen)** | `mean(r − r_f) − β · mean(r_m − r_f)`, nhân `P` | Lấy từ hệ số chặn của hồi quy; xem cả t-stat |
| **Information ratio** | `mean(r − r_b) / std(r − r_b) · sqrt(P)` | Mẫu số là tracking error |

### Hệ số annualize `P`

| Tần suất | Cổ phiếu Mỹ | Crypto 24/7 |
|---|---|---|
| Daily | 252 | 365 |
| Weekly | 52 | 52 |
| 4h | ≈ 252 × 6.5 / 4 ≈ 410 (ít dùng) | 365 × 6 = 2 190 |
| 1h | ≈ 252 × 6.5 = 1 638 | 365 × 24 = 8 760 |
| 1m | ≈ 252 × 390 = 98 280 | 525 600 |

Lưu ý:

- Thị trường khác có số phiên và giờ giao dịch khác (ví dụ Việt Nam có nghỉ trưa và khoảng 250 phiên/năm). Cách chắc nhất: **đếm số bar thực tế mỗi năm trong dữ liệu**.
- So sánh Sharpe crypto với cổ phiếu phải cùng quy ước. Dùng `sqrt(252)` cho chuỗi daily crypto làm Sharpe thấp đi khoảng 17% so với `sqrt(365)`.
- Annualize từ dữ liệu tần suất cao bằng `sqrt(P)` thổi phồng Sharpe khi return có tự tương quan dương. Lo (2002) đưa hệ số hiệu chỉnh; cách đơn giản là tính Sharpe trên return daily đã gộp.
- Return intraday cổ phiếu có khoảng trống qua đêm; phải quyết định có tính overnight return hay không và ghi rõ.
- Sharpe ước lượng có sai số chuẩn xấp xỉ `sqrt((1 + SR²/2) / T)` (theo đơn vị mỗi kỳ). Với 1 năm dữ liệu daily, khoảng tin cậy rất rộng.

---

## 4. Quản trị rủi ro và position sizing

### 4.1 Các phương pháp sizing

| Phương pháp | Công thức | Ưu điểm | Nhược điểm |
|---|---|---|---|
| **Fixed fractional** | `qty = (equity · risk%) / |entry − stop|` | Đơn giản, lỗ mỗi lệnh có trần | Bỏ qua tương quan giữa các vị thế; gap vượt stop |
| **Volatility targeting** | `w_t = σ_target / σ̂_t` (cắt ở trần đòn bẩy) | Ổn định rủi ro qua các regime | Phụ thuộc ước lượng `σ̂`; tăng size đúng lúc vol thấp trước cú sốc |
| **Kelly** | Rời rạc: `f* = p − (1 − p)/b`. Liên tục: `f* = μ / σ²` | Tối đa hoá tăng trưởng log dài hạn | Cực nhạy với sai số ước lượng `μ`; drawdown rất sâu |
| **Fractional Kelly** | `f = c · f*`, `c` thường 0.25–0.5 | Giữ phần lớn tăng trưởng, giảm mạnh biến động | Vẫn cần ước lượng edge |
| **ATR stop / ATR sizing** | `stop = entry − k · ATR(n)`; `qty = (equity · risk%) / (k · ATR)` | Stop thích ứng với biến động | `k`, `n` là tham số dễ overfit |

Ghi chú về Kelly: `b` là tỷ lệ lãi/lỗ trung bình, `p` là xác suất thắng. Half-Kelly giữ khoảng 75% tốc độ tăng trưởng với một nửa volatility. Vì `μ` ước lượng từ backtest hầu như luôn bị thổi phồng, full Kelly trên số liệu backtest gần như chắc chắn là over-bet.

### 4.2 VaR và CVaR

- **VaR(α)**: mức lỗ không bị vượt với xác suất `α` trong một kỳ. Ba cách tính: historical (phân vị thực nghiệm), parametric (`z_α · σ − μ`, giả định chuẩn), Monte Carlo.
- **CVaR / Expected Shortfall**: lỗ trung bình *khi đã vượt* VaR: `E[L | L ≥ VaR_α]`. CVaR là thước đo coherent (subadditive) còn VaR thì không, và phản ánh đuôi tốt hơn.
- Return crypto có đuôi dày: VaR parametric chuẩn đánh giá thấp rủi ro. Nên dùng historical, hoặc mô hình GARCH với phân phối Student-t (thư viện `arch`).

### 4.3 Giới hạn drawdown và kiểm soát vận hành

- Giới hạn theo tầng: lỗ tối đa mỗi lệnh, mỗi ngày, mỗi tuần, và drawdown tổng (ví dụ giảm nửa size khi DD chạm mức A, dừng hẳn khi chạm mức B). Mức cụ thể là lựa chọn cá nhân, cần viết ra **trước**.
- Giới hạn tập trung: trần cho một mã, một ngành, một sàn; trần gross và net exposure.
- Kill-switch: dừng khi dữ liệu trễ, khi vị thế thực tế lệch vị thế mong muốn, khi lỗi API lặp lại.
- Rủi ro đối tác (đặc biệt crypto): không để toàn bộ vốn trên một sàn; API key không bật quyền rút tiền.
- Toán học phục hồi: lỗ 20% cần +25% để hoà, lỗ 50% cần +100%.

### 4.4 Đòn bẩy và thanh lý trong futures crypto

Khái niệm:

- **Initial margin** ≈ `notional / leverage`; **maintenance margin** = `notional × MMR` (MMR theo bậc vị thế, vị thế càng lớn MMR càng cao).
- **Mark price** (không phải last price) dùng để tính PnL chưa thực hiện và kích hoạt thanh lý.
- **Isolated** (margin riêng cho từng vị thế) và **cross** (dùng chung số dư, một vị thế xấu kéo cả tài khoản).

Giá thanh lý xấp xỉ cho isolated margin, hợp đồng linear, bỏ qua phí và funding:

```
Long : P_liq ≈ P_entry · (1 − 1/L + MMR)
Short: P_liq ≈ P_entry · (1 + 1/L − MMR)
```

Ví dụ minh hoạ với `MMR = 0.5%`: long 10x bị thanh lý khi giá giảm khoảng 9.5%; long 20x khi giảm khoảng 4.5%. Công thức chính xác khác nhau theo sàn và loại hợp đồng (inverse/coin-margined có payoff phi tuyến), phải đọc tài liệu của sàn đang dùng.

Những điểm hay bị bỏ sót:

- **Funding**: perp trả/nhận funding định kỳ (thường 8h, một số sàn/mã 1h hoặc 4h). Funding 0.01%/8h tương đương khoảng 11%/năm trên notional; ở đòn bẩy cao, chi phí này tính trên vốn rất lớn.
- **Phí thanh lý, quỹ bảo hiểm và ADL** (auto-deleveraging): vị thế đang lãi có thể bị đóng cưỡng bức khi thị trường cực đoan.
- **Đòn bẩy hiệu dụng** = `tổng notional / equity`. Đây mới là con số cần quản lý, không phải con số cài trên sàn.
- Backtest có đòn bẩy phải mô phỏng thanh lý theo giá intrabar (high/low), nếu không sẽ sống sót giả tạo qua các cú wick.

---

## 5. Các họ chiến lược

| Họ | Ý tưởng | Dữ liệu cần | Rủi ro chính |
|---|---|---|---|
| **Momentum / trend following** | Xu hướng có quán tính. *Time-series* (mua tài sản đang tăng so với chính nó) hoặc *cross-sectional* (mua nhóm mạnh nhất, bán nhóm yếu nhất) | OHLCV daily/4h, universe đầy đủ theo thời gian | Whipsaw khi đi ngang; momentum crash khi đảo chiều nhanh; win rate thấp, cần kỷ luật |
| **Mean reversion** | Giá lệch khỏi mức cân bằng ngắn hạn rồi quay lại (z-score, Bollinger, RSI ngắn, đảo chiều qua đêm) | OHLCV tần suất cao hơn, dữ liệu spread | "Bắt dao rơi" khi regime đổi; lãi nhỏ đều, lỗ lớn hiếm (skew âm); rất nhạy chi phí |
| **Pairs / stat-arb / cointegration** | Tổ hợp tuyến tính của các tài sản là chuỗi dừng; giao dịch độ lệch của spread | Giá đồng bộ thời gian; kiểm định Engle–Granger/Johansen; ước lượng half-life (OU) | Quan hệ gãy vĩnh viễn; hedge ratio trôi; phí vay và khả năng short; đông người cùng làm |
| **Market making** | Đặt lệnh hai phía, ăn spread và rebate, quản lý tồn kho (Avellaneda–Stoikov) | L2/L3 order book, trades tick, độ trễ thực tế | Adverse selection; tồn kho khi giá chạy một chiều; cần hạ tầng và phí ưu đãi |
| **Funding / basis arbitrage** | Long spot + short perp để nhận funding dương; hoặc cash-and-carry với futures có kỳ hạn | Lịch sử funding rate, basis, phí, lãi vay margin | Funding đổi dấu; thanh lý chân short khi giá tăng mạnh; rủi ro sàn; vốn nằm ở hai nơi |
| **Factor investing (cổ phiếu)** | Nắm rổ cổ phiếu theo đặc tính có premium dài hạn: value, quality, momentum, size, low-vol | Báo cáo tài chính point-in-time, giá adjusted, vốn hoá, danh sách delist | Factor thua kéo dài nhiều năm; crowding; turnover; premium giảm sau khi công bố |
| **Machine learning** | Gradient boosting (XGBoost/LightGBM) dự đoán return hoặc nhãn triple-barrier từ nhiều feature | Feature point-in-time, nhãn không chồng lấn hoặc có sample weight | Tỷ lệ tín hiệu/nhiễu rất thấp; overfit; non-stationarity; leak qua CV thường |

Ghi chú cho ML:

- Mô hình cây trên dữ liệu bảng thường là baseline mạnh hơn deep learning khi dữ liệu ít và nhiễu.
- **Feature importance**: MDI (có sẵn trong cây, thiên vị feature nhiều giá trị), MDA/permutation importance (đo OOS, bị pha loãng khi feature tương quan), SHAP (giải thích từng dự đoán). Với feature tương quan, nên gom cụm rồi đo importance theo cụm (*clustered feature importance*).
- Đánh giá bằng purged/CPCV, không bằng `train_test_split` ngẫu nhiên.
- Metric phân loại (accuracy, AUC) không phải PnL. Luôn kiểm tra lại bằng backtest có chi phí.
- Làm cho chuỗi dừng mà giữ bộ nhớ: fractional differentiation (*AFML* ch. 5).

---

## 6. Microstructure cơ bản

- **Order book**: danh sách lệnh limit theo mức giá. L1 = best bid/ask; L2 = khối lượng gộp theo mức giá; L3 = từng lệnh. Khớp theo ưu tiên giá rồi thời gian, nên vị trí trong hàng đợi có giá trị.
- **Spread**: `ask − bid`. Một lệnh market trả nửa spread so với mid. *Effective spread* đo trên giá khớp thực; *realized spread* trừ đi biến động giá sau khớp (phần còn lại là adverse selection).
- **Market impact**: lệnh lớn đẩy giá. Quy luật kinh nghiệm *square-root*: `impact ≈ Y · σ · sqrt(Q / V)` với `Q` là khối lượng lệnh, `V` là volume ngày, `Y` là hằng số cỡ 1. Impact có phần tạm thời và phần vĩnh viễn (Almgren–Chriss).
- **Maker / taker fee**: maker thêm thanh khoản (phí thấp, đôi khi rebate), taker lấy thanh khoản (phí cao hơn). Biểu phí theo bậc volume và khác nhau theo sàn; luôn lấy từ trang phí của sàn. Lệnh *post-only* đảm bảo làm maker nhưng có thể không khớp.
- **Latency**: từ lúc sự kiện xảy ra đến lúc lệnh vào sổ gồm trễ feed, xử lý, mạng, matching engine. HFT đo bằng micro giây và dùng co-location; bot cá nhân qua REST/WebSocket thường ở mức chục đến trăm mili giây.

### Vì sao "HFT thật" khác với dự đoán nến 1h/4h bằng LLM

| | HFT / market making thật | Dự đoán nến 1h/4h (kể cả bằng LLM) |
|---|---|---|
| Nguồn edge | Tốc độ, vị trí hàng đợi, rebate, mô hình hoá order flow | Dự báo hướng giá trong vài giờ |
| Dữ liệu | Tick, L2/L3, dung lượng lớn | OHLCV, tin tức, chỉ báo |
| Thời gian nắm giữ | Mili giây đến phút | Giờ đến ngày |
| Hạ tầng | Co-location, C++/Rust/FPGA, phí bậc cao | Một máy chủ nhỏ, API công khai |
| Độ trễ suy luận | Phải nhỏ hơn mili giây | LLM mất hàng giây: **không dùng được** cho HFT |
| Số mẫu độc lập | Hàng triệu lệnh, kiểm định thống kê nhanh | Vài nghìn bar mỗi năm, khó phân biệt edge với may mắn |
| Rủi ro phương pháp | Adverse selection, lỗi hệ thống | Overfit, leak, và với LLM là **training-data leakage** |

Điểm cần nhớ khi dùng LLM cho dự đoán:

- LLM đã "đọc" lịch sử thị trường trong dữ liệu huấn luyện. Backtest trên giai đoạn trước knowledge cutoff của mô hình là look-ahead trá hình. Chỉ kết quả **sau cutoff** mới có ý nghĩa.
- Đầu ra không tất định (non-deterministic) và thay đổi theo phiên bản mô hình: phải ghi lại model ID, prompt, và lưu nguyên văn output để tái lập.
- LLM hữu ích hơn ở vai trò khác: trích xuất cấu trúc từ văn bản (báo cáo, tin tức, filing), tóm tắt, sinh giả thuyết, viết và review code. Tín hiệu số vẫn nên qua mô hình thống kê có kiểm định.
- Ở khung 1h/4h, chi phí giao dịch và chất lượng kiểm định quan trọng hơn tốc độ. Đây là giao dịch tần suất trung bình, không phải HFT.

---

## 7. So sánh thư viện Python

Phiên bản và ngày phát hành lấy từ PyPI ngày 2026-11-13; ngày push gần nhất và license lấy từ GitHub API cùng ngày.

### 7.1 Dữ liệu, tính toán, chỉ báo

| Thư viện | Mục đích | Ưu | Nhược | Bảo trì (2026-11-13) | License |
|---|---|---|---|---|---|
| **pandas** | DataFrame chuẩn của hệ sinh thái | Mọi thư viện quant đều nhận pandas; time-series index mạnh | Chậm và tốn RAM với dữ liệu lớn; bản 3.x có thay đổi phá vỡ (copy-on-write) | 3.1.1 (2026-11-04), tích cực | BSD-3 |
| **polars** | DataFrame cột, lazy, đa luồng (Rust) | Nhanh hơn nhiều, đọc Parquet theo kiểu streaming, API rõ ràng | Ít thư viện quant nhận trực tiếp, hay phải `.to_pandas()` | 2.1.0 (2026-10-25), tích cực | MIT |
| **numpy** | Mảng số, đại số tuyến tính | Nền tảng của tất cả | Không có nhãn thời gian | 2.5.4 (2026-10-10), tích cực | BSD-3 |
| **TA-Lib** (python wrapper) | Hơn 150 chỉ báo kỹ thuật, lõi C | Nhanh, chuẩn tham chiếu | Phụ thuộc thư viện C (các bản gần đây có wheel dựng sẵn) | 0.8.3 (2026-10-28), tích cực | BSD-2 |
| **pandas-ta** | Chỉ báo dạng pandas extension | API tiện, nhiều chỉ báo | Tình trạng không rõ: repo GitHub gốc trả 404, tên miền tài liệu không phân giải được trong ngày tra cứu | 0.4.71b0 (2025-09-14, beta). **[chưa xác minh]** tương lai dự án | **[chưa xác minh]** (trang license không mở được) |
| **pandas-ta-classic** | Fork cộng đồng của pandas-ta | Đang được duy trì, cùng kiểu API | Fork nhỏ, ít người dùng hơn | 0.9.0 (2026-10-28), tích cực | MIT |

### 7.2 Backtest và giao dịch

| Thư viện | Mục đích | Ưu | Nhược | Bảo trì | License |
|---|---|---|---|---|---|
| **vectorbt** (bản mở) | Backtest vectorized, quét tham số | Rất nhanh (numba; có thêm gói `vectorbt-rust`), phân tích portfolio phong phú | Đường học dốc; mô phỏng thực thi kém chi tiết hơn event-driven | 1.2.1 (2026-11-11), tích cực | **Apache 2.0 + Commons Clause** ("fair code": không được bán sản phẩm/dịch vụ mà giá trị chủ yếu đến từ phần mềm) |
| **VectorBT PRO** | Bản trả phí, nhiều tính năng hơn | Cập nhật thường xuyên, repo riêng, Discord | Trả phí, mã đóng với công chúng | Ví dụ cài đặt trên trang ghi v2026.10.5 | Độc quyền. Giá trên trang: 25 USD/tháng, 225 USD/năm, 500 USD trọn đời |
| **backtrader** | Event-driven cổ điển | Tài liệu và ví dụ rất nhiều | Chậm; **không còn phát triển thực chất** | PyPI 1.9.78.123 (2023-04-19); push cuối 2024-08-19 | GPL-3.0 |
| **backtesting.py** | Backtest nhẹ cho một tài sản | API tối giản, biểu đồ đẹp | Không hỗ trợ portfolio đa tài sản đúng nghĩa; AGPL | 0.6.6 (2026-07-22); push cuối 2026-08-05 | AGPL-3.0 |
| **zipline-reloaded** | Event-driven kiểu Quantopian, cổ phiếu | Pipeline API cho factor, xử lý corporate action | Nạp dữ liệu (bundle) rườm rà; thiên về cổ phiếu Mỹ daily | 3.2.1 (2026-10-25), tích cực | Apache-2.0 |
| **NautilusTrader** | Engine event-driven hiệu năng cao (lõi Rust), backtest và live chung code | Mô phỏng sổ lệnh, loại lệnh, latency; nhiều adapter sàn crypto | Phức tạp, API còn thay đổi | 1.231.0 trên PyPI (2026-08-02); repo push 2026-11-13 | LGPL-3.0 |
| **freqtrade** | Bot crypto hoàn chỉnh: backtest, hyperopt, dry-run, live | Sẵn dùng, cộng đồng lớn, có FreqAI | Khuôn chiến lược cố định; hyperopt dễ dẫn tới overfit | 2026.10 (2026-10-30), tích cực | GPL-3.0 |
| **hummingbot** | Market making và arbitrage crypto | Nhiều connector CEX/DEX, chiến lược MM có sẵn | Nặng; lợi nhuận MM phụ thuộc phí và hạ tầng | 20260922 (PyPI 2026-10-07), tích cực | Apache-2.0 |
| **QuantConnect LEAN** | Engine đa tài sản (C#, API Python), chạy local hoặc cloud | Dữ liệu và broker tích hợp, mô hình thực thi chi tiết | Nặng (Docker); dữ liệu chất lượng nằm trên cloud trả phí | `lean` CLI 1.0.233 (2026-10-27); repo push 2026-11-13 | Apache-2.0 |
| **ccxt** | API thống nhất cho hơn 100 sàn crypto (REST + WebSocket) | Chuẩn de facto, cập nhật liên tục | Khác biệt giữa các sàn vẫn rò ra; phải tự xử lý rate limit | 4.5.92 (2026-11-04), tích cực | MIT |

### 7.3 Phân tích hiệu suất, portfolio, thống kê, ML

| Thư viện | Mục đích | Ưu | Nhược | Bảo trì | License |
|---|---|---|---|---|---|
| **quantstats** | Tearsheet và metric hiệu suất | Một dòng ra báo cáo HTML | Mặc định 252 kỳ/năm: phải truyền `periods` cho crypto; nên đối chiếu công thức | 0.0.86 (2026-09-27), tích cực | Apache-2.0 |
| **pyfolio / empyrical** (gốc Quantopian) | Tearsheet / metric | Từng là chuẩn | **Bỏ hoang**: pyfolio 0.9.2 (2019), empyrical 0.5.5 (2020) | Không dùng | Apache-2.0 |
| **pyfolio-reloaded / empyrical-reloaded** | Fork được duy trì | Tương thích pandas/numpy mới | Ít tính năng mới | 0.10.2 / 0.7.2 (đều 2026-11-02), tích cực | Apache-2.0 |
| **Riskfolio-Lib** | Tối ưu portfolio: mean-risk, CVaR, risk parity, HRC/NCO | Rất nhiều thước đo rủi ro | Phụ thuộc solver (cvxpy), API rộng | 7.4.1 (2026-11-04), tích cực | BSD-3 |
| **PyPortfolioOpt** | Mean-variance, Black-Litterman, HRP | Dễ học | Ít mô hình hơn Riskfolio; phát hành thưa | 1.6.0 (2026-02-26); repo `PyPortfolio/PyPortfolioOpt` push 2026-07-07 | MIT |
| **statsmodels** | Hồi quy, time series (ARIMA, VAR), kiểm định (ADF, cointegration) | Thống kê suy diễn đầy đủ | API không đồng nhất | 0.15.0 (2026-08-30), tích cực | BSD-3 |
| **arch** | ARCH/GARCH, bootstrap, unit root | Chuẩn cho mô hình volatility | Phạm vi hẹp | 9.0.0 (2026-11-11), tích cực | NCSA |
| **scikit-learn** | ML cổ điển, pipeline, CV | Chuẩn mực | Không có purged CV sẵn, phải tự viết splitter | 1.9.1 (2026-09-10), tích cực | BSD-3 |
| **xgboost** | Gradient boosting | Mạnh trên dữ liệu bảng, hỗ trợ GPU | Nhiều hyperparameter | 3.4.1 (2026-08-15), tích cực | Apache-2.0 |
| **lightgbm** | Gradient boosting | Nhanh, ít RAM | Dễ overfit với dữ liệu nhỏ | 4.7.0 (2026-07-18), tích cực | MIT (theo repo; PyPI không ghi trường license) |
| **mlfinlab** (Hudson & Thames) | Cài đặt các kỹ thuật trong *AFML* | Đầy đủ, có tài liệu | **Mã đóng, trả phí**; không có trên PyPI; repo công khai chỉ để nhận issue (push cuối 2023-10-02) | Giá **[chưa xác minh]** | Độc quyền |
| **mlfinpy** | Bản mở thay thế một phần mlfinlab | MIT | Phát hành cuối 0.1.2 (2024-10-09): gần như dừng | Thấp | MIT |

Với các kỹ thuật López de Prado (purged K-fold, CPCV, triple-barrier, DSR), phương án an toàn về license và bảo trì là **tự cài đặt** từ sách; mỗi kỹ thuật chỉ vài chục dòng. `skfolio` (1.12.10, 2026-11-12, BSD-3) có sẵn `CombinatorialPurgedCV` cho bài toán portfolio. **[chưa xác minh]** chi tiết API hiện tại.

### 7.4 Lưu trữ

| Công nghệ | Mục đích | Ưu | Nhược | Bảo trì | License |
|---|---|---|---|---|---|
| **Parquet** (qua pyarrow) | Định dạng file cột, nén | Nhỏ, nhanh, đọc được từ mọi công cụ; partition theo thư mục | Không sửa tại chỗ, ghi thêm phải ghi file mới | pyarrow 26.0.1 (2026-11-03) | Apache-2.0 |
| **DuckDB** | OLAP nhúng trong tiến trình (như SQLite cho phân tích) | Truy vấn SQL thẳng trên Parquet, `ASOF JOIN`, không cần server | Một tiến trình ghi tại một thời điểm; không phải DB phục vụ nhiều client | 2.0.0 (2026-10-21), tích cực | MIT |
| **TimescaleDB** (công ty đổi tên thành Tiger Data từ 2025-06-17) | Extension time-series cho PostgreSQL | SQL đầy đủ, continuous aggregate, nén, nhiều client ghi đồng thời | Phải vận hành Postgres | Repo push 2026-11-13 | Hai bản: Apache-2.0 và Community (Tiger Data License, cấm cung cấp dạng DBaaS) |
| **QuestDB** | DB time-series cột, nạp tốc độ cao | Ingest tick rất nhanh, SQL có `ASOF JOIN`, `SAMPLE BY` | Hệ sinh thái nhỏ hơn Postgres | Repo push 2026-11-13 | Apache-2.0 |

Nguồn mục 7: <https://pypi.org/> (JSON API từng gói), <https://github.com/polakowo/vectorbt/blob/master/LICENSE.md>, <https://vectorbt.pro/>, <https://github.com/hudson-and-thames/mlfinlab>, <https://www.tigerdata.com/legal/licenses>, <https://www.tigerdata.com/docs/get-started/choose-your-path/timescaledb-editions>, <https://github.com/xgboosted/pandas-ta-classic>.

---

## 8. Nguồn dữ liệu

Giá và giới hạn thay đổi thường xuyên. Cột "Giới hạn" ghi theo trang chính thức khi mở được; số từ nguồn thứ cấp có ghi chú.

### 8.1 Cổ phiếu (Mỹ và quốc tế)

| Nguồn | Loại dữ liệu | Miễn phí / trả phí | Giới hạn | Cách truy cập |
|---|---|---|---|---|
| **yfinance** (Yahoo Finance, không chính thức) | OHLCV, cổ tức, split, một phần báo cáo tài chính | Miễn phí | Không có SLA, hay hỏng khi Yahoo đổi trang. README ghi dữ liệu Yahoo chỉ dành cho **mục đích cá nhân**, cần đọc điều khoản của Yahoo | `pip install yfinance` (1.8.0, 2026-11-03) |
| **Alpha Vantage** | OHLCV, fundamentals, forex, crypto, chỉ báo, kinh tế | Free + trả phí | Free: **25 request/ngày** (nguồn thứ cấp: kèm 5/phút). Trả phí từ 49.99 USD/tháng cho 75 request/phút, không giới hạn theo ngày | REST + API key. <https://www.alphavantage.co/premium/> |
| **Polygon.io → Massive** (đổi tên 2025-10-30, key và endpoint cũ vẫn chạy) | Trades/quotes tick, aggregates, options, forex, crypto | Free + trả phí | Free: 5 call/phút, dữ liệu end-of-day, khoảng 2 năm lịch sử. Stocks Starter khoảng 29 USD/tháng. **[chưa xác minh]** trên trang chính thức (số từ nguồn thứ cấp, có nguồn mâu thuẫn) | REST, WebSocket, flat files. <https://massive.com/pricing> |
| **Tiingo** | EOD, IEX intraday, fundamentals, news, crypto, forex | Free + trả phí | Free: 50 request/giờ, 1 000/ngày, 1 GB băng thông/tháng. Trần 500 mã/tháng **[chưa xác minh]**. Chỉ dùng nội bộ | REST + token. <https://api.tiingo.com/documentation> |
| **Finnhub** | Quote, news, fundamentals cơ bản, filings, WebSocket | Free + trả phí | Free: 60 call/phút. Nguồn thứ cấp: stock candles là premium, WebSocket 50 mã, chỉ dùng cá nhân | REST, WebSocket; `finnhub-python` 2.4.30. <https://finnhub.io/pricing> |
| **Financial Modeling Prep** | Báo cáo tài chính, ratios, DCF, giá EOD | Free + trả phí | Free: 250 request/ngày, dữ liệu EOD. Starter khoảng 22 USD/tháng (trả theo năm) | REST + API key. <https://site.financialmodelingprep.com/pricing-plans> |
| **SEC EDGAR** | Filing gốc (10-K, 10-Q, 8-K), XBRL company facts | Miễn phí, không cần key | Tối đa **10 request/giây**; phải khai báo `User-Agent` | REST JSON tại `data.sec.gov`, file bulk hằng đêm. <https://www.sec.gov/os/accessing-edgar-data> |
| **Stooq** | EOD nhiều thị trường, chỉ số, forex | Miễn phí | Từ đầu 2026 truy cập CSV bằng script đòi API key lấy qua CAPTCHA; reader Stooq của `pandas-datareader` hỏng. **[chưa xác minh]** bằng nguồn chính thức | Tải tay gói bulk tại <https://stooq.com/db/h/>. Xem <https://github.com/pydata/pandas-datareader/issues/1012> |

Lưu ý về `User-Agent` của SEC: SEC yêu cầu kèm thông tin liên hệ. Đây là dữ liệu cá nhân gửi ra ngoài, nên cân nhắc dùng một địa chỉ email riêng cho mục đích này.

### 8.2 Chứng khoán Việt Nam

| Nguồn | Loại dữ liệu | Miễn phí / trả phí | Giới hạn | Cách truy cập |
|---|---|---|---|---|
| **vnstock** (thế hệ 6) | Lớp kết nối và chuẩn hoá dữ liệu chứng khoán Việt Nam; **không** tự cung cấp dữ liệu | Bản Cộng đồng (cá nhân, học tập, nghiên cứu) + các gói Bronze/Silver/Golden/Diamond | Không còn trên PyPI; phát hành gói dựng sẵn qua kho riêng. Các bản trước thế hệ 6 **ngừng hoạt động từ 2026-11-10**. Người dùng tự chọn nguồn và dùng khoá do nguồn cấp. Giá các gói và danh sách nguồn hỗ trợ **[chưa xác minh]** | <https://vnstocks.com/onboard>, giấy phép: <https://vnstocks.com/onboard/giay-phep-su-dung>, repo lịch sử: <https://github.com/thinh-vu/vnstock> |
| **SSI FastConnect Data** | Realtime và EOD cơ sở, phái sinh | Cần tài khoản giao dịch SSI; phí **[chưa xác minh]** | Đăng ký tại quầy, qua môi giới hoặc bưu điện; kỳ hạn dịch vụ 1 năm | REST + streaming. <https://guide.ssi.com.vn/ssi-products/tieng-viet/fastconnect-data> |
| **TCBS**, **DNSE** và các CTCK khác | Giá, dữ liệu doanh nghiệp | **[chưa xác minh]** | Không tìm được thông tin chính thức hiện hành về API dữ liệu công khai | Kiểm tra trực tiếp trang nhà cung cấp |

Điểm quan trọng: các endpoint "công khai" của website CTCK không phải API được cấp phép. Tài liệu vnstock thế hệ 6 cũng nói rõ không cổ vũ khai thác giao diện công khai của website. Phương án bền vững là API chính thức của CTCK nơi có tài khoản.

### 8.3 Vĩ mô, lãi suất, vàng, forex

| Nguồn | Loại dữ liệu | Miễn phí / trả phí | Giới hạn | Cách truy cập |
|---|---|---|---|---|
| **FRED** (St. Louis Fed) | Hơn 800 000 chuỗi kinh tế Mỹ và quốc tế | Miễn phí, cần API key | Khoảng 120 request/phút (nguồn thứ cấp, **[chưa xác minh]** trên trang chính thức) | REST; `fredapi` 0.5.2 (2024-05). <https://fred.stlouisfed.org/docs/api/fred/> |
| **ALFRED** | Bản *vintage* của chuỗi FRED (dữ liệu như đã biết tại từng thời điểm) | Miễn phí | Như FRED | Tham số `realtime_start`/`realtime_end` |
| **Lịch kinh tế** | Thời điểm công bố CPI, NFP, FOMC… | Tuỳ nguồn | Finnhub và FMP có endpoint lịch kinh tế (gói nào được dùng **[chưa xác minh]**). FRED có API "releases" cho ngày phát hành chuỗi | REST |
| **Vàng / forex** | XAU/USD, cặp tiền | Tuỳ nguồn | Alpha Vantage, Tiingo, Massive, Finnhub đều có forex. Vàng spot chất lượng thường trả phí. Có thể dùng futures (`GC=F`) qua yfinance làm proxy | REST |

Các series FRED hay dùng (ID theo kiến thức nền, **[chưa xác minh]** trong ngày vì trang FRED chặn truy vấn tự động):

| Series ID | Nội dung |
|---|---|
| `FEDFUNDS` / `DFF` | Effective federal funds rate (tháng / ngày) |
| `SOFR` | Secured Overnight Financing Rate |
| `DGS2`, `DGS10`, `DTB3` | Lợi suất Treasury 2 năm, 10 năm; T-bill 3 tháng |
| `T10Y2Y` | Chênh lệch 10 năm − 2 năm |
| `DTWEXBGS` | Chỉ số USD theo trọng số thương mại (broad) |
| `CPIAUCSL` | CPI Mỹ |
| `VIXCLS` | VIX đóng cửa |

Về **DXY**: chỉ số DXY là sản phẩm của ICE và FRED **không** phát hành nó. `DTWEXBGS` là chỉ số USD khác rổ, không thay thế 1:1. Muốn đúng DXY cần nguồn có dữ liệu ICE (ví dụ futures `DX` qua nhà cung cấp trả phí, hoặc `DX-Y.NYB` trên Yahoo với các hạn chế của yfinance).

Về dữ liệu vĩ mô trong backtest: số liệu bị **revise** sau khi công bố. Dùng bản hiện tại là look-ahead; hãy dùng ALFRED và căn theo ngày giờ công bố.

### 8.4 Crypto

Dữ liệu OHLCV, trades, order book, funding trực tiếp từ sàn (Binance, Bybit, OKX…) lấy qua `ccxt` hoặc API của sàn, miễn phí với rate limit riêng. Một số sàn có kho dữ liệu lịch sử tải file (ví dụ <https://data.binance.vision/>, **[chưa xác minh]** trong ngày). Bảng dưới là nguồn **ngoài sàn**.

| Nguồn | Loại dữ liệu | Miễn phí / trả phí | Giới hạn | Cách truy cập |
|---|---|---|---|---|
| **CoinGecko** | Giá, market cap, volume tổng hợp, metadata, DEX (GeckoTerminal) | Demo miễn phí + trả phí | Demo: 10 000 call/tháng, 100 call/phút (theo trang giá chính thức). Basic khoảng 35 USD/tháng (nguồn thứ cấp) | REST + key. <https://www.coingecko.com/en/api/pricing> |
| **CoinMarketCap** | Giá, xếp hạng, metadata | Basic miễn phí + trả phí | Basic: 15 000 credit/tháng, 50 request/phút, dùng cá nhân. Lịch sử trên gói free rất hạn chế (các nguồn mâu thuẫn, **[chưa xác minh]**) | REST + key. <https://coinmarketcap.com/api/pricing> |
| **CoinGlass** | Derivatives: open interest, funding, liquidation, long/short ratio | Trả phí | Hobbyist 29 USD/tháng, 30 request/phút, dùng cá nhân; Startup 79 USD; Standard 299 USD | REST + key. <https://www.coinglass.com/pricing> |
| **Glassnode** | On-chain (BTC, ETH và các chain khác) | Trả phí cho API | API là add-on của gói Professional; giá add-on không công bố (**[chưa xác minh]**) | REST. <https://studio.glassnode.com/pricing> |
| **CryptoQuant** | On-chain, dòng tiền sàn, miner | Free + trả phí | Mọi gói tạo được API key; on-chain cần gói Professional trở lên. Giá từ nguồn thứ cấp: khoảng 29 / 99 / 799 USD/tháng (**[chưa xác minh]**) | REST. <https://cryptoquant.com/pricing> |
| **DefiLlama** | TVL, DEX volume, fees, stablecoin, yields | API công khai miễn phí + Pro | Free không cần xác thực (rate limit **[chưa xác minh]**). Pro: 1 000 request/phút, 1 triệu call/tháng; giá 300 USD/tháng theo đa số nguồn, có nguồn ghi khác (**[chưa xác minh]**) | REST. <https://api-docs.defillama.com/>, <https://defillama.com/pro-api> |
| **Kaiko** | Tick, order book, reference rate cấp tổ chức | Trả phí, bán qua sales | Không có giá công khai; nguồn thứ cấp nêu từ khoảng 1 000 USD/tháng (**[chưa xác minh]**). Quá tầm dự án cá nhân | REST, stream, file |
| **Tardis.dev** | Tick lịch sử: trades, L2 incremental, snapshot, funding, OI, liquidation; hơn 50 sàn | Trả phí, có dùng thử | Free trial theo tài liệu: ngày 1–10 của tháng trước, 20 GB. Giá gói **[chưa xác minh]** (các nguồn thứ cấp mâu thuẫn) | HTTP API, CSV tải về, client Python/Node. <https://docs.tardis.dev/faq/general> |

### 8.5 TradingView

TradingView **không có API dữ liệu thị trường công khai chính thức**. Những gì có:

| Lựa chọn | Dùng để làm gì | Lưu ý |
|---|---|---|
| **Webhook alerts** từ Pine Script | Đẩy tín hiệu từ chart ra server của mình | Cách chính thức để tự động hoá; cần gói trả phí hỗ trợ webhook (**[chưa xác minh]** gói nào) |
| **Export chart data** (CSV) | Xuất dữ liệu đang hiển thị, thủ công | Tính năng của gói trả phí (**[chưa xác minh]**) |
| **Charting Library / Lightweight Charts** | Nhúng biểu đồ vào ứng dụng, **tự cấp dữ liệu** từ nguồn của mình | Lightweight Charts mã mở (Apache-2.0); Charting Library cần xin cấp phép |
| **Broker Integration REST API** | Dành cho broker kết nối vào TradingView | Không phải API lấy dữ liệu |
| Thư viện không chính thức (`tvdatafeed`, `tradingview-ta`, các scraper) | Lấy dữ liệu qua endpoint nội bộ | Nhiều khả năng **vi phạm điều khoản sử dụng** (hạn chế truy cập tự động và dùng dữ liệu ngoài hiển thị cho người xem); rủi ro khoá tài khoản; có thể hỏng bất cứ lúc nào |

Khuyến nghị kỹ thuật: dùng TradingView để **xem và vẽ**; lấy dữ liệu cho backtest từ sàn hoặc nhà cung cấp có điều khoản rõ ràng. Đọc bản điều khoản hiện hành tại <https://www.tradingview.com/policies/> (**[chưa xác minh]** nguyên văn trong phiên này).

### 8.6 Lưu ý chung về điều khoản dữ liệu

- "Miễn phí" thường đi kèm "chỉ dùng cá nhân, không phân phối lại". Nếu dự án sau này công khai sản phẩm, phải xem lại license của từng nguồn.
- Không commit API key; để trong biến môi trường hoặc file `.env` đã `.gitignore`.
- Lưu **raw response** kèm thời điểm tải để tái lập và để phát hiện khi nhà cung cấp sửa dữ liệu.

---

## 9. Phân tích cơ bản cho stock analyzer

### 9.1 Ba báo cáo tài chính

| Báo cáo | Trả lời câu hỏi | Mục chính |
|---|---|---|
| **Income statement** | Kỳ này lãi bao nhiêu | Revenue → gross profit → operating income (EBIT) → net income, EPS |
| **Balance sheet** | Tại một thời điểm có gì, nợ gì | Assets = Liabilities + Equity; tiền, nợ vay, vốn lưu động |
| **Cash flow statement** | Tiền thật đi đâu | CFO, CFI (trong đó có capex), CFF; `FCF = CFO − capex` |

Lưu ý dữ liệu: dùng số TTM (trailing twelve months) cho chỉ số dòng chảy; lưu **ngày công bố** (filing date) chứ không chỉ ngày kết thúc kỳ; phân biệt số *as reported* với số *restated*.

### 9.2 Chỉ số định giá

| Chỉ số | Công thức | Dùng khi | Bẫy |
|---|---|---|---|
| **P/E** | `Price / EPS` | Doanh nghiệp có lãi ổn định | Vô nghĩa khi EPS âm hoặc bị bóp méo bởi khoản một lần; chu kỳ |
| **EV/EBITDA** | `(Market cap + Debt − Cash) / EBITDA` | So sánh công ty có cấu trúc vốn khác nhau | EBITDA bỏ qua capex; không dùng cho ngân hàng |
| **P/B** | `Price / Book value per share` | Ngân hàng, bảo hiểm, công ty nặng tài sản | Kém ý nghĩa với công ty nhiều tài sản vô hình hoặc mua lại cổ phiếu nhiều |
| **PEG** | `(P/E) / tăng trưởng EPS (%)` | Công ty tăng trưởng | Rất nhạy với dự báo tăng trưởng |
| **FCF yield** | `FCF / Market cap` (hoặc `/ EV`) | Đánh giá khả năng sinh tiền | FCF biến động theo chu kỳ capex và vốn lưu động |
| **EV/Sales**, **Dividend yield** | — | Công ty chưa có lãi; cổ phiếu thu nhập | — |

### 9.3 Chỉ số chất lượng

| Nhóm | Chỉ số | Công thức |
|---|---|---|
| Sinh lời | **ROE** | `Net income / Equity bình quân`. Phân rã DuPont: `biên ròng × vòng quay tài sản × đòn bẩy` |
| | **ROIC** | `NOPAT / Invested capital`, `NOPAT = EBIT × (1 − thuế suất)`, invested capital ≈ `Debt + Equity − Cash dư` |
| | **ROA** | `Net income / Total assets` |
| Biên lợi nhuận | Gross, operating, net margin | Chia cho revenue; xem xu hướng nhiều năm |
| Nợ | **Debt/Equity**, **Net debt/EBITDA** | Đòn bẩy tài chính |
| | **Interest coverage** | `EBIT / Interest expense` |
| | **Current ratio** | `Current assets / Current liabilities` |
| Chất lượng lợi nhuận | **Accruals** | `(Net income − CFO) / Total assets`; cao là tín hiệu cảnh báo |
| | **Cash conversion** | `FCF / Net income` |
| Điểm tổng hợp | Piotroski F-score (0–9), Altman Z-score | Sàng lọc sức khoẻ tài chính và rủi ro phá sản |

ROE cao nhờ đòn bẩy khác với ROE cao nhờ biên lợi nhuận; luôn xem kèm ROIC và so với chi phí vốn.

### 9.4 DCF tóm tắt

1. Dự phóng FCFF cho `N` năm (thường 5–10): `FCFF = EBIT × (1 − t) + D&A − Capex − ΔNWC`.
2. Tính suất chiết khấu: `WACC = E/V · Re + D/V · Rd · (1 − t)`, với `Re = r_f + β · ERP` (CAPM).
3. Giá trị cuối kỳ: `TV = FCFF_{N+1} / (WACC − g)` (Gordon), `g` không vượt tăng trưởng danh nghĩa dài hạn của nền kinh tế.
4. `EV = Σ FCFF_t / (1 + WACC)^t + TV / (1 + WACC)^N`.
5. `Equity value = EV − Net debt − lợi ích thiểu số`; chia cho số cổ phiếu pha loãng.

Thực tế cần nhớ:

- Terminal value thường chiếm 60–80% giá trị, nên kết quả rất nhạy với `WACC` và `g`. Luôn trình bày **bảng độ nhạy** thay vì một con số.
- *Reverse DCF* (hỏi giá hiện tại đang hàm ý tăng trưởng bao nhiêu) thường hữu ích hơn một ước tính điểm.
- DCF là công cụ tổ chức giả định, không phải máy cho ra "giá đúng".

### 9.5 Factor và screening

| Factor | Định nghĩa thường dùng | Trực giác |
|---|---|---|
| **Value** | B/M, E/P, FCF/P, EBIT/EV cao | Rẻ so với cơ bản |
| **Quality** | ROE/ROIC cao, gross profitability, accruals thấp, nợ thấp, lợi nhuận ổn định | Doanh nghiệp tốt |
| **Momentum** | Return 12 tháng, bỏ tháng gần nhất (12−1) | Người thắng tiếp tục thắng |
| **Size** | Vốn hoá nhỏ | Premium vốn hoá nhỏ (yếu và gây tranh cãi sau khi công bố) |
| **Low volatility** | Volatility hoặc beta thấp | Cổ phiếu rủi ro thấp cho return điều chỉnh rủi ro cao hơn |

Quy trình screening và xây factor:

1. Xác định universe **theo thời gian**, có lọc thanh khoản (giá trị giao dịch tối thiểu) và gồm cả mã đã huỷ niêm yết.
2. Tính chỉ số từ dữ liệu point-in-time (trễ theo ngày công bố).
3. Xử lý ngoại lai (winsorize 1–99%), chuẩn hoá z-score hoặc rank, có thể trung hoà theo ngành.
4. Kết hợp thành điểm tổng hợp; xếp hạng; chia nhóm phân vị.
5. Đánh giá bằng return theo phân vị, long-short spread, **IC** (rank correlation giữa điểm và return kỳ sau), turnover và chi phí.
6. Tái cân bằng theo tháng hoặc quý; so với benchmark phù hợp.

Screener cho người dùng cuối nên hiển thị cả dữ liệu thô và ngày dữ liệu, để người xem tự đánh giá. Kết quả sàng lọc là danh sách cần nghiên cứu thêm, không phải khuyến nghị.

---

## 10. Kiến trúc lưu trữ và pipeline đề xuất

### 10.1 Lựa chọn: Parquet + DuckDB, polars để xử lý

Lý do cho dự án cá nhân:

- **Không vận hành server**: DuckDB chạy trong tiến trình, dữ liệu là file. Sao lưu là copy thư mục.
- **Khối lượng công việc là phân tích**: quét cột theo khoảng thời gian trên nhiều mã. Lưu trữ cột có nén và predicate pushdown phù hợp hơn DB hàng.
- **Parquet là định dạng trung lập**: pandas, polars, DuckDB, Spark đều đọc được, không bị khoá vào một công cụ.
- **Quy mô đủ**: OHLCV 1 phút của vài trăm mã trong nhiều năm chỉ ở mức vài GB đến vài chục GB.
- **`ASOF JOIN`** của DuckDB giải quyết gọn bài toán ghép point-in-time (fundamentals, vĩ mô vào giá).
- **Tái lập**: file bất biến + manifest cho phép biết chính xác backtest đã chạy trên dữ liệu nào.

Khi nào cần thứ khác:

| Tình huống | Chọn |
|---|---|
| Nhiều tiến trình ghi đồng thời, cần dashboard hoặc service truy vấn liên tục | PostgreSQL + TimescaleDB |
| Thu tick/L2 realtime tốc độ cao từ nhiều sàn | QuestDB, hoặc ghi thẳng Parquet theo lô |
| Trạng thái bot live (lệnh, vị thế, đối soát) | SQLite hoặc PostgreSQL (OLTP), **tách khỏi** kho dữ liệu nghiên cứu |

### 10.2 Bố cục thư mục

```
data/
  raw/                      # bất biến: response gốc, không sửa
    binance/ohlcv/1m/symbol=BTCUSDT/date=2026-11-12.parquet
    edgar/companyfacts/cik=0000320193/fetched=2026-11-12.json
  curated/                  # đã làm sạch, schema ổn định
    ohlcv/exchange=binance/timeframe=1h/symbol=BTCUSDT/year=2026/part-0.parquet
    funding/exchange=binance/symbol=BTCUSDT/year=2026/part-0.parquet
    fundamentals/ticker=AAPL/part-0.parquet       # có cột filed_at, period_end
    macro/series=DGS10/part-0.parquet             # có cột realtime_start
  features/                 # feature đã tính, có version
    v3/…
  meta/
    manifest.parquet        # nguồn, khoảng thời gian, số dòng, checksum, thời điểm tải
    instruments.parquet     # mã, sàn, tick size, ngày niêm yết/huỷ niêm yết
research.duckdb             # chỉ chứa VIEW trỏ vào Parquet + bảng kết quả backtest
```

Quy tắc schema:

- Timestamp **UTC**, kiểu `TIMESTAMP` có độ phân giải rõ; quy ước `ts` là thời điểm **mở** bar và ghi quy ước này vào tài liệu.
- Mọi bảng có `ingested_at`; dữ liệu công bố muộn có thêm `available_at` (hoặc `filed_at`, `realtime_start`).
- Giá cổ phiếu: lưu **raw** và hệ số điều chỉnh riêng; tính adjusted khi truy vấn, vì hệ số thay đổi theo thời gian.
- Partition vừa phải (theo symbol và năm); tránh hàng chục nghìn file nhỏ.

### 10.3 Pipeline

| Giai đoạn | Việc làm | Công cụ gợi ý |
|---|---|---|
| **Ingest** | Tải tăng dần theo watermark, idempotent, có retry và tôn trọng rate limit; ghi raw nguyên trạng | `ccxt`, `httpx`, client của từng nguồn |
| **Validate** | Kiểm tra trùng, thiếu bar, `high ≥ max(open, close)`, giá ≤ 0, nhảy giá bất thường, lệch múi giờ | polars + bộ kiểm tra tự viết, hoặc `pandera` |
| **Curate** | Chuẩn hoá schema, khử trùng lặp, ghi Parquet theo partition, cập nhật manifest | polars, pyarrow |
| **Feature** | Tính feature chỉ từ dữ liệu có `available_at ≤ t`; lưu kèm version và commit hash | polars, DuckDB SQL |
| **Research / backtest** | Đọc qua DuckDB view; ghi kết quả, tham số, commit hash vào bảng `runs` | vectorbt hoặc tự viết → NautilusTrader khi cần độ chân thực |
| **Lập lịch** | Chạy định kỳ, báo lỗi khi dữ liệu trễ | `cron`/`launchd` là đủ; chỉ dùng Prefect/Dagster khi pipeline thật sự phức tạp |

Ví dụ ghép point-in-time bằng DuckDB:

```sql
SELECT p.ts, p.ticker, p.close, f.eps_ttm
FROM read_parquet('data/curated/ohlcv/**/*.parquet', hive_partitioning = true) AS p
ASOF LEFT JOIN read_parquet('data/curated/fundamentals/**/*.parquet') AS f
  ON p.ticker = f.ticker AND p.ts >= f.filed_at;
```

Kiểm thử nên có từ đầu:

- Test chống look-ahead: tính feature trên dữ liệu cắt tại `t` và trên toàn bộ dữ liệu, giá trị trước `t` phải giống nhau.
- Test engine backtest trên chuỗi giá ngẫu nhiên: lợi nhuận kỳ vọng sau phí phải âm đúng bằng chi phí.
- Test đối chiếu metric tự viết với `quantstats`/`empyrical-reloaded` trên cùng chuỗi return.

---

## 11. Sách và paper nền tảng

URL ghi theo trí nhớ, **chưa mở kiểm tra từng link** trong phiên này.

### Sách

| Tác giả, tên | Nội dung | Mức |
|---|---|---|
| Ernest Chan — *Quantitative Trading* (2nd ed.), *Algorithmic Trading: Winning Strategies and Their Rationale* | Nhập môn thực dụng: mean reversion, momentum, cointegration, Kelly | Bắt đầu |
| Marcos López de Prado — *Advances in Financial Machine Learning* (2018) | Triple-barrier, meta-labeling, purged CV, CPCV, fractional differentiation, DSR | Trung cấp, cốt lõi |
| Marcos López de Prado — *Machine Learning for Asset Managers* (2020) | Denoising, clustering, feature importance, false discovery | Trung cấp |
| Robert Carver — *Systematic Trading*, *Advanced Futures Trading Strategies* | Thiết kế hệ thống, volatility targeting, kết hợp tín hiệu | Bắt đầu đến trung cấp |
| Grinold & Kahn — *Active Portfolio Management* | Information ratio, fundamental law, xây dựng portfolio | Nâng cao |
| Antti Ilmanen — *Expected Returns* | Tổng quan risk premia theo loại tài sản và factor | Trung cấp |
| Lasse Pedersen — *Efficiently Inefficient* | Các chiến lược hedge fund và lý do kinh tế | Trung cấp |
| Larry Harris — *Trading and Exchanges* | Microstructure kinh điển | Nền tảng |
| Bouchaud, Bonart, Donier, Gould — *Trades, Quotes and Prices* | Order book, market impact định lượng | Nâng cao |
| Stefan Jansen — *Machine Learning for Algorithmic Trading* (2nd ed.) | Thực hành Python từ đầu đến cuối | Trung cấp |
| Ruey Tsay — *Analysis of Financial Time Series* | ARIMA, GARCH, mô hình đa biến | Nền tảng |
| Aswath Damodaran — *Investment Valuation* (và tài liệu miễn phí trên trang cá nhân) | DCF và định giá | Nền tảng cho stock analyzer |
| Benjamin Graham — *The Intelligent Investor*; Joel Greenblatt — *The Little Book That Beats the Market* | Tư duy giá trị, ví dụ factor đơn giản | Bắt đầu |

### Paper

| Paper | Chủ đề | Link |
|---|---|---|
| Kelly (1956), *A New Interpretation of Information Rate* | Tiêu chí Kelly | — |
| Sharpe (1966, 1994), *The Sharpe Ratio* | Định nghĩa Sharpe | — |
| Lo (2002), *The Statistics of Sharpe Ratios* | Sai số và annualize Sharpe | — |
| Fama & French (1993), *Common Risk Factors in the Returns on Stocks and Bonds*; (2015) *A Five-Factor Asset Pricing Model* | Mô hình factor | — |
| Jegadeesh & Titman (1993), *Returns to Buying Winners and Selling Losers* | Momentum cross-sectional | — |
| Carhart (1997), *On Persistence in Mutual Fund Performance* | Factor momentum | — |
| Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum* | Trend following | — |
| Asness, Moskowitz & Pedersen (2013), *Value and Momentum Everywhere* | Factor đa tài sản | — |
| Novy-Marx (2013), *The Other Side of Value: The Gross Profitability Premium* | Quality | — |
| Frazzini & Pedersen (2014), *Betting Against Beta* | Low-beta | — |
| Piotroski (2000), *Value Investing: The Use of Historical Financial Statement Information* | F-score | — |
| Engle & Granger (1987), *Co-integration and Error Correction* | Cointegration | — |
| Gatev, Goetzmann & Rouwenhorst (2006), *Pairs Trading* | Pairs trading | — |
| Avellaneda & Lee (2010), *Statistical Arbitrage in the U.S. Equities Market* | Stat-arb | — |
| Avellaneda & Stoikov (2008), *High-frequency Trading in a Limit Order Book* | Market making | — |
| Almgren & Chriss (2000), *Optimal Execution of Portfolio Transactions* | Thực thi, market impact | — |
| Kyle (1985), *Continuous Auctions and Insider Trading* | Microstructure | — |
| Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* | DSR | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551> |
| Bailey, Borwein, López de Prado & Zhu (2017), *The Probability of Backtest Overfitting* | PBO, CSCV | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253> |
| Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns* | Multiple testing trong factor | <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2249314> |
| White (2000), *A Reality Check for Data Snooping* | Data snooping | — |
| McLean & Pontiff (2016), *Does Academic Research Destroy Stock Return Predictability?* | Premium giảm sau công bố | — |
| Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning* | ML cho dự báo return | — |
| Liu & Tsyvinski (2021), *Risks and Returns of Cryptocurrency* | Factor trong crypto | — |

Thứ tự đọc gợi ý: Chan → Carver → López de Prado (*AFML*) → Harris; song song Damodaran cho phần cổ phiếu. Ba paper nên đọc sớm: DSR, PBO, Harvey–Liu–Zhu.

---

## 12. Danh sách điều chưa xác minh

| # | Nội dung | Vì sao | Nơi kiểm tra |
|---|---|---|---|
| 1 | Tình trạng và license của `pandas-ta` gốc | Repo GitHub 404, tên miền tài liệu không phân giải | <https://pypi.org/project/pandas-ta/> |
| 2 | Giá và gói miễn phí của Massive (Polygon) | Chỉ có nguồn thứ cấp, có mâu thuẫn | <https://massive.com/pricing> |
| 3 | Trần 500 mã/tháng của Tiingo free | Chỉ từ trang so sánh của đối thủ | <https://www.tiingo.com/about/pricing> |
| 4 | Chi tiết gói free Finnhub (candles, WebSocket) | Nguồn thứ cấp | <https://finnhub.io/pricing> |
| 5 | Cơ chế API key/CAPTCHA của Stooq | Không có tài liệu chính thức | <https://stooq.com/> |
| 6 | Giá các gói vnstock, danh sách nguồn hỗ trợ ở thế hệ 6 | Trang giấy phép không nêu | <https://vnstocks.com/> |
| 7 | Phí SSI FastConnect Data; API dữ liệu của TCBS, DNSE | Không tìm được thông tin chính thức | Trang từng CTCK |
| 8 | Rate limit FRED và sự tồn tại hiện tại của từng series ID | Trang FRED chặn truy vấn tự động | <https://fred.stlouisfed.org/docs/api/fred/> |
| 9 | Lịch sử trên gói free của CoinMarketCap | Các nguồn mâu thuẫn | <https://coinmarketcap.com/api/pricing> |
| 10 | Giá API add-on Glassnode; giá các gói CryptoQuant | Không công bố hoặc chỉ có nguồn thứ cấp | Trang pricing chính thức |
| 11 | Giá DefiLlama Pro (300 USD hay khác), rate limit bản free | Nguồn mâu thuẫn | <https://defillama.com/subscription> |
| 12 | Giá Kaiko, giá gói Tardis.dev | Bán qua sales / nguồn thứ cấp mâu thuẫn | Liên hệ nhà cung cấp |
| 13 | Nguyên văn điều khoản TradingView; gói nào có webhook và export | Không mở trang chính sách | <https://www.tradingview.com/policies/> |
| 14 | Giá mlfinlab | Không công bố | <https://hudsonthames.org/mlfinlab/> |
| 15 | API hiện tại của `skfolio` cho CPCV; kho `data.binance.vision` | Không kiểm tra trong phiên | Tài liệu từng dự án |
| 16 | Toàn bộ URL paper ở mục 11 | Ghi theo trí nhớ | SSRN / trang tạp chí |
| 17 | Gói nào của Finnhub/FMP có lịch kinh tế | Không kiểm tra | Trang pricing |
