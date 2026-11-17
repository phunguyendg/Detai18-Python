"""Quản lý đăng nhập, phân quyền và tài khoản người dùng."""
import json
from dataclasses import dataclass

from backend.exceptions import AuthError
from config import DATA_DIR, ROLE_ADMIN, ROLE_STAFF, ROLE_USER
from gui import validators


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
    def status_text(self):
        return "Hoạt động" if self.active else "Đã khóa"

    @property
    def locked(self):
        return False

    @property
    def last_login(self):
        return None

    @property
    def created_by(self):
        return "Hệ thống"


class AuthService:
    FILE = DATA_DIR / "accounts.json"

    def __init__(self, audit=None):
        self._accounts = {}
        self._current_user = None
        self.audit = audit
        self.load()

    def _log(self, action, detail="", actor=None, role=None):
        """Ghi nhật ký hoạt động nếu AuditService đã được gắn."""
        if self.audit:
            self.audit.log(action, detail, actor=actor, role=role)

    def _validate_account_fields(self, username, full_name, phone, password):
        """Kiểm tra toàn bộ thông tin đầu vào khi tạo hoặc đăng ký tài khoản."""
        username = (username or "").strip()
        full_name = validators.normalize_full_name(full_name)
        phone_clean = validators.normalize_phone(phone)
        pw = password or ""

        if not username:
            raise AuthError("Vui lòng nhập tên đăng nhập.")
        if not validators.is_valid_username(username):
            raise AuthError("Tên đăng nhập 3-20 ký tự, bắt đầu bằng chữ cái (chỉ gồm chữ, số, '_').")
        if not validators.is_valid_full_name(full_name):
            raise AuthError("Họ tên từ 2-60 ký tự, chỉ gồm chữ cái và khoảng trắng.")
        if not validators.is_valid_phone(phone_clean):
            raise AuthError("Số điện thoại không hợp lệ (10 chữ số, đầu số 03/05/07/08/09 hoặc +84).")

        pw_err = validators.password_error(pw)
        if pw_err:
            raise AuthError(pw_err)

        return username, full_name, phone_clean, pw

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
                self._accounts = {item["username"]: Account(**item) for item in raw}
            elif isinstance(raw, dict):
                self._accounts = {username: Account(**data) for username, data in raw.items()}
            else:
                raise ValueError("Định dạng accounts.json không hợp lệ.")

            if "admin" not in self._accounts:
                self._accounts["admin"] = Account(
                    "admin", "admin123", "Quản trị viên", "0900000000", ROLE_ADMIN
                )
                self.save()
        except (ValueError, TypeError, KeyError) as e:
            raise RuntimeError(f"Không thể đọc tài khoản trong {self.FILE}: {e}") from e

    def save(self):
        self.FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.__dict__ for k, v in self._accounts.items()}
        self.FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def login(self, username, password):
        username = (username or "").strip()
        password = password or ""

        if not username or not password:
            raise AuthError("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")

        acc = self._accounts.get(username)
        if not acc or acc.password != password:
            self._log("login_failed", f"Đăng nhập sai cho tài khoản {username}",
                      actor=username, role=acc.role if acc else "-")
            raise AuthError("Sai tên đăng nhập hoặc mật khẩu.")

        if not acc.active:
            self._log("login_failed", f"Tài khoản {username} đã bị khóa",
                      actor=username, role=acc.role)
            raise AuthError("Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.")

        self._current_user = acc
        if self.audit:
            self.audit.set_actor(acc)
        self._log("login", "Đăng nhập thành công", actor=username, role=acc.role)
        return acc

    def logout(self):
        if self._current_user:
            self._log("logout", "Đăng xuất khỏi hệ thống",
                      actor=self._current_user.username, role=self._current_user.role)
        self._current_user = None
        if self.audit:
            self.audit.set_actor(None)

    def register(self, username, password, full_name, phone):
        username, full_name, phone_clean, pw = self._validate_account_fields(
            username, full_name, phone, password
        )
        if username in self._accounts:
            raise AuthError("Tên đăng nhập đã tồn tại.")

        self._accounts[username] = Account(username, pw, full_name, phone_clean, ROLE_USER)
        self.save()
        self._log("register", f"Khách đăng ký: {username} ({full_name})",
                  actor=username, role=ROLE_USER)

    def change_password(self, username, old, new):
        username = (username or "").strip()
        old = old or ""
        new = new or ""

        if not old or not new:
            raise AuthError("Vui lòng nhập đầy đủ mật khẩu hiện tại và mật khẩu mới.")

        acc = self._accounts.get(username)
        if not acc or acc.password != old:
            raise AuthError("Mật khẩu hiện tại không đúng.")

        pw_err = validators.password_error(new)
        if pw_err:
            raise AuthError(pw_err)
        if new == old:
            raise AuthError("Mật khẩu mới phải khác mật khẩu hiện tại.")

        acc.password = new
        acc.must_change_password = False
        self.save()
        self._log("password_change", f"Đổi mật khẩu cho tài khoản {username}",
                  actor=username, role=acc.role)

    def list_accounts(self, role=None, keyword=""):
        kw = (keyword or "").strip().lower()
        res = list(self._accounts.values())
        if role:
            res = [a for a in res if a.role == role]
        if kw:
            res = [a for a in res if kw in a.username.lower()
                   or kw in a.full_name.lower() or kw in a.phone]
        return res

    def create_staff(self, username, full_name, phone, password):
        username, full_name, phone_clean, pw = self._validate_account_fields(
            username, full_name, phone, password
        )
        if username in self._accounts:
            raise AuthError("Tên đăng nhập đã tồn tại.")

        acc = Account(username, pw, full_name, phone_clean, ROLE_STAFF, must_change_password=True)
        self._accounts[username] = acc
        self.save()

        actor = self._current_user.username if self._current_user else "admin"
        role = self._current_user.role if self._current_user else ROLE_ADMIN
        self._log("account_create", f"Tạo nhân viên {username} ({full_name})",
                  actor=actor, role=role)
        return acc

    def set_active(self, username, active):
        username = (username or "").strip()
        acc = self._accounts.get(username)
        if not acc:
            raise AuthError("Không tìm thấy tài khoản.")
        if not active and self._current_user and username == self._current_user.username:
            raise AuthError("Không thể tự khóa tài khoản của chính mình.")
        if not active and acc.role == ROLE_ADMIN:
            active_admins = sum(1 for a in self._accounts.values() if a.role == ROLE_ADMIN and a.active)
            if active_admins <= 1:
                raise AuthError("Không thể khóa quản trị viên cuối cùng.")

        acc.active = active
        self.save()

        actor = self._current_user.username if self._current_user else "admin"
        role = self._current_user.role if self._current_user else ROLE_ADMIN
        self._log("account_lock", f"{'Mở khóa' if active else 'Khóa'} tài khoản {username}",
                  actor=actor, role=role)

    def reset_password(self, username, new_pass):
        username = (username or "").strip()
        acc = self._accounts.get(username)
        if not acc:
            raise AuthError("Không tìm thấy tài khoản.")

        pw_err = validators.password_error(new_pass)
        if pw_err:
            raise AuthError(pw_err)

        acc.password = new_pass
        acc.must_change_password = True
        self.save()

        actor = self._current_user.username if self._current_user else "admin"
        role = self._current_user.role if self._current_user else ROLE_ADMIN
        self._log("password_reset", f"Đặt lại mật khẩu cho {username}",
                  actor=actor, role=role)

    def unlock_login(self, username):
        username = (username or "").strip()
        if not username or username not in self._accounts:
            raise AuthError("Không tìm thấy tài khoản.")
        return True
