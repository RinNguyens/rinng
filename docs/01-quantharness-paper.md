# 01 — QuantHarness: tóm tắt paper, repo và đánh giá phản biện

> Nguồn đã đọc:
> - **Paper**: "QuantHarness: Price-Driven Multi-Agent LLMs for High-Frequency Trading", arXiv 2509.09995**v4** (dấu ngày trên bản PDF: 27 Jul 2026), 32 trang, đọc toàn bộ kể cả phụ lục A–H. Tác giả: Fei Xiong, Xiang Zhang (đồng đóng góp), Aosong Feng, Siqi Sun, Chenyu You (Stony Brook, CMU, UBC, Yale, Fudan) — tr.1.
> - **Repo**: https://github.com/Y-Research-SBU/QuantHarness, đọc tại commit `2e64c7b` (2026-08-18, "Merge pull request #24 … upgrade-minimax-m3").
> - **Trang dự án**: https://Y-Research-SBU.github.io/QuantHarness/ (chỉ đọc được phần chữ; các bảng trên trang là ảnh).
>
> Quy ước: `[tr.N]` = trang N của PDF; `[code: file]` = đọc trực tiếp từ repo; **chưa xác minh** = không tìm thấy bằng chứng trong paper lẫn repo.
> Tài liệu này không phải lời khuyên đầu tư.

---

## 0. Kết luận nhanh

1. Ý tưởng kiến trúc (tách indicator / pattern / trend / decision, chỉ dùng OHLC, có tool tính toán thật thay vì để LLM tự bịa số) là hợp lý và dễ tái dùng.
2. **Bằng chứng thực nghiệm yếu.** Ở Bảng 1 (bảng duy nhất có Sharpe / cumulative return), QuantHarness **không đứng đầu cumulative return ở bất kỳ tài sản nào (0/8)** và **không đứng đầu Sharpe ở bất kỳ tài sản nào (0/8)**. Linear Regression có cumulative return cao hơn ở **7/7** tài sản có số liệu LR. Một số ô in đậm trong Bảng 1 không phải giá trị tốt nhất của cột.
3. Ở Bảng 2 (4h), hệ thống đứng đầu accuracy ở 8/8 tài sản, nhưng mức chênh nhỏ (có chỗ 0,3 điểm %), n = 100 đoạn/tài sản, không có khoảng tin cậy, không lặp lại nhiều seed.
4. Paper **không** tính phí giao dịch, slippage, spread; **không** nêu tên model LLM dùng cho thực nghiệm; **không** công bố code đánh giá/baseline.
5. Repo là một bản demo phân tích (Flask + LangGraph), **không có** RiskAgent, **không có** stop-loss 0.0005, **không có** backtest, **không có** ngưỡng độ dốc τ của Thuật toán 1.

---

## 1. Kiến trúc

Paper mô tả "bốn agent chuyên biệt" Indicator, Pattern, Trend, Risk [tr.1, tr.3], cộng thêm DecisionAgent ở tầng cuối [tr.5–6]. Hệ thống xây trên LangGraph [tr.3], chỉ dùng dữ liệu giá OHLC, không dùng tin tức/sentiment [tr.3].

Luồng thực tế trong code là **tuần tự**, không có debate, không có nhánh song song [code: `graph_setup.py`]:

```
START → Indicator Agent → Pattern Agent → Trend Agent → Decision Maker → END
```

State dùng chung là `IndicatorAgentState` (TypedDict) gồm `kline_data`, `time_frame`, `stock_name`, `indicator_report`, `pattern_report`, `trend_report`, `final_trade_decision`, ảnh base64… [code: `agent_state.py`].

### 1.1 IndicatorAgent

| Mục | Paper | Code |
|---|---|---|
| Đầu vào | OHLC gần nhất + `time_frame` [tr.18] | `state["kline_data"]` (dict các list), dump JSON vào system prompt [code: `indicator_agent.py`] |
| Tool | `compute_rsi`, `compute_macd`, `compute_roc`, `compute_stoch`, `compute_willr` [tr.18] | Giống paper, tính bằng TA-Lib [code: `graph_util.py`] |
| Đầu ra | Báo cáo văn bản tóm tắt tín hiệu (ví dụ "bullish but extended") [tr.31] | `indicator_report` (text tự do) |
| LLM | không nêu | `graph_llm` (mặc định `gpt-4o`) [code: `graph_setup.py`, `default_config.py`] |

Tham số indicator:

| Indicator | Tham số | Nguồn |
|---|---|---|
| MACD | fast EMA 12, slow EMA 26, signal 9; α = 2/(N+1) | Paper Phụ lục G [tr.32] và code |
| RSI | period 14 | **Chỉ có trong code** (paper không ghi chu kỳ) |
| ROC | period 10 | Chỉ có trong code |
| Stochastic | `fastk_period=14, slowk_period=3, slowd_period=3` | Chỉ có trong code |
| Williams %R | period 14 | Chỉ có trong code |

Chi tiết code đáng chú ý [code: `graph_util.py`]:
- Các chu kỳ là giá trị mặc định của tool; LLM được phép truyền chu kỳ khác khi gọi tool (trừ Stochastic bị hard-code).
- Mỗi tool chỉ trả về **28 giá trị cuối**, làm tròn 2 chữ số (riêng `macd` trả toàn bộ chuỗi).
- Giá trị NaN ở giai đoạn warm-up bị thay bằng **0** (`fillna(0)`). Với cửa sổ 45 nến của web demo, MACD signal cần khoảng 33 nến warm-up, nên phần lớn chuỗi MACD LLM nhìn thấy là số 0 giả. Đây là lỗi thiết kế cần sửa nếu tái dùng.
- Vòng lặp tool tối đa 5 lượt [code: `indicator_agent.py`].

Prompt (Phụ lục C.1 [tr.18], tóm tắt): "You are a high-frequency trading (HFT) analyst assistant working under strict latency constraints…", liệt kê 5 tool, nói dữ liệu OHLC đến từ khung `{time_frame}`, chèn `{kline_data}`, kết thúc bằng "Call necessary tools, and analyze the results." Prompt trong code gần như trùng khớp.

