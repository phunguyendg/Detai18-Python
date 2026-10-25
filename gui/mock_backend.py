"""BACKEND GIẢ để phát triển và chạy thử GUI.

Có CÙNG tên hàm / tham số / giá trị trả về với hợp đồng giao tiếp (xem CONTRACT.md).
"""
import calendar
import copy
import csv
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from typing import Optional

from config import (SLOT_ROWS, COLS_PER_ROW, STATUS_EMPTY, STATUS_OCCUPIED, STATUS_MAINTENANCE,
                    TICKET_PARKED, TICKET_CLOSED, VEHICLE_TYPES,
                    PAYMENT_METHODS, CASH_METHOD, TXN_KINDS, DEFAULT_PRICES, PARKING_NAME, MIN_MAINTENANCE_REASON,
                    ROLE_ADMIN, STAFF_ROLES)
from gui.contracts import (ParkingError, InvalidPlateError, NoSlotAvailableError,
                           VehicleAlreadyParkedError, TicketNotFoundError, DuplicateMonthlyTicketError,
                           ShiftNotOpenError, PaymentError, PermissionDeniedError)
from gui import validators
from gui.utils import format_money
from gui.mock_accounts import MockAuditLog, MockAuthService, MockCustomerService


                                                                          
@dataclass
class ParkingSlot:
    slot_id: str
    status: str = STATUS_EMPTY
    current_plate: str = ""
    entry_time: Optional[datetime] = None
    ticket_id: str = ""
    note: str = ""                                    


