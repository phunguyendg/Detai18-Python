"""Thống kê bãi xe + xuất báo cáo ca (CSV) + sao lưu dữ liệu."""
import csv
import json
from datetime import date, datetime
from pathlib import Path

from config import (DATA_DIR, STATUS_EMPTY, STATUS_OCCUPIED, STATUS_MAINTENANCE, 
                    TICKET_PARKED, PAYMENT_METHODS, PARKING_NAME)
from backend.exceptions import ParkingError

class StatsService:
    def __init__(self, parking_lot, tickets_provider, payments_service):
        self.parking_lot = parking_lot
        self.tickets = tickets_provider
        self.payments = payments_service

    def get_statistics(self) -> dict:
        slots = self.parking_lot.get_all_slots()
        total = len(slots)
        empty = sum(s.status == STATUS_EMPTY for s in slots)
        occupied = sum(s.status == STATUS_OCCUPIED for s in slots)
        maint = sum(s.status == STATUS_MAINTENANCE for s in slots)
        rate = (occupied / (total - maint) * 100) if (total - maint) else 0.0

        today = date.today()
        try: 
            today_tickets = self.tickets.get_history({"date_from": today, "date_to": today})
        except Exception: 
            today_tickets = []
        
        hourly = {h: 0 for h in range(24)}
        for t in today_tickets: 
            hourly[t.entry_time.hour] += 1

        return {"total_slots": total, "empty": empty, "occupied": occupied, "maintenance": maint,
                "occupancy_rate": rate, "vehicles_in": len(today_tickets),
                "vehicles_out": sum(1 for t in today_tickets if t.status != TICKET_PARKED),
                "revenue": 0, "hourly_counts": hourly}

    def export_shift_report(self, path: str) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["BÁO CÁO CA TRỰC", PARKING_NAME])
            w.writerow(["Ngày xuất", datetime.now().strftime("%d/%m/%Y %H:%M")])
        return str(path)

    def backup_data(self, path: str) -> str:
        path = Path(path)
        bundle = {"_backup_at": datetime.now().isoformat(), "files": {}}
        for name in ["parking_slots.json", "tickets.json", "monthly_tickets.json"]:
            fp = DATA_DIR / name
            if fp.exists(): 
                bundle["files"][name] = json.loads(fp.read_text(encoding="utf-8"))
        path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)