Ngưỡng diễn giải trong Hình 1 [tr.2]: RSI > 70 bearish, RSI < 30 bullish, 30–70 neutral; Williams %R > −20 bearish, < −80 bullish; ROC > 0 bullish, < 0 bearish. Các ngưỡng này chỉ là minh hoạ; không có trong prompt hay code — LLM tự diễn giải.

### 1.2 PatternAgent

| Mục | Paper | Code |
|---|---|---|
| Đầu vào | OHLC → vẽ thành ảnh nến [tr.4, tr.19] | `kline_data`, hoặc ảnh dựng sẵn trong state |
| Tool | `generate_kline_image` [tr.19] | mplfinance, **40 nến cuối** (`df.tail(40)`), figsize 12×6, dpi 600 [code: `graph_util.py`] |
| Đầu ra | Tên pattern + giải thích theo structure / trend / symmetry [tr.7, tr.19] | `pattern_report` (text tự do) |
| LLM | "multimodal" | Bước gọi tool: `agent_llm` (`gpt-4o-mini`); bước đọc ảnh: `graph_llm` (`gpt-4o`) |

Thư viện 16 pattern trong prompt (Phụ lục C.2 [tr.19], trùng với code `pattern_agent.py`):

1. Inverse Head and Shoulders — 2. Double Bottom — 3. Rounded Bottom — 4. Hidden Base — 5. Falling Wedge — 6. Rising Wedge — 7. Ascending Triangle — 8. Descending Triangle — 9. Bullish Flag — 10. Bearish Flag — 11. Rectangle — 12. Island Reversal — 13. V-shaped Reversal — 14. Rounded Top / Bottom — 15. Expanding Triangle — 16. Symmetrical Triangle.

Mỗi pattern chỉ có một câu mô tả. Không có Head and Shoulders (đỉnh), Double Top, Triple Top/Bottom trong danh sách, dù Hình 1 [tr.2] vẽ "Double Top". Nhận diện pattern hoàn toàn do LLM nhìn ảnh; không có thuật toán hình học nào kiểm tra lại. Phụ lục F [tr.29–30] mô tả việc "extracts swing pivots… least-squares fit through those highs" nhưng code PatternAgent không có bước này — **chưa xác minh** mô tả đó ứng với phần code nào.

### 1.3 TrendAgent

| Mục | Paper | Code |
|---|---|---|
| Đầu vào | OHLC → ảnh nến có kênh xu hướng [tr.5, tr.20] | `kline_data` hoặc ảnh dựng sẵn |
| Tool | `generate_trend_image` [tr.20] | **50 nến cuối** (`data.iloc[-50:]`) [code: `graph_util.py`] |
| Đầu ra | Dự đoán upward / downward / sideways + "prediction, reasoning, signals" [tr.20] | `trend_report` (text tự do) |

Prompt (Phụ lục C.3 [tr.20], tóm tắt): bắt buộc gọi `generate_trend_image` trước; chỉ sau khi có ảnh mới dự đoán; prompt đọc ảnh nói đường **xanh dương = support**, **đỏ = resistance**, "both derived from recent closing prices".

Lệch giữa paper và code:
- Paper nói đường resistance/support fit qua **highs/lows** [tr.5, Thuật toán 1 tr.3]. Code tính cả hai bộ đường (theo close, và theo high/low), nhưng bộ high/low được vẽ **màu trắng trên nền trắng** nên không nhìn thấy; LLM chỉ thấy bộ đường theo **close** [code: `graph_util.py`, `color_style.py`].
- Đường trend trong code không phải OLS thuần: lấy OLS làm điểm khởi đầu, tìm pivot xa nhất, rồi tối ưu độ dốc sao cho đường đi qua pivot và không cắt giá (hàm `optimize_slope`, lấy từ repo `neurotrader888/TechnicalAnalysisAutomation` theo README).
- Code **không có** bước phân loại theo ngưỡng τ (mục 2). Việc phân loại uptrend/downtrend/sideways do LLM nhìn ảnh quyết định.

### 1.4 RiskAgent

Theo paper [tr.5, Hình 2 tr.4]:
- Không sinh tín hiệu; gom đầu ra các agent khác vào khung risk–reward.
- Stop-loss cố định **ρ = 0.0005** (0,05%).
- Take-profit **R = r · ρ**, với **r ∈ [1.2, 1.8]** do LLM dự đoán.
- Hình 2 vẽ radar 6 trục: Momentum Strength, Trend Certainty, Pattern Reliability, Breakout Likelihood, S/R Strength, Volatility Risk.

Trong repo: **không có file/nút RiskAgent nào**; không có hằng số 0.0005; không có radar chart. Phần duy nhất còn lại là câu yêu cầu `risk_reward_ratio` 1.2–1.8 trong prompt của DecisionAgent. Paper không có prompt riêng cho RiskAgent trong Phụ lục C. Trang dự án cũng chỉ liệt kê Indicator / Pattern / Trend / Decision.

### 1.5 DecisionAgent

| Mục | Nội dung |
|---|---|
| Đầu vào | `indicator_report`, `pattern_report`, `trend_report`, `time_frame`, `stock_name` [tr.21; code: `decision_agent.py`] |
| Tool | Không có |
| Đầu ra | JSON: `forecast_horizon`, `decision` (LONG/SHORT), `justification`, `risk_reward_ratio` (1.2–1.8) [tr.21] |
| LLM | `graph_llm` (mặc định `gpt-4o`), một lần gọi |

Quy tắc trong prompt (Phụ lục C.4 [tr.21], tóm tắt):
- "Issue an immediate execution order: LONG or SHORT. (HOLD is prohibited.)"
- Horizon: dự đoán **3 nến tiếp theo** (ví dụ 15-min → 45 phút; 4-hour → 12 giờ).
- Indicator: ưu tiên tín hiệu mạnh (MACD cross, RSI divergence, vùng cực trị), giảm trọng số tín hiệu trung tính.
- Pattern: chỉ hành động khi pattern đã hình thành rõ và có xác nhận breakout.
- Trend: support dốc lên = lực mua; resistance dốc xuống = lực bán; không suy ra hướng breakout chỉ từ hình học.
- Khi các báo cáo mâu thuẫn: chọn phía có xác nhận mạnh và gần hơn; khi đi ngang: theo độ dốc trendline chủ đạo.
- Đề xuất risk-reward 1.2–1.8.

