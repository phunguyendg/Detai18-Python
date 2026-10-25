# Hợp đồng giao tiếp GUI <-> Backend (bản mở rộng: thanh toán, ca trực, bảng giá)

GUI chỉ gọi các hàm dưới đây. Bản chạy thử đầy đủ nằm ở `gui/mock_backend.py` (cùng tên hàm, tham số, giá trị trả về).
Mọi lỗi nghiệp vụ ném `ParkingError` (hoặc lớp con) với **thông báo tiếng Việt**; GUI hiện nguyên văn `str(e)`.
Exception: `backend/exceptions.py` cần có đủ: ParkingError, InvalidPlateError, NoSlotAvailableError,
VehicleAlreadyParkedError, TicketNotFoundError, DuplicateMonthlyTicketError, **ShiftNotOpenError, PaymentError**, AuthError.

## Vĩ - ParkingManager / PriceTable
| Hàm | Ghi chú |
|---|---|
| `get_all_slots()`, `get_slot(id)`, `get_history(filters)`, `set_slot_maintenance(id, flag)` | như trước |
| `vehicle_entry(plate, vehicle_type, slot_id=None)` | trả `ParkingTicket` (có `is_monthly`) |
| `estimate_fee(key, lost_ticket=False)` | trả `(minutes, fee)` |
| `vehicle_exit(key, lost_ticket=False, method="cash", received=None, reference=None)` | trả ticket đã đóng, có `fee`, `payment_id` (rỗng nếu miễn phí). **Thu tiền (payments.collect) TRƯỚC khi đóng vé; lỗi thanh toán thì vé vẫn mở.** |
| `get_prices()` / `set_prices(dict)` | dict gồm `hourly{vt}`, `free_minutes`, `lost_ticket{vt}`, `monthly{vt}`, `monthly_discount{months:%}` |

Công thức phí: `0` nếu vé tháng hoặc <= `free_minutes`; ngược lại `ceil(phút/60) * giá giờ` (tối thiểu 1 giờ);
mất vé cộng thêm `lost_ticket[vt]` (kể cả vé tháng).

## Phú - MonthlyTicketService
| Hàm | Ghi chú |
|---|---|
| `add / update / remove / get_all / search / check_monthly_ticket` | như trước (quản trị nhập tay, không thu tiền) |
| `quote_monthly(plate, vehicle_type, months, start_date=None)` | dict: `start_date, end_date, months, base, discount_pct, discount, total, is_renewal`. Xe còn vé hạn -> gia hạn nối tiếp (`start = end_cũ + 1`). Ngày bắt đầu không được ở quá khứ. `end = start + months tháng - 1 ngày` |
| `purchase_monthly_ticket(plate, owner, phone, vehicle_type, months, start_date, method, received=None, reference=None)` | trả `(MonthlyTicket, Payment)`. Thu tiền trước, thành công mới tạo/gia hạn vé |

## PaymentService (đề xuất: Vĩ làm, Phú dùng cho thống kê)
| Hàm | Ghi chú |
|---|---|
| `get_payment_methods()` | `[(key, nhãn)]`: cash, bank_transfer, momo, zalopay, card |
| `collect(kind, plate, ref, description, amount, method, received, reference)` | Điều kiện: **phải có ca đang mở** (`ShiftNotOpenError`); `amount > 0`; tiền mặt: `received >= amount`, tính `change`; phi tiền mặt: `reference` khớp `^[A-Za-z0-9-]{6,24}$` và **không trùng** mã đã dùng (`PaymentError`) |
| `get_payment(id)`, `get_transactions(filters)` | filters: `kind, method, plate, date_from, date_to` |
| `build_receipt(payment_id)` | trả chuỗi hóa đơn nhiều dòng |
| `open_shift(cashier, opening_cash)`, `current_shift()`, `get_shifts()` | chỉ 1 ca mở tại một thời điểm |
| `shift_summary(shift_id)` | `{count, total, cash, by_method}` |
| `close_shift(counted_cash, note="")` | `expected = đầu ca + tiền mặt thu trong ca`; `difference = counted - expected`; lệch thì **bắt buộc ghi chú** |
| `revenue_by_method(day=None)`, `revenue_by_kind(day=None)` | cho thống kê |

