# Bộ tài liệu nền của dự án

Lập ngày 2026-11-13. Sáu file dưới đây do sáu luồng nghiên cứu độc lập viết; file này là mục lục và phần tổng hợp.

## Phạm vi

Dự án chỉ làm crypto. Các phần về cổ phiếu trong file 05 (nguồn dữ liệu cổ phiếu, phân tích cơ bản ở mục 9, factor investing) nằm ngoài phạm vi và chỉ để tham khảo. Lớp LLM multi-agent (file 01, 06) tạm gác.

## Trạng thái kiểm chứng

- Mỗi file có mục "chưa xác minh" ở cuối. Tổng cộng khoảng 120 chỗ được đánh dấu. Đọc mục đó trước khi dựa vào một con số.
- Chỉ các ví dụ Python trong file 02 đã chạy thật. Code Pine, giả mã Python (file 03, 04) và ví dụ Claude API (file 06) chưa chạy.
- Nhiều trích dẫn paper trong file 04 và 05 được ghi theo trí nhớ, chưa mở bài gốc.
- Phần tổng hợp chỉ mới đối chiếu cấu trúc và vài đoạn chính của từng file, chưa đọc lại toàn bộ 5.000 dòng.

## Mục lục

| File | Nội dung | Đọc khi |
|---|---|---|
| [01-quantharness-paper.md](01-quantharness-paper.md) | Paper QuantHarness đủ 32 trang, repo GitHub, mọi bảng kết quả, đánh giá phản biện | Thiết kế lớp agent |
| [02-exchange-apis.md](02-exchange-apis.md) | Binance và OKX: REST, WebSocket, rate limit, xác thực, dữ liệu lịch sử, ví dụ Python | Viết lớp dữ liệu |
| [03-pine-script-va-smc.md](03-pine-script-va-smc.md) | Pine Script v6; SMC dưới dạng thuật toán; phân tích indicator "Dynamic SMC & Market Structure PRO" | Viết indicator hoặc module SMC |
| [04-phuong-phap-phan-tich.md](04-phuong-phap-phan-tich.md) | Volume profile, order flow, phái sinh crypto, Wyckoff, Elliott, thanh khoản, indicator cổ điển, vĩ mô, on-chain | Viết module phân tích |
| [05-quant-backtest-va-du-lieu.md](05-quant-backtest-va-du-lieu.md) | Quy trình nghiên cứu, backtest, metric, quản trị rủi ro, thư viện Python, nguồn dữ liệu, phân tích cơ bản cổ phiếu, kiến trúc lưu trữ | Chọn công cụ, viết backtest |
| [06-llm-multi-agent.md](06-llm-multi-agent.md) | Các hệ LLM cho tài chính, bằng chứng phản biện, framework agent, Claude API, MCP, kiến trúc đề xuất | Viết lớp LLM |
| [07-ke-hoach-trien-khai.md](07-ke-hoach-trien-khai.md) | Kế hoạch từng bước, giới hạn và chặn của hai sàn, dữ liệu cần cho từng indicator | Trước khi bắt đầu code |
| [08-kien-truc.md](08-kien-truc.md) | Kiến trúc: các lớp, tiến trình, module, mô hình dữ liệu, giao diện | Trước khi dựng khung |

## Kết luận xuyên suốt

1. **Paper là khung tham khảo, không phải bằng chứng.** Ở Bảng 1, hồi quy tuyến tính có lợi nhuận tích lũy cao hơn QuantHarness ở 7/7 mã có số liệu. Paper không tính phí, không cho HOLD, không nêu model LLM; repo không có code đánh giá. (File 01, mục 0 và 6.)
2. **Tính toán tất định trước, LLM sau.** Indicator, volume profile, SMC và mức stop/TP tính bằng code; LLM chỉ diễn giải. Lớp tất định tự nó là baseline để đo LLM có đóng góp gì không. (File 06, mục 7.)
3. **Backtest có LLM bị look-ahead** nếu dữ liệu nằm trước knowledge cutoff của model. Chỉ forward test mới có giá trị. (File 06, mục 2.)
4. **Bằng chứng cho SMC, Wyckoff, Elliott, volume profile đều yếu.** Chúng lập trình được từng phần và phải tự kiểm định. (File 03 phần D; file 04 mục 10.)
5. **Một số dữ liệu không lấy lại được.** Open interest và long/short ratio qua REST chỉ giữ khoảng 30 ngày; liquidation chỉ còn qua WebSocket; aggTrades futures chỉ 48 giờ. Cần chạy bộ thu thập từ sớm. (File 02; file 04 mục 3.)
6. **Lưu trữ:** Parquet + DuckDB, mỗi feature có `event_time` và `known_at`. (File 05 mục 10; file 04 mục 10.2.)
7. **Giấy phép:** SMC của LuxAlgo cấm dùng thương mại; vectorbt có Commons Clause; indicator Dynamic SMC theo MPL 2.0. (File 03 phần C; file 05 mục 7.)

## Những gì bộ tài liệu chưa có

- Thiết kế chi tiết và mã nguồn của dự án: chưa viết dòng code nào.
- Thực thi lệnh, quản lý vị thế, đối soát: mới liệt kê nhóm endpoint.
- Thuế và pháp lý giao dịch crypto/chứng khoán.
- Chứng khoán Việt Nam: chỉ có một đoạn ngắn trong file 05, phần API của SSI/TCBS/DNSE chưa xác minh.
- Sàn khác ngoài Binance và OKX (Bybit, Hyperliquid, DEX).
- Options và biến động ngụ ý.

## Lộ trình đề xuất

1. Lớp dữ liệu: tải nến Binance/OKX về Parquet, kèm bộ thu OI, funding, liquidation chạy nền.
2. Module tất định: indicator, volume profile, swing/BOS/CHoCH/FVG, có unit test.
3. Backtest có phí và slippage, so với baseline hồi quy tuyến tính và buy-and-hold.
4. Lớp LLM diễn giải và báo cáo, đánh giá bằng forward test.
5. Indicator Pine Script cho các tín hiệu đã qua kiểm định.
