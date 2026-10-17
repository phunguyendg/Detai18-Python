"""Vé tháng: class MonthlyTicket + MonthlyManager (CRUD, kiểm tra hạn, báo giá, mua/gia hạn)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from calendar import monthrange

from backend.exceptions import ParkingError, DuplicateMonthlyTicketError
from config import DATA_DIR, VEHICLE_TYPES, DEFAULT_PRICES


@dataclass
class MonthlyTicket:
    plate: str
    owner: str
    phone: str
    vehicle_type: str
    start_date: date
    end_date: date

    def is_valid(self, today: date | None = None) -> bool:
        today = today or date.today()
        return self.start_date <= today <= self.end_date

    def days_left(self, today: date | None = None) -> int:
        return (self.end_date - (today or date.today())).days

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start_date"] = self.start_date.isoformat()
        d["end_date"] = self.end_date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MonthlyTicket":
        return cls(
            plate=d["plate"], owner=d["owner"], phone=d["phone"],
            vehicle_type=d["vehicle_type"],
            start_date=date.fromisoformat(d["start_date"]),
            end_date=date.fromisoformat(d["end_date"]),
        )


class MonthlyManager:
    FILE = DATA_DIR / "monthly_tickets.json"

    def __init__(self, prices_provider=None, payment_service=None):
        self._tickets: dict[str, MonthlyTicket] = {}
        self._prices_provider = prices_provider or (lambda: DEFAULT_PRICES)
        self._payments = payment_service
        self.load()

    def load(self):
        if not self.FILE.exists():
            self._tickets = {}
            return
        try:
            raw = json.loads(self.FILE.read_text(encoding="utf-8"))
            self._tickets = {d["plate"]: MonthlyTicket.from_dict(d) for d in raw}
        except Exception:
            self._tickets = {}

    def save(self):
        self.FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [t.to_dict() for t in self._tickets.values()]
        self.FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_all_monthly_tickets(self) -> list[MonthlyTicket]:
        return sorted(self._tickets.values(), key=lambda t: t.plate)

    def search_monthly_tickets(self, keyword: str) -> list[MonthlyTicket]:
        kw = keyword.strip().lower()
        if not kw:
            return self.get_all_monthly_tickets()
        return [t for t in self._tickets.values()
                if kw in t.plate.lower() or kw in t.owner.lower() or kw in t.phone]

    def check_monthly_ticket(self, plate: str, today: date | None = None) -> bool:
        t = self._tickets.get(plate.upper())
        return bool(t and t.is_valid(today))

    def add_monthly_ticket(self, plate, owner, phone, vehicle_type, start_date, end_date):
        plate = plate.upper()
        if plate in self._tickets:
            raise DuplicateMonthlyTicketError(f"Xe {plate} đã có vé tháng.")
        self._validate(plate, vehicle_type, start_date, end_date)
        self._tickets[plate] = MonthlyTicket(plate, owner.strip(), phone.strip(),
                                             vehicle_type, start_date, end_date)
        self.save()
        return self._tickets[plate]

    def update_monthly_ticket(self, plate, **kwargs):
        plate = plate.upper()
        t = self._tickets.get(plate)
        if not t:
            raise ParkingError(f"Không tìm thấy vé tháng của xe {plate}.")
        for k in ("owner", "phone", "vehicle_type", "start_date", "end_date"):
            if k in kwargs and kwargs[k] is not None:
                setattr(t, k, kwargs[k])
        self._validate(t.plate, t.vehicle_type, t.start_date, t.end_date)
        self.save()
        return t

    def remove_monthly_ticket(self, plate) -> bool:
        ok = self._tickets.pop(plate.upper(), None) is not None
        if ok:
            self.save()
        return ok

    def quote_monthly(self, plate, vehicle_type, months, start_date) -> dict:
        if vehicle_type not in VEHICLE_TYPES:
            raise ParkingError("Loại xe không hợp lệ.")
        if months not in (1, 3, 6, 12):
            raise ParkingError("Gói vé tháng chỉ nhận 1, 3, 6 hoặc 12 tháng.")
        
        prices = self._prices_provider()
        base_price = prices["monthly"][vehicle_type]
        disc_pct = prices["monthly_discount"].get(months, 0)
        base = base_price * months
        discount = base * disc_pct // 100
        total = base - discount

        plate = plate.upper()
        today = date.today()
        start = start_date or today
        old = self._tickets.get(plate)
        is_renewal = False
        
        if old and old.end_date >= start:
            start = old.end_date + timedelta(days=1)
            is_renewal = True
        end = self._add_months(start, months) - timedelta(days=1)

        return {
            "base": base, "discount": discount, "discount_pct": disc_pct,
            "total": total, "start_date": start, "end_date": end,
            "is_renewal": is_renewal,
        }

    def purchase_monthly_ticket(self, plate, owner, phone, vehicle_type, months,
                                start_date, method, received, reference):
        if self._payments is None:
            # Nếu chưa có dịch vụ thanh toán (chờ Hưng), tạo một object giả để test
            class FakePayment:
                payment_id = "PAY_MOCK_001"
            payment = FakePayment()
        else:
            q = self.quote_monthly(plate, vehicle_type, months, start_date)
            payment = self._payments.create_payment(
                kind="monthly", plate=plate.upper(), amount=q["total"],
                method=method, received=received, reference=reference,
                description=f"Vé tháng {months} tháng ({q['start_date']} → {q['end_date']})",
            )
            start_date = q["start_date"]
            end_date = q["end_date"]

        # Ghi nhận vé
        q = self.quote_monthly(plate, vehicle_type, months, start_date) # Gọi lại để chắc chắn
        ticket = MonthlyTicket(plate.upper(), owner.strip(), phone.strip(), vehicle_type,
                               q["start_date"], q["end_date"])
        self._tickets[ticket.plate] = ticket
        self.save()
        return ticket, payment

    @staticmethod
    def _validate(plate, vehicle_type, start_date, end_date):
        if not plate:
            raise ParkingError("Biển số không được để trống.")
        if vehicle_type not in VEHICLE_TYPES:
            raise ParkingError("Loại xe không hợp lệ.")
        if end_date < start_date:
            raise ParkingError("Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.")

    @staticmethod
    def _add_months(d: date, months: int) -> date:
        y, m = divmod(d.month - 1 + months, 12)
        y += d.year
        m += 1
        day = min(d.day, monthrange(y, m)[1])
        return date(y, m, day)