## Phú - Statistics
`get_statistics()` thêm khóa: `revenue_parking, revenue_monthly, revenue_by_method`;
`revenue` = tổng doanh thu trong ngày (phí gửi xe + bán vé tháng).
`export_shift_report(path)` gồm thông tin ca + doanh thu theo hình thức + danh sách giao dịch.
`backup_data(path)` sao lưu toàn bộ dữ liệu ra JSON.

## Khóa dữ liệu (JSON) đề xuất
`payments.json`, `shifts.json`, `prices.json` (thêm vào danh sách file ở mục 5 của file phân công).

---
# BẢN MỞ RỘNG 2: Tài khoản, phân quyền 3 vai trò, nhật ký, cổng khách hàng

## Vai trò
| Vai trò | Cấp tài khoản | Được làm |
|---|---|---|
| `admin` Quản trị | có sẵn | Mọi chức năng + Nhân sự & Tài khoản + Nhật ký + Bảng giá + Sao lưu + Đặt bảo trì ô + sửa/xóa vé tháng + chốt thay ca |
| `staff` Nhân viên ca trực | **Admin tạo** (`create_staff`), phải đổi MK lần đầu | Xe vào/ra, thu tiền, bán/gia hạn vé tháng, xử lý yêu cầu & xác minh xe khách, mở/chốt **ca của chính mình**, xem giao dịch/ca **của chính mình**, xuất báo cáo ca |
| `user` Khách hàng | **Tự đăng ký** (`register`) | Chỉ xem tình trạng bãi (không thấy biển số), xe/vé tháng/lịch sử/hóa đơn **của chính mình**, gửi yêu cầu mua/gia hạn vé tháng |

**Quyền kiểm tra ở BACKEND** (GUI chỉ ẩn/hiện): mỗi hàm gọi `audit.require(*roles)`, sai quyền ném `PermissionDeniedError`.
Người thao tác lấy từ `audit.actor` (được set khi `auth.login`, xóa khi `auth.logout`).

## AuthService 
`login(u, p) -> User(username, role, full_name, must_change_password)`; `logout()`; `register(u, p, full_name, phone)` (luôn là `user`);
`change_password(u, old, new)`; `get_profile(u)`; admin: `list_accounts(role, kw)`, `create_staff(u, name, phone, temp_pw)`,
`set_active(u, flag)`, `reset_password(u, temp_pw)`, `unlock_login(u)`.
Điều kiện: MK >= 8 ký tự có chữ + số; **PBKDF2-HMAC-SHA256 + salt riêng từng người** (demo 200k vòng, triển khai thật >= 600k);
thông báo sai đăng nhập **chung chung** (không lộ tài khoản có tồn tại); không tự khóa mình;
không khóa admin cuối cùng; lỗi đăng nhập/khóa đều ghi nhật ký. `users.json` lưu `salt`, `pw_hash` (không lưu MK gốc).

## AuditLog
`log(action, detail)`, `get_entries(filters)` (chỉ admin; filters: `actor, action, date_from, date_to`). Các hành động: xem `AUDIT_ACTIONS` trong `config.py`.

## Ca trực gắn với tài khoản
- `open_shift(cashier, cash)`: `cashier` phải bằng tài khoản đang đăng nhập; chỉ **1 ca mở** tại một thời điểm.
- `collect(...)`: chỉ thu ngân của ca đang mở mới thu được (`PaymentError` nếu ca của người khác).
- `close_shift`: chỉ chủ ca chốt; **admin chốt thay** được (tự ghi chú "[Quản trị ... chốt thay]").
- `get_shifts / get_transactions / revenue_*`: nhân viên chỉ thấy dữ liệu **của mình**, admin thấy tất cả.