Ghi chú:
- Prompt in trong paper còn sót câu trả lời của chatbot: "Here is a LaTeX-style refactored version of your original decision guideline…" và "Let me know if you want this formatted directly in LaTeX code or exported to PDF." [tr.21].
- Prompt trong code tự mâu thuẫn về horizon: phần thân ghi ví dụ "N = 1 → Predict the next 4 hours", phần output format ghi "Predicting next 3 candlestick" [code: `decision_agent.py`]. Hình 10 [tr.25] cũng hiện "Predicting next 1 candlestick (4 hours)".
- Code không parse JSON trong graph; `final_trade_decision` là chuỗi thô, `risk_reward_ratio` là string.
- Vì cấm HOLD, hệ thống luôn ở trong thị trường. Prompt vừa nói "Only act on confirmed signals" vừa cấm không hành động — hai yêu cầu này không thể cùng thoả.

### 1.6 Số nến đưa vào — các nguồn không khớp nhau

| Nguồn | Số nến |
|---|---|
| Benchmark, paper [tr.6, tr.28] | Đoạn 100 nến, giấu 3 nến cuối → 97 nến đầu vào |
| Hình 9, paper [tr.24] | "the most recent 40–50 price bars" |
| README repo | "the most recent 30 candlesticks" |
| Code web [`web_interface.py`, dòng 317] | `df.tail(45)` |
| Tool pattern / trend [code] | 40 / 50 nến cuối |

---

## 2. Thuật toán 1 — Slope-aware trend detection [tr.3]

```
Input: P_{0:T-1} (chuỗi nến), N (độ dài cửa sổ), τ (ngưỡng độ dốc)
for t = N-1 to T-1:
    Fit OLS trên highs / lows → m_r, m_s
    κ_t ← (m_r + m_s) / 2
    if   κ_t >  τ : Trend ← Uptrend
    elif κ_t < -τ : Trend ← Downtrend
    else          : Trend ← Sideways
Render chart K_t(P_t, κ_t, Trend)
```

Công thức đi kèm [tr.5]:
- Resistance: `R_t(x) = m_r·x + b_r` (qua các đỉnh cục bộ gần đây).
- Support: `S_t(x) = m_s·x + b_s` (qua các đáy cục bộ gần đây).
- Độ dốc trung bình: `κ_t = (m_r + m_s) / 2`.

Điều paper không nói:
- **Giá trị của N và τ không được nêu ở bất kỳ đâu** trong 32 trang. → **chưa xác minh**.
- τ có được chuẩn hoá theo giá hay không (độ dốc tính theo đơn vị giá/nến sẽ không so sánh được giữa BTC ~80.000 và VIX ~20) — không nêu.
- Code không cài đặt bước so ngưỡng này (mục 1.3).

---

## 3. Metric đánh giá

### 3.1 Bảng 2 (định nghĩa ở tr.6–7)

- **Accuracy α = C / T**. Với LONG, mỗi nến trong 3 nến kế tiếp có close **cao hơn close cuối cùng đã thấy** tính 1 điểm (tối đa 3); SHORT thì ngược lại. Mỗi mẫu được 0–3 điểm, lấy trung bình trên các mẫu. Lưu ý: cả 3 nến đều so với cùng một mốc nên 3 điểm trong một mẫu tương quan mạnh với nhau; số quan sát độc lập gần 100 hơn là 300.
- **Δα%**: mức cải thiện tương đối so với baseline ngẫu nhiên (kiểm tra lại: NQ 55.3 / 43.7 − 1 = +26.5%, khớp Bảng 2).
- **R_cc, R_max, R_min**: các ước lượng Rate of Return, "incorporate risk-constrained execution": thoát lệnh tại mức giá đầu tiên trong 3 nến kế tiếp chạm stop-loss hoặc take-profit. Stop-loss ρ = 0.0005; ngưỡng lời R = r·ρ, với r do LLM đưa ra.
- **R_max**: lợi suất tốt nhất có thể đạt trong 3 nến (high cao nhất với LONG, low thấp nhất với SHORT).
- **R_min**: biến động bất lợi nhất trong cùng khoảng.

Chỗ chưa rõ:
- **Công thức chính xác của R_cc không được viết ra** (không nêu "cc" là gì, giá vào lệnh là gì, thoát ở đâu khi không chạm ngưỡng nào). → **chưa xác minh**.
- **Đơn vị của R không được nêu.** Nếu là %, thì R_min ≈ −1.2 (BTC) hay −3.1 (VIX) lớn gấp hàng chục lần stop-loss 0,05% — không tương thích với việc "đã áp stop-loss". Nếu stop 0,05% thật sự được áp trên nến 4h, gần như lệnh nào cũng bị quét. Paper không giải thích. → **chưa xác minh**.

### 3.2 Bảng 1

Bảng 1 [tr.8] dùng Sharpe, Sortino, Cumulative Return, Max Drawdown. **Paper không định nghĩa cách tính các metric này** (chu kỳ lợi suất, lãi suất phi rủi ro, annualize hay không, khung thời gian, giai đoạn, quy mô vị thế). Phần chữ của paper cũng không hề dẫn chiếu tới Bảng 1 (mục 5.1 chỉ bàn Bảng 2). → **chưa xác minh** toàn bộ thiết lập của Bảng 1.

### 3.3 Công thức MACD (Phụ lục G [tr.32])

- `E_t = α·P_t + (1−α)·E_{t−1}`, `α = 2/(N+1)`
- `M_t = E_t^(f) − E_t^(s)` với N = 12 (fast), 26 (slow)
- `S_t = EMA_9(M_t)`; bullish khi M_t cắt lên S_t.

---

## 4. Thiết lập thực nghiệm

| Hạng mục | Nội dung | Nguồn |
|---|---|---|
| Khung thời gian | 1h và 4h | tr.6, tr.28 |
| Dữ liệu | 5.000 nến lịch sử mỗi tài sản, mỗi khung | tr.6, tr.28 |
| Nguồn dữ liệu | "public TradingView data extraction tool API" [tr.6]; Phụ lục ghi "YFinance and TradingView" [tr.28] | |
| Lấy mẫu | Mỗi tài sản lấy ngẫu nhiên **100 đoạn**, mỗi đoạn **100 nến liên tiếp**, giấu **3 nến cuối** để chấm | tr.6, tr.28 |
| Chế độ | Zero-shot, không fine-tune, không ví dụ mẫu | tr.6 |
| Model LLM | **Không nêu trong paper.** Phụ lục H chỉ nói GPT-4o dùng để chỉnh câu chữ [tr.32]. Code mặc định `gpt-4o` + `gpt-4o-mini`, temperature 0.1 | **chưa xác minh** model của thực nghiệm |
| Case study | 1 đoạn SPX 100 nến, 10 cửa sổ chồng nhau lệch 5 nến, đúng 8/10 | tr.10, Hình 6 |

