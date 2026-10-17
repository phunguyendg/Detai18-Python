"""Cổng thông tin khách hàng (liên kết xe, gửi yêu cầu)."""
from backend.exceptions import ParkingError

class CustomerService:
    def __init__(self, manager, monthly):
        self.manager = manager
        self.monthly = monthly
        self._requests = []

    def get_public_status(self):
        # Trả về thống kê cơ bản cho khách xem
        slots = self.manager.lot.get_all_slots()
        empty = sum(1 for s in slots if s.status == "empty")
        occupied = sum(1 for s in slots if s.status == "occupied")
        return {"empty": empty, "occupied": occupied, "occupancy_rate": (occupied/len(slots)*100) if slots else 0}

    def get_public_slots(self): return self.manager.lot.get_all_slots()

    def get_my_vehicles(self): return []
    def get_pending_vehicles(self): return []
    def link_vehicle(self, plate, vtype): return True
    def unlink_vehicle(self, plate): pass
    
    def get_requests(self, status="pending"): return self._requests
    def submit_monthly_request(self, plate, months):
        req = {"request_id": f"REQ{len(self._requests)+1}", "plate": plate, "months": months, "status": "pending", "note": "", "created_at": "now"}
        self._requests.append(req)
        return req
    def resolve_request(self, rid, status, note=""):
        for r in self._requests:
            if r["request_id"] == rid: r["status"] = status; r["note"] = note

    def get_my_monthly_tickets(self): return []
    def get_my_history(self): return []
    def get_my_payments(self): return []
    def get_my_receipt(self, pid): return "Hóa đơn khách hàng"