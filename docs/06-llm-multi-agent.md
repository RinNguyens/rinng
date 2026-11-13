# 06 — Lớp LLM multi-agent cho quant trading / crypto / phân tích cổ phiếu

> Ngày tra cứu: **2026-11-13**. Mọi số liệu "hiện hành" (model ID, giá, sao GitHub, license) được đọc trực tiếp từ nguồn trong ngày này và kèm URL.
> Quy ước: **[chưa xác minh]** = chưa đọc được từ nguồn gốc trong phiên tra cứu này (lấy từ nguồn thứ cấp hoặc kiến thức nền), cần kiểm tra lại trước khi dựa vào.
> Tài liệu này không phải lời khuyên đầu tư. Phần 2 (bằng chứng phản biện) nên được đọc trước khi quyết định đầu tư công sức vào lớp LLM.

## Mục lục

1. [Tổng quan các hệ LLM cho tài chính](#1-tổng-quan-các-hệ-llm-cho-tài-chính)
2. [Bằng chứng phản biện và cách thiết kế đánh giá](#2-bằng-chứng-phản-biện-và-cách-thiết-kế-đánh-giá)
3. [Framework dựng agent](#3-framework-dựng-agent)
4. [Kỹ thuật cần cho dự án](#4-kỹ-thuật-cần-cho-dự-án)
5. [Claude API cụ thể](#5-claude-api-cụ-thể)
6. [MCP server tài chính / crypto / TradingView](#6-mcp-server-tài-chính--crypto--tradingview)
7. [Đề xuất kiến trúc cho dự án](#7-đề-xuất-kiến-trúc-cho-dự-án)
8. [Danh sách điều chưa xác minh](#8-danh-sách-điều-chưa-xác-minh)

---

## 1. Tổng quan các hệ LLM cho tài chính

### 1.0 Bảng tóm tắt

Số sao và ngày push lấy từ GitHub API ngày 2026-11-13.

| Hệ | Loại | Repo | License | Sao | Push gần nhất |
|---|---|---|---|---|---|
| QuantHarness | Multi-agent, chỉ OHLC, có vision | [Y-Research-SBU/QuantHarness](https://github.com/Y-Research-SBU/QuantHarness) | MIT | 2.9k | 2026-08-18 |
| TradingAgents | Multi-agent mô phỏng công ty trading | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | 122.4k | 2026-11-04 |
| FinMem | Single agent + layered memory | [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) | MIT | 973 | 2024-08-18 |
| FinCon | Multi-agent manager–analyst | [The-FinAI/FinCon](https://github.com/The-FinAI/FinCon) | MIT | 72 | 2026-10-08 |
| FinGPT | LLM tài chính mã nguồn mở (fine-tune) | [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | MIT | 21.6k | 2026-10-25 |
| FinRobot | Nền tảng agent phân tích tài chính | [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | Apache-2.0 | 8.4k | 2026-10-24 |
| RD-Agent(Q) | Agent tự động R&D factor + model | [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) | MIT | 15.4k | 2026-10-21 |
| FinAgent | Multimodal agent + tool + reflection | [DVampire/FinAgent](https://github.com/DVampire/FinAgent) | MIT | 78 | 2024-08-31 |
| StockAgent | Mô phỏng thị trường bằng nhiều agent | [MingyuJ666/Stockagent](https://github.com/MingyuJ666/Stockagent) | **không khai báo** | 719 | 2026-06-16 |
| AI Hedge Fund | Proof of concept giáo dục | [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | MIT | 64.7k | 2026-11-09 |
| Trading-R1 | Terminal nghiên cứu tài chính | [TauricResearch/Trading-R1](https://github.com/TauricResearch/Trading-R1) | Apache-2.0 | 678 | 2026-11-09 |
| AI-Trader | Benchmark agent giao dịch thời gian thực | [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) | **không khai báo** | 23.3k | 2026-06-11 |

Repo không khai báo license nghĩa là mặc định "all rights reserved": đọc để học được, không nên sao chép code vào dự án.

### 1.1 QuantHarness (nguồn cảm hứng của dự án)

- **Paper**: "QuantHarness: Price-Driven Multi-Agent LLMs for High-Frequency Trading", Xiong, Zhang, Feng, Sun, You. arXiv [2509.09995](https://arxiv.org/abs/2509.09995), v1 ngày 2025-09-12, bản hiện hành v4 ngày 2026-07-27. Repo trước đây tên `QuantAgent`, nay chuyển hướng về `QuantHarness`.
- **Ý tưởng**: bỏ hẳn tin tức và mạng xã hội, chỉ dùng tín hiệu suy ra từ giá (OHLC) cho khung ngắn 1h/4h.
- **Kiến trúc** (đọc từ [bản HTML v4](https://arxiv.org/html/2509.09995v4)): dựng trên **LangGraph**. Abstract nêu bốn agent (Indicator, Pattern, Trend, Risk); mục 3.4 của paper thêm DecisionAgent làm lớp tổng hợp cuối.
  - IndicatorAgent: gọi tool `compute_rsi`, `compute_macd`, `compute_roc`, `compute_stoch`, `compute_willr`.
  - PatternAgent: tool `generate_kline_image` vẽ chart nến giản lược, model vision so với thư viện 16 mẫu hình cổ điển.
  - TrendAgent: tool `generate_trend_image` vẽ chart có hai đường hỗ trợ/kháng cự fit bằng OLS, phân loại trend theo độ dốc.
  - RiskAgent: stop-loss cố định 0.0005, take-profit = r × stop-loss, LLM chỉ dự đoán r trong [1.2, 1.8].
  - DecisionAgent: ra LONG/SHORT, lý do, tỉ lệ risk-reward, dự báo cho 3 nến kế tiếp.
- **Dữ liệu vào**: OHLC; README cho biết lấy 30 nến gần nhất từ Yahoo Finance qua `yfinance`, cần TA-Lib, và model phải nhận được ảnh.
- **Kết quả công bố**: directional accuracy 1h, ví dụ SPX 63.7% (random 47.3%), NQ 55.3% (random 43.7%), BTC 50.7% (random 45.0%). Baseline: random, linear regression (độ dốc 40 nến), XGBoost.
- **Hạn chế** (một phần do chính paper nêu, một phần đọc từ bảng kết quả):
  - Cumulative return âm trên một số mã (AAPL −22.51%, VIX −38.70%) và linear regression thường có return cao hơn. Accuracy cao hơn random **không** kéo theo lợi nhuận.
  - Paper không nêu tên LLM được dùng ("zero-shot LLM ensemble"), nên không kiểm tra được knowledge cutoff so với giai đoạn test (dữ liệu 4h trải 2015–2025, 1h chủ yếu 2022–2025). Rủi ro look-ahead ở mục 2.2 áp dụng trực tiếp.
  - Số lượng tài sản không nhất quán giữa abstract (chín), thân bài (tám) và các bảng.
  - Không thật sự real-time: mỗi chu kỳ gồm một lần gọi LLM và nhiều tool call; chính tác giả nói độ chính xác giảm ở nến 1–15 phút.
  - Paper không mô tả chi phí giao dịch/slippage **[chưa xác minh]** (chưa đọc 13k ký tự cuối của bản HTML).
- **Mặc định model trong README**: Anthropic `claude-haiku-4-5-20251001`; OpenAI `gpt-4o-mini`/`gpt-4o`; Qwen `qwen3-max`/`qwen3-vl-plus`; MiniMax `MiniMax-M3`.

### 1.2 TradingAgents (TauricResearch)

- **Paper**: arXiv [2412.20138](https://arxiv.org/abs/2412.20138).
- **Ý tưởng**: mô phỏng một công ty trading với các vai chuyên biệt tranh luận với nhau.
- **Kiến trúc** (đọc từ [README](https://github.com/TauricResearch/TradingAgents)): dựng bằng LangGraph. Analyst Team (Fundamentals, Sentiment, News, Technical) chạy song song → Researcher Team (bull và bear tranh luận) → Trader → Risk Management → Portfolio Manager duyệt hoặc từ chối.
- **Dữ liệu vào**: SEC EDGAR, Yahoo Finance, StockTwits, Reddit, FRED, Polymarket, Alpha Vantage (cần API key).
- **LLM**: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Mistral, Kimi, Groq, NVIDIA NIM, Ollama.
- **Phiên bản**: README ghi v0.7.1 (2026-10).
- **Kết quả công bố**: paper báo cáo vượt các baseline về cumulative return, Sharpe và max drawdown trên vài mã cổ phiếu Mỹ trong vài tháng năm 2024 **[chưa xác minh con số cụ thể]**.
- **Hạn chế**: README tự ghi "designed for research purposes", không phải lời khuyên đầu tư, kết quả thay đổi theo model, temperature, chất lượng dữ liệu. Giai đoạn backtest ngắn và nằm trong vùng dữ liệu huấn luyện của LLM. Mỗi quyết định tốn rất nhiều lần gọi LLM. FINSABER (mục 2.1) kiểm tra lại nhóm hệ này trên khung dài và thấy lợi thế biến mất.

### 1.3 FinMem

- **Paper**: arXiv [2311.13743](https://arxiv.org/abs/2311.13743); đã đăng IEEE Transactions on Big Data (2025) theo nguồn thứ cấp.
- **Ý tưởng**: một agent có ba mô-đun profiling (tính cách/khẩu vị rủi ro), layered memory (nông/trung/sâu, mỗi lớp có tốc độ quên khác nhau) và decision.
- **Dữ liệu vào**: giá ngày, tin tức, báo cáo 10-Q/10-K.
- **Kết quả công bố**: tác giả báo cáo cumulative return và Sharpe tốt hơn baseline thuật toán trên vài mã cổ phiếu Mỹ **[chưa xác minh con số]**.
- **Hạn chế**: repo không còn hoạt động từ 2024-08; đánh giá từng mã riêng lẻ, khung ngắn; là đối tượng bị FINSABER kiểm tra lại.

### 1.4 FinCon

- **Paper**: arXiv [2407.06567](https://arxiv.org/abs/2407.06567), NeurIPS 2024 **[chưa xác minh venue trong phiên này]**.
- **Ý tưởng**: phân cấp manager–analyst kiểu công ty đầu tư; "conceptual verbal reinforcement": sau mỗi episode một mô-đun kiểm soát rủi ro cập nhật "niềm tin đầu tư" bằng lời rồi truyền ngược xuống các agent. Làm cả single-stock trading lẫn portfolio management.
- **Hạn chế**: repo nhỏ (72 sao); việc "học" bằng lời trên dữ liệu quá khứ càng làm tăng nguy cơ overfit và leakage.

### 1.5 FinGPT

- **Paper**: arXiv [2306.06031](https://arxiv.org/abs/2306.06031).
- **Ý tưởng**: không phải trading agent. Đây là bộ công cụ và model mã nguồn mở để fine-tune LLM (LoRA) cho tác vụ tài chính như sentiment, phân loại tin, trích xuất quan hệ, dự báo.
- **Liên quan tới dự án**: hữu ích nếu sau này cần sentiment từ tin tức. Dự án hiện chỉ dùng OHLC nên chưa cần.
- **Hạn chế**: model nền cũ hơn nhiều so với model thương mại hiện hành; benchmark sentiment không chuyển thành lợi nhuận giao dịch.

### 1.6 FinRobot

- **Paper**: arXiv [2405.14767](https://arxiv.org/abs/2405.14767).
- **Ý tưởng**: nền tảng agent cho phân tích tài chính (báo cáo định giá, phân tích doanh nghiệp) theo nhiều tầng: agent, thuật toán LLM, LLMOps/DataOps, foundation model. Một paper benchmark mô tả nó thiên về phân tích thị trường hơn là giao dịch.
- **Framework nền**: AutoGen **[chưa xác minh trong phiên này]**. Lưu ý AutoGen đã vào maintenance mode (mục 3.6).

### 1.7 RD-Agent(Q) của Microsoft

- **Paper**: "R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization", arXiv [2505.15155](https://arxiv.org/abs/2505.15155) (v2 ngày 2025-09-25).
- **Ý tưởng**: LLM không ra lệnh mua/bán. LLM đóng vai nhà nghiên cứu: đề xuất giả thuyết factor, viết code, chạy backtest trên Qlib, đọc kết quả rồi lặp lại. Hai pha Research và Development nối bằng pha Feedback; một multi-armed bandit scheduler chọn hướng tối ưu factor hay model.
- **Kết quả công bố**: ARR khoảng gấp đôi thư viện factor cổ điển với ít hơn 70% số factor, chi phí dưới 10 USD mỗi lần chạy.
- **Vì sao đáng chú ý**: đầu ra là **code factor tất định**, backtest được, kiểm toán được, chạy không cần LLM. AlphaForgeBench (mục 2.3) lập luận đây là cách dùng LLM ổn định hơn so với để LLM ra quyết định trực tiếp.
- **Hạn chế**: vòng lặp tìm factor trên dữ liệu quá khứ là data mining; cần giữ tập out-of-sample tách biệt và hiệu chỉnh multiple testing. Venue NeurIPS **[chưa xác minh]**.

### 1.8 FinAgent

- **Paper**: "A Multimodal Foundation Agent for Financial Trading: Tool-Augmented, Diversified, and Generalist", arXiv [2402.18485](https://arxiv.org/abs/2402.18485), KDD 2024 **[chưa xác minh venue]**.
- **Ý tưởng**: agent đa phương thức (số, văn bản, **ảnh chart**), có market intelligence module, dual-level reflection, diversified memory retrieval, và dùng tool/chiến lược chuyên gia làm tham chiếu.
- **Kết quả công bố**: 6 bộ dữ liệu (cổ phiếu và crypto), vượt 9 baseline; return 92.27% trên một bộ dữ liệu.
- **Hạn chế**: repo dừng từ 2024-08; return rất cao trên một mã trong khung ngắn là dấu hiệu cần nghi ngờ theo mục 2.

### 1.9 StockAgent

- **Paper**: arXiv [2407.18957](https://arxiv.org/abs/2407.18957); mô tả repo ghi "[TIST]".
- **Ý tưởng**: mô phỏng **thị trường** với nhiều agent nhà đầu tư để nghiên cứu hành vi dưới tác động của sự kiện bên ngoài. Không nhằm tạo chiến lược sinh lời.
- **Liên quan tới dự án**: thấp. FinCon nhận xét kiểu thảo luận nhiều agent làm tăng chi phí giao tiếp và chậm quyết định.

### 1.10 AI Hedge Fund (virattt)

- **Đọc từ [README](https://github.com/virattt/ai-hedge-fund)**: proof of concept cho mục đích giáo dục; "the system does not actually make any trades"; có paper trading bằng tiền mô phỏng và backtester so với benchmark. Cần API key của Financial Datasets và một API key model. Hỗ trợ Anthropic, OpenAI, DeepSeek, Google, xAI, Kimi.
- **Kiến trúc**: nhiều "investor agent" mô phỏng phong cách nhà đầu tư nổi tiếng cộng agent định giá, sentiment, fundamentals, technicals, risk manager, portfolio manager, điều phối bằng LangGraph **[chưa xác minh danh sách agent và framework trong phiên này]**.
- **Hạn chế**: không có kết quả công bố có kiểm chứng; persona "nhà đầu tư nổi tiếng" là prompt nhập vai, không phải phương pháp định lượng.

### 1.11 Alpha Arena và các benchmark LLM giao dịch thật

Trang [nof1.ai](https://nof1.ai/) chỉ dẫn link sang alphaarena.ai, và alphaarena.ai trả HTTP 429 khi tra cứu. Vì vậy **toàn bộ số liệu Alpha Arena dưới đây lấy từ báo chí, [chưa xác minh] với nguồn gốc**.

- **Season 1** (khoảng 2025-10-17 đến 2025-11-03): sáu LLM, mỗi model 10.000 USD tiền thật, giao dịch crypto perpetual trên Hyperliquid, cùng prompt và dữ liệu. Qwen thắng với khoảng +22.3%; chỉ Qwen và DeepSeek có lãi; GPT-5 lỗ hơn 62%. Nguồn: [Decrypt](https://decrypt.co/345006/ai-crypto-trading-showdown-deepseek-grok-winning-gemini-implodes), [iWeaver](https://iweaver.ai/blog/alpha-arena-ai-trading-season-1-results).
- **Season 1.5** (2025-11-19 đến 2025-12-03): tám model, cổ phiếu Mỹ. "Mystery Model" thắng với +12.11%, sau được cho là Grok 4.20. Nguồn: [GNcrypto](https://www.gncrypto.news/news/mystery-model-alpha-arena-season-1-5-winner/), [ForkLog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/amp).
- **Season 2**: không tìm được ngày bắt đầu hay kết quả được xác nhận.
- **Cách đọc**: mỗi mùa chỉ 2–3 tuần, một lần chạy cho mỗi model, đòn bẩy cao. Thứ hạng đảo lộn giữa các mùa. Đây là giai thoại, không đủ sức mạnh thống kê để kết luận model nào "giỏi trade". Nhà sáng lập Nof1 cũng nói chưa thể giao tiền cho LLM tự trade (theo báo chí).

Các benchmark học thuật chạy live hoặc sau cutoff:

| Benchmark | Thiết kế | Phát hiện chính |
|---|---|---|
| StockBench, arXiv [2510.02209](https://arxiv.org/abs/2510.02209), repo [ChenYXxxx/stockbench](https://github.com/ChenYXxxx/stockbench) (Apache-2.0) | Dữ liệu sau training cutoff của model; giá, fundamentals, tin tức hằng ngày; khoảng 82 phiên (2025-03 đến 2025-06) **[chưa xác minh cửa sổ]** | Phần lớn model không vượt được equal-weight buy-and-hold; giỏi QA tài chính không kéo theo giỏi giao dịch |
| LiveTradeBench, arXiv [2511.03628](https://arxiv.org/abs/2511.03628) | 50 ngày live, 21 LLM, cổ phiếu Mỹ và Polymarket | Điểm LMArena cao không kéo theo kết quả giao dịch tốt hơn |
| AI-Trader, arXiv [2512.10971](https://arxiv.org/abs/2512.10971) | 6 LLM, cổ phiếu Mỹ, A-shares, crypto, nhiều tần suất | "General intelligence does not automatically translate to effective trading capability"; đa số agent return kém, quản trị rủi ro yếu |
| Agent Market Arena ("When Agents Trade") | Live, nhiều thị trường | Kết quả tích cực hơn: một số agent vượt buy-and-hold; kiến trúc agent quan trọng hơn LLM nền **[chưa xác minh, chỉ đọc bản tóm tắt thứ cấp]** |

### 1.12 Công trình mới 2025–2026 khác

- **FINSABER**, arXiv [2505.07078](https://arxiv.org/abs/2505.07078), KDD 2026 Datasets & Benchmarks (Oral), repo [waylonli/FINSABER](https://github.com/waylonli/FINSABER) (Apache-2.0). Xem mục 2.1.
- **Profit Mirage**, arXiv [2510.07920](https://arxiv.org/abs/2510.07920). Xem mục 2.2.
- **AlphaForgeBench**, arXiv [2602.18481](https://arxiv.org/abs/2602.18481) (v2 ngày 2026-05-27). Xem mục 2.3.
- **Trading-R1**: paper "Trading-R1: Financial trading with LLM reasoning via reinforcement learning" (Xiao và cộng sự, theo trích dẫn trong repo; mã arXiv 2509.11420 **[chưa xác minh]**). Repo hiện là một ứng dụng terminal nghiên cứu tài chính; README không nêu kết quả và không giải thích quan hệ giữa phần mềm với phương pháp trong paper.
- **MemGuard-Alpha**, arXiv [2603.26797](https://arxiv.org/abs/2603.26797): lọc tín hiệu LLM bằng membership inference để giảm ảnh hưởng của memorization **[chưa xác minh chi tiết]**.
- **Nghiên cứu FX live của HKU** (2026-07): mười agent giao dịch live sáu tuần; tác giả tự lưu ý sáu tuần chỉ là một lát cắt **[chưa xác minh, nguồn thứ cấp]**.

---

## 2. Bằng chứng phản biện và cách thiết kế đánh giá

### 2.1 Hiệu quả không bền ngoài mẫu

- **FINSABER** ([2505.07078](https://arxiv.org/abs/2505.07078)): backtest hai thập kỷ, hơn 100 mã. Lợi thế của các chiến lược LLM báo cáo trong đánh giá hẹp trước đó "suy giảm đáng kể". LLM quá thận trọng trong bull market nên thua benchmark thụ động, và quá hung hăng trong bear market nên lỗ nặng. Tác giả đề xuất ưu tiên nhận diện trend và kiểm soát rủi ro theo regime thay vì tăng độ phức tạp của framework.
- **StockBench**, **AI-Trader**, **LiveTradeBench** (mục 1.11): khi test sau cutoff hoặc live, phần lớn agent không vượt buy-and-hold, và năng lực chung của model không dự báo được kết quả giao dịch.
- **QuantHarness** tự nó: accuracy hơn random nhưng return âm ở một số mã và thua linear regression về return (mục 1.1).

Mẫu số chung của các paper báo kết quả đẹp: vài mã, vài tháng, một lần chạy, không tính phí, giai đoạn test nằm trong dữ liệu huấn luyện của LLM.

### 2.2 Look-ahead do dữ liệu huấn luyện của LLM

Backtest truyền thống chỉ cần đảm bảo feature tại thời điểm t không dùng dữ liệu sau t. Với LLM còn một kênh rò rỉ nữa: **trọng số model đã thấy tương lai**. Nếu giai đoạn backtest nằm trước knowledge cutoff, model có thể "nhớ" rằng BTC sập tháng 5/2021 hay NVDA tăng mạnh năm 2023 mà không cần suy luận gì từ chart.

- **Profit Mirage** ([2510.07920](https://arxiv.org/abs/2510.07920)): return của agent sụp đổ khi đánh giá lại trên dữ liệu sau cutoff. Bộ FinLake-Bench gồm 2.000 câu hỏi kiểu "ngày X thị trường tăng hay giảm"; các model như GPT-4o trả lời đúng hơn 85% **[con số lấy từ bản tóm tắt, chưa đọc toàn văn]**.
- **The Memorization Problem** (Lopez-Lira, Tang, Zhu; arXiv [2504.14765](https://arxiv.org/abs/2504.14765)): LLM nhớ lại được giá trị số chính xác của dữ liệu kinh tế trong giai đoạn huấn luyện; không thể tin dự báo của LLM cho giai đoạn đó.
- **Detecting Lookahead Bias in LLM Forecasts** (Gao, Jiang, Yan; arXiv [2512.23847](https://arxiv.org/abs/2512.23847)): kiểm định thống kê cho thấy memorization khuếch đại đáng kể sức dự báo bề ngoài.
- **Glasserman & Lin** (arXiv [2309.17322](https://arxiv.org/abs/2309.17322)): trong vùng huấn luyện, ẩn tên công ty khỏi headline lại cho return cao hơn. Ngoài look-ahead còn có hiệu ứng "distraction": hiểu biết chung về công ty làm lệch đánh giá.
- **Sarkar & Vafa, "Lookahead Bias in Pretrained Language Models"** **[chưa xác minh, không tìm được trong phiên này]**.

Ẩn danh hóa (bỏ ticker, bỏ ngày, chuẩn hóa giá) làm giảm nhưng không loại được rò rỉ: hình dạng chuỗi giá của một tài sản nổi tiếng vẫn có thể nhận ra.

**Hệ quả trực tiếp cho dự án này.** Theo [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview), cả bốn model Claude hiện hành (Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5) đều có "reliable knowledge cutoff" và "training data cutoff" là **tháng 6/2026**. Tính đến hôm nay (2026-11-13):

- Mọi backtest có LLM trong vòng lặp trên dữ liệu trước tháng 7/2026 đều bị nhiễm.
- Cửa sổ sạch chỉ còn khoảng 4,5 tháng (2026-07 đến nay), quá ngắn cho kết luận thống kê ở khung 4h/1d.
- Mỗi lần đổi sang model mới hơn, cửa sổ sạch lại bị thu hẹp.
- Cách duy nhất có giá trị lâu dài là **forward test / paper trading liên tục**, ghi lại quyết định trước khi biết kết quả.

### 2.3 Tính không tất định

- **AlphaForgeBench** ([2602.18481](https://arxiv.org/abs/2602.18481)): LLM làm trading agent có phương sai giữa các lần chạy rất lớn, chuỗi hành động không nhất quán **ngay cả khi decoding tất định**, và hay đổi hành động vô lý giữa hai bước thời gian liền kề. Tác giả quy cho bản chất stateless của LLM và độ nhạy khi ánh xạ liên tục sang rời rạc. Đề xuất: cho LLM **sinh alpha factor chạy được** thay vì ra lệnh trực tiếp.
- **Riêng với Claude API**: không còn "cố định temperature" được. Trang [API versions](https://platform.claude.com/docs/en/api/versioning) ghi với phiên bản `2026-10-21`: "The `temperature`, `top_p`, and `top_k` request parameters are removed. A request that sends any of them returns a 400 error on every model." Tham số `seed` cho Claude API: không thấy trong các trang đã đọc **[chưa xác minh là không tồn tại]**.
- Ngoài sampling còn các nguồn bất định khác: nhà cung cấp cập nhật hạ tầng, thay đổi model alias (Claude từ thế hệ 4.6 dùng ID không ngày nhưng là snapshot cố định), thay đổi prompt, thứ tự tool result.

Cách sống chung với tính không tất định:

1. Lưu **toàn bộ** request và response; coi bản ghi là nguồn sự thật, replay từ bản ghi thay vì gọi lại model.
2. Với mỗi điểm quyết định trong đánh giá, chạy N lần (ví dụ 5) và báo cáo phân phối: tỉ lệ đồng thuận về direction, độ lệch chuẩn của confidence. Quyết định không đồng thuận coi là `neutral`.
3. Thu hẹp không gian đầu ra: enum thay cho văn bản tự do, số do code tính.
4. Pin model ID, pin phiên bản SDK, hash system prompt và schema, ghi tất cả vào log.

### 2.4 Chi phí và độ trễ

- QuantHarness thừa nhận mỗi chu kỳ (một lần gọi LLM cộng nhiều tool call) có thể dài hơn cửa sổ cơ hội 1 phút. Tên paper có chữ "High-Frequency" nhưng thực tế là khung 1h/4h.
- Hệ kiểu TradingAgents gọi LLM hàng chục lần cho một quyết định.
- Chi phí tăng tuyến tính theo số mã × số khung × tần suất × số agent × số lần lặp N. Ước tính ở mục 5.6.
- Chi phí LLM là chi phí cố định trừ thẳng vào lợi nhuận; với tài khoản nhỏ có thể lớn hơn edge kỳ vọng.

### 2.5 Checklist thiết kế đánh giá

| Nguyên tắc | Cách làm cụ thể |
|---|---|
| Chỉ tính điểm sau knowledge cutoff | Ghi `model_id` và cutoff của nó vào mỗi quyết định; loại mọi mẫu có thời điểm ≤ cutoff khỏi bảng kết quả chính. Với Claude hiện hành: chỉ tính từ 2026-07 |
| Forward test là chuẩn vàng | Chạy paper trading; ghi quyết định với timestamp trước khi nến tiếp theo đóng; log append-only |
| So với baseline đơn giản | Buy-and-hold, random có cùng tần suất và cùng phân bố long/short, MA crossover, linear regression slope (baseline mà QuantHarness thua về return), và **chính lớp tất định của dự án khi không có LLM** |
| Ablation | Chạy pipeline có và không có từng agent; nếu bỏ LLM mà kết quả không đổi thì LLM không đóng góp gì |
| Tính đủ ma sát | Phí, spread, slippage, funding rate (perp), độ trễ từ lúc đóng nến đến lúc có quyết định |
| Đo cả lợi nhuận lẫn accuracy | Return, Sharpe, Sortino, max drawdown, turnover, cùng với directional accuracy và calibration của `confidence` (Brier score, reliability diagram) |
| Đủ mẫu, nhiều regime | Nhiều tài sản, có cả giai đoạn tăng, giảm, đi ngang; báo cáo khoảng tin cậy bằng bootstrap |
| Kiểm soát bất định | N lần chạy cho mỗi điểm, báo cáo phương sai; lưu và replay response |
| Chống tự lừa mình | Đăng ký trước giả thuyết và metric; đếm số biến thể prompt đã thử (multiple testing); khóa prompt trước khi mở tập test |
| Log đầy đủ | Xem mục 7.3 |

Tiêu chí dừng nên định trước: nếu sau K tháng forward test lớp LLM không vượt lớp tất định một cách có ý nghĩa thống kê, giữ LLM ở vai trò viết báo cáo diễn giải và bỏ vai trò tạo tín hiệu.

---

## 3. Framework dựng agent

### 3.1 LangGraph

Nguồn: [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence). Repo [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph), MIT, 44.9k sao. Cài: `pip install -U langgraph`.

LangGraph tự mô tả là framework orchestration cấp thấp cho agent stateful chạy dài. Nó không áp đặt prompt hay kiến trúc agent, và cho phép trộn bước tất định với bước do LLM điều khiển trong cùng một graph.

- **State**: một cấu trúc dữ liệu dùng chung (thường là `TypedDict` hoặc Pydantic model) mà mọi node đọc và ghi. Mỗi key có thể có **reducer** quy định cách gộp cập nhật (ghi đè, nối list...) **[khái niệm reducer chưa đọc lại từ tài liệu trong phiên này]**.
- **Node**: một hàm Python nhận state, trả về phần state cần cập nhật. Node có thể gọi LLM, hoặc chỉ là code thuần.
- **Edge**: nối node với node. Edge thường là cố định; **conditional edge** dùng một hàm định tuyến đọc state để chọn node kế tiếp. Có hai node đặc biệt `START` và `END`.
- **Checkpoint**: khi compile graph với một checkpointer, state được lưu thành checkpoint theo `thread_id`. Tài liệu nêu các công dụng: bộ nhớ ngắn hạn theo thread, human-in-the-loop, time travel, chịu lỗi. Thư viện checkpointer: `InMemorySaver` (mất khi restart), `SqliteSaver` (phát triển cục bộ), `PostgresSaver`/`AsyncPostgresSaver` (production, cần gọi `setup()`).
- **Interrupt**: dừng graph, cho người xem hoặc sửa state, rồi chạy tiếp. Đây là cơ chế phù hợp cho bước "người duyệt".

Ví dụ tối thiểu theo tài liệu:

```python
from langgraph.graph import StateGraph, MessagesState, START, END

def mock_llm(state: MessagesState):
    return {"messages": [{"role": "ai", "content": "hello world"}]}

graph = StateGraph(MessagesState)
graph.add_node(mock_llm)
graph.add_edge(START, "mock_llm")
graph.add_edge("mock_llm", END)
graph = graph.compile()
```

Ưu điểm: luồng điều khiển tường minh, vẽ được, test từng node; checkpoint và interrupt có sẵn; QuantHarness và TradingAgents đều dùng nên dễ đối chiếu. Nhược điểm: thêm phụ thuộc và một lớp trừu tượng; nếu dùng `langchain-anthropic` làm lớp model thì tính năng mới của Claude API (structured output, cache breakpoint, effort) có thể đến chậm hoặc bị che. Có thể dùng LangGraph chỉ để orchestration và gọi SDK `anthropic` trực tiếp trong node.

### 3.2 Claude Agent SDK

Nguồn: [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview). Repo [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python), MIT.

Đây là Claude Code đóng gói thành thư viện (Python, TypeScript): chạy binary Claude Code, có sẵn tool đọc/ghi/sửa file, chạy lệnh, tìm web, cùng hooks, subagents, MCP, permissions, sessions. Tài liệu phân biệt rõ với Client SDK: Client SDK là truy cập trực tiếp Claude API, tự viết vòng lặp tool hoặc dùng tool runner.

- Hợp với: agent cần thao tác file và shell, ví dụ agent nghiên cứu tự viết và chạy notebook backtest.
- Không hợp với: pipeline phân tích có cấu trúc cố định, chạy hàng nghìn lần, cần kiểm soát từng token. Cấp cho agent quyền shell trong một hệ liên quan tới tiền là mở rộng bề mặt rủi ro không cần thiết.
- Điều khoản: việc dùng SDK chịu Commercial Terms of Service của Anthropic; cần xác thực bằng API key, không dùng đăng nhập claude.ai cho sản phẩm bên thứ ba.

### 3.3 OpenAI Agents SDK

Nguồn: [tài liệu](https://openai.github.io/openai-agents-python/). Repo [openai/openai-agents-python](https://github.com/openai/openai-agents-python), MIT, 30.6k sao. Cài: `pip install openai-agents`.

Primitive: Agents, Handoffs / agents-as-tools, Guardrails (kiểm tra input và output), Sessions, Tracing có sẵn. Mặc định dùng Responses API của OpenAI; có adapter LiteLLM và Any-LLM cho nhà cung cấp khác. Hợp nếu dự án chọn OpenAI làm nhà cung cấp chính. Nếu dùng Claude qua adapter thì mất các tính năng riêng của Claude API.

### 3.4 CrewAI

Nguồn: [tài liệu](https://docs.crewai.com/en/introduction). Repo [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI), MIT, 60.8k sao.

Hai khái niệm: **Flows** (xương sống: bước, logic, state, điều kiện, vòng lặp) và **Crews** (nhóm agent nhập vai cộng tác trên task do Flow giao). Tài liệu khuyên bắt đầu bằng Flow và gọi Crew bên trong một bước khi cần tính tự chủ. Dựng nhanh, dễ đọc. Điểm yếu cho dự án này: mô hình nhập vai (role/goal/backstory) khuyến khích để LLM "thảo luận", trong khi dự án cần đầu ra có schema và luồng cố định.

### 3.5 AutoGen và Microsoft Agent Framework

README của [microsoft/autogen](https://github.com/microsoft/autogen) ghi AutoGen đang ở **maintenance mode**; người dùng mới nên bắt đầu với [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) (MIT, 14.7k sao). Agent Framework 1.0 GA vào tháng 4/2026 **[ngày chính xác chưa xác minh, các nguồn lệch nhau 2–8/4]**. Fork cộng đồng [ag2ai/ag2](https://github.com/ag2ai/ag2) (Apache-2.0) vẫn phát triển; gói PyPI `autogen` trỏ về AG2 **[chưa xác minh]**. Không nên bắt đầu dự án mới trên AutoGen.

### 3.6 PydanticAI

Nguồn: [tài liệu](https://pydantic.dev/docs/ai/overview/). Repo [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai), MIT, 21.2k sao.

Đầu ra được validate theo kiểu (Pydantic model); dependency injection qua `RunContext`; đổi model bằng một chuỗi, có hỗ trợ Anthropic; Pydantic Graph cho luồng điều khiển có kiểu; durable execution qua Temporal/DBOS/Prefect; Pydantic Evals; MCP; OpenTelemetry. Human-in-the-loop qua "deferred tools": một lần chạy có thể dừng chờ người duyệt tool call. Rất hợp triết lý "schema trước" của dự án. Điểm cần cân nhắc: lớp trừu tượng đa nhà cung cấp có thể chậm hơn SDK gốc với tính năng mới.

### 3.7 Tự viết vòng lặp tool-use

Với SDK `anthropic` có hai mức ([tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [tool runner](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner)):

**Tool runner** (helper beta của SDK, tự chạy vòng lặp):

```python
import anthropic
from anthropic import beta_tool

client = anthropic.Anthropic()

@beta_tool
def compute_rsi(symbol: str, timeframe: str, period: int = 14) -> str:
    """Tính RSI từ dữ liệu OHLC đã lưu.

    Args:
        symbol: Mã, ví dụ BTCUSDT.
        timeframe: Khung nến, ví dụ 1h hoặc 4h.
        period: Chu kỳ RSI.
    """
    return indicators.rsi_json(symbol, timeframe, period)  # hàm tất định của dự án

runner = client.beta.messages.tool_runner(
    model="claude-opus-5-5",
    max_tokens=16000,
    tools=[compute_rsi],
    messages=[{"role": "user", "content": "Đánh giá momentum BTCUSDT khung 4h."}],
)
for message in runner:
    log(message)
```

**Vòng lặp thủ công**: gọi `client.messages.create(...)`; nếu `stop_reason == "tool_use"` thì chạy các tool được yêu cầu, nối `{"role": "assistant", "content": response.content}` và một message `user` chứa **tất cả** `tool_result` (khóa theo `tool_use_id`), rồi gọi lại, cho tới khi `stop_reason` khác `tool_use`. Cần đặt trần số vòng lặp.

Ưu điểm: không phụ thuộc framework, thấy rõ từng request, log dễ, dùng được mọi tính năng API ngay. Nhược điểm: tự lo checkpoint, retry, song song, interrupt.

### 3.8 Khi nào dùng cái nào

| Tình huống | Lựa chọn |
|---|---|
| Pipeline cố định: tính toán → vài agent diễn giải → tổng hợp → báo cáo | Code Python thuần gọi SDK `anthropic`, mỗi agent là một lời gọi có structured output. Đây là mức đủ cho giai đoạn đầu |
| Cần nhánh có điều kiện, chạy song song, dừng chờ người duyệt, khôi phục sau lỗi | LangGraph làm lớp orchestration, node gọi SDK `anthropic` trực tiếp |
| Muốn kiểu dữ liệu chặt và đổi nhà cung cấp dễ | PydanticAI |
| Agent nghiên cứu tự viết code, chạy backtest, đọc file | Claude Agent SDK, chạy trong sandbox, tách khỏi hệ ra tín hiệu |
| Đã chọn OpenAI làm nhà cung cấp chính | OpenAI Agents SDK |
| Prototype nhập vai nhanh | CrewAI |
| Dự án mới | Không dùng AutoGen |

Khuyến nghị cho dự án: bắt đầu bằng code thuần với SDK `anthropic`. Vì QuantHarness có luồng gần như tuyến tính (ba agent song song → risk → decision), nó chưa cần framework. Chuyển sang LangGraph khi thật sự cần checkpoint và interrupt, và giữ giao diện mỗi agent là một hàm `(state) -> dict` để việc chuyển không phải viết lại.

---

## 4. Kỹ thuật cần cho dự án

### 4.1 Tool calling / function calling

Model không chạy code. Model trả về một block `tool_use` có tên tool và đối số; ứng dụng chạy hàm và gửi lại `tool_result`. Theo [tài liệu tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview):

- Client tool chạy trong ứng dụng của bạn; server tool (web search, code execution) chạy trên hạ tầng Anthropic.
- Định nghĩa tool gồm `name`, `description`, `input_schema`. Thêm `strict: true` để đối số luôn khớp schema.
- `tool_choice` mặc định là `{"type": "auto"}`. Có thể giới hạn một tool mỗi lượt bằng `disable_parallel_tool_use: true`.
- Khi có `tools`, API tự thêm một system prompt cho tool use: 286 token trên Opus 5.5, Sonnet 5.5, Haiku 5.5.
- Trên Opus 5.5 và Sonnet 5.5, bảng token của tài liệu để trống cột `any`/`tool`; ép gọi tool (`tool_choice` kiểu `any` hoặc `tool`) không dùng được trên các model này **[chưa xác minh trực tiếp câu chữ trong tài liệu web; lấy từ tài liệu tham chiếu SDK]**. Dùng `auto` kèm chỉ dẫn trong prompt, hoặc structured output.

Mô tả tool là phần quan trọng nhất: ghi rõ tool trả gì, đơn vị, khi nào nên gọi.

### 4.2 Structured output (JSON schema)

Nguồn: [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

- Đặt schema ở `output_config.format` với `type: "json_schema"`; phản hồi là JSON khớp schema trong text block.
- SDK Python có `client.messages.parse(..., output_format=PydanticModel)`, trả `response.parsed_output` đã validate.
- **Giới hạn schema** cần biết khi thiết kế:
  - Hỗ trợ: object, array, string, integer, number, boolean, null; `enum`; `const`; `anyOf`; `$ref` nội bộ; `required`; `additionalProperties: false`.
  - **Không hỗ trợ**: `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, schema đệ quy, `additionalProperties` khác `false`. Dùng sẽ bị lỗi 400.
  - Hệ quả: không ràng buộc được `confidence` trong [0, 1] ở mức schema. Phải validate trong code.
  - Trường kiểu `dict` tự do sẽ thành object rỗng; dùng model lồng với key cố định.
- Grammar đã biên dịch được cache 24 giờ; request đầu với schema mới chậm hơn. Đổi `output_config.format` làm mất prompt cache của hội thoại đó.
- Không dùng chung với citations.

Structured output đảm bảo **dạng**, không đảm bảo **nội dung đúng**. Vẫn cần kiểm tra nghiệp vụ: stop nằm đúng phía so với giá vào, R:R hợp lý, số được trích dẫn khớp số đầu vào.

### 4.3 Đưa ảnh chart cho model vision

Nguồn: [Vision](https://platform.claude.com/docs/en/build-with-claude/vision).

**Giới hạn và chi phí:**

- Định dạng: JPEG, PNG, GIF, WebP.
- Tối đa 8000×8000 px mỗi ảnh; 10 MB mỗi ảnh (base64) trên Claude API; tối đa 600 ảnh mỗi request (100 với model context 200k). Trên 20 ảnh trong một request thì giới hạn kích thước mỗi ảnh chặt hơn.
- Chi phí: ảnh được chia thành patch 28×28 px, mỗi patch là một visual token. Số token = `⌈width/28⌉ × ⌈height/28⌉`.
- Trần độ phân giải: model Claude 4.7 trở lên có cạnh dài tối đa 2.576 px và tối đa 4.784 visual token; model cũ hơn là 1.568 px và 1.568 token. Ảnh lớn hơn bị thu nhỏ trước khi xử lý.

| Kích thước | Token (model 4.7+) | Ghi chú |
|---|---|---|
| 1000×1000 | 1.296 | Không bị resize |
| 1092×1092 | 1.521 | Không bị resize |
| 1456×819 (16:9) | 1.560 | Tự tính: ⌈1456/28⌉ × ⌈819/28⌉ = 52 × 30 |
| 1920×1080 | 2.691 | |
| 3840×2160 | 4.784 | Bị thu về 2576×1449 |

- Tài liệu khuyên: đặt ảnh **trước** văn bản trong message; tự resize trước khi gửi để kiểm soát chi phí và độ trễ; nén lossy nặng có thể làm chữ khó đọc.
- Hạn chế tài liệu nêu: tọa độ và định vị không gian chỉ gần đúng; đếm nhiều vật thể nhỏ không chính xác; ảnh nhỏ dưới 200 px dễ bị đọc sai.

**Khuyến nghị vẽ chart** (kinh nghiệm thiết kế, chưa có benchmark riêng của dự án; nên A/B trên forward test):

- Kích thước mặc định **1456×819 PNG** (khoảng 1.560 token): đủ rõ, chi phí cố định, cùng kích thước cho mọi lần gọi để so sánh được.
- 60–120 nến mỗi ảnh. Nhiều hơn thì thân nến chỉ còn vài pixel, và model đếm vật nhỏ kém.
- Nền trắng hoặc sáng, màu nến tương phản, không gradient, không logo, không watermark.
- Tiêu đề chứa symbol, timeframe và thời điểm nến cuối. Trong lúc **đánh giá** thì ẩn symbol và ngày (dùng chỉ số nến) để giảm rò rỉ theo mục 2.2.
- Trục giá bên phải với nhãn đủ lớn; vẽ đường ngang có nhãn số cho mức quan trọng (POC, VAH/VAL, order block, swing high/low). Đừng bắt model đọc giá từ pixel.
- Mỗi ảnh một mục đích: một ảnh giá + volume, một ảnh riêng cho cấu trúc (trendline, vùng SMC). Tối đa 2–3 overlay mỗi ảnh.
- Luôn gửi kèm **số liệu dạng JSON** cho mọi thứ vẽ trên chart. Ảnh để model nhận hình thái; số để model trích dẫn.

Với `mplfinance` (lưu ý: [repo](https://github.com/matplotlib/mplfinance) push gần nhất 2024-08, nên pin phiên bản):

```python
import io
import mplfinance as mpf

def render_chart_png(df, levels: list[float], title: str) -> bytes:
    """df: DataFrame có DatetimeIndex và cột Open, High, Low, Close, Volume."""
    buf = io.BytesIO()
    mpf.plot(
        df.tail(100),
        type="candle",
        style="yahoo",
        volume=True,
        mav=(20, 50),
        hlines=dict(hlines=levels, linestyle="--", linewidths=0.8),
        title=title,
        figsize=(14.56, 8.19),          # × dpi 100 = 1456×819 px
        savefig=dict(fname=buf, dpi=100, format="png"),
    )
    return buf.getvalue()
```

Không dùng `bbox_inches="tight"` vì nó làm kích thước pixel thay đổi giữa các lần vẽ.

Với `plotly` (xuất ảnh tĩnh cần gói `kaleido`):

```python
import plotly.graph_objects as go

fig = go.Figure(go.Candlestick(
    x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"]))
fig.update_layout(template="plotly_white", xaxis_rangeslider_visible=False,
                  title=title, margin=dict(l=40, r=60, t=50, b=40))
for lv in levels:
    fig.add_hline(y=lv, line_dash="dash", annotation_text=f"{lv:g}")
png_bytes = fig.to_image(format="png", width=1456, height=819, scale=1)
```

### 4.4 Prompt caching

Nguồn: [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

- Cache là **khớp tiền tố**, thứ tự `tools` → `system` → `messages`. Thay đổi ở một tầng làm mất cache của tầng đó và mọi tầng sau.
- Hai cách bật: tự động (một trường `cache_control: {"type": "ephemeral"}` ở cấp cao nhất của request) hoặc đặt breakpoint tường minh trên từng content block. Tối đa 4 breakpoint.
- TTL: 5 phút (mặc định, ghi giá 1.25× input) hoặc 1 giờ (`"ttl": "1h"`, ghi giá 2× input). Đọc cache giá 0.1× input; riêng Opus 5.5 và Sonnet 5.5 là 0.05×, Fable 5.2 là 0.025×.
- Độ dài tối thiểu để cache: **512 token** trên Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5. Ngắn hơn thì không cache và không báo lỗi.
- Thêm hoặc bớt **ảnh** ở bất kỳ đâu làm mất cache của tầng messages (tầng tools và system vẫn giữ). Đổi định nghĩa tool làm mất tất cả.
- Kiểm tra bằng `usage.cache_read_input_tokens` và `usage.cache_creation_input_tokens`.

Áp dụng cho dự án: phần ổn định (định nghĩa tool, system prompt của từng agent, hướng dẫn đọc chart, định nghĩa SMC/volume profile) đặt đầu và cache; phần thay đổi mỗi lần (dict indicator, ảnh chart, thời điểm) đặt ở message cuối. Không đưa timestamp hay ID ngẫu nhiên vào system prompt. Serialize JSON với `sort_keys=True`.

### 4.5 Batch API

Nguồn: [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing).

- Giảm **50%** giá. Tối đa 100.000 request hoặc 256 MB mỗi batch. Phần lớn batch xong trong 1 giờ; hết hạn sau 24 giờ. Kết quả giữ 29 ngày.
- Hỗ trợ vision, tool use, prompt caching (cache hit theo kiểu best-effort; tài liệu khuyên dùng TTL 1 giờ). Không hỗ trợ `stream`, `speed`, `fallbacks`, `max_tokens: 0`.
- Kết quả trả về không theo thứ tự; ghép bằng `custom_id`.
- Không đủ điều kiện zero data retention.

Áp dụng: batch hợp với **đánh giá hàng loạt** (N lần chạy × nhiều mã × nhiều điểm thời gian), báo cáo cuối ngày, và khung 1d. Không hợp với quyết định khung 1h cần kết quả trong vài phút.

### 4.6 Kiểm soát chi phí và độ trễ

Theo thứ tự nên làm:

1. **Gọi LLM ít lần hơn.** Lớp tất định lọc trước: chỉ gọi LLM khi có sự kiện (giá chạm vùng, có BOS/CHoCH mới, đóng nến của khung chính). Phần lớn nến không cần LLM.
2. **Không dùng vòng lặp tool khi không cần.** Nếu biết trước cần indicator nào, tính sẵn và đưa vào prompt trong một lần gọi. Vòng lặp tool nhân số request và độ trễ. Chỉ để agent tự gọi tool ở nhánh "đào sâu".
3. **Chạy song song** các agent diễn giải độc lập (`asyncio` với `AsyncAnthropic`).
4. **Prompt caching** cho phần ổn định.
5. **Chọn model theo vai** (mục 5.6) và đặt `effort` thấp cho tác vụ đơn giản. Đo trên forward test trước khi hạ.
6. **Batch** cho mọi thứ không gấp.
7. **Kích thước ảnh cố định** ở mức vừa đủ.
8. **Trần cứng**: `max_tokens` hợp lý, giới hạn số vòng lặp, ngân sách USD theo ngày với cơ chế ngắt, timeout cho mỗi request.
9. **Đo**: ghi `usage` và thời gian của mỗi request; tính chi phí cho mỗi quyết định, không chỉ mỗi request.

### 4.7 Cho agent gọi hàm tất định thay vì để LLM tự tính số

Nguyên tắc: **LLM không bao giờ là nguồn của một con số.** LLM tính nhẩm sai, và không tái lập được. Mọi con số trong báo cáo phải truy được về một hàm tất định có phiên bản.

Hai cách đưa số vào:

- **Tính trước** (ưu tiên): pipeline gọi `indicators.compute(df)`, `volume_profile.compute(df)`, `smc.detect(df)` rồi đưa kết quả JSON vào prompt. Một lần gọi LLM, tất định ở đầu vào.
- **Tool theo yêu cầu**: định nghĩa tool cho các phép tính ít dùng hoặc tốn kém (đổi timeframe, profile theo phiên, backtest nhanh một điều kiện). Dùng `strict: true`.

Quy tắc thiết kế tool và dữ liệu:

- Tool chỉ nhận **tham số định danh** (symbol, timeframe, period, số nến). Tool không nhận mảng giá do model tự gõ; dữ liệu giá luôn lấy từ kho của dự án theo `data_snapshot_id`.
- Tool trả JSON gọn, có đơn vị, có `as_of` (thời điểm nến cuối **đã đóng**), có `calc_version`.
- Làm tròn số theo tick size trước khi đưa cho model.
- Trả về **sự kiện đã diễn giải ở mức tất định** thay vì chuỗi số thô: "RSI(14) = 71.3, vượt 70 từ 3 nến trước", "bullish order block tại 61.200–61.450, chưa bị mitigate", "giá nằm trên VAH 2.1%". Model diễn giải tổ hợp các sự kiện, không tự phát hiện từ chuỗi số.
- **Stop và take-profit**: để lớp tất định sinh các mức ứng viên (ATR, swing gần nhất, biên order block, VAL/VAH). LLM **chọn** trong danh sách ứng viên, hoặc code chọn và LLM chỉ giải thích. QuantHarness cũng làm tương tự: stop cố định, LLM chỉ chọn hệ số r.
- Hậu kiểm: mọi con số xuất hiện trong `rationale` phải khớp một giá trị trong đầu vào (so khớp có dung sai); nếu không khớp thì đánh dấu và loại.

---

## 5. Claude API cụ thể

Mọi thông tin trong mục này đọc từ tài liệu chính thức ngày 2026-11-13. Giá tính bằng USD cho mỗi triệu token (MTok).

### 5.1 Model hiện hành

Nguồn: [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview).

| | Claude Fable 5.2 | Claude Opus 5.5 | Claude Sonnet 5.5 | Claude Haiku 5.5 |
|---|---|---|---|---|
| Claude API ID | `claude-fable-5-2` | `claude-opus-5-5` | `claude-sonnet-5-5` | `claude-haiku-5-5` |
| Mô tả của Anthropic | Reasoning khó, agentic dài hạn | Agentic coding và knowledge work chạy dài | Cân bằng tốc độ và trí tuệ | Khối lượng lớn, nhạy độ trễ: phân loại, trích xuất, định tuyến |
| Độ trễ tương đối | Moderate | Moderate | Fast | Fastest |
| Context window | 1M token | 1M token | 1M token | 1M token |
| Max output | 128K token | 128K token | 128K token | 128K token |
| Thinking | Adaptive (luôn bật) | Adaptive (luôn bật) | Adaptive | Adaptive |
| Effort mặc định | `high` | `medium` | `high` | `medium` |
| Reliable knowledge cutoff | 2026-06 | 2026-06 | 2026-06 | 2026-06 |
| Training data cutoff | 2026-06 | 2026-06 | 2026-06 | 2026-06 |

- Tài liệu khuyên: nếu chưa chắc, bắt đầu với Claude Opus 5.5 cho phần lớn workload.
- "All current models support text and image input, text output, multilingual capabilities, vision, and tool use."
- Mọi model ID là snapshot cố định, kể cả ID không có ngày từ thế hệ 4.6 trở đi.
- Model cũ còn dùng được (danh sách đầy đủ ở trang trên): Opus 5, Opus 4.8/4.7/4.6/4.5, Sonnet 5, Sonnet 4.6/4.5, Haiku 4.5, Fable 5.1/5. Claude Mythos là dòng hạn chế truy cập.
- Có thể truy vấn năng lực và giới hạn token bằng [Models API](https://platform.claude.com/docs/en/api/models/list) (`max_input_tokens`, `max_tokens`, `capabilities`).

### 5.2 Giá

Nguồn: [Pricing](https://platform.claude.com/docs/en/about-claude/pricing).

| Model | Input | Ghi cache 5 phút | Ghi cache 1 giờ | Đọc cache | Output | Batch input | Batch output |
|---|---|---|---|---|---|---|---|
| Claude Fable 5.2 | $8 | $10 | $16 | $0.20 | $40 | **[chưa xác minh]** | **[chưa xác minh]** |
| Claude Opus 5.5 | $4 | $5 | $8 | $0.20 | $20 | $2 | $10 |
| Claude Sonnet 5.5 | $2 | $2.50 | $4 | $0.10 | $10 | $1 | $5 |
| Claude Haiku 5.5 (prompt ≤ 100.000 token) | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 | $0.05 | $0.25 |
| Claude Haiku 5.5 (prompt > 100.000 token) | $0.50 | $0.625 | $1 | $0.05 | $2.50 | $0.25 | $1.25 |
| Claude Haiku 4.5 | $1 | $1.25 | $2 | $0.10 | $5 | $0.50 | $2.50 |

Ghi chú từ trang giá:

- Batch giảm 50% (trang Models overview ghi "Batch API requests are 50% off"). Dòng Fable 5.2 trong bảng batch bị cắt khi tra cứu nên để trống.
- Context 1M token tính giá chuẩn trên các model 4.6 trở lên, trừ Haiku 5.5 tính theo độ dài prompt (ngưỡng 100.000 token, tính cả token đọc và ghi cache).
- Chỉ định suy luận chỉ ở Mỹ (`inference_geo`) nhân 1.1× mọi loại token.
- Hệ số cache cộng dồn với giảm giá batch.
- Model Claude 4.7 trở lên dùng tokenizer mới, sinh nhiều hơn khoảng 30% token cho cùng văn bản so với model cũ.
- Thinking token được tính là output **[chưa xác minh câu chữ trong tài liệu web trong phiên này]**; vì thinking luôn bật trên Opus 5.5 và Fable 5.2, chi phí output thực tế cao hơn phần JSON nhìn thấy.

### 5.3 Hỗ trợ tính năng

| Tính năng | Trạng thái | Nguồn |
|---|---|---|
| Vision | Mọi model hiện hành; JPEG/PNG/GIF/WebP; nguồn base64, URL, hoặc `file_id` | [Vision](https://platform.claude.com/docs/en/build-with-claude/vision) |
| Tool use | Mọi model hiện hành; `strict: true` cho schema chặt | [Tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) |
| Structured output | `output_config.format`; metadata trang liệt kê `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` và các model khác | [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) |
| Prompt caching | Mọi model đang hoạt động | [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) |
| Batch | Mọi model đang hoạt động; trên Claude API | [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing) |

### 5.4 Các điểm dễ vấp

- **Không có temperature.** API version `2026-10-21` loại bỏ `temperature`, `top_p`, `top_k`; gửi kèm sẽ lỗi 400 trên mọi model ([API versions](https://platform.claude.com/docs/en/api/versioning)). Thư viện trung gian (LangChain, LiteLLM) có thể vẫn gửi các trường này nếu được cấu hình.
- **Thinking luôn bật** trên Opus 5.5 và Fable 5.2; điều chỉnh độ sâu bằng `output_config.effort` ([Effort](https://platform.claude.com/docs/en/build-with-claude/effort)).
- **`stop_reason`** phải được kiểm tra trước khi đọc nội dung: `max_tokens` nghĩa là JSON có thể bị cắt; `refusal` nghĩa là model từ chối. Có tham số `fallbacks` (beta) để tự chạy lại trên model khác khi bị từ chối ([Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)) **[chưa xác minh chi tiết trong phiên này]**; không dùng được với Batch.
- **Structured output không hỗ trợ `minimum`/`maximum`**: validate khoảng giá trị trong code.

### 5.5 Ví dụ Python: agent nhận dict indicator + ảnh chart, trả JSON

Cài: `pip install anthropic pydantic`. SDK tự đọc `ANTHROPIC_API_KEY` từ môi trường. Dạng request (`image` block base64, `output_config.format`, `cache_control` trên system block, trường `usage`) theo các trang tài liệu đã dẫn ở trên. Đoạn code chưa được chạy thử trong phiên tra cứu này.

```python
"""Agent diễn giải: dict indicator + ảnh chart -> TradeView (JSON có schema)."""
import base64
import hashlib
import json
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
PROMPT_VERSION = "interpreter-v1"

SYSTEM_PROMPT = """Bạn là agent diễn giải kỹ thuật trong một hệ hỗ trợ quyết định.
Bạn KHÔNG đặt lệnh. Đầu ra của bạn được một người xem xét trước khi có hành động nào.

Quy tắc:
- Chỉ dùng các con số có trong khối <indicators>. Không tự tính, không ước lượng số mới.
- Ảnh chart dùng để nhận hình thái và cấu trúc; không đọc giá từ ảnh.
- stop và take_profit phải được chọn từ danh sách stop_candidates và tp_candidates.
- Nếu tín hiệu mâu thuẫn hoặc không đủ, trả direction = "neutral", stop = null, take_profit = null.
- confidence là xác suất chủ quan trong khoảng 0 đến 1 rằng direction đúng sau 3 nến.
- rationale: tối đa 5 câu, mỗi nhận định dẫn tên trường trong <indicators>.
"""
# Prompt thật nên dài hơn (định nghĩa SMC, volume profile, ví dụ). Dưới 512 token thì
# Opus 5.5 không cache và không báo lỗi.


class TradeView(BaseModel):
    direction: Literal["long", "short", "neutral"]
    confidence: float
    rationale: str
    stop: Optional[float]
    take_profit: Optional[float]


# Viết schema bằng tay vì structured output không hỗ trợ minimum/maximum.
TRADE_VIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["long", "short", "neutral"]},
        "confidence": {"type": "number", "description": "Từ 0 đến 1"},
        "rationale": {"type": "string"},
        "stop": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "take_profit": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    },
    "required": ["direction", "confidence", "rationale", "stop", "take_profit"],
    "additionalProperties": False,
}

client = anthropic.Anthropic()


def analyze(indicators: dict, chart_png: bytes) -> tuple[TradeView, dict]:
    """indicators phải chứa last_close, stop_candidates, tp_candidates."""
    indicators_json = json.dumps(indicators, sort_keys=True, ensure_ascii=False)
    image_b64 = base64.standard_b64encode(chart_png).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": TRADE_VIEW_SCHEMA},
        },
        messages=[{
            "role": "user",
            "content": [
                {   # ảnh đặt trước văn bản
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {
                    "type": "text",
                    "text": f"<indicators>\n{indicators_json}\n</indicators>\n"
                            "Đưa ra nhận định theo schema.",
                },
            ],
        }],
    )

    audit = {
        "request_id": response.id,
        "model": response.model,
        "prompt_version": PROMPT_VERSION,
        "system_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "indicators_sha256": hashlib.sha256(indicators_json.encode()).hexdigest(),
        "chart_sha256": hashlib.sha256(chart_png).hexdigest(),
        "stop_reason": response.stop_reason,
        "usage": response.usage.model_dump(),
    }

    if response.stop_reason != "end_turn":
        # "max_tokens": JSON có thể bị cắt; "refusal": model từ chối.
        raise RuntimeError(f"Không có kết quả hợp lệ: stop_reason={response.stop_reason}")

    text = next(b.text for b in response.content if b.type == "text")
    view = TradeView.model_validate_json(text)
    check_business_rules(view, indicators)
    return view, audit


def check_business_rules(view: TradeView, indicators: dict) -> None:
    """Schema đảm bảo dạng; hàm này đảm bảo nội dung hợp lệ."""
    if not 0.0 <= view.confidence <= 1.0:
        raise ValueError("confidence ngoài [0, 1]")
    if view.direction == "neutral":
        if view.stop is not None or view.take_profit is not None:
            raise ValueError("neutral không được có stop/take_profit")
        return
    if view.stop not in indicators["stop_candidates"]:
        raise ValueError("stop không nằm trong danh sách ứng viên")
    if view.take_profit not in indicators["tp_candidates"]:
        raise ValueError("take_profit không nằm trong danh sách ứng viên")
    last = indicators["last_close"]
    if view.direction == "long" and not view.stop < last < view.take_profit:
        raise ValueError("long: cần stop < last_close < take_profit")
    if view.direction == "short" and not view.take_profit < last < view.stop:
        raise ValueError("short: cần take_profit < last_close < stop")
```

Ghi chú:

- Có thể thay phần schema viết tay bằng `client.messages.parse(..., output_format=TradeView)`; SDK tự chuyển Pydantic model thành schema và trả `response.parsed_output`.
- `audit` cùng với bản sao nguyên văn request và response là đầu vào cho log kiểm toán ở mục 7.3.
- Khi một quy tắc nghiệp vụ bị vi phạm: không sửa đầu ra bằng tay. Ghi lại vi phạm và coi quyết định là `neutral`.

### 5.6 Ước tính chi phí cho mỗi lần gọi

Giả định: một ảnh 1456×819 (1.560 token), khoảng 1.500 token văn bản đầu vào, khoảng 600 token JSON đầu ra. **Chưa tính thinking token** (tính như output, phụ thuộc `effort`) và chưa tính cache.

| Model | Input 3.060 token | Output 600 token | Tổng mỗi lần gọi | Với Batch (−50%) |
|---|---|---|---|---|
| Claude Opus 5.5 | $0.0122 | $0.0120 | khoảng $0.024 | khoảng $0.012 |
| Claude Sonnet 5.5 | $0.0061 | $0.0060 | khoảng $0.012 | khoảng $0.006 |
| Claude Haiku 5.5 | $0.0003 | $0.0003 | khoảng $0.0006 | khoảng $0.0003 |

Ví dụ: 10 mã × 2 khung × 3 agent diễn giải + 1 tổng hợp, mỗi nến 4h (6 lần mỗi ngày) là 10 × 2 × 4 × 6 = 480 lần gọi mỗi ngày, khoảng 11,5 USD mỗi ngày với Opus 5.5 trước khi tính thinking. Nhân thêm N = 5 nếu chạy lặp để đo bất định. Lọc theo sự kiện (mục 4.6) là đòn bẩy lớn nhất.

Gợi ý phân vai, cần kiểm chứng bằng đo đạc trên chính dữ liệu của dự án: Haiku 5.5 hoặc Sonnet 5.5 cho agent diễn giải đơn lẻ; Opus 5.5 cho agent tổng hợp và viết báo cáo.

---

## 6. MCP server tài chính / crypto / TradingView

MCP (Model Context Protocol) cho phép model gọi tool của một server bên ngoài. Mức tin cậy dưới đây là đánh giá cho mục đích dùng trong dự án.

| Server | Nguồn | Chính thức? | Cung cấp | Mức tin cậy |
|---|---|---|---|---|
| **TradingView MCP Server** (beta) | [tradingview.com/mcp/docs](https://www.tradingview.com/mcp/docs), URL `https://mcp.tradingview.com/mcp` | Có, của TradingView | OHLCV lịch sử (tối đa 5.000 nến mỗi lần gọi), snapshot indicator, screener, tin tức, fundamentals, lịch kinh tế, watchlist, alert giá đơn giản. **Không** có screenshot chart, Pine Script, đặt lệnh | Cao về nguồn gốc. Đang beta; OAuth 2.1 bằng tài khoản TradingView; cần gói Essential trở lên; khoảng 100 tool call mỗi phút. Điều khoản sử dụng dữ liệu cho hệ tự động **[chưa xác minh]** |
| **CoinGecko MCP** | [docs.coingecko.com/docs/mcp-server](https://docs.coingecko.com/docs/mcp-server); gói npm `@coingecko/coingecko-mcp` | Có, của CoinGecko | Giá, market cap, volume hiện tại và lịch sử; dữ liệu sàn; on-chain DEX. Có endpoint không cần key `https://mcp.api.coingecko.com/mcp` | Cao về nguồn gốc. Bản miễn phí dùng chung rate limit |
| **Alpaca MCP Server** | [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server), MIT, 1.1k sao, push 2026-11-12 | Có, của Alpaca | Dữ liệu và **giao dịch** cổ phiếu, ETF, crypto, options | Cao về nguồn gốc. **Có khả năng đặt lệnh**: nếu dùng thì chỉ với paper account và key chỉ đọc |
| **Financial Datasets MCP** | [financial-datasets/mcp-server](https://github.com/financial-datasets/mcp-server), MIT, 2.3k sao | Của nhà cung cấp API | Báo cáo tài chính, giá cổ phiếu, tin | Trung bình: push gần nhất 2025-06 |
| **tradingview-mcp** (atilaahmettaner) | [repo](https://github.com/atilaahmettaner/tradingview-mcp), MIT, 5.3k sao, push 2026-11-10 | Không. README ghi không liên kết với TradingView Inc. | 39 tool: screener, phân tích đa khung, mẫu nến, backtest, sentiment; dựa trên thư viện `tradingview_ta`, `tradingview-screener`, Yahoo Finance | Thấp đến trung bình: dữ liệu qua endpoint công khai không chính thức, có thể trễ hoặc sai. README cảnh báo có bản sao giả mạo kèm gói npm độc hại |
| **tradingview-mcp** (tradesdontlie) | [repo](https://github.com/tradesdontlie/tradingview-mcp), 7.2k sao, push 2026-10-21 | Không | Điều khiển TradingView Desktop qua Chrome DevTools Protocol (cổng 9222): đọc chart, Pine Script, replay, screenshot. Không đặt lệnh thật | Thấp: dùng giao diện nội bộ không có tài liệu, có thể hỏng bất cứ lúc nào. README tự nêu có thể xung đột Terms of Use của TradingView và cấm dùng dữ liệu trích xuất cho giao dịch tự động |
| Các server bọc CCXT (ví dụ [Nayshins/mcp-server-ccxt](https://github.com/Nayshins/mcp-server-ccxt)) | Cộng đồng | Không | Giá, order book, nến từ nhiều sàn qua CCXT | Thấp: repo nhỏ, **[chưa xác minh]** license và tình trạng bảo trì (GitHub API giới hạn tần suất khi tra) |

Không tìm thấy MCP server chính thức của Binance trong phiên này **[chưa xác minh]**.

**Khuyến nghị cho dự án:**

- Lõi dữ liệu và tính toán **không** nên đi qua MCP. Dùng thư viện Python trực tiếp ([ccxt](https://github.com/ccxt/ccxt), MIT; API của sàn; `yfinance`), lưu snapshot có phiên bản. MCP thêm một tầng không tất định và khó tái lập.
- MCP hữu ích ở lớp **tương tác**: khi người dùng hỏi đáp tự do trong Claude Code hay Claude Desktop và cần tra nhanh dữ liệu.
- Nếu tự đóng gói các hàm indicator, volume profile, SMC của dự án thành một MCP server riêng, cùng một bộ hàm sẽ phục vụ được cả pipeline lẫn phiên tương tác.
- Tuyệt đối không cấp cho agent MCP server có tool đặt lệnh, rút tiền hoặc chuyển tiền. Với server chỉ đọc vẫn cần: pin phiên bản, đọc code trước khi chạy, cấp API key chỉ đọc, và coi nội dung server trả về (tin tức, mô tả) là dữ liệu không đáng tin, có thể chứa prompt injection.

---

## 7. Đề xuất kiến trúc cho dự án

### 7.1 Bốn lớp

```
┌──────────────────────────────────────────────────────────────────────┐
│ L1  TÍNH TOÁN TẤT ĐỊNH (không có LLM)                                │
│     data snapshot (OHLCV, có id) → indicator, volume profile, SMC    │
│     → sự kiện đã phát hiện + mức stop/TP ứng viên + ảnh chart        │
│     → bộ lọc sự kiện: có đáng gọi LLM không?                         │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ features (JSON) + chart (PNG) + hash
┌──────────────────────────────▼───────────────────────────────────────┐
│ L2  AGENT DIỄN GIẢI (song song, mỗi agent một lần gọi, có schema)    │
│     IndicatorAgent │ StructureAgent (SMC + volume profile, có ảnh)   │
│     │ TrendAgent (có ảnh)                                            │
│     Mỗi agent chỉ thấy phần dữ liệu của mình; đầu ra AgentView       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ danh sách AgentView
┌──────────────────────────────▼───────────────────────────────────────┐
│ L3  AGENT TỔNG HỢP                                                   │
│     Kiểm tra risk bằng code (R:R, khoảng cách stop, giới hạn vị thế) │
│     → SynthesisAgent: gộp, nêu mâu thuẫn, ra TradeView cuối          │
│     → hậu kiểm tất định (quy tắc nghiệp vụ, khớp số)                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ TradeView đã kiểm
┌──────────────────────────────▼───────────────────────────────────────┐
│ L4  BÁO CÁO + NGƯỜI DUYỆT                                            │
│     Báo cáo Markdown/HTML: nhận định, chart, bảng số, nguồn từng số  │
│     → người duyệt: chấp nhận / từ chối / ghi chú (được log)          │
│     → KHÔNG có đường nào từ đây tới API đặt lệnh                     │
└──────────────────────────────────────────────────────────────────────┘
```

Khác biệt có chủ ý so với QuantHarness:

- RiskAgent được thay bằng **code**: các mức stop/TP ứng viên và giới hạn rủi ro là tất định; LLM chỉ chọn trong danh sách và giải thích.
- Agent diễn giải không tự gọi tool trong luồng chính; số được tính trước. Điều này cắt số request và làm đầu vào tái lập được.
- Có trạng thái `neutral` và có bước người duyệt. QuantHarness chỉ ra LONG/SHORT.
- Lớp L1 tự nó là một hệ ra tín hiệu hoàn chỉnh và là baseline bắt buộc để đo đóng góp của L2–L3.

### 7.2 Lược đồ state

Dùng Pydantic để cùng một định nghĩa phục vụ validate, log và (nếu sau này cần) state của LangGraph.

```python
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel

Direction = Literal["long", "short", "neutral"]


class RunMeta(BaseModel):
    run_id: str                      # UUID sinh ở L1, không đưa vào prompt
    symbol: str
    timeframe: str
    as_of: datetime                  # thời điểm đóng của nến cuối, UTC
    data_snapshot_id: str            # định danh bộ OHLCV bất biến
    calc_version: str                # phiên bản code L1 (git SHA)
    mode: Literal["live", "paper", "eval"]


class Features(BaseModel):
    indicators: dict[str, float]     # RSI, MACD, ATR... đã làm tròn theo tick
    events: list[str]                # sự kiện tất định, dạng câu ngắn có số
    volume_profile: dict[str, float] # poc, vah, val
    smc: list[dict]                  # order block, FVG, BOS/CHoCH kèm mức giá
    last_close: float
    stop_candidates: list[float]
    tp_candidates: list[float]
    features_sha256: str


class ChartRef(BaseModel):
    kind: Literal["price_volume", "structure", "trend"]
    path: str                        # đường dẫn file PNG bất biến
    width: int
    height: int
    sha256: str


class LLMCall(BaseModel):
    request_id: str
    model: str
    prompt_version: str
    system_sha256: str
    request_path: str                # bản sao nguyên văn request
    response_path: str               # bản sao nguyên văn response
    stop_reason: str
    usage: dict
    latency_ms: int
    cost_usd: float


class AgentView(BaseModel):
    agent: str
    direction: Direction
    confidence: float
    rationale: str
    cited_fields: list[str]          # tên trường trong Features mà agent dựa vào
    call: LLMCall


class RiskCheck(BaseModel):
    passed: bool
    reward_risk: Optional[float]
    violations: list[str]


class TradeView(BaseModel):
    direction: Direction
    confidence: float
    rationale: str
    stop: Optional[float]
    take_profit: Optional[float]
    disagreements: list[str]         # mâu thuẫn giữa các agent
    call: LLMCall


class HumanReview(BaseModel):
    reviewer: str
    decision: Literal["approved", "rejected", "needs_changes"]
    note: str
    reviewed_at: datetime


class PipelineState(BaseModel):
    meta: RunMeta
    features: Features
    charts: list[ChartRef]
    deterministic_signal: Direction  # tín hiệu của L1 khi không có LLM (baseline)
    agent_views: list[AgentView] = []
    risk: Optional[RiskCheck] = None
    final: Optional[TradeView] = None
    validation_errors: list[str] = []
    review: Optional[HumanReview] = None
    outcome: Optional[dict] = None   # điền SAU, bởi job đánh giá: giá sau k nến
```

Nếu chuyển sang LangGraph: `agent_views` và `validation_errors` là các key cần reducer kiểu nối list vì nhiều node song song cùng ghi; các key còn lại ghi đè.

### 7.3 Log để kiểm toán quyết định

Mục tiêu: với bất kỳ quyết định nào trong quá khứ, trả lời được "hệ thống đã thấy gì, đã nói gì, bằng model và prompt nào, ai duyệt, kết quả ra sao" mà không cần gọi lại model.

- **Append-only.** Mỗi lần chạy là một bản ghi JSONL (hoặc một thư mục `runs/{date}/{run_id}/`). Không sửa bản ghi cũ; `outcome` và `review` là bản ghi nối thêm tham chiếu `run_id`.
- **Lưu nguyên văn** request và response của mọi lần gọi LLM, kể cả ảnh (theo hash). Đây là điều kiện để replay và để chứng minh quyết định có trước kết quả.
- **Định danh mọi đầu vào**: `data_snapshot_id`, `calc_version` (git SHA), `prompt_version`, hash system prompt, hash schema, model ID, phiên bản SDK.
- **Thời gian**: `as_of` (nến cuối đã đóng), thời điểm gọi LLM, thời điểm có kết quả, thời điểm người duyệt. Chênh lệch giữa `as_of` và thời điểm có kết quả chính là độ trễ cần đưa vào backtest.
- **Chuỗi hash**: mỗi bản ghi chứa hash của bản ghi trước, để phát hiện sửa đổi về sau. Có thể công bố hash đầu chuỗi hằng ngày ra một nơi độc lập.
- **Chi phí và hiệu năng**: `usage` (gồm token cache), độ trễ, chi phí quy đổi USD cho mỗi lần gọi và mỗi quyết định.
- **Lỗi cũng là dữ liệu**: `stop_reason` bất thường, vi phạm quy tắc nghiệp vụ, timeout, retry đều được ghi; quyết định tương ứng được ghi là `neutral` kèm lý do.
- **Baseline song song**: luôn ghi `deterministic_signal` cạnh `final` để so sánh trên cùng tập mẫu.
- **Bảo mật**: không ghi API key hay thông tin tài khoản vào log; log request trước khi thêm header xác thực.

### 7.4 Guardrail

**Agent không tự đặt lệnh.** Điều này phải được đảm bảo bằng cấu trúc, không bằng prompt:

1. **Không có năng lực.** Tiến trình chạy agent không có API key giao dịch, không import client đặt lệnh, không có tool nào ghi ra thế giới bên ngoài. Tool của agent chỉ đọc dữ liệu từ kho nội bộ.
2. **API key chỉ đọc** cho mọi kết nối sàn dùng trong pipeline; không bật quyền trade hay withdraw; giới hạn IP.
3. **Tách tiến trình.** Nếu sau này có mô-đun thực thi, nó là một dịch vụ riêng, chỉ nhận lệnh từ hành động của người (bấm duyệt trong giao diện), có giới hạn kích thước lệnh và kill switch độc lập với LLM.
4. **Luôn có người duyệt.** `TradeView` chỉ là đề xuất. Trạng thái mặc định là "chờ duyệt"; không có cơ chế tự duyệt theo ngưỡng confidence.

Guardrail khác:

- **Xác thực hai tầng**: schema (structured output) và quy tắc nghiệp vụ (code). Thất bại ở tầng nào cũng dẫn tới `neutral`, không tự sửa.
- **Kiểm tra số**: mọi con số trong `rationale` phải khớp đầu vào.
- **Dữ liệu cũ**: từ chối chạy nếu `as_of` quá xa hiện tại hoặc nến cuối chưa đóng.
- **Prompt injection**: dự án chỉ dùng OHLC nên bề mặt nhỏ. Nếu sau này thêm tin tức hay dữ liệu qua MCP, nội dung đó phải nằm trong khối dữ liệu tách biệt, và agent đọc nội dung không tin cậy không được có tool nào ngoài đọc.
- **Ngân sách**: trần USD theo ngày, trần số lần gọi cho mỗi lần chạy, timeout; vượt trần thì dừng và báo.
- **Hiển thị bất định**: báo cáo luôn ghi mức đồng thuận giữa các agent, tín hiệu của baseline tất định, và câu nhắc rằng đây không phải lời khuyên đầu tư.
- **Kiểm định định kỳ**: job hằng tuần điền `outcome`, tính accuracy, calibration và so với baseline. Nếu lớp LLM không hơn baseline theo tiêu chí đã định trước ở mục 2.5, hạ vai trò của nó xuống chỉ còn diễn giải.

### 7.5 Lộ trình gợi ý

1. Hoàn thiện L1 và báo cáo không có LLM; đo baseline.
2. Thêm một agent diễn giải duy nhất (ví dụ ở mục 5.5) với log đầy đủ; chạy paper, thu mẫu sau cutoff.
3. Thêm các agent còn lại và agent tổng hợp; chạy ablation.
4. Chỉ khi cần nhánh, song song phức tạp, hoặc dừng chờ duyệt trong cùng một luồng thì đưa LangGraph vào.
5. Song song, thử hướng kiểu RD-Agent(Q): dùng LLM đề xuất factor/điều kiện, đưa vào L1 dưới dạng code, kiểm định như mọi factor khác.

---

## 8. Danh sách điều chưa xác minh

1. Toàn bộ số liệu Alpha Arena (ngày, return, model thắng) lấy từ báo chí; trang gốc alphaarena.ai trả HTTP 429. Chưa có thông tin Season 2.
2. Con số kết quả cụ thể của TradingAgents, FinMem; venue của FinCon (NeurIPS 2024), FinAgent (KDD 2024), RD-Agent(Q).
3. FinRobot dựa trên AutoGen; danh sách agent và việc dùng LangGraph của AI Hedge Fund.
4. Cửa sổ đánh giá của StockBench; chi tiết Agent Market Arena, MemGuard-Alpha, nghiên cứu FX của HKU; con số 85% của FinLake-Bench (chưa đọc toàn văn).
5. Paper Sarkar & Vafa về lookahead bias không tìm được trong phiên này.
6. QuantHarness: phần cuối bản HTML v4 chưa đọc (chi phí giao dịch, LLM cụ thể); thư viện vẽ chart thật sự dùng trong repo.
7. Claude API: sự tồn tại của tham số `seed`; giá batch của Fable 5.2; câu chữ chính thức về việc thinking token tính như output; chi tiết tham số `fallbacks`; câu chữ trên tài liệu web về việc Opus 5.5 và Sonnet 5.5 từ chối `tool_choice` kiểu `any`/`tool`.
8. Ngày GA chính xác của Microsoft Agent Framework 1.0; gói PyPI `autogen` trỏ về AG2.
9. Khái niệm reducer, conditional edge, time travel của LangGraph mô tả theo kiến thức nền, chưa đọc lại từ trang tài liệu tương ứng; phiên bản LangGraph hiện hành.
10. MCP: license và tình trạng bảo trì của các server bọc CCXT; việc có hay không MCP chính thức của Binance; điều khoản dùng dữ liệu TradingView MCP cho hệ tự động.
11. Mã ví dụ Python trong tài liệu chưa được chạy thử (máy tra cứu không cài gói `anthropic`).
12. Khuyến nghị về kích thước và cách vẽ chart là kinh nghiệm thiết kế, chưa có benchmark riêng.
