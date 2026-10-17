"""Quản lý thanh toán, in hóa đơn, ca trực."""
import json
from dataclasses import dataclass
from datetime import datetime, date
from backend.exceptions import ParkingError
from config import DATA_DIR, PAYMENT_METHODS, PARKING_NAME, DEFAULT_OPENING_CASH

@dataclass
class Payment:
    payment_id: str
    created_at: datetime
    kind: str
    plate: str
    amount: int
    method: str
    reference_code: str | None = None
    description: str = ""
    cashier: str = "admin"
    shift_id: str = "S01"

@dataclass
class Shift:
    shift_id: str
    cashier: str
    opened_at: datetime
    opening_cash: int
    closed_at: datetime = None
    counted_cash: int = None
    expected_cash: int = None
    difference: int = None

class PaymentService:
    def __init__(self):
        self.payments = []
        self.shifts = []
        self.current_shift_obj = None
        self.load()

    def load(self):
        pass # Trong bản demo này, ta không lưu payment ra file để đơn giản hóa

    def get_payment_methods(self): return list(PAYMENT_METHODS.items())

    def current_shift(self): return self.current_shift_obj

    def open_shift(self, cashier, opening_cash):
        shift = Shift(f"S{len(self.shifts)+1:02d}", cashier, datetime.now(), opening_cash)
        self.shifts.append(shift)
        self.current_shift_obj = shift
        return shift

    def shift_summary(self, shift_id):
        return {"total": 0, "count": 0, "cash": 0, "by_method": {}}

    def close_shift(self, counted, note):
        shift = self.current_shift_obj
        if not shift: raise ParkingError("Không có ca nào đang mở.")
        shift.closed_at = datetime.now()
        shift.counted_cash = counted
        shift.expected_cash = shift.opening_cash # Giả lập
        shift.difference = counted - shift.expected_cash
        self.current_shift_obj = None
        return shift

    def create_payment(self, kind, plate, amount, method, received, reference, description=""):
        pid = f"PAY-{datetime.now().strftime('%y%m%d%H%M%S')}"
        p = Payment(pid, datetime.now(), kind, plate, amount, method, reference, description)
        self.payments.append(p)
        return p

    def get_transactions(self, filters=None): return self.payments
    def revenue_by_method(self, d: date): return {k: 0 for k in PAYMENT_METHODS}
    def build_receipt(self, pid):
        p = next((x for x in self.payments if x.payment_id == pid), None)
        if not p: raise ParkingError("Không tìm thấy hóa đơn.")
        return f"--- HÓA ĐƠN ---\nMã: {p.payment_id}\nSố tiền: {p.amount} đ\nNgày: {p.created_at}"