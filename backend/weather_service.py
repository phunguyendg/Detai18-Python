"""Dịch vụ thời tiết (Giả lập API)."""
from datetime import datetime
from backend.exceptions import ParkingError

class WeatherService:
    def last_location(self): return {"name": "Hà Nội", "lat": 21.0, "lon": 105.8}
    
    def get(self, loc, force=False):
        # Trả về dữ liệu giả lập để giao diện không bị lỗi
        return {
            "data": {
                "current": {"temp": 28, "desc": "Nắng", "kind": "clear", "is_day": True, "feels": 30, "humidity": 60, "wind": 5, "rain_mm": 0},
                "location": loc,
                "daily": [],
                "hourly": [],
                "advice": []
            },
            "saved_at": datetime.now(),
            "stale": False,
            "error": None,
            "from_cache": False
        }
        
    def search_location(self, q): return []