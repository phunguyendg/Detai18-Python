# Backend services (JSON)

Thư mục `backend/` chứa các service backend đã được bổ sung xử lý và lưu JSON:

- `parking_manager.py`: ô đỗ, vé xe, bảng giá (`parking_slots.json`, `tickets.json`, `prices.json`).
- `monthly.py`: CRUD, báo giá, mua/gia hạn vé tháng (`monthly_tickets.json`). Mua vé tháng yêu cầu `PaymentService` được truyền vào, không còn tự sinh thanh toán giả.
- `payments.py`: lịch sử thanh toán, tiền nhận/tiền thối, ca trực, tổng kết ca và hóa đơn (`payments.json`, `shifts.json`).
- `auth.py`: đăng ký/đăng nhập/phân quyền/tài khoản (`accounts.json`). Tài khoản mẫu khi chưa có file: `admin/admin123`, `staff/staff123`, `khach01/khach123`.
- `customers.py`: liên kết xe chờ xác minh, duyệt/từ chối xe, yêu cầu vé tháng, lịch sử và hóa đơn theo tài khoản (`customer_data.json`).
- `stats.py`: thống kê và báo cáo CSV; sao lưu các file JSON.
- `audit.py`: ghi và lọc nhật ký (`audit.json`).

Các file dữ liệu tự tạo trong `parking_app/data/` khi chạy service. Hãy sao lưu thư mục `data` trước khi thay đổi dữ liệu hiện có.

## Lưu ý tích hợp

Giao diện Tkinter hiện tại vẫn khởi tạo các service tương thích cũ từ `gui/mock_backend.py`. Các service trong `backend/` đã được hoàn thiện riêng nhưng chưa thay trực tiếp backend của giao diện, vì giao diện hiện gọi một số phương thức/thuộc tính khác nhau. Không xóa `gui/mock_backend.py` trước khi hoàn tất lớp adapter và kiểm thử từng màn hình.
