"""Các class thực thể: Vehicle, ParkingSlot, ParkingTicket."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import STATUS_EMPTY, STATUS_OCCUPIED, STATUS_MAINTENANCE, TICKET_PARKED, TICKET_CLOSED


@dataclass
class Vehicle:
    plate: str
    vehicle_type: str  # "motorbike" hoặc "car"


@dataclass
class ParkingSlot:
    slot_id: str  # Ví dụ: "A1", "B5"
    status: str = STATUS_EMPTY
    current_plate: str = ""
    entry_time: Optional[datetime] = None
    note: str = ""  # Lý do bảo trì (nếu có)

    @property
    def is_empty(self) -> bool:
        return self.status == STATUS_EMPTY


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
    payment_id: str = ""  # Mã hóa đơn (nếu đã thanh toán)

    def calculate_fee(self, prices: dict, lost_ticket: bool = False) -> int:
        """Tính phí gửi xe dựa trên bảng giá."""
        if self.is_monthly:
            return 0
        if lost_ticket:
            return prices["lost_ticket"][self.vehicle_type]

        # Tính thời gian gửi (phút)
        end = self.exit_time or datetime.now()
        minutes = int((end - self.entry_time).total_seconds() / 60)
        
        # Miễn phí N phút đầu
        if minutes <= prices["free_minutes"]:
            return 0
            
        # Tính theo giờ (làm tròn lên)
        hours = (minutes + 59) // 60
        return hours * prices["hourly"][self.vehicle_type]