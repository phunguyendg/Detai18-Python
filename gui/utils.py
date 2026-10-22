"""Hàm tiện ích định dạng / phân tích dữ liệu hiển thị trên GUI."""
import re
import secrets
import string
from datetime import datetime

from config import DATE_FMT, DATETIME_FMT

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def format_money(value) -> str:
    """12500 -> '12.500 đ'."""
    try:
        return f"{int(value or 0):,}".replace(",", ".") + " đ"
    except Exception:
        return "0 đ"


def format_duration(minutes) -> str:
    if minutes is None:
        return "0 phút"
    try:
        hours, mins = divmod(int(minutes), 60)
        return f"{hours} giờ {mins:02d} phút" if hours else f"{mins} phút"
    except Exception:
        return "—"


def format_dt(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            from datetime import datetime
            value = datetime.fromisoformat(value)
        except Exception:
            return value
    return value.strftime(DATETIME_FMT) if hasattr(value, "strftime") else str(value)


def format_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            from datetime import datetime
            value = datetime.fromisoformat(value).date()
        except Exception:
            return value
    return value.strftime(DATE_FMT) if hasattr(value, "strftime") else str(value)


def parse_date(text: str, field: str = "Ngày"):
    """Chuỗi dd/mm/yyyy -> date. Chuỗi rỗng -> None. Sai định dạng -> ValueError (có thông báo tiếng Việt)."""
    text = text.strip()
    if not text:
        return None
    if not _DATE_RE.match(text):
        raise ValueError(f"{field} phải có dạng dd/mm/yyyy (ví dụ 25/12/2026).")
    try:
        return datetime.strptime(text, DATE_FMT).date()
    except ValueError:
        raise ValueError(f"{field} không tồn tại trong lịch: {text}.") from None


def gen_temp_password(length: int = 10) -> str:
    """Mật khẩu tạm ngẫu nhiên (có cả chữ và số), dùng cho tài khoản nhân viên mới / đặt lại."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw):
            return pw
