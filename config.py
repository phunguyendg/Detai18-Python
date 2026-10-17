"""Hằng số và cấu hình dùng chung cho toàn bộ ứng dụng (đường dẫn, màu, font...)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"          # JSON/CSV mẫu và file báo cáo xuất ra
RECEIPT_DIR = DATA_DIR / "receipts"   # hóa đơn .txt lưu ra file

APP_TITLE = "Quản lý bãi đỗ xe"
MIN_WINDOW_SIZE = (1100, 680)

# --- Sơ đồ bãi: 2 hàng A, B; mỗi hàng 10 ô (A1-A10, B1-B10) ---
SLOT_ROWS = ("A", "B")
COLS_PER_ROW = 10

STATUS_EMPTY = "empty"
STATUS_OCCUPIED = "occupied"
STATUS_MAINTENANCE = "maintenance"

SLOT_COLORS = {
    STATUS_EMPTY: "#2E7D32",        # xanh = trống   (đủ tương phản với chữ trắng)
    STATUS_OCCUPIED: "#D32F2F",     # đỏ = đang có xe
    STATUS_MAINTENANCE: "#607D8B",  # xám xanh = bảo trì
}
STATUS_LABELS = {
    STATUS_EMPTY: "Trống",
    STATUS_OCCUPIED: "Có xe",
    STATUS_MAINTENANCE: "Bảo trì",
}

# --- Loại xe / trạng thái vé ---
VEHICLE_TYPES = {"motorbike": "Xe máy", "car": "Ô tô"}
TICKET_PARKED = "parked"
TICKET_CLOSED = "closed"
TICKET_STATUS_LABELS = {TICKET_PARKED: "Đang đỗ", TICKET_CLOSED: "Đã ra"}

# --- Vai trò ---
ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"      # nhân viên ca trực: tài khoản do Quản trị cấp, không tự đăng ký
ROLE_USER = "user"        # khách hàng / chủ xe: tự đăng ký
ROLE_LABELS = {ROLE_ADMIN: "Quản trị viên", ROLE_STAFF: "Nhân viên ca trực", ROLE_USER: "Khách hàng"}
STAFF_ROLES = (ROLE_STAFF, ROLE_ADMIN)

# --- Định dạng ngày ---
DATE_FMT = "%d/%m/%Y"
DATETIME_FMT = "%d/%m/%Y %H:%M"

# --- Giao diện ---
FONT_BASE = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_HEADER = ("Segoe UI", 15, "bold")
FONT_BIG = ("Segoe UI", 20, "bold")

# Bảng màu: nền trung tính + xanh dương chủ đạo + màu ngữ nghĩa (thành công / cảnh báo / lỗi)
COLOR_BG = "#EEF1F6"
COLOR_CARD = "#FFFFFF"
COLOR_HEADER = "#0F2A47"
COLOR_BORDER = "#D9DFE7"
COLOR_TEXT = "#1F2933"
COLOR_PRIMARY = "#1E6FD9"
COLOR_PRIMARY_DARK = "#1556AD"
COLOR_DANGER = "#D32F2F"
COLOR_SUCCESS = "#2E7D32"
COLOR_WARNING = "#F9A825"
COLOR_ORANGE = "#EF6C00"
COLOR_MUTED = "#6B7785"

ROW_COLORS = {
    "parked": "#FDECEA",
    "closed": "#E9F5EC",
    "valid": "#FFFFFF",
    "expiring": "#FFF4D6",
    "expired": "#ECEFF1",
}

EXPIRING_DAYS = 7          # vé tháng còn <= 7 ngày thì cảnh báo vàng
MIN_PASSWORD_LEN = 8        # tối thiểu 8 ký tự, có cả chữ và số
MAX_LOGIN_ATTEMPTS = 5      # sai quá số lần này thì khóa tạm
LOCKOUT_MINUTES = 5
PBKDF2_ITERATIONS = 200_000  # bản demo; triển khai thật nên dùng >= 600.000 (khuyến nghị OWASP)


# --- Thanh toán ---
PAYMENT_METHODS = {
    "cash": "Tiền mặt",
    "bank_transfer": "Chuyển khoản / VietQR",
    "momo": "Ví MoMo",
    "zalopay": "Ví ZaloPay",
    "card": "Thẻ ngân hàng (máy POS)",
}
CASH_METHOD = "cash"
TXN_KINDS = {"parking": "Phí gửi xe", "monthly": "Vé tháng"}
QUICK_CASH = (50_000, 100_000, 200_000, 500_000)   # nút chọn nhanh mệnh giá
DEFAULT_OPENING_CASH = 500_000                      # tiền lẻ đầu ca gợi ý
PARKING_NAME = "BÃI ĐỖ XE DEMO"

# Thông tin nhận chuyển khoản hiển thị cạnh mã QR. ĐÂY CHỈ LÀ GIÁ TRỊ MẪU - thay bằng thông tin thật
# của bãi khi triển khai (không đưa số tài khoản thật vào mã nguồn nộp bài).
BANK_INFO = {"bank": "(Tên ngân hàng)", "account": "0000000000", "holder": "BAI DO XE DEMO"}

# --- Bảng giá mặc định (đồng). Admin có thể sửa trong menu Tệp > Bảng giá ---
DEFAULT_PRICES = {
    "hourly": {"motorbike": 3000, "car": 10000},          # mỗi giờ bắt đầu tính tròn 1 giờ
    "free_minutes": 15,                                   # miễn phí trong N phút đầu
    "lost_ticket": {"motorbike": 50000, "car": 100000},   # phụ thu mất vé
    "monthly": {"motorbike": 120000, "car": 1200000},     # giá vé tháng / 1 tháng
    "monthly_discount": {1: 0, 3: 5, 6: 10, 12: 15},      # số tháng -> % giảm giá
}


# --- Nhật ký hoạt động ---
AUDIT_ACTIONS = {
    "login": "Đăng nhập", "login_failed": "Đăng nhập sai", "lockout": "Khóa tạm do đăng nhập sai",
    "logout": "Đăng xuất", "register": "Khách đăng ký", "password_change": "Đổi mật khẩu",
    "account_create": "Tạo tài khoản NV", "account_lock": "Khóa/Mở khóa tài khoản",
    "password_reset": "Đặt lại mật khẩu", "shift_open": "Mở ca", "shift_close": "Chốt ca",
    "vehicle_entry": "Xe vào", "vehicle_exit": "Xe ra", "payment": "Thu tiền",
    "monthly_manage": "Quản lý vé tháng", "price_change": "Đổi bảng giá", "maintenance": "Bảo trì ô",
    "vehicle_link": "Khách liên kết xe", "vehicle_verify": "Xác minh xe", "request_submit": "Khách gửi yêu cầu",
    "request_resolve": "Xử lý yêu cầu", "backup": "Sao lưu", "export": "Xuất báo cáo",
}

AUTO_SLOT_LABEL = "Tự động (hệ thống chọn)"   # lựa chọn "chỗ bất kỳ": hệ thống tự gán ô trống
MIN_MAINTENANCE_REASON = 3                     # lý do bảo trì tối thiểu 3 ký tự


# --- Thời tiết (API Open-Meteo: https://open-meteo.com - miễn phí cho mục đích phi thương mại, giấy phép CC BY 4.0) ---
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_CACHE = DATA_DIR / "weather.json"      # dữ liệu API đã làm sạch, lưu JSON (dùng khi mất mạng)
WEATHER_TIMEOUT = 8                            # giây
WEATHER_REFRESH_MINUTES = 30                   # tự cập nhật; không gọi API quá thường xuyên (giới hạn 10.000 lượt/ngày)
WEATHER_TIMEZONE = "Asia/Bangkok"              # UTC+7 (giờ Việt Nam)
WEATHER_FORECAST_DAYS = 5
WEATHER_SOURCE = "Open-Meteo.com (CC BY 4.0)"
WEATHER_LOCATIONS = [                          # địa điểm có sẵn; có thể tìm thêm bằng tên trên giao diện
    {"name": "Vĩnh Yên, Phú Thọ", "lat": 21.3089, "lon": 105.6049},
    {"name": "Hà Nội", "lat": 21.0285, "lon": 105.8542},
    {"name": "TP. Hồ Chí Minh", "lat": 10.8231, "lon": 106.6297},
    {"name": "Đà Nẵng", "lat": 16.0544, "lon": 108.2022},
]