Tài sản 4h (Bảng 3 [tr.28]), mỗi dòng 5.000 nến:

| Asset | Loại | Bắt đầu | Kết thúc |
|---|---|---|---|
| BTC/USD | Cryptocurrency | 2023-04-01 | 2025-06-23 |
| CL | Commodity Futures | 2022-04-25 | 2025-06-19 |
| DJI | Equity Index (Spot) | 2015-08-26 | 2025-05-16 |
| ES | Equity Index Futures | 2022-04-19 | 2025-06-19 |
| NQ | Equity Index Futures | 2022-04-19 | 2025-06-19 |
| QQQ | Equity ETF | 2015-08-24 | 2025-05-16 |
| SPX | Equity Index (Spot) | 2015-08-25 | 2025-05-16 |
| VIX | Volatility Index (CBOE) | 2020-10-20 | 2025-08-27 |

Tài sản 1h (Bảng 4 [tr.29]), mỗi dòng 5.000 nến:

| Asset | Loại | Bắt đầu | Kết thúc |
|---|---|---|---|
| BTC/USD | Cryptocurrency | 2025-02-21 | 2025-09-13 |
| CL | Commodity Futures | 2024-11-12 | 2025-09-10 |
| DJI | Equity Index (Spot) | 2022-11-14 | 2025-09-02 |
| ES | Equity Index Futures | 2024-11-11 | 2025-09-10 |
| NQ | Equity Index Futures | 2024-11-11 | 2025-09-10 |
| QQQ | Equity ETF | 2022-11-14 | 2025-09-02 |
| SPX | Equity Index (Spot) | 2022-11-14 | 2025-09-02 |
| DAX | Equity Index (Futures) | 2024-10-21 | 2025-09-22 |

Baseline [tr.6]:
1. **Random**: chọn ngẫu nhiên LONG/SHORT và risk-reward ∈ [1.2, 1.8].
2. **Linear Regression (LR)**: fit tuyến tính trên **40 nến close** gần nhất; slope > 0 → LONG, ngược lại SHORT.
3. **XGBoost**: feature từ TA-Lib (RSI, MACD, SMA); train trên "hàng trăm mẫu sliding-window" từ 50 file CSV chọn ngẫu nhiên, test trên 50 file còn lại; bỏ phiếu đa số ra LONG/SHORT/HOLD, **quyết định HOLD bị loại khỏi phép tính trung bình**.
4. **QuantHarness**.

Bảng 1 có thêm dòng **TradingAgent** nhưng mục Baselines không mô tả cách chạy baseline này. → **chưa xác minh**.

Số lượng tài sản không nhất quán: abstract ghi "nine financial instruments" [tr.1]; trang dự án ghi "ten"; Bảng 2 có 8; Bảng 3 và 4 mỗi bảng 8 (hợp lại là 9: thêm DAX); Bảng 1 lại có AAPL và AMZN, hai mã **không xuất hiện** trong phần mô tả benchmark.

---

## 5. Kết quả

### 5.1 Bảng 1 — Sharpe, Sortino, Cumulative Return, Max Drawdown [tr.8]

Chép nguyên từ paper. Dòng "Baseline" trong paper toàn dấu "–" nên lược bỏ. "Our" = QuantHarness.

| Asset | Method | Sharpe | Sortino | CumReturn | MaxDrawdown |
|---|---|---|---|---|---|
| AAPL | LR | 0.044 | 0.068 | 10.21% | -29.59% |
| | XGBoost | -0.241 | -0.372 | -5.35% | -8.23% |
| | TradingAgent | -0.189 | -0.245 | -13.69% | 15.25% |
| | **Our** | -0.155 | -0.264 | -22.51% | -25.44% |
| AMZN | LR | 0.298 | 0.709 | 153.29% | -13.60% |
| | XGBoost | -0.248 | -0.324 | -6.82% | -10.31% |
| | TradingAgent | 0.199 | 0.482 | 20.53% | 4.85% |
| | **Our** | 0.236 | 0.502 | 44.85% | -17.31% |
| DJI | LR | 0.332 | 0.779 | 41.46% | -3.12% |
| | XGBoost | 0.320 | 0.751 | 3.87% | -2.61% |
| | TradingAgent | 0.194 | 0.332 | 5.82% | 2.34% |
| | **Our** | 0.271 | 0.590 | 15.50% | -3.12% |
| ES | LR | 0.430 | 0.953 | 74.50% | -5.90% |
| | XGBoost | 0.596 | 0.807 | 9.41% | -1.88% |
| | TradingAgent | 0.017 | 0.030 | 1.25% | 8.55% |
| | **Our** | 0.339 | 0.661 | 25.43% | -4.72% |
| QQQ | LR | 0.250 | 0.415 | 59.16% | -10.74% |
| | XGBoost | 0.684 | 1.604 | 15.54% | -2.01% |
| | TradingAgent | 0.067 | 0.112 | 3.82% | 3.66% |
| | **Our** | 0.516 | 0.000 | 1.44% | -0.27% |
| SPX | LR | 0.467 | 1.017 | 77.78% | -5.12% |
| | XGBoost | 1.266 | 6.048 | 15.34% | -0.37% |
| | TradingAgent | -0.158 | -0.226 | -6.11% | 7.68% |
| | **Our** | 0.179 | 0.301 | 12.52% | -8.24% |
| NQ | LR | 0.246 | 0.399 | 59.11% | -11.53% |
| | XGBoost | -0.072 | -0.108 | -2.00% | -5.10% |
| | TradingAgent | -0.092 | -0.114 | -5.04% | 9.26% |
| | **Our** | 0.190 | 0.289 | 19.76% | -5.46% |
| VIX | TradingAgent | -0.129 | -0.189 | -30.40% | 32.28% |
| | **Our** | -0.141 | -0.460 | -38.70% | -41.14% |

