"""Kiểm tra dữ liệu nhập bằng Regular Expression (GUI kiểm tra nhanh; backend kiểm tra chính thức)."""
import re

from config import MIN_PASSWORD_LEN

                                                      
PLATE_RE = re.compile(r"^\d{2}-?[A-Z][A-Z0-9]?[- ]?\d{3,4}\.?\d{0,2}$")
                                      
PHONE_RE = re.compile(r"^(0|\+84)\d{9}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
                                                                                
REFERENCE_RE = re.compile(r"^[A-Za-z0-9\-]{6,24}$")
_MONEY_RE = re.compile(r"^\d{1,3}([.,]\d{3})*$|^\d+$")


def normalize_plate(text: str) -> str:
    return text.strip().upper()


def is_valid_plate(text: str) -> bool:
    return bool(PLATE_RE.match(normalize_plate(text)))


def is_valid_phone(text: str) -> bool:
    return bool(PHONE_RE.match(text.strip()))


def is_valid_username(text: str) -> bool:
    return bool(USERNAME_RE.match(text.strip()))


def password_error(password: str):
    """Mật khẩu >= 8 ký tự và có cả chữ lẫn số. Trả về thông báo lỗi hoặc None."""
    if len(password) < MIN_PASSWORD_LEN:
        return f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LEN} ký tự."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Mật khẩu phải gồm cả chữ cái và chữ số."
    return None


def is_valid_full_name(text: str) -> bool:
    return 2 <= len(text.strip()) <= 60


def is_valid_reference(text: str) -> bool:
    return bool(REFERENCE_RE.match(text.strip()))


def parse_money(text: str) -> int:
    """'1.200.000' / '1,200,000' / '50000' -> int. Sai định dạng -> ValueError."""
    t = text.strip().replace(" ", "")
    if not t or not _MONEY_RE.match(t):
        raise ValueError("Số tiền không hợp lệ (chỉ nhập chữ số, ví dụ 100000 hoặc 100.000).")
    return int(t.replace(".", "").replace(",", ""))
