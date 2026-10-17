"""Quản lý bãi đỗ xe: Xe vào, xe ra, tìm chỗ trống."""
import json
import random
import string
from datetime import datetime
from pathlib import Path

from backend.exceptions import ParkingError, VehicleAlreadyParkedError, NoSlotAvailableError, TicketNotFoundError, InvalidPlateError
from backend.models import ParkingSlot, ParkingTicket
from config import (DATA_DIR, STATUS_EMPTY, STATUS_OCCUPIED, STATUS_MAINTENANCE, 
                    SLOT_ROWS, COLS_PER_ROW, TICKET_PARKED, TICKET_CLOSED, DEFAULT_PRICES)


class ParkingLot:
    def __init__(self):
        self.slots: list[ParkingSlot] = []
        self.load_slots()

    def load_slots(self):
        """Khởi tạo 20 ô đỗ xe (A1-A10, B1-B10) nếu chưa có."""
        file = DATA_DIR / "parking_slots.json"
        if file.exists():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                self.slots = [ParkingSlot(**d) for d in data]
                return
            except Exception:
                pass
        
        # Tạo mới nếu chưa có
        self.slots = []
        for row in SLOT_ROWS:
            for col in range(1, COLS_PER_ROW + 1):
                self.slots.append(ParkingSlot(slot_id=f"{row}{col}"))
        self.save_slots()

    def save_slots(self):
        file = DATA_DIR / "parking_slots.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        data = [{"slot_id": s.slot_id, "status": s.status, "current_plate": s.current_plate, 
                 "note": s.note, "entry_time": s.entry_time.isoformat() if s.entry_time else None} for s in self.slots]
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_all_slots(self) -> list[ParkingSlot]:
        return self.slots

    def get_slot(self, slot_id: str) -> ParkingSlot:
        for s in self.slots:
            if s.slot_id == slot_id:
                return s
        raise ParkingError(f"Không tìm thấy ô đỗ {slot_id}.")

    def set_slot_maintenance(self, slot_id: str, is_maintenance: bool, reason: str = ""):
        slot = self.get_slot(slot_id)
        if slot.status == STATUS_OCCUPIED:
            raise ParkingError("Không thể đổi trạng thái ô đang có xe.")
        
        if is_maintenance:
            if len(reason.strip()) < 3:
                raise ParkingError("Lý do bảo trì phải có ít nhất 3 ký tự.")
            slot.status = STATUS_MAINTENANCE
            slot.note = reason.strip()
        else:
            slot.status = STATUS_EMPTY
            slot.note = ""
        self.save_slots()


