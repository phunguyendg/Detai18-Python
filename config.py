"""Hằng số và cấu hình dùng chung cho toàn bộ ứng dụng (đường dẫn, màu, font...)."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"                                                
RECEIPT_DIR = DATA_DIR / "receipts"                             

APP_TITLE = "Quản lý bãi đỗ xe"
MIN_WINDOW_SIZE = (1100, 680)

                                                                
SLOT_ROWS = ("A", "B")
COLS_PER_ROW = 10

STATUS_EMPTY = "empty"
STATUS_OCCUPIED = "occupied"
STATUS_MAINTENANCE = "maintenance"

SLOT_COLORS = {
    STATUS_EMPTY: "#2E7D32",                                                      
    STATUS_OCCUPIED: "#D32F2F",                      
    STATUS_MAINTENANCE: "#607D8B",                      
}
STATUS_LABELS = {
    STATUS_EMPTY: "Trống",
    STATUS_OCCUPIED: "Có xe",
    STATUS_MAINTENANCE: "Bảo trì",
}

                                 
VEHICLE_TYPES = {"motorbike": "Xe máy", "car": "Ô tô"}
TICKET_PARKED = "parked"
TICKET_CLOSED = "closed"
TICKET_STATUS_LABELS = {TICKET_PARKED: "Đang đỗ", TICKET_CLOSED: "Đã ra"}

                 
ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"                                                                      
ROLE_USER = "user"                                         
ROLE_LABELS = {ROLE_ADMIN: "Quản trị viên", ROLE_STAFF: "Nhân viên ca trực", ROLE_USER: "Khách hàng"}
STAFF_ROLES = (ROLE_STAFF, ROLE_ADMIN)

                        
DATE_FMT = "%d/%m/%Y"
DATETIME_FMT = "%d/%m/%Y %H:%M"

                   
FONT_BASE = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_HEADER = ("Segoe UI", 15, "bold")
FONT_BIG = ("Segoe UI", 20, "bold")

                                                                                             
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

EXPIRING_DAYS = 7                                                    
MIN_PASSWORD_LEN = 8                                            
MAX_LOGIN_ATTEMPTS = 5                                       
LOCKOUT_MINUTES = 5
PBKDF2_ITERATIONS = 200_000                                                                     


                    
PAYMENT_METHODS = {
    "cash": "Tiền mặt",
    "bank_transfer": "Chuyển khoản / VietQR",
    "momo": "Ví MoMo",
    "zalopay": "Ví ZaloPay",
    "card": "Thẻ ngân hàng (máy POS)",
}
CASH_METHOD = "cash"
TXN_KINDS = {"parking": "Phí gửi xe", "monthly": "Vé tháng"}
QUICK_CASH = (50_000, 100_000, 200_000, 500_000)                            
DEFAULT_OPENING_CASH = 500_000                                            
PARKING_NAME = "BÃI ĐỖ XE"

                                                                                                    
                                                                            
# Thông tin tài khoản thụ hưởng thanh toán
BANK_INFO = {
    "bank_bin": "970422",                  # Mã BIN ngân hàng (970422 = MBBank)
    "bank_code": "MB",                     # Mã ngân hàng
    "bank_name": "MBBank (Ngân hàng Quân Đội)",
    "bank": "MBBank",                      # Tương thích ngược
    "account": "0987654321",               # Số tài khoản
    "holder": "BAI DO XE THONG MINH",      # Tên chủ tài khoản
}

DEFAULT_PRICES = {
    "hourly": {"motorbike": 3000, "car": 10000},
    "free_minutes": 15,
    "lost_ticket": {"motorbike": 50000, "car": 100000},
    "monthly": {"motorbike": 120000, "car": 1200000},
    "monthly_discount": {1: 0, 3: 5, 6: 10, 12: 15},
}

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

AUTO_SLOT_LABEL = "Tự động (hệ thống chọn)"
MIN_MAINTENANCE_REASON = 3

# Cấu hình API VietQR (Chuẩn Napas 247 / EMVCo)
VIETQR_API_URL = "https://api.vietqr.io/v2/generate"
VIETQR_BANKS_API_URL = "https://api.vietqr.io/v2/banks"
VIETQR_IMAGE_URL = "https://img.vietqr.io/image"
VIETQR_CACHE = DATA_DIR / "vietqr.json"
VIETQR_TIMEOUT = 8
VIETQR_TEMPLATE = "compact2"
VIETQR_SOURCE = "VietQR.io (Napas 247)"

# Các hằng số cũ thời tiết (giữ tương thích)
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_CACHE = DATA_DIR / "weather.json"
WEATHER_TIMEOUT = 8
WEATHER_REFRESH_MINUTES = 30
WEATHER_TIMEZONE = "Asia/Bangkok"
WEATHER_FORECAST_DAYS = 5
WEATHER_SOURCE = "Open-Meteo.com (CC BY 4.0)"
WEATHER_LOCATIONS = [
    {"name": "Vĩnh Yên, Phú Thọ", "lat": 21.3089, "lon": 105.6049},
    {"name": "Hà Nội", "lat": 21.0285, "lon": 105.8542},
    {"name": "TP. Hồ Chí Minh", "lat": 10.8231, "lon": 106.6297},
    {"name": "Đà Nẵng", "lat": 16.0544, "lon": 108.2022},
]
