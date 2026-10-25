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
    def __init__(self, audit=None):
        self._accounts = {}
        self._current_user = None
        self.audit = audit
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
        if not acc or acc.password != password:
            if hasattr(self, 'audit') and self.audit:
                self.audit.log("login_failed", f"Đăng nhập sai cho tài khoản {username}", actor=username, role=acc.role if acc else "-")
            raise AuthError("Sai tên đăng nhập hoặc mật khẩu.")
        if not acc.active:
            if hasattr(self, 'audit') and self.audit:
                self.audit.log("login_failed", f"Tài khoản {username} đã bị khóa", actor=username, role=acc.role)
            raise AuthError("Tài khoản đã bị khóa.")
        self._current_user = acc
        if hasattr(self, 'audit') and self.audit:
            self.audit.set_actor(acc)
            self.audit.log("login", f"Đăng nhập thành công", actor=username, role=acc.role)
        return acc

    def logout(self):
        if hasattr(self, 'audit') and self.audit and self._current_user:
            self.audit.log("logout", f"Đăng xuất khỏi hệ thống", actor=self._current_user.username, role=self._current_user.role)
        self._current_user = None
    
    def register(self, username, password, full_name, phone):
        if username in self._accounts: raise AuthError("Tên đăng nhập đã tồn tại.")
        if len(password) < MIN_PASSWORD_LEN: raise AuthError("Mật khẩu quá ngắn.")
        self._accounts[username] = Account(username, password, full_name, phone, ROLE_USER)
        self.save()
        if hasattr(self, 'audit') and self.audit:
            self.audit.log("register", f"Khách đăng ký: {username} ({full_name})", actor=username, role=ROLE_USER)

    def change_password(self, username, old, new):
        acc = self._accounts.get(username)
        if not acc or acc.password != old: raise AuthError("Mật khẩu cũ không đúng.")
        acc.password = new
        self.save()
        if hasattr(self, 'audit') and self.audit:
            self.audit.log("password_change", f"Đổi mật khẩu cho tài khoản {username}", actor=username, role=acc.role)

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
        if hasattr(self, 'audit') and self.audit:
            actor = self._current_user.username if self._current_user else "admin"
            role = self._current_user.role if self._current_user else ROLE_ADMIN
            self.audit.log("account_create", f"Tạo nhân viên {username} ({full_name})", actor=actor, role=role)
        return acc

    def set_active(self, username, active):
        if username in self._accounts:
            self._accounts[username].active = active
            self.save()
            if hasattr(self, 'audit') and self.audit:
                actor = self._current_user.username if self._current_user else "admin"
                role = self._current_user.role if self._current_user else ROLE_ADMIN
                self.audit.log("account_lock", f"{'Mở khóa' if active else 'Khóa'} tài khoản {username}", actor=actor, role=role)

    def reset_password(self, username, new_pass):
        if username in self._accounts:
            self._accounts[username].password = new_pass
            self._accounts[username].must_change_password = True
            self.save()
            if hasattr(self, 'audit') and self.audit:
                actor = self._current_user.username if self._current_user else "admin"
                role = self._current_user.role if self._current_user else ROLE_ADMIN
                self.audit.log("password_reset", f"Đặt lại mật khẩu cho {username}", actor=actor, role=role)

    def unlock_login(self, username):
        if username not in self._accounts:
            raise AuthError("Không tìm thấy tài khoản.")
        return True