**Kiểm tra lại nhận định "LR có cumulative return cao hơn trên hầu hết mã": đúng, và còn mạnh hơn thế.**

| Asset | CumReturn LR | CumReturn Our | Phương pháp cao nhất | Our xếp hạng |
|---|---|---|---|---|
| AAPL | 10.21% | -22.51% | LR | 4/4 (tệ nhất) |
| AMZN | 153.29% | 44.85% | LR | 2/4 |
| DJI | 41.46% | 15.50% | LR | 2/4 |
| ES | 74.50% | 25.43% | LR | 2/4 |
| QQQ | 59.16% | 1.44% | LR | 4/4 (thua cả XGBoost 15.54% và TradingAgent 3.82%) |
| SPX | 77.78% | 12.52% | LR | 3/4 (thua XGBoost 15.34%) |
| NQ | 59.11% | 19.76% | LR | 2/4 |
| VIX | (không có) | -38.70% | TradingAgent -30.40% | 2/2 (tệ nhất) |

- **Cumulative return**: LR thắng QuantHarness ở **7/7** tài sản có số LR. QuantHarness đứng đầu **0/8**.
- **Sharpe**: QuantHarness đứng đầu **0/8** (LR tốt nhất ở AAPL, AMZN, DJI, NQ; XGBoost ở ES, QQQ, SPX; TradingAgent ở VIX).
- **Sortino**: QuantHarness đứng đầu **0/8**.
- **Max drawdown**: nếu coi số ít âm hơn là tốt hơn, QuantHarness tốt nhất duy nhất ở QQQ (-0.27%). Dòng TradingAgent mang dấu **dương** (15.25%, 32.28%…) trong khi các dòng khác âm — quy ước dấu không nhất quán, không so sánh trực tiếp được.

**Ô in đậm sai trong paper** (in đậm thường nghĩa là tốt nhất cột):
- CumReturn của "Our" được in đậm ở DJI (15.50%), ES (25.43%), QQQ (1.44%), SPX (12.52%), NQ (19.76%) dù LR cao hơn ở cả năm.
- Sharpe/Sortino của "Our" được in đậm ở AMZN (0.236 / 0.502) dù LR là 0.298 / 0.709; ở NQ (0.190 / 0.289) dù LR là 0.246 / 0.399.
- Bảng 1 không có chú thích giải thích quy tắc in đậm.

Điểm bất thường khác: QQQ "Our" có Sharpe 0.516 nhưng Sortino 0.000 và CumReturn chỉ 1.44%, MaxDD -0.27% — tổ hợp này gợi ý gần như không có lệnh hoặc lỗi tính toán; paper không giải thích.

### 5.2 Bảng 2 — khung 4h [tr.9]

Chép nguyên. Baseline = random.

| Asset | Method | Acc α | Δα% | R_cc | R_max | R_min |
|---|---|---|---|---|---|---|
| BTC | Baseline | 45.0 | – | -0.009 | 1.220 | -1.245 |
| | LR | 46.0 | +2.2% | -0.066 | 1.245 | -1.210 |
| | XGBoost | 45.3 | +0.7% | -0.050 | 1.218 | -1.331 |
| | **Our** | 50.7 | +12.7% | 0.089 | 1.232 | -1.212 |
| CL | Baseline | 41.0 | – | -0.373 | 0.970 | -1.348 |
| | LR | 54.3 | +32.4% | -0.114 | 1.178 | -1.141 |
| | XGBoost | 40.0 | -2.4% | -0.056 | 0.958 | -1.151 |
| | **Our** | 55.0 | +34.1% | -0.008 | 1.200 | -1.119 |
| DJI | Baseline | 47.0 | – | 0.048 | 0.755 | -0.793 |
| | LR | 52.0 | +10.6% | 0.149 | 0.790 | -0.725 |
| | XGBoost | 47.3 | +0.6% | -0.020 | 0.874 | -0.660 |
| | **Our** | 52.3 | +11.3% | 0.163 | 0.891 | -0.649 |
| ES | Baseline | 51.0 | – | -0.048 | 0.538 | -0.552 |
| | LR | 43.0 | -15.7% | 0.032 | 0.553 | -0.546 |
| | XGBoost | 52.0 | +2.0% | -0.182 | 0.440 | -0.644 |
| | **Our** | 55.0 | +7.8% | 0.179 | 0.613 | -0.485 |
| VIX | Baseline | 46.3 | – | 0.059 | 3.259 | -3.157 |
| | LR | 48.7 | +5.2% | -0.140 | 3.407 | -3.099 |
| | XGBoost | 53.3 | +15.1% | 0.161 | 3.325 | -3.110 |
| | **Our** | 54.7 | +18.1% | 0.458 | 3.872 | -2.851 |
| NQ | Baseline | 43.7 | – | -0.140 | 0.646 | -0.793 |
| | LR | 48.7 | +11.4% | 0.147 | 0.782 | -0.670 |
| | XGBoost | 47.3 | +8.2% | -0.007 | 0.706 | -0.753 |
| | **Our** | 55.3 | +26.5% | 0.216 | 0.814 | -0.639 |
| QQQ | Baseline | 47.3 | – | -0.048 | 0.930 | -1.017 |
| | LR | 56.0 | +18.4% | 0.175 | 1.113 | -0.849 |
| | XGBoost | 52.7 | +11.4% | 0.210 | 1.206 | -0.973 |
| | **Our** | 59.7 | +26.2% | 0.211 | 1.052 | -0.881 |
| SPX | Baseline | 47.3 | – | -0.162 | 0.719 | -0.862 |
| | LR | 59.7 | +26.2% | 0.377 | 0.960 | -0.648 |
| | XGBoost | 60.0 | +26.8% | 0.050 | 0.782 | -0.712 |
| | **Our** | 63.7 | +34.6% | 0.341 | 0.965 | -0.641 |

Đối chiếu các tuyên bố ở mục 5.1 của paper [tr.9–10]:

| Tuyên bố | Kết quả kiểm tra |
|---|---|
| Accuracy cao nhất ở cả 8 thị trường | Đúng theo bảng. Nhưng chênh với phương pháp đứng nhì chỉ 0,3 điểm ở DJI (52.3 vs 52.0), 0,7 ở CL (55.0 vs 54.3), 1,4 ở VIX |
| R_cc tốt nhất 7/8 | Đúng (thua LR ở SPX: 0.341 vs 0.377). Ở CL, "tốt nhất" vẫn là số âm (-0.008); ở QQQ hơn XGBoost 0.001 |
| R_max cao nhất 6/8 | Đúng (thua LR ở BTC, thua XGBoost ở QQQ) |
| R_min tốt | Tốt nhất ở 6/8; thua LR ở BTC và QQQ |

Nhận xét:
- Baseline ngẫu nhiên đạt 41.0–51.0% tuỳ tài sản. Một bộ sinh ngẫu nhiên lý tưởng nên quanh 50%; việc nó dao động tới 10 điểm cho thấy **nhiễu lấy mẫu của chính phép đo đã vào cỡ ±5 điểm**. Mọi chênh lệch dưới mức đó (phần lớn bảng) không thể coi là có ý nghĩa.
- Cột Δα% so với baseline ngẫu nhiên thấp bất thường (41.0 ở CL, 43.7 ở NQ) nên con số "+34.1%", "+26.5%" bị thổi phồng.
- LR (40 nến, một dòng code) bám rất sát: 59.7 vs 63.7 ở SPX, 56.0 vs 59.7 ở QQQ, 54.3 vs 55.0 ở CL.
- Trên chỉ số cổ phiếu Mỹ giai đoạn 2015–2025 (xu hướng tăng dài), bất kỳ chiến lược thiên LONG nào cũng có accuracy > 50%. Paper không báo cáo tỷ lệ LONG/SHORT của hệ thống hay baseline "always LONG".

### 5.3 Khung 1h — Hình 5 [tr.10]

Kết quả 1h chỉ có dạng **biểu đồ đường** cho 8 tài sản (BTC, CL, DAX, DJI, ES, NQ, QQQ, SPX); **không có bảng số**. Paper khẳng định QuantHarness vượt baseline "across most metrics and markets", rõ nhất ở SPX, QQQ, BTC, nhưng thừa nhận "less satisfactory R_min in some assets". Không chép được số liệu → **chưa xác minh** giá trị cụ thể.

### 5.4 Case study [tr.10–11]

- SPX (2025), 10 cửa sổ chồng nhau: đúng 8/10 = "80%". Sai ở cửa sổ 2 và 7 (paper giải thích do dựa vào pattern chưa hoàn chỉnh và gọi tăng quá sớm).
- Con số "up to 80% directional accuracy" ở phần giới thiệu [tr.2] chính là 8/10 này: **một đoạn, mười mẫu chồng lấn**, không phải kết quả thống kê.

### 5.5 Hạn chế paper tự nêu [tr.11]

- Độ chính xác giảm mạnh ở nến cực ngắn (≈ 1–15 phút) so với 30 phút–4 giờ.
- Không thực sự real-time: mỗi chu kỳ gồm lời gọi LLM và nhiều tool, độ trễ có thể vượt cửa sổ cơ hội 1 phút.

---

## 6. Đánh giá phản biện

### 6.1 Những điểm paper không tính / không nói

| Vấn đề | Tình trạng |
|---|---|
| Phí giao dịch, slippage, spread, funding | **Không được nhắc tới ở bất kỳ đâu** trong paper; tìm trong repo (`fee`, `commission`, `slippage`) cũng không có. Với stop 0,05% và take-profit 0,06–0,09%, một lượt phí taker crypto điển hình đã cùng cỡ hoặc lớn hơn toàn bộ biên lợi nhuận mục tiêu |
| HOLD | Cấm trong prompt [tr.6, tr.21]. Hệ thống buộc phải vào lệnh cả khi tín hiệu mâu thuẫn. Baseline XGBoost thì được HOLD và các lần HOLD bị loại khỏi trung bình [tr.6] → so sánh không cùng điều kiện |
| Model LLM của thực nghiệm | Không nêu. Không tái lập được |
| Ý nghĩa thống kê | Không có khoảng tin cậy, p-value, số seed, số lần chạy lặp; LLM có temperature 0.1 nên không tất định |
| Ablation | Không có. Không biết agent nào đóng góp, hay một lời gọi LLM đơn lẻ có đạt kết quả tương đương không |
| Chi phí và độ trễ | Không có số liệu token, tiền, giây/quyết định |
| Định nghĩa metric Bảng 1 | Không có (mục 3.2) |
| N, τ của Thuật toán 1 | Không có |
| Đơn vị và công thức R_cc | Không rõ (mục 3.1) |
| Baseline TradingAgent | Có trong Bảng 1, không mô tả cấu hình |
| Quy mô vị thế, đòn bẩy, vốn | Không nêu |

### 6.2 Rủi ro rò rỉ dữ liệu

- **Giấu 3 nến cuối** là đúng về mặt quy trình [tr.6, tr.28]. Tuy nhiên file CSV benchmark trong repo có đủ **100 dòng** (đã kiểm tra), tức chứa cả 3 nến đáp án; việc cắt bỏ phải do script đánh giá làm, mà script này **không có trong repo** → không kiểm chứng được.
- **Các đoạn chồng lấn mạnh.** 100 đoạn × 100 nến lấy từ 5.000 nến. Kiểm tra trực tiếp trên repo cho 4 thư mục (`benchmark/btc`, `benchmark/1h/btc`, `benchmark/spx`, `benchmark/vix`): sau khi sắp theo thời gian, **86/99 cặp đoạn liền kề chồng lên nhau**. Hệ quả: (a) các mẫu không độc lập, cỡ mẫu hiệu dụng nhỏ hơn 100; (b) XGBoost train trên 50 file, test trên 50 file còn lại sẽ thấy dữ liệu trùng thời gian với tập test.
- **LLM có thể đã "thấy" lịch sử giá.** Dữ liệu 4h của DJI/QQQ/SPX kéo từ 2015; prompt chứa cả cột `Datetime` và trục thời gian trên ảnh, cộng với tên tài sản ở DecisionAgent. Một LLM huấn luyện tới 2023–2024 có thể nhớ diễn biến thị trường các ngày đó. Paper không bàn và không làm thí nghiệm che ngày/tên. Đây là rủi ro, **chưa xác minh** mức độ ảnh hưởng.
- Không có tách train/test theo thời gian vì hệ thống zero-shot; nhưng việc thiết kế prompt (16 pattern, quy tắc quyết định) có được tinh chỉnh trên chính benchmark này hay không thì paper không nói.