class ParkingManager:
    def __init__(self, parking_lot: ParkingLot):
        self.lot = parking_lot
        self.tickets: list[ParkingTicket] = []
        self.prices = DEFAULT_PRICES.copy()
        self.load_tickets()
        
    def get_all_slots(self):
        return self.lot.get_all_slots()

    def get_slot(self, slot_id: str):
        return self.lot.get_slot(slot_id)

    def set_slot_maintenance(self, slot_id: str, is_maintenance: bool, reason: str = ""):
        return self.lot.set_slot_maintenance(slot_id, is_maintenance, reason)

    def load_tickets(self):
        file = DATA_DIR / "tickets.json"
        if file.exists():
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                self.tickets = []
                for d in data:
                    d["entry_time"] = datetime.fromisoformat(d["entry_time"])
                    if d["exit_time"]:
                        d["exit_time"] = datetime.fromisoformat(d["exit_time"])
                    self.tickets.append(ParkingTicket(**d))
            except Exception:
                self.tickets = []

    def save_tickets(self):
        file = DATA_DIR / "tickets.json"
        data = []
        for t in self.tickets:
            d = t.__dict__.copy()
            d["entry_time"] = t.entry_time.isoformat()
            d["exit_time"] = t.exit_time.isoformat() if t.exit_time else None
            data.append(d)
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_prices(self) -> dict:
        return self.prices

    def set_prices(self, new_prices: dict):
        self.prices = new_prices

    def _generate_ticket_id(self) -> str:
        """Sinh mã vé tự động, VD: T-231015-ABCD"""
        date_str = datetime.now().strftime("%y%m%d")
        rand_str = "".join(random.choices(string.ascii_uppercase, k=4))
        return f"T-{date_str}-{rand_str}"

    # ------------------------------------------------------------ XE VÀO
    def vehicle_entry(self, plate: str, vehicle_type: str, slot_id: str | None = None) -> ParkingTicket:
        plate = plate.upper()
        
        # 1. Kiểm tra xe đã ở trong bãi chưa
        for t in self.tickets:
            if t.plate == plate and t.status == TICKET_PARKED:
                raise VehicleAlreadyParkedError(f"Xe {plate} đang ở trong bãi (vé {t.ticket_id}).")

        # 2. Tìm chỗ trống
        if slot_id:
            slot = self.lot.get_slot(slot_id)
            if slot.status != STATUS_EMPTY:
                raise NoSlotAvailableError(f"Ô {slot_id} không trống.")
        else:
            empty_slots = [s for s in self.lot.get_all_slots() if s.status == STATUS_EMPTY]
            if not empty_slots:
                raise NoSlotAvailableError("Bãi xe đã hết chỗ trống.")
            slot = empty_slots[0]

        # 3. Tạo vé
        ticket = ParkingTicket(
            ticket_id=self._generate_ticket_id(),
            plate=plate,
            vehicle_type=vehicle_type,
            slot_id=slot.slot_id,
            entry_time=datetime.now()
        )
        self.tickets.append(ticket)

        # 4. Cập nhật chỗ đỗ
        slot.status = STATUS_OCCUPIED
        slot.current_plate = plate
        slot.entry_time = ticket.entry_time

        self.save_tickets()
        self.lot.save_slots()
        return ticket

    # ------------------------------------------------------------ XE RA
    def estimate_fee(self, key: str, lost_ticket: bool = False) -> tuple[int, int]:
        """Trả về (số phút, số tiền). Key có thể là mã vé hoặc biển số."""
        key = key.upper()
        ticket = None
        for t in self.tickets:
            if (t.ticket_id == key or t.plate == key) and t.status == TICKET_PARKED:
                ticket = t
                break
        if not ticket:
            raise TicketNotFoundError(f"Không tìm thấy xe/vé {key} đang đỗ trong bãi.")
        
        ticket.exit_time = datetime.now()
        fee = ticket.calculate_fee(self.prices, lost_ticket)
        minutes = int((ticket.exit_time - ticket.entry_time).total_seconds() / 60)
        return minutes, fee

    def vehicle_exit(self, key: str, lost_ticket: bool = False, method: str = "cash", received=None, reference=None) -> ParkingTicket:
        key = key.upper()
        ticket = None
        for t in self.tickets:
            if (t.ticket_id == key or t.plate == key) and t.status == TICKET_PARKED:
                ticket = t
                break
        if not ticket:
            raise TicketNotFoundError(f"Không tìm thấy xe/vé {key}.")

        # Tính tiền
        ticket.exit_time = datetime.now()
        ticket.fee = ticket.calculate_fee(self.prices, lost_ticket)
        ticket.status = TICKET_CLOSED
        
        # Tạo mã thanh toán (giả lập)
        if ticket.fee > 0:
            ticket.payment_id = f"PAY-{ticket.ticket_id}"

        # Trả lại chỗ trống
        slot = self.lot.get_slot(ticket.slot_id)
        slot.status = STATUS_EMPTY
        slot.current_plate = ""
        slot.entry_time = None

        self.save_tickets()
        self.lot.save_slots()
        return ticket

    def get_history(self, filters: dict | None = None) -> list[ParkingTicket]:
        """Lấy lịch sử vé, có thể lọc theo biển số, trạng thái, ngày."""
        result = self.tickets
        if not filters:
            return sorted(result, key=lambda x: x.entry_time, reverse=True)
            
        if "plate" in filters:
            result = [t for t in result if filters["plate"].upper() in t.plate]
        if "status" in filters:
            result = [t for t in result if t.status == filters["status"]]
        if "date_from" in filters:
            result = [t for t in result if t.entry_time.date() >= filters["date_from"]]
        if "date_to" in filters:
            result = [t for t in result if t.entry_time.date() <= filters["date_to"]]
            
        return sorted(result, key=lambda x: x.entry_time, reverse=True)