@dataclass
class ParkingTicket:
    ticket_id: str
    plate: str
    vehicle_type: str
    slot_id: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    fee: int = 0
    status: str = TICKET_PARKED
    is_monthly: bool = False
    lost_ticket: bool = False
    payment_id: str = ""

    @property
    def duration_minutes(self) -> int:
        end = self.exit_time or datetime.now()
        return max(1, int((end - self.entry_time).total_seconds() // 60))


@dataclass
class MonthlyTicket:
    plate: str
    owner: str
    phone: str
    vehicle_type: str
    start_date: date
    end_date: date


@dataclass
class Payment:
    payment_id: str
    kind: str                                        
    plate: str
    ref: str                                                    
    description: str
    amount: int
    method: str
    reference_code: str                                                          
    received: int                                                                
    change: int                          
    created_at: datetime
    cashier: str
    shift_id: str


@dataclass
class Shift:
    shift_id: str
    cashier: str
    opened_at: datetime
    opening_cash: int
    closed_at: Optional[datetime] = None
    counted_cash: Optional[int] = None
    expected_cash: Optional[int] = None
    difference: Optional[int] = None
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


                                                                           
class MockPriceTable:
    def __init__(self, audit):
        self._audit = audit
        self._p = copy.deepcopy(DEFAULT_PRICES)

    def get_prices(self) -> dict:
        return copy.deepcopy(self._p)

    def set_prices(self, prices: dict):
        self._audit.require(ROLE_ADMIN)
        for vt in VEHICLE_TYPES:
            for group in ("hourly", "lost_ticket", "monthly"):
                v = prices.get(group, {}).get(vt)
                if not isinstance(v, int) or v < 0:
                    raise ParkingError("Giá phải là số nguyên không âm.")
        if not isinstance(prices.get("free_minutes"), int) or not 0 <= prices["free_minutes"] <= 120:
            raise ParkingError("Số phút miễn phí phải từ 0 đến 120.")
        disc = prices.get("monthly_discount", {})
        if 1 not in disc or any(not isinstance(v, int) or not 0 <= v <= 50 for v in disc.values()):
            raise ParkingError("Phần trăm giảm giá vé tháng phải từ 0 đến 50.")
        self._p = copy.deepcopy(prices)
        self._audit.log("price_change", "Cập nhật bảng giá")


                                                                                       
class MockPaymentService:
    def __init__(self, audit):
        self._audit = audit
        self._payments = []
        self._shifts = []
        self._counter = 0
        self._shift_counter = 0

                      
    def get_payment_methods(self):
        return list(PAYMENT_METHODS.items())

                  
    def current_shift(self) -> Optional[Shift]:
        return next((s for s in self._shifts if s.is_open), None)

    def _visible(self, p) -> bool:
        """Admin thấy tất cả; nhân viên chỉ thấy giao dịch do chính mình thu."""
        if not self._audit.enabled:
            return True
        u = self._audit.actor
        return bool(u and (u.role == ROLE_ADMIN or p.cashier == u.username))

    def get_shifts(self):
        self._audit.require(*STAFF_ROLES)
        u = self._audit.actor
        rows = [x for x in self._shifts if (not u or u.role == ROLE_ADMIN or x.cashier == u.username)]
        return sorted(rows, key=lambda x: x.opened_at, reverse=True)

    def open_shift(self, cashier: str, opening_cash: int) -> Shift:
        self._audit.require(*STAFF_ROLES)
        cur = self.current_shift()
        if cur:
            raise PaymentError(f"Ca {cur.shift_id} của {cur.cashier} đang mở. Cần chốt ca đó trước khi mở ca mới.")
        if cashier.strip() != self._audit.username:
            raise PermissionDeniedError("Chỉ được mở ca đứng tên chính tài khoản đang đăng nhập.")
        if opening_cash < 0:
            raise PaymentError("Tiền đầu ca không được âm.")
        self._shift_counter += 1
        sh = Shift(f"CA-{datetime.now():%y%m%d}-{self._shift_counter:02d}", cashier.strip(),
                   datetime.now(), int(opening_cash))
        self._shifts.append(sh)
        self._audit.log("shift_open", f"{sh.shift_id}, tiền đầu ca {format_money(sh.opening_cash)}")
        return sh

    def shift_summary(self, shift_id: str) -> dict:
        pays = [p for p in self._payments if p.shift_id == shift_id]
        by_method = {k: 0 for k in PAYMENT_METHODS}
        for p in pays:
            by_method[p.method] += p.amount
        return {"count": len(pays), "total": sum(by_method.values()),
                "cash": by_method[CASH_METHOD], "by_method": by_method}

    def close_shift(self, counted_cash: int, note: str = "") -> Shift:
        self._audit.require(*STAFF_ROLES)
        sh = self.current_shift()
        if not sh:
            raise ShiftNotOpenError("Không có ca trực nào đang mở.")
        by_admin = self._audit.actor and self._audit.actor.role == ROLE_ADMIN and sh.cashier != self._audit.username
        if sh.cashier != self._audit.username and not by_admin:
            raise PermissionDeniedError(f"Ca này thuộc về {sh.cashier}, bạn không được chốt thay.")
        if counted_cash < 0:
            raise PaymentError("Số tiền kiểm đếm không được âm.")
        expected = sh.opening_cash + self.shift_summary(sh.shift_id)["cash"]
        diff = int(counted_cash) - expected
        if diff != 0 and not note.strip():
            raise PaymentError("Tiền kiểm đếm lệch so với hệ thống - vui lòng nhập ghi chú giải trình.")
        sh.closed_at, sh.counted_cash = datetime.now(), int(counted_cash)
        sh.expected_cash, sh.difference, sh.note = expected, diff, note.strip()
        if by_admin:
            sh.note = (sh.note + " " if sh.note else "") + f"[Quản trị {self._audit.username} chốt thay]"
        self._audit.log("shift_close", f"{sh.shift_id}: lệch {format_money(abs(diff))}" + ("" if diff == 0 else
                        (" (thừa)" if diff > 0 else " (thiếu)")))
        return sh

                   
    def collect(self, kind, plate, ref, description, amount, method, received=None, reference=None) -> Payment:
        self._audit.require(*STAFF_ROLES)
        sh = self.current_shift()
        if not sh:
            raise ShiftNotOpenError("Chưa mở ca trực - hãy mở ca trước khi thu tiền.")
        if sh.cashier != self._audit.username:
            raise PaymentError(f"Ca {sh.shift_id} đang mở bởi {sh.cashier}. Mỗi ca chỉ thu bởi thu ngân của ca đó - "
                               "hãy nhờ họ chốt ca hoặc nhờ quản trị chốt thay.")
        if kind not in TXN_KINDS:
            raise PaymentError("Loại giao dịch không hợp lệ.")
        if method not in PAYMENT_METHODS:
            raise PaymentError("Phương thức thanh toán không hợp lệ.")
        if amount <= 0:
            raise PaymentError("Số tiền thanh toán phải lớn hơn 0.")
        ref_code = (reference or "").strip()
        if method == CASH_METHOD:
            if received is None or received < amount:
                short = amount - (received or 0)
                raise PaymentError(f"Khách đưa chưa đủ tiền, còn thiếu {format_money(short)}.")
            change = received - amount
            ref_code = ""
        else:
            if not validators.is_valid_reference(ref_code):
                raise PaymentError("Mã giao dịch không hợp lệ (6-24 ký tự gồm chữ, số hoặc dấu gạch ngang).")
            if any(p.reference_code.upper() == ref_code.upper() and p.method == method for p in self._payments):
                raise PaymentError("Mã giao dịch này đã được dùng cho một giao dịch khác.")
            received, change = amount, 0
        pay = self._add(kind, plate, ref, description, amount, method, ref_code, received, change,
                        datetime.now(), sh.cashier, sh.shift_id)
        self._audit.log("payment", f"{pay.payment_id}: {format_money(amount)} ({PAYMENT_METHODS[method]}) - {plate}")
        return pay

    def _add(self, kind, plate, ref, description, amount, method, ref_code, received, change,
             created_at, cashier, shift_id) -> Payment:
        self._counter += 1
        pay = Payment(f"TT{created_at:%y%m%d}-{self._counter:04d}", kind, plate, ref, description, int(amount),
                      method, ref_code, int(received), int(change), created_at, cashier, shift_id)
        self._payments.append(pay)
        return pay

                  
    def get_payment(self, payment_id) -> Payment:
        for p in self._payments:
            if p.payment_id == payment_id:
                return p
        raise PaymentError(f"Không tìm thấy giao dịch {payment_id}.")

    def get_transactions(self, filters=None):
        self._audit.require(*STAFF_ROLES)
        f = filters or {}
        rows = []
        for p in self._payments:
            if not self._visible(p):
                continue
            if f.get("kind") and p.kind != f["kind"]:
                continue
            if f.get("method") and p.method != f["method"]:
                continue
            if f.get("plate") and f["plate"].upper() not in p.plate.upper():
                continue
            if f.get("date_from") and p.created_at.date() < f["date_from"]:
                continue
            if f.get("date_to") and p.created_at.date() > f["date_to"]:
                continue
            rows.append(p)
        return sorted(rows, key=lambda p: p.created_at, reverse=True)

    def revenue_by_method(self, day: Optional[date] = None) -> dict:
        out = {k: 0 for k in PAYMENT_METHODS}
        for p in self._payments:
            if self._visible(p) and (day is None or p.created_at.date() == day):
                out[p.method] += p.amount
        return out

    def revenue_by_kind(self, day: Optional[date] = None) -> dict:
        out = {k: 0 for k in TXN_KINDS}
        for p in self._payments:
            if self._visible(p) and (day is None or p.created_at.date() == day):
                out[p.kind] += p.amount
        return out

    def build_receipt(self, payment_id) -> str:
        self._audit.require(*STAFF_ROLES)
        p = self.get_payment(payment_id)
        if not self._visible(p):
            raise PermissionDeniedError("Giao dịch này do thu ngân khác thực hiện.")
        return self._receipt_text(p)

    def _receipt_text(self, p) -> str:
        w = 40
        line = "=" * w
        rows = [line, PARKING_NAME.center(w), "HÓA ĐƠN THANH TOÁN".center(w), line,
                f"Mã giao dịch : {p.payment_id}",
                f"Thời gian    : {p.created_at:%d/%m/%Y %H:%M:%S}",
                f"Thu ngân     : {p.cashier}  ({p.shift_id})",
                f"Loại         : {TXN_KINDS[p.kind]}",
                f"Biển số      : {p.plate}",
                f"Nội dung     : {p.description}",
                "-" * w,
                f"THÀNH TIỀN   : {format_money(p.amount)}",
                f"Hình thức    : {PAYMENT_METHODS[p.method]}"]
        if p.method == CASH_METHOD:
            rows += [f"Khách đưa    : {format_money(p.received)}", f"Tiền thối    : {format_money(p.change)}"]
        else:
            rows.append(f"Mã tham chiếu: {p.reference_code}")
        rows += [line, "Cảm ơn quý khách!".center(w), line]
        return "\n".join(rows)



                                                                           
class MockMonthlyService:
    def __init__(self, prices: MockPriceTable, payments: MockPaymentService, audit):
        self._prices, self._payments, self._audit = prices, payments, audit
        self._items = {}

    def _validate(self, plate, owner, phone, vehicle_type, start, end):
        if not validators.is_valid_plate(plate):
            raise InvalidPlateError("Biển số không hợp lệ.")
        if not owner.strip():
            raise ParkingError("Tên chủ xe không được để trống.")
        if not validators.is_valid_phone(phone):
            raise ParkingError("Số điện thoại không hợp lệ.")
        if vehicle_type not in VEHICLE_TYPES:
            raise ParkingError("Loại xe không hợp lệ.")
        if end < start:
            raise ParkingError("Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.")

                          
    def add_monthly_ticket(self, plate, owner, phone, vehicle_type, start, end):
        self._audit.require(ROLE_ADMIN)
        plate = validators.normalize_plate(plate)
        self._validate(plate, owner, phone, vehicle_type, start, end)
        if plate in self._items:
            raise DuplicateMonthlyTicketError(f"Xe {plate} đã có vé tháng.")
        self._items[plate] = MonthlyTicket(plate, owner.strip(), phone.strip(), vehicle_type, start, end)
        self._audit.log("monthly_manage", f"Thêm vé tháng {plate}")
        return self._items[plate]

    def update_monthly_ticket(self, plate, **fields):
        self._audit.require(ROLE_ADMIN)
        plate = validators.normalize_plate(plate)
        if plate not in self._items:
            raise ParkingError(f"Không tìm thấy vé tháng của xe {plate}.")
        t = self._items[plate]
        new = {"owner": t.owner, "phone": t.phone, "vehicle_type": t.vehicle_type,
               "start_date": t.start_date, "end_date": t.end_date}
        new.update(fields)
        self._validate(plate, new["owner"], new["phone"], new["vehicle_type"],
                       new["start_date"], new["end_date"])
        for k, v in new.items():
            setattr(t, k, v)
        self._audit.log("monthly_manage", f"Sửa vé tháng {plate}")
        return t

    def remove_monthly_ticket(self, plate) -> bool:
        self._audit.require(ROLE_ADMIN)
        plate = validators.normalize_plate(plate)
        ok = self._items.pop(plate, None) is not None
        if ok:
            self._audit.log("monthly_manage", f"Xóa vé tháng {plate}")
        return ok

    def get_all_monthly_tickets(self):
        self._audit.require(*STAFF_ROLES)
        return sorted(self._items.values(), key=lambda t: t.plate)

    def search_monthly_tickets(self, keyword):
        k = keyword.strip().lower()
        return [t for t in self.get_all_monthly_tickets()
                if k in t.plate.lower() or k in t.owner.lower() or k in t.phone]

    def check_monthly_ticket(self, plate) -> bool:
        t = self._items.get(validators.normalize_plate(plate))
        return bool(t and t.start_date <= date.today() <= t.end_date)

                                        
    def quote_monthly(self, plate, vehicle_type, months, start_date=None) -> dict:
        self._audit.require(*STAFF_ROLES)
        plate = validators.normalize_plate(plate)
        prices = self._prices.get_prices()
        if vehicle_type not in VEHICLE_TYPES:
            raise ParkingError("Loại xe không hợp lệ.")
        if months not in prices["monthly_discount"]:
            raise ParkingError("Gói vé tháng không hợp lệ.")
        today = date.today()
        existing = self._items.get(plate)
        renewal = bool(existing and existing.end_date >= today)
        if renewal:
            start = existing.end_date + timedelta(days=1)                                 
        else:
            start = start_date or today
            if start < today:
                raise ParkingError("Ngày bắt đầu không được nằm trong quá khứ.")
        end = add_months(start, months) - timedelta(days=1)
        base = prices["monthly"][vehicle_type] * months
        pct = prices["monthly_discount"][months]
        discount = base * pct // 100
        return {"start_date": start, "end_date": end, "months": months, "base": base, "discount_pct": pct,
                "discount": discount, "total": base - discount, "is_renewal": renewal}

    def purchase_monthly_ticket(self, plate, owner, phone, vehicle_type, months, start_date,
                                method, received=None, reference=None):
        self._audit.require(*STAFF_ROLES)
        plate = validators.normalize_plate(plate)
        if not validators.is_valid_plate(plate):
            raise InvalidPlateError("Biển số không hợp lệ.")
        if not owner.strip():
            raise ParkingError("Tên chủ xe không được để trống.")
        if not validators.is_valid_phone(phone):
            raise ParkingError("Số điện thoại không hợp lệ.")
        q = self.quote_monthly(plate, vehicle_type, months, start_date)
        label = "Gia hạn" if q["is_renewal"] else "Mua mới"
        pay = self._payments.collect(                                                                     
            "monthly", plate, plate,
            f"{label} vé tháng {months} tháng ({q['start_date']:%d/%m/%Y}-{q['end_date']:%d/%m/%Y})",
            q["total"], method, received, reference)
        t = self._items.get(plate)
        if t:
            t.owner, t.phone, t.vehicle_type, t.end_date = owner.strip(), phone.strip(), vehicle_type, q["end_date"]
            if not q["is_renewal"]:
                t.start_date = q["start_date"]
        else:
            t = self._items[plate] = MonthlyTicket(plate, owner.strip(), phone.strip(), vehicle_type,
                                                   q["start_date"], q["end_date"])
        self._audit.log("monthly_manage", f"{label} vé tháng {plate} {months} tháng")
        return t, pay


                                                                         
class MockParkingManager:
    def __init__(self, monthly: MockMonthlyService, payments: MockPaymentService, prices: MockPriceTable, audit):
        self._monthly, self._payments, self._prices, self._audit = monthly, payments, prices, audit
        self._slots = {f"{r}{i}": ParkingSlot(f"{r}{i}")
                       for r in SLOT_ROWS for i in range(1, COLS_PER_ROW + 1)}
        self._tickets = []
        self._counter = 0

    def _new_ticket(self, plate, vt, slot_id, entry_time, is_monthly=False):
        self._counter += 1
        t = ParkingTicket(f"VE{entry_time:%y%m%d}-{self._counter:04d}", plate, vt,
                          slot_id, entry_time, is_monthly=is_monthly)
        self._tickets.append(t)
        return t

    def _calc_fee(self, vehicle_type, minutes, is_monthly, lost=False) -> int:
        p = self._prices.get_prices()
        fee = 0
        if not is_monthly and minutes > p["free_minutes"]:
            fee = max(1, -(-minutes // 60)) * p["hourly"][vehicle_type]                              
        if lost:
            fee += p["lost_ticket"][vehicle_type]                                                          
        return fee

    def _active_ticket(self, key):
        k = key.strip().upper()
        for t in self._tickets:
            if t.status == TICKET_PARKED and k in (t.plate.upper(), t.ticket_id.upper()):
                return t
        return None

                   
    def get_prices(self) -> dict:
        return self._prices.get_prices()

    def set_prices(self, prices: dict):
        self._prices.set_prices(prices)

                      
    def get_all_slots(self):
        self._audit.require(*STAFF_ROLES)
        return list(self._slots.values())

    def get_slot(self, slot_id):
        self._audit.require(*STAFF_ROLES)
        return self._slots[slot_id]

    def vehicle_entry(self, plate, vehicle_type, slot_id=None):
        """Nhân viên cho xe vào. slot_id=None: hệ thống tự gán ô trống; hoặc chọn một ô trống cụ thể."""
        self._audit.require(*STAFF_ROLES)
        return self._enter(plate, vehicle_type, slot_id)

    def _enter(self, plate, vehicle_type, slot_id=None, by_customer=False):
        """Dùng chung cho nhân viên và khách tự vào (khách đi qua CustomerService.self_entry)."""
        plate = validators.normalize_plate(plate)
        if not validators.is_valid_plate(plate):
            raise InvalidPlateError(f"Biển số '{plate}' không hợp lệ.")
        if vehicle_type not in VEHICLE_TYPES:
            raise ParkingError("Loại xe không hợp lệ.")
        if self._active_ticket(plate):
            raise VehicleAlreadyParkedError(f"Xe {plate} đang ở trong bãi.")
        if slot_id is None:
            free = [s for s in self._slots.values() if s.status == STATUS_EMPTY]
            if not free:
                raise NoSlotAvailableError("Bãi đã hết chỗ trống.")
            slot = free[0]
        else:
            slot = self._slots.get(slot_id)
            if slot is None or slot.status != STATUS_EMPTY:
                raise ParkingError(f"Ô {slot_id} không thể sử dụng.")
        now = datetime.now()
        ticket = self._new_ticket(plate, vehicle_type, slot.slot_id, now,
                                  is_monthly=self._monthly.check_monthly_ticket(plate))
        slot.status, slot.current_plate = STATUS_OCCUPIED, plate
        slot.entry_time, slot.ticket_id = now, ticket.ticket_id
        self._audit.log("vehicle_entry", f"{plate} vào ô {slot.slot_id} ({ticket.ticket_id})"
                        + (" - khách tự vào" if by_customer else "") + (" - tự động" if slot_id is None else ""))
        return ticket

    def estimate_fee(self, plate_or_ticket_id, lost_ticket=False):
        self._audit.require(*STAFF_ROLES)
        t = self._active_ticket(plate_or_ticket_id)
        if not t:
            raise TicketNotFoundError(f"Không tìm thấy xe/vé đang gửi: {plate_or_ticket_id}")
        return t.duration_minutes, self._calc_fee(t.vehicle_type, t.duration_minutes, t.is_monthly, lost_ticket)

    def vehicle_exit(self, plate_or_ticket_id, lost_ticket=False, method="cash", received=None, reference=None):
        self._audit.require(*STAFF_ROLES)
        t = self._active_ticket(plate_or_ticket_id)
        if not t:
            raise TicketNotFoundError(f"Không tìm thấy xe/vé đang gửi: {plate_or_ticket_id}")
        t.exit_time = datetime.now()
        fee = self._calc_fee(t.vehicle_type, t.duration_minutes, t.is_monthly, lost_ticket)
        try:
            pay = None
            if fee > 0:                                                                               
                desc = f"Phí gửi xe {t.ticket_id}" + (" (mất vé)" if lost_ticket else "")
                pay = self._payments.collect("parking", t.plate, t.ticket_id, desc, fee, method, received, reference)
        except ParkingError:
            t.exit_time = None
            raise
        t.fee, t.lost_ticket, t.status = fee, lost_ticket, TICKET_CLOSED
        t.payment_id = pay.payment_id if pay else ""
        self._slots[t.slot_id] = ParkingSlot(t.slot_id)
        self._audit.log("vehicle_exit", f"{t.plate} ra khỏi ô {t.slot_id}, phí {format_money(fee)}" + (" (mất vé)" if lost_ticket else ""))
        return t

    def get_history(self, filters=None):
        self._audit.require(*STAFF_ROLES)
        f = filters or {}
        rows = []
        for t in self._tickets:
            if f.get("plate") and f["plate"].upper() not in t.plate.upper():
                continue
            if f.get("vehicle_type") and t.vehicle_type != f["vehicle_type"]:
                continue
            if f.get("status") and t.status != f["status"]:
                continue
            if f.get("date_from") and t.entry_time.date() < f["date_from"]:
                continue
            if f.get("date_to") and t.entry_time.date() > f["date_to"]:
                continue
            rows.append(t)
        return sorted(rows, key=lambda t: t.entry_time, reverse=True)

    def set_slot_maintenance(self, slot_id, flag: bool, reason: str = ""):
        """Nhân viên & Quản trị sửa trạng thái ô: Trống <-> Bảo trì (bảo trì bắt buộc có lý do). Ô có xe không đổi được."""
        self._audit.require(*STAFF_ROLES)
        slot = self._slots.get(slot_id)
        if slot is None:
            raise ParkingError(f"Không có ô {slot_id}.")
        if slot.status == STATUS_OCCUPIED:
            raise ParkingError(f"Ô {slot_id} đang có xe - hãy cho xe ra trước khi đổi trạng thái.")
        if flag:
            if len(reason.strip()) < MIN_MAINTENANCE_REASON:
                raise ParkingError("Vui lòng nhập lý do bảo trì (ít nhất 3 ký tự).")
            slot.status, slot.note = STATUS_MAINTENANCE, reason.strip()
        else:
            slot.status, slot.note = STATUS_EMPTY, ""
        self._audit.log("maintenance", f"Ô {slot_id}: " + (f"đặt bảo trì - {reason.strip()}" if flag else "bỏ bảo trì"))

    @property
    def tickets(self):
        return self._tickets


                                                                           
class MockStatsService:
    def __init__(self, manager: MockParkingManager, monthly: MockMonthlyService, payments: MockPaymentService, audit):
        self._m, self._mo, self._pay, self._audit = manager, monthly, payments, audit

    def get_statistics(self) -> dict:
        self._audit.require(*STAFF_ROLES)
        slots = self._m.get_all_slots()
        total = len(slots)
        occ = sum(s.status == STATUS_OCCUPIED for s in slots)
        mnt = sum(s.status == STATUS_MAINTENANCE for s in slots)
        today = date.today()
        tks = self._m.tickets
        hourly = {h: 0 for h in range(24)}
        for t in tks:
            hourly[t.entry_time.hour] += 1
        by_method = self._pay.revenue_by_method(today)
        by_kind = self._pay.revenue_by_kind(today)
        return {
            "total_slots": total, "empty": total - occ - mnt, "occupied": occ, "maintenance": mnt,
            "occupancy_rate": round(occ / total * 100, 1) if total else 0.0,
            "vehicles_in": sum(t.entry_time.date() == today for t in tks),
            "vehicles_out": sum(bool(t.exit_time) and t.exit_time.date() == today for t in tks),
            "revenue": sum(by_method.values()),                                           
            "revenue_parking": by_kind["parking"], "revenue_monthly": by_kind["monthly"],
            "revenue_by_method": by_method, "hourly_counts": hourly,
        }

    def export_shift_report(self, path):
        self._audit.require(*STAFF_ROLES)
        s = self.get_statistics()
        sh = self._pay.current_shift() or (self._pay.get_shifts() or [None])[0]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["BÁO CÁO CA", datetime.now().strftime("%d/%m/%Y %H:%M")])
            if sh:
                w.writerow(["Ca", sh.shift_id, "Thu ngân", sh.cashier, "Tiền đầu ca", sh.opening_cash,
                            "Trạng thái", "Đang mở" if sh.is_open else "Đã chốt"])
            for k in ("total_slots", "empty", "occupied", "maintenance", "occupancy_rate",
                      "vehicles_in", "vehicles_out", "revenue", "revenue_parking", "revenue_monthly"):
                w.writerow([k, s[k]])
            for k, v in s["revenue_by_method"].items():
                w.writerow([f"revenue_{k}", v])
            w.writerow([])
            w.writerow(["payment_id", "kind", "plate", "description", "amount", "method", "reference",
                        "received", "change", "time", "cashier", "shift"])
            for p in self._pay.get_transactions():
                w.writerow([p.payment_id, p.kind, p.plate, p.description, p.amount, p.method, p.reference_code,
                            p.received, p.change, p.created_at, p.cashier, p.shift_id])
        self._audit.log("export", "Xuất báo cáo ca")
        return str(path)

    def backup_data(self, path):
        """Sao lưu toàn bộ dữ liệu ra 1 file JSON (chỉ Quản trị)."""
        self._audit.require(ROLE_ADMIN)
        data = {
            "created_at": datetime.now(), "prices": self._m.get_prices(),
            "tickets": [asdict(t) for t in self._m.tickets],
            "monthly_tickets": [asdict(t) for t in self._mo.get_all_monthly_tickets()],
            "payments": [asdict(p) for p in self._pay.get_transactions()],
            "shifts": [asdict(sh) for sh in self._pay.get_shifts()],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        self._audit.log("backup", "Sao lưu dữ liệu")
        return str(path)


def create_mock_backend():
    """Trả về (manager, monthly, stats, auth, payments, customers, audit)."""
    audit = MockAuditLog()
    prices = MockPriceTable(audit)
    payments = MockPaymentService(audit)
    monthly = MockMonthlyService(prices, payments, audit)
    manager = MockParkingManager(monthly, payments, prices, audit)
    stats = MockStatsService(manager, monthly, payments, audit)
    auth = MockAuthService(audit)
    customers = MockCustomerService(auth, audit, manager, monthly, payments)
    from gui.json_persistence import attach_json_persistence
    attach_json_persistence(manager, monthly, stats, auth, payments, customers, audit, prices)
    return manager, monthly, stats, auth, payments, customers, audit