### 6.3 Cỡ mẫu

- 100 đoạn mỗi tài sản, mỗi đoạn chấm 3 nến tương quan nhau. Sai số chuẩn của accuracy vào khoảng 3–5 điểm %. Chỉ SPX (63.7) và QQQ (59.7) cách mốc 50% đủ xa, và hai mã này lại có thiên hướng tăng dài hạn.
- Case study "80%" dựa trên 10 mẫu.

### 6.4 Cách dùng từ

- "High-Frequency Trading" trong tên paper không khớp với thực nghiệm trên nến **1h và 4h**; chính paper thừa nhận kém ở 1–15 phút và không real-time [tr.11].
- "Consistently outperforms baseline methods" [tr.1] không đứng vững trước Bảng 1.
- RiskAgent được trình bày như một agent nhưng không có prompt, không có code.

### 6.5 Điểm mạnh thật sự

- Số liệu indicator do tool (TA-Lib) tính, LLM chỉ diễn giải → giảm bịa số.
- Mỗi quyết định kèm lý do bằng ngôn ngữ tự nhiên, truy vết được theo từng agent.
- Benchmark CSV công khai (16 thư mục × 100 file) và code MIT.
- Paper tự công bố Bảng 1 dù bất lợi, và có mục Limitations.

---

## 7. Repo: cấu trúc và cách chạy

### 7.1 Cấu trúc (commit `2e64c7b`)

```
QuantHarness/
├── trading_graph.py      # TradingGraph: khởi tạo LLM theo provider, dựng graph
├── graph_setup.py        # SetGraph: nối Indicator → Pattern → Trend → Decision
├── agent_state.py        # IndicatorAgentState (TypedDict)
├── indicator_agent.py    # node Indicator + prompt
├── pattern_agent.py      # node Pattern + thư viện 16 pattern
├── trend_agent.py        # node Trend + prompt
├── decision_agent.py     # node Decision + prompt
├── graph_util.py         # TechnicalTools (@tool): 5 indicator, 2 hàm vẽ, fit trendline
├── static_util.py        # bản không-@tool của 2 hàm vẽ (web dùng để dựng ảnh trước)
├── color_style.py        # style mplfinance
├── default_config.py     # model, provider, temperature, API key
├── web_interface.py      # Flask app, lấy dữ liệu yfinance, 1.175 dòng
├── templates/            # demo.html, demo_new.html, output.html
├── tests/                # chỉ test provider MiniMax
├── benchmark/            # CSV: {btc,cl,dji,es,nq,qqq,spx,vix}/ (4h) và 1h/{btc,cl,dax,dji,es,nq,qqq,spx}/
├── index.html, assets/   # trang dự án (GitHub Pages)
├── requirements.txt
├── README.md, README_CN.md
└── LICENSE               # MIT
```

- Benchmark: 16 thư mục × 100 file × 100 dòng; cột `Datetime,Close,High,Low,Open,Volume`. Tên file dạng `BTC_4h_1.csv`, `BTC_1h_1.csv`.
- **Không có**: script đánh giá, code baseline (LR / XGBoost / random / TradingAgent), code tính Sharpe/R_cc, RiskAgent, backtest, kết nối sàn/đặt lệnh, pin phiên bản thư viện.

### 7.2 Dependencies (`requirements.txt`, không pin version)

`flask, yfinance, pandas, numpy, matplotlib, mplfinance, scipy, TA-Lib, langchain, langchain-openai, langchain-anthropic, langchain-qwq, langchain-core, langgraph, openai, anthropic, ipython, Pillow, requests`

TA-Lib cần thư viện C; README gợi ý `conda install -c conda-forge ta-lib` nếu `pip` lỗi.

### 7.3 Cách chạy (theo README; **chưa chạy thử** trong lần khảo sát này)

```bash
conda create -n quantharness python=3.11
conda activate quantharness
pip install -r requirements.txt

export OPENAI_API_KEY="..."        # hoặc ANTHROPIC_API_KEY / DASHSCOPE_API_KEY / MINIMAX_API_KEY

python web_interface.py            # http://127.0.0.1:5000
```

Dùng trong code:

```python
from trading_graph import TradingGraph

tg = TradingGraph()                       # hoặc TradingGraph(config={...})
state = {
    "kline_data": df_dict,                # dict các list: Datetime, Open, High, Low, Close
    "analysis_results": None,
    "messages": [],
    "time_frame": "4hour",
    "stock_name": "BTC",
}
out = tg.graph.invoke(state)
out["final_trade_decision"]; out["indicator_report"]; out["pattern_report"]; out["trend_report"]
```

Cấu hình [code: `default_config.py`]: `agent_llm_model="gpt-4o-mini"`, `graph_llm_model="gpt-4o"`, hai temperature = 0.1. Provider hỗ trợ trong code: `openai`, `anthropic`, `qwen`, `minimax`, `minimax_cn`, `gemini` (README không nhắc `gemini`). Model mặc định khi đổi provider (theo README): Anthropic `claude-haiku-4-5-20251001`; Qwen `qwen3-max` / `qwen3-vl-plus`; MiniMax `MiniMax-M3`. **Bắt buộc model nhận ảnh.**

Lưu ý khi chạy:
- Web demo lấy dữ liệu qua yfinance (BTC → `BTC-USD`, NQ → `NQ=F`, SPX → `^GSPC`…), cắt `tail(45)`, dựng sẵn ảnh rồi mới gọi graph. Khung 1h/4h giới hạn 730 ngày; 30m giới hạn 60 ngày.
- Tool ghi file vào thư mục hiện hành: `kline_chart.png`, `trend_graph.png`, `record.csv` (dpi 600, ảnh lớn → tốn token vision).
- `DEFAULT_CONFIG["api_key"] = "sk-"` là chuỗi không rỗng nên code sẽ không rơi về biến môi trường nếu dùng config mặc định qua đường Python; cần gán key vào config hoặc qua web UI. (Suy ra từ đọc code `_get_api_key`, **chưa chạy thử**.)
- Web demo có các trường tĩnh giả lập ở trang output (ví dụ `"forecast_horizon": "24-48 hours"`); Hình 12 trong paper [tr.27] cũng hiện ADX, "RSI Divergence", "Volume" — các chỉ số **không có** trong tool.

