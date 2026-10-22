"""Quản lý đăng nhập, phân quyền, tài khoản."""
import json
from dataclasses import dataclass
from backend.exceptions import AuthError
from config import DATA_DIR, ROLE_ADMIN, ROLE_STAFF, ROLE_USER, MIN_PASSWORD_LEN

@dataclass
class Account:
    username: str
    password: str
    full_name: str
    phone: str
    role: str
    active: bool = True
    must_change_password: bool = False

    @property
    def must_change(self): 
        return self.must_change_password
    @property
    def status_text(self): return "Hoạt động" if self.active else "Đã khóa"
    @property
    def locked(self): return False
    @property
    def last_login(self): return None
    @property
    def created_by(self): return "Hệ thống"

class AuthService:
    FILE = DATA_DIR / "accounts.json"
    def __init__(self):
        self._accounts = {}
        self._current_user = None
        self.load()

    
    def load(self):
        if not self.FILE.exists():
            self._accounts = {
                "admin": Account("admin", "admin123", "Quản trị viên", "0900000000", ROLE_ADMIN),
                "staff": Account("staff", "staff123", "Nhân viên", "0900000001", ROLE_STAFF),
                "khach01": Account("khach01", "khach123", "Khách hàng", "0900000002", ROLE_USER),
            }
            self.save()
            return

        try:
            raw = json.loads(self.FILE.read_text(encoding="utf-8"))

            if isinstance(raw, list):
                self._accounts = {
                    item["username"]: Account(**item)
                    for item in raw
                }
            elif isinstance(raw, dict):
                self._accounts = {
                    username: Account(**data)
                    for username, data in raw.items()
                }
            else:
                raise ValueError("Định dạng accounts.json không hợp lệ.")

            if "admin" not in self._accounts:
                self._accounts["admin"] = Account(
                    "admin", "admin123", "Quản trị viên",
                    "0900000000", ROLE_ADMIN
                )
                self.save()

        except (ValueError, TypeError, KeyError) as e:
            raise RuntimeError(
                f"Không thể đọc tài khoản trong {self.FILE}: {e}"
            ) from e


    def save(self):
        self.FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.__dict__ for k, v in self._accounts.items()}
        self.FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def login(self, username, password):
        acc = self._accounts.get(username)
        if not acc or acc.password != password: raise AuthError("Sai tên đăng nhập hoặc mật khẩu.")
        if not acc.active: raise AuthError("Tài khoản đã bị khóa.")
        self._current_user = acc
        return acc

    def logout(self): self._current_user = None
    
    def register(self, username, password, full_name, phone):
        if username in self._accounts: raise AuthError("Tên đăng nhập đã tồn tại.")
        if len(password) < MIN_PASSWORD_LEN: raise AuthError("Mật khẩu quá ngắn.")
        self._accounts[username] = Account(username, password, full_name, phone, ROLE_USER)
        self.save()

    def change_password(self, username, old, new):
        acc = self._accounts.get(username)
        if not acc or acc.password != old: raise AuthError("Mật khẩu cũ không đúng.")
        acc.password = new
        self.save()

    def list_accounts(self, role=None, keyword=""):
        res = list(self._accounts.values())
        if role: res = [a for a in res if a.role == role]
        if keyword: res = [a for a in res if keyword.lower() in a.username.lower() or keyword.lower() in a.full_name.lower()]
        return res

    def create_staff(self, username, full_name, phone, password):
        if username in self._accounts: raise AuthError("Tên đăng nhập đã tồn tại.")
        acc = Account(username, password, full_name, phone, ROLE_STAFF, must_change_password=True)
        self._accounts[username] = acc
        self.save()
        return acc

    def set_active(self, username, active):
        if username in self._accounts:
            self._accounts[username].active = active
            self.save()

    def reset_password(self, username, new_pass):
        if username in self._accounts:
            self._accounts[username].password = new_pass
            self._accounts[username].must_change_password = True
            self.save()

    def unlock_login(self, username):
        if username not in self._accounts:
            raise AuthError("Không tìm thấy tài khoản.")
        return True