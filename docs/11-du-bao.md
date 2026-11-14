# 11. Dự báo (Projection): hình nón xác suất cho đường đi tiếp theo

Code: `src/rinng/analysis/forecast.py`, lens `forecast` trong `src/rinng/web/lenses.py`.
Chỉ phân tích, không phải khuyến nghị giao dịch.

## Vì sao là hình nón, không phải một đường

Giá crypto ngắn hạn gần như ngẫu nhiên. Một đường "giá sẽ đi thế này" luôn trông chắc chắn hơn
thực tế. Thứ đo được và kiểm chứng được là **phân phối**: giá có khả năng nằm trong khoảng nào sau
H nến, và xác suất chạm từng mức giá quan trọng.

## Phương pháp

1. **Biến động** sigma_t: EWMA của log-return (lambda 0.94). Mọi quỹ đạo được chia theo sigma của
   chính nó, nên quá khứ biến động mạnh/yếu đều so sánh được với hiện tại.
2. **Trạng thái** mỗi nến (8 đặc trưng, chỉ dùng dữ liệu tới nến đó): lợi suất 1/5/20/60 nến theo
   sigma, chế độ biến động (sigma / độ lệch chuẩn 200 nến), vị trí trong range 50 nến, RSI 14,
   volume so với trung bình 50 nến.
3. **Tình huống tương tự**: K nến quá khứ gần nhất với trạng thái hiện tại (K ≈ pool/15, 100–600),
   chỉ những nến mà H nến sau đó đã kết thúc trước hiện tại. Trọng số kernel theo khoảng cách.
4. **Trộn** 70% phân phối có điều kiện với 30% phân phối của mọi quỹ đạo quá khứ, để không quá tin
   một nhóm nhỏ.
5. **Kết quả**: phân vị 5/10/25/50/75/90/95% cho từng bước 1..H (hình nón), và xác suất chạm mức
   giá = tỉ lệ có trọng số các quỹ đạo có high/low chạm mức đó trong H nến.

H theo khung: 15m/1h: 48 nến, 4h: 42 (≈ 7 ngày), 1d: 30, 1w: 12. Tập quỹ đạo: tối đa 20.000 nến
lịch sử của khung đó. Tính lại khi nến của khung đóng (cùng cơ chế realtime).

## Kiểm chứng walk-forward

Chạy lại đúng quy trình tại 250 điểm trong quá khứ, mỗi điểm chỉ thấy dữ liệu trước nó, so với giá
thật sau H nến. Số liệu hiện ngay trên chart và dashboard. Kết quả ngày 2026-11-14 (Binance):

| Cặp | Khung | Dải 50% chứa | Dải 80% chứa | Dải 90% chứa | Đúng chiều | Kỹ năng vs không điều kiện |
|---|---|---|---|---|---|---|
| BTC | 1h (H=48) | 50% | 80% | 90% | 52% | 0.0% |
| BTC | 4h (H=42) | 51% | 83% | 90% | 49% | −0.3% |
| BTC | 1d (H=30) | 53% | 81% | 91% | 55% | +3.7% |
| ETH | 1h | 56% | 81% | 90% | 52% | +1.0% |
| ETH | 4h | 54% | 79% | 91% | 47% | −0.6% |
| ETH | 1d | 47% | 74% | 86% | 46% | −1.8% |

Đọc kết quả:
- **Độ rộng hình nón đáng tin**: các dải chứa kết quả thật gần đúng tỉ lệ danh nghĩa. Riêng ETH 1d
  hơi hẹp: dải 80% chỉ chứa 74%.
- **Chiều đi không đoán được**: trung vị đúng chiều quanh 50%, kỹ năng so với phân phối không điều
  kiện xấp xỉ 0. Đây là kết quả thật, không phải lỗi; UI ghi rõ "not a direction call".
- Giá trị dùng được: khoảng dao động hợp lý và xác suất chạm BSL/SSL/POC/VAH/VAL trong H nến.

## Test

`tests/analysis/test_forecast.py`: không nhìn trước tương lai (dự báo trên dữ liệu cắt = dự báo trên
dữ liệu đầy đủ tại cùng điểm), phân vị có thứ tự và mở rộng theo thời gian, xác suất chạm đơn điệu,
và trên random walk thì các dải được hiệu chỉnh đúng còn kỹ năng ≈ 0 (không có "kỹ năng ảo").

## Hướng cải thiện có thể thử (mỗi thay đổi phải qua walk-forward trước khi dùng)

- Thêm đặc trưng phái sinh (funding, thay đổi OI, CVD) vào trạng thái.
- Chọn `blend`, K theo walk-forward riêng từng khung (cẩn thận overfit: tách giai đoạn chọn và
  giai đoạn chấm).
- Hiệu chỉnh lại (conformal) khi độ phủ lệch, ví dụ ETH 1d.