### 7.4 License

- Code: **MIT**, "Copyright (c) 2025 Y-Research @SBU" [`LICENSE`]. Được dùng, sửa, phân phối, thương mại hoá, miễn giữ thông báo bản quyền.
- Trang dự án ghi ở chân trang "© 2025 QuantHarness, All Rights Reserved" — áp cho nội dung trang web, không đổi license của code.
- README có disclaimer: chỉ cho mục đích giáo dục/nghiên cứu, không phải tư vấn tài chính.
- Phần fit trendline lấy từ `neurotrader888/TechnicalAnalysisAutomation` (README ghi nhận); license của repo gốc đó **chưa xác minh**.
- Dữ liệu benchmark lấy từ TradingView/yfinance; điều khoản tái phân phối dữ liệu **chưa xác minh**.

---

## 8. Áp dụng cho dự án

### 8.1 Đáng tái dùng

| Thành phần | Lý do |
|---|---|
| Tách vai trò: indicator / pattern / trend / decision, state dùng chung | Dễ thay từng phần, dễ log và debug |
| Tool tính indicator bằng thư viện, LLM chỉ diễn giải | Tránh LLM bịa số |
| Hàm fit trendline support/resistance (`fit_trendlines_single`, `optimize_slope`) | Thuật toán tất định, dùng được độc lập với LLM (kiểm tra license nguồn gốc trước) |
| Schema đầu ra quyết định (direction, justification, risk_reward) | Điểm khởi đầu tốt, cần siết thành structured output |
| Bộ CSV benchmark + giao thức "giấu k nến cuối" | Dùng làm smoke test nhanh |
| Baseline LR 40 nến | Rẻ, mạnh; **mọi phiên bản của dự án phải thắng baseline này sau phí** mới đáng giữ |

### 8.2 Cần thay đổi

1. **Viết harness đánh giá riêng** (repo không có): walk-forward theo thời gian, đoạn không chồng lấn, có phí + slippage + funding, có baseline always-long / buy-and-hold / random / LR / momentum đơn giản, có khoảng tin cậy (bootstrap) và nhiều seed.
2. **Cho phép HOLD / không vào lệnh** và đo cả tỷ lệ tham gia. Cấm HOLD buộc hệ thống đánh cả khi không có lợi thế.
3. **Risk tính bằng code, không để LLM chọn.** Thay stop cố định 0,05% bằng stop theo biến động (ATR hoặc độ lệch chuẩn theo khung thời gian và tài sản); tính position sizing, giới hạn lỗ theo ngày ở tầng tất định.
4. **Cài thật Thuật toán 1** với độ dốc chuẩn hoá (theo % giá hoặc theo ATR) và τ được hiệu chỉnh trên tập validation; đưa kết quả phân loại dạng số cho LLM thay vì chỉ đưa ảnh.
5. **Sửa lỗi dữ liệu indicator**: bỏ `fillna(0)`, nạp đủ nến warm-up (ít nhất ~100 nến cho MACD 12/26/9), chỉ trả phần hợp lệ.
6. **Kiểm chứng pattern bằng thuật toán** (pivot, độ hội tụ) trước hoặc song song với vision; đo riêng độ chính xác nhận diện pattern. Giảm dpi ảnh để tiết kiệm token.
7. **Chống rò rỉ từ trí nhớ LLM**: thử che ngày tháng và tên tài sản, chuẩn hoá giá; ưu tiên đánh giá trên dữ liệu sau ngày cutoff của model.
8. **Ablation bắt buộc**: một lời gọi LLM đơn vs đa agent; bỏ từng agent; chỉ số liệu vs có ảnh. Giữ lại phần nào chứng minh được đóng góp.
9. **Structured output + validation** cho mọi agent (JSON schema), parse và kiểm tra miền giá trị; pin version thư viện; log đầy đủ prompt/response/chi phí/độ trễ.
10. **Không gọi là HFT.** Phạm vi thực tế là hỗ trợ quyết định ở khung 30 phút–4 giờ trở lên. Với cổ phiếu, cân nhắc thêm dữ liệu ngoài giá (paper cố ý loại bỏ).
11. Thực thi lệnh thật nằm ngoài phạm vi repo này; nếu dự án cần, đó là một phần phải thiết kế riêng với kiểm soát rủi ro độc lập với LLM.

---

## 9. Danh sách "chưa xác minh"

1. Model LLM dùng cho thực nghiệm trong paper (code mặc định gpt-4o / gpt-4o-mini, paper không nêu).
2. Giá trị N và τ của Thuật toán 1.
3. Công thức chính xác và đơn vị của R_cc, R_max, R_min; cách chúng tương thích với stop-loss 0,05%.
4. Toàn bộ thiết lập của Bảng 1: khung thời gian, giai đoạn, cách tính Sharpe/Sortino/CumReturn/MaxDD, quy ước dấu MaxDD, nguồn dữ liệu AAPL/AMZN, cấu hình baseline TradingAgent, lý do VIX thiếu LR/XGBoost.
5. Số liệu cụ thể khung 1h (chỉ có biểu đồ, Hình 5).
6. Script đánh giá có thật sự cắt 3 nến cuối trước khi đưa vào LLM hay không (script không công bố).
7. Mức ảnh hưởng của việc LLM đã thấy dữ liệu lịch sử trong lúc huấn luyện.
8. Prompt/benchmark có được tinh chỉnh lặp trên cùng tập test hay không.
9. RiskAgent có tồn tại dưới dạng code ở phiên bản nào khác không (không có ở commit `2e64c7b`).
10. Mô tả "extract swing pivots / least-squares fit" của PatternAgent ở Phụ lục F ứng với code nào.
11. Repo có chạy được nguyên trạng không (chưa cài đặt và chạy thử); hành vi `api_key="sk-"` chỉ suy ra từ đọc code.
12. License của mã trendline gốc (`TechnicalAnalysisAutomation`) và điều khoản tái phân phối dữ liệu TradingView/yfinance.
13. Số tài sản "chín" (abstract) hay "mười" (trang dự án) — các bảng không khớp với cả hai.
14. Mức độ chồng lấn đoạn benchmark mới kiểm tra trên 4/16 thư mục.
