"""Backend GIẢ cho tài khoản, phân quyền, nhật ký hoạt động và cổng khách hàng.

3 vai trò:
  - admin : quản trị (tạo/khóa tài khoản nhân viên, bảng giá, sao lưu, xem nhật ký, mọi chức năng)
  - staff : nhân viên ca trực (tài khoản do admin cấp; xe vào/ra, thu tiền, bán vé tháng, ca của chính mình)
  - user  : khách hàng (tự đăng ký; chỉ xem xe/vé/hóa đơn của mình, gửi yêu cầu gia hạn)
"""
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from config import (ROLE_ADMIN, ROLE_STAFF, ROLE_USER, STAFF_ROLES, VEHICLE_TYPES, MAX_LOGIN_ATTEMPTS,
                    LOCKOUT_MINUTES, PBKDF2_ITERATIONS, STATUS_OCCUPIED, STATUS_EMPTY, TICKET_PARKED)
from gui import validators
from gui.contracts import (ParkingError, AuthError, InvalidPlateError, PermissionDeniedError, ShiftNotOpenError)


                                                                                           
@dataclass
class User:
    username: str
    role: str
    full_name: str = ""
    must_change_password: bool = False


@dataclass
class AuditEntry:
    time: datetime
    actor: str
    role: str
    action: str
    detail: str


class MockAuditLog:
    """Giữ người đang thao tác (actor) và ghi nhật ký. Backend lấy actor từ đây."""

    def __init__(self):
        self._entries = []
        self.actor: Optional[User] = None
        self.enabled = True                                     

    def set_actor(self, user):
        self.actor = user

    @property
    def username(self):
        return self.actor.username if self.actor else ""

    def log(self, action, detail="", actor=None, role=None):
        if not self.enabled:
            return
        u = self.actor
        self._entries.append(AuditEntry(datetime.now(), actor or (u.username if u else "system"),
                                        role or (u.role if u else "system"), action, detail))

    def require(self, *roles):
        if not self.enabled:
            return
        if self.actor is None or self.actor.role not in roles:
            raise PermissionDeniedError("Bạn không có quyền thực hiện thao tác này.")

    def get_entries(self, filters=None):
        self.require(ROLE_ADMIN)
        f = filters or {}
        rows = []
        for e in self._entries:
            if f.get("actor") and f["actor"].lower() not in e.actor.lower():
                continue
            if f.get("action") and e.action != f["action"]:
                continue
            if f.get("date_from") and e.time.date() < f["date_from"]:
                continue
            if f.get("date_to") and e.time.date() > f["date_to"]:
                continue
            rows.append(e)
        return sorted(rows, key=lambda e: e.time, reverse=True)


                                                                            
@dataclass
class Account:
    username: str
    full_name: str
    phone: str
    role: str
    salt: str
    pw_hash: str
    active: bool = True
    failed: int = 0
    locked_until: Optional[datetime] = None
    must_change: bool = False
    created_at: datetime = None
    created_by: str = "system"
    last_login: Optional[datetime] = None


@dataclass
class AccountInfo:
    """Thông tin công khai của tài khoản (không có mật khẩu)."""
    username: str
    full_name: str
    phone: str
    role: str
    active: bool
    locked: bool
    must_change: bool
    created_at: datetime
    created_by: str
    last_login: Optional[datetime]

    @property
    def status_text(self):
        if not self.active:
            return "Đã khóa"
        return "Khóa tạm (sai MK)" if self.locked else "Hoạt động"


def _hash_pw(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
                               PBKDF2_ITERATIONS).hex()


