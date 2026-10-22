# Quản lý bãi đỗ xe

## Chạy ứng dụng

1. Cài Python 3.10 trở lên.
2. Mở terminal tại thư mục `parking_app`.
3. Cài thư viện: `python -m pip install -r requirements.txt`.
4. Chạy: `python main.py`.

Ứng dụng khởi động với các ô đỗ trống nếu chưa có dữ liệu. Dữ liệu nghiệp vụ được lưu trong `data/parking_data.json`; tài khoản được lưu riêng trong `data/accounts.json`. Các file được tạo tự động khi chạy lần đầu, ghi an toàn qua file tạm và giữ bản sao lưu `.bak` trước khi cập nhật. Tích hợp cổng API tạo mã QR thanh toán ngân hàng trực tuyến theo chuẩn quốc gia VietQR (Napas 247 / EMVCo) lưu nhật ký tại `data/vietqr.json`.

Tài khoản quản trị khởi tạo: `admin` / `admin123`. Hãy đổi mật khẩu trước khi sử dụng thực tế. Tài khoản nhân viên được tạo từ mục **Nhân sự & Tài khoản**; khách hàng có thể đăng ký ở màn hình đăng nhập.

Thông tin ngân hàng và tên bãi xe có thể chỉnh trong `config.py` (hỗ trợ MBBank, Vietcombank, Vietinbank, BIDV...). Khách hàng quét mã VietQR bằng bất kỳ App ngân hàng nào để thanh toán nhanh phí gửi xe và vé tháng. Phần nghiệp vụ dùng lớp backend của đồ án và lưu trữ JSON theo yêu cầu không sử dụng hệ quản trị CSDL.
