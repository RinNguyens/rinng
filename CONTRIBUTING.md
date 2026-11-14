# Đóng góp cho rinng

Cảm ơn bạn quan tâm. Ai cũng có thể clone, chạy và đề xuất thay đổi. Chỉ chủ repo
(@RinNguyens) được merge vào `main` và `dev`. Mọi thay đổi đều đi qua pull request và cần
chủ repo review.

## Nhánh

| Nhánh | Vai trò |
|---|---|
| `main` | bản ổn định, được bảo vệ |
| `dev` | nhánh tích hợp, được bảo vệ. PR nhắm vào đây |
| `feat/...`, `fix/...`, `docs/...` | nhánh làm việc của bạn |

## Quy trình

1. **Fork** repo trên GitHub (người ngoài không push thẳng vào repo này được).
2. Clone bản fork, rồi tạo nhánh từ `dev`:
   ```bash
   git clone https://github.com/<tên-bạn>/rinng.git
   cd rinng
   git remote add upstream https://github.com/RinNguyens/rinng.git
   git fetch upstream
   git checkout -b feat/ten-tinh-nang upstream/dev
   ```
3. Viết code kèm test, rồi kiểm tra:
   ```bash
   uv sync
   uv run pytest
   uv run ruff check && uv run ruff format --check
   pnpm --dir web lint && pnpm --dir web typecheck   # nếu sửa web/
   ```
4. Push lên fork và mở **pull request vào `dev`** của `RinNguyens/rinng`. Mô tả rõ thay đổi gì và lý do.
5. Chủ repo review. Sửa theo góp ý bằng cách push thêm commit lên cùng nhánh. Khi PR được duyệt,
   chủ repo sẽ merge.

## Quy ước

- Mỗi PR một việc. Commit message ngắn, viết ở thể mệnh lệnh ("Add OKX funding poller").
- Không commit dữ liệu (`data/`), `.env`, API key hay file build.
- rinng chỉ phân tích, không đặt lệnh. PR thêm chức năng giao dịch tự động sẽ không được nhận.
- Báo lỗi hoặc đề xuất tính năng: mở [Issue](https://github.com/RinNguyens/rinng/issues).

Khi gửi đóng góp, bạn đồng ý để code đó được phát hành theo [giấy phép MIT](LICENSE).