## CustomerService (cổng khách hàng)
`get_public_slots()` (ô không có biển số), `get_public_status()`, `link_vehicle(plate, type) -> verified`, `unlink_vehicle`,
`get_my_vehicles()`, `get_my_monthly_tickets()`, `get_my_history()`, `get_my_payments()`, `get_my_receipt(payment_id)`,
`submit_monthly_request(plate, months)`, `get_my_requests()`.
Xác minh xe: tự động nếu SĐT tài khoản trùng SĐT chủ vé tháng của biển số đó; ngược lại chờ nhân viên.
Mỗi biển số chỉ liên kết với **một** tài khoản. Phía nhân viên: `get_pending_vehicles()`, `verify_vehicle(plate, approve)`,
`get_requests(status)`, `resolve_request(id, "done"|"rejected", note)` (từ chối bắt buộc có lý do).
Thêm file dữ liệu: `users.json`, `customer_vehicles.json`, `monthly_requests.json`, `audit_log.json`.

---
# BẢN MỞ RỘNG 3: Vào bãi tự động / chọn ô, khách tự vào bãi, sửa trạng thái ô, tự đăng xuất khi chốt ca

| Hàm | Quyền | Ghi chú |
|---|---|---|
| `vehicle_entry(plate, vehicle_type, slot_id=None)` | staff, admin | `slot_id=None`: hệ thống tự gán ô trống (gần cổng nhất); hoặc chọn ô trống cụ thể. Ô đã có xe/bảo trì -> `ParkingError` |
| `CustomerService.self_entry(plate, slot_id=None)` | user | Khách TỰ vào bãi. Điều kiện: xe đã liên kết + xác minh; **đang có ca trực mở** (`ShiftNotOpenError` nếu không - để có người thu phí khi ra); ô còn trống. Lấy xe ra vẫn do nhân viên thu phí tại quầy |
| `set_slot_maintenance(slot_id, flag, reason="")` | **staff, admin** | `flag=True` (bảo trì) **bắt buộc có lý do** >= 3 ký tự, lưu vào `ParkingSlot.note`; `flag=False` mở lại ô. Ô đang có xe không đổi được. Ghi nhật ký (hành động `maintenance`) |

`ParkingSlot` thêm thuộc tính `note` (lý do bảo trì). `get_public_slots()` của khách không trả `note`/biển số.
Nhật ký vào bãi ghi thêm "tự động" / "khách tự vào".

**Tự đăng xuất khi chốt ca (GUI):** sau khi nhân viên chốt ca của chính mình, GUI tự đăng xuất và quay lại màn đăng nhập.
Quản trị chốt thay ca người khác thì không đăng xuất.

---
# BẢN MỞ RỘNG: API Tạo mã QR thanh toán ngân hàng chuẩn VietQR (Napas 247 / EMVCo)
`VietQRService(cache_path, api_url, banks_url, timeout, template)` - dịch vụ tích hợp thanh toán ngân hàng trực tuyến không phụ thuộc đăng nhập/vai trò.
| Hàm | Ghi chú |
|---|---|
| `generate_qr(amount, memo, plate="", bank_bin="970422", account_no="0987654321", account_name="...", bank_name="MBBank")` | Gọi API VietQR công khai (https://api.vietqr.io/v2/generate) để tạo mã QR chuẩn Napas 247. Tự động chuyển đổi và sinh chuỗi chuẩn EMVCo kèm CRC-16 CCITT và ma trận QR cục bộ khi mất mạng. Lưu vết giao dịch vào `data/vietqr.json`. |
| `get_banks()` | Lấy danh sách hơn 70 ngân hàng Việt Nam từ https://api.vietqr.io/v2/banks hoặc dùng danh mục offline có sẵn |
| `get_recent_transactions()` | Danh sách các giao dịch mã QR đã tạo phục vụ đối soát |
| `load_cache()`, `save_transaction(txn)` | Đọc và ghi an toàn nhật ký giao dịch qua file tạm và thay thế nguyên tử |

Lỗi: `VietQRError` (thông báo tiếng Việt). File dữ liệu lưu trữ: `data/vietqr.json`.