class MockAuthService:
    def __init__(self, audit: MockAuditLog):
        self._audit = audit
        self._users = {}
        self._create("admin", "Quản trị viên", "", ROLE_ADMIN, "admin123", "system")

    def _create(self, username, full_name, phone, role, password, created_by, must_change=False):
        salt = os.urandom(16).hex()
        self._users[username] = Account(username, full_name, phone, role, salt, _hash_pw(password, salt),
                                        must_change=must_change, created_at=datetime.now(), created_by=created_by)

    @staticmethod
    def _info(a: Account) -> AccountInfo:
        locked = bool(a.locked_until and a.locked_until > datetime.now())
        return AccountInfo(a.username, a.full_name, a.phone, a.role, a.active, locked, a.must_change,
                           a.created_at, a.created_by, a.last_login)

                                
    def login(self, username, password) -> User:
        username = username.strip()
        acc = self._users.get(username)
        generic = "Sai tên đăng nhập hoặc mật khẩu."                                                          
        if acc is None:
            self._audit.log("login_failed", f"Tài khoản không tồn tại: {username[:30]}", actor=username or "?", role="-")
            raise AuthError(generic)
        now = datetime.now()
        if acc.locked_until and acc.locked_until > now:
            mins = int((acc.locked_until - now).total_seconds() // 60) + 1
            raise AuthError(f"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau {mins} phút "
                            "hoặc nhờ quản trị viên mở khóa.")
        if not hmac.compare_digest(acc.pw_hash, _hash_pw(password, acc.salt)):
            acc.failed += 1
            self._audit.log("login_failed", "Sai mật khẩu", actor=username, role=acc.role)
            if acc.failed >= MAX_LOGIN_ATTEMPTS:
                acc.failed, acc.locked_until = 0, now + timedelta(minutes=LOCKOUT_MINUTES)
                self._audit.log("lockout", f"Khóa {LOCKOUT_MINUTES} phút do sai {MAX_LOGIN_ATTEMPTS} lần",
                                actor=username, role=acc.role)
                raise AuthError(f"Sai mật khẩu {MAX_LOGIN_ATTEMPTS} lần - tài khoản bị khóa {LOCKOUT_MINUTES} phút.")
            raise AuthError(f"{generic} Còn {MAX_LOGIN_ATTEMPTS - acc.failed} lần thử.")
        if not acc.active:
            self._audit.log("login_failed", "Tài khoản đã bị khóa", actor=username, role=acc.role)
            raise AuthError("Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.")
        acc.failed, acc.locked_until, acc.last_login = 0, None, now
        user = User(acc.username, acc.role, acc.full_name, acc.must_change)
        self._audit.set_actor(user)
        self._audit.log("login")
        return user

    def logout(self):
        self._audit.log("logout")
        self._audit.set_actor(None)

    def get_profile(self, username) -> AccountInfo:
        a = self._users.get(username)
        if not a:
            raise AuthError("Không tìm thấy tài khoản.")
        return self._info(a)

                                                    
    def register(self, username, password, full_name, phone) -> User:
        username = username.strip()
        if not validators.is_valid_username(username):
            raise AuthError("Tên đăng nhập gồm 3-20 ký tự chữ, số hoặc dấu gạch dưới.")
        if not validators.is_valid_full_name(full_name):
            raise AuthError("Họ tên phải từ 2 đến 60 ký tự.")
        if not validators.is_valid_phone(phone):
            raise AuthError("Số điện thoại không hợp lệ (10 số, bắt đầu bằng 0 hoặc +84).")
        err = validators.password_error(password)
        if err:
            raise AuthError(err)
        if username in self._users:
            raise AuthError("Tên đăng nhập đã tồn tại.")
        self._create(username, full_name.strip(), phone.strip(), ROLE_USER, password, username)
        self._audit.log("register", f"Khách {username}", actor=username, role=ROLE_USER)
        return User(username, ROLE_USER, full_name.strip())

    def change_password(self, username, old_password, new_password):
        a = self._users.get(username)
        if not a or not hmac.compare_digest(a.pw_hash, _hash_pw(old_password, a.salt)):
            raise AuthError("Mật khẩu hiện tại không đúng.")
        err = validators.password_error(new_password)
        if err:
            raise AuthError(err)
        if new_password == old_password:
            raise AuthError("Mật khẩu mới phải khác mật khẩu cũ.")
        a.salt = os.urandom(16).hex()
        a.pw_hash, a.must_change = _hash_pw(new_password, a.salt), False
        self._audit.log("password_change", actor=username, role=a.role)

                                         
    def list_accounts(self, role=None, keyword=""):
        self._audit.require(ROLE_ADMIN)
        k = keyword.strip().lower()
        return [self._info(a) for a in sorted(self._users.values(), key=lambda a: (a.role, a.username))
                if (not role or a.role == role) and (not k or k in a.username.lower() or k in a.full_name.lower()
                                                     or k in a.phone)]

    def create_staff(self, username, full_name, phone, temp_password):
        self._audit.require(ROLE_ADMIN)
        username = username.strip()
        if not validators.is_valid_username(username):
            raise AuthError("Tên đăng nhập gồm 3-20 ký tự chữ, số hoặc dấu gạch dưới.")
        if username in self._users:
            raise AuthError("Tên đăng nhập đã tồn tại.")
        if not validators.is_valid_full_name(full_name):
            raise AuthError("Họ tên phải từ 2 đến 60 ký tự.")
        if not validators.is_valid_phone(phone):
            raise AuthError("Số điện thoại không hợp lệ.")
        err = validators.password_error(temp_password)
        if err:
            raise AuthError(err)
        self._create(username, full_name.strip(), phone.strip(), ROLE_STAFF, temp_password,
                     self._audit.username, must_change=True)                                                  
        self._audit.log("account_create", f"Tạo nhân viên {username} ({full_name.strip()})")
        return self._info(self._users[username])

    def set_active(self, username, active: bool):
        self._audit.require(ROLE_ADMIN)
        a = self._users.get(username)
        if not a:
            raise AuthError("Không tìm thấy tài khoản.")
        if username == self._audit.username:
            raise AuthError("Không thể tự khóa tài khoản của chính mình.")
        if not active and a.role == ROLE_ADMIN and sum(x.role == ROLE_ADMIN and x.active for x in self._users.values()) <= 1:
            raise AuthError("Không thể khóa quản trị viên cuối cùng.")
        a.active = active
        self._audit.log("account_lock", f"{'Mở khóa' if active else 'Khóa'} tài khoản {username}")

    def reset_password(self, username, temp_password):
        self._audit.require(ROLE_ADMIN)
        a = self._users.get(username)
        if not a:
            raise AuthError("Không tìm thấy tài khoản.")
        err = validators.password_error(temp_password)
        if err:
            raise AuthError(err)
        a.salt = os.urandom(16).hex()
        a.pw_hash, a.must_change, a.failed, a.locked_until = _hash_pw(temp_password, a.salt), True, 0, None
        self._audit.log("password_reset", f"Đặt lại mật khẩu cho {username}")

    def unlock_login(self, username):
        self._audit.require(ROLE_ADMIN)
        a = self._users.get(username)
        if not a:
            raise AuthError("Không tìm thấy tài khoản.")
        a.failed, a.locked_until = 0, None
        self._audit.log("account_lock", f"Mở khóa đăng nhập tạm cho {username}")


                                                                                  
class MockCustomerService:
    def __init__(self, auth, audit, manager, monthly, payments):
        self._auth, self._audit = auth, audit
        self._m, self._mo, self._pay = manager, monthly, payments
        self._vehicles = {}                                                         
        self._requests = []
        self._req_counter = 0

    def _me(self) -> str:
        self._audit.require(ROLE_USER)
        return self._audit.username

    def _all_monthly(self):
        """Truy cập nội bộ (không qua kiểm quyền nhân viên) để lọc theo xe của khách."""
        return sorted(self._mo._items.values(), key=lambda t: t.plate)

    def _mine(self, username, verified_only=True):
        return {p: v for p, v in self._vehicles.items()
                if v["username"] == username and (v["verified"] or not verified_only)}

                                                            
    def get_public_slots(self):
        from gui.mock_backend import ParkingSlot
        self._audit.require(ROLE_USER)
        return [ParkingSlot(s.slot_id, s.status) for s in self._m._slots.values()]

    def get_public_status(self) -> dict:
        self._audit.require(ROLE_USER)
        slots = list(self._m._slots.values())
        occ = sum(s.status == STATUS_OCCUPIED for s in slots)
        mnt = sum(s.status == "maintenance" for s in slots)
        total = len(slots)
        return {"total_slots": total, "empty": total - occ - mnt, "occupied": occ, "maintenance": mnt,
                "occupancy_rate": round(occ / total * 100, 1) if total else 0.0}

                     
    def link_vehicle(self, plate, vehicle_type):
        me = self._me()
        plate = validators.normalize_plate(plate)
        if not validators.is_valid_plate(plate):
            raise InvalidPlateError("Biển số không hợp lệ. Ví dụ: 59A1-123.45")
        if vehicle_type not in VEHICLE_TYPES:
            raise ParkingError("Loại xe không hợp lệ.")
        if plate in self._vehicles:
            who = "bạn" if self._vehicles[plate]["username"] == me else "một tài khoản khác"
            raise ParkingError(f"Biển số {plate} đã được liên kết với {who}.")
        phone = self._auth.get_profile(me).phone
        t = next((t for t in self._all_monthly() if t.plate == plate), None)
        verified = bool(t and t.phone == phone)                                                   
        self._vehicles[plate] = {"username": me, "vehicle_type": vehicle_type, "verified": verified}
        self._audit.log("vehicle_link", f"{plate} ({'đã xác minh' if verified else 'chờ xác minh'})")
        return verified

    def unlink_vehicle(self, plate):
        me = self._me()
        plate = validators.normalize_plate(plate)
        v = self._vehicles.get(plate)
        if not v or v["username"] != me:
            raise PermissionDeniedError("Bạn chỉ được gỡ xe của chính mình.")
        if any(r["plate"] == plate and r["status"] == "pending" for r in self._requests):
            raise ParkingError("Xe đang có yêu cầu vé tháng chờ xử lý, chưa thể gỡ.")
        del self._vehicles[plate]
        self._audit.log("vehicle_link", f"Gỡ xe {plate}")

    def get_my_vehicles(self):
        me = self._me()
        out = []
        for plate, v in sorted(self._mine(me, verified_only=False).items()):
            row = {"plate": plate, "vehicle_type": v["vehicle_type"], "verified": v["verified"], "parked": False,
                   "slot_id": "", "entry_time": None, "minutes": 0, "fee": 0, "monthly_end": None}
            if v["verified"]:
                tk = self._m._active_ticket(plate)
                if tk:
                    row.update(parked=True, slot_id=tk.slot_id, entry_time=tk.entry_time, minutes=tk.duration_minutes,
                               fee=self._m._calc_fee(tk.vehicle_type, tk.duration_minutes, tk.is_monthly))
                mt = next((t for t in self._all_monthly() if t.plate == plate), None)
                row["monthly_end"] = mt.end_date if mt else None
            out.append(row)
        return out

    def self_entry(self, plate, slot_id=None):
        """Khách TỰ cho xe của mình vào bãi: chọn ô trống (slot_id) hoặc để hệ thống tự gán (None).
        Điều kiện: xe đã liên kết + xác minh, đang có nhân viên trực ca (để thu phí khi ra), ô còn trống."""
        me = self._me()
        plate = validators.normalize_plate(plate)
        v = self._mine(me).get(plate)
        if not v:
            raise PermissionDeniedError("Chỉ xe đã liên kết và xác minh của bạn mới được tự vào bãi.")
        if not self._pay.current_shift():
            raise ShiftNotOpenError("Hiện chưa có nhân viên trực ca nên chưa thể tự vào bãi. Vui lòng liên hệ quầy.")
        return self._m._enter(plate, v["vehicle_type"], slot_id, by_customer=True)

    def get_my_monthly_tickets(self):
        me = self._me()
        plates = self._mine(me)
        return [t for t in self._all_monthly() if t.plate in plates]

    def get_my_history(self):
        me = self._me()
        plates = self._mine(me)
        return sorted((t for t in self._m.tickets if t.plate in plates), key=lambda t: t.entry_time, reverse=True)

    def get_my_payments(self):
        me = self._me()
        plates = self._mine(me)
        return sorted((p for p in self._pay._payments if p.plate in plates), key=lambda p: p.created_at, reverse=True)

    def get_my_receipt(self, payment_id) -> str:
        me = self._me()
        p = self._pay.get_payment(payment_id)
        if p.plate not in self._mine(me):
            raise PermissionDeniedError("Bạn chỉ được xem hóa đơn của xe thuộc tài khoản mình.")
        return self._pay._receipt_text(p)

                                                                                  
    def submit_monthly_request(self, plate, months):
        me = self._me()
        plate = validators.normalize_plate(plate)
        v = self._mine(me).get(plate)
        if not v:
            raise PermissionDeniedError("Chỉ được gửi yêu cầu cho xe đã liên kết và xác minh của bạn.")
        if months not in self._m.get_prices()["monthly_discount"]:
            raise ParkingError("Gói vé tháng không hợp lệ.")
        if any(r["plate"] == plate and r["status"] == "pending" for r in self._requests):
            raise ParkingError(f"Xe {plate} đã có yêu cầu đang chờ xử lý.")
        self._req_counter += 1
        prof = self._auth.get_profile(me)
        req = {"request_id": f"YC{self._req_counter:04d}", "username": me, "full_name": prof.full_name,
               "phone": prof.phone, "plate": plate, "vehicle_type": v["vehicle_type"], "months": months,
               "created_at": datetime.now(), "status": "pending", "note": ""}
        self._requests.append(req)
        self._audit.log("request_submit", f"{req['request_id']}: {plate} {months} tháng")
        return req

    def get_my_requests(self):
        me = self._me()
        return sorted((r for r in self._requests if r["username"] == me), key=lambda r: r["created_at"], reverse=True)

                                    
    def get_pending_vehicles(self):
        self._audit.require(*STAFF_ROLES)
        return [{"plate": p, **v} for p, v in self._vehicles.items() if not v["verified"]]

    def verify_vehicle(self, plate, approve: bool):
        self._audit.require(*STAFF_ROLES)
        v = self._vehicles.get(plate)
        if not v:
            raise ParkingError("Không tìm thấy xe.")
        if approve:
            v["verified"] = True
        else:
            del self._vehicles[plate]
        self._audit.log("vehicle_verify", f"{plate}: {'đồng ý' if approve else 'từ chối'}")

    def get_requests(self, status=None):
        self._audit.require(*STAFF_ROLES)
        return [r for r in sorted(self._requests, key=lambda r: r["created_at"], reverse=True)
                if not status or r["status"] == status]

    def resolve_request(self, request_id, status, note=""):
        self._audit.require(*STAFF_ROLES)
        if status not in ("done", "rejected"):
            raise ParkingError("Trạng thái không hợp lệ.")
        req = next((r for r in self._requests if r["request_id"] == request_id), None)
        if not req or req["status"] != "pending":
            raise ParkingError("Yêu cầu không tồn tại hoặc đã được xử lý.")
        if status == "rejected" and not note.strip():
            raise ParkingError("Vui lòng nhập lý do từ chối.")
        req["status"], req["note"] = status, note.strip()
        self._audit.log("request_resolve", f"{request_id}: {'hoàn tất' if status == 'done' else 'từ chối'}")
