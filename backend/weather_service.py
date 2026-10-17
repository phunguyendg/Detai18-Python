"""Dịch vụ thời tiết (Open-Meteo API).

Trả về đúng định dạng mà gui/weather_tab.py cần:
  get(loc, force)  -> {"data": {...}, "saved_at": datetime, "stale": bool, "error": str|None, "from_cache": bool}
  search_location(q) -> [{"name", "lat", "lon"}]   (báo lỗi bằng WeatherError, không trả list rỗng)
  last_location()  -> {"name", "lat", "lon"}
Dữ liệu được lưu ra file JSON để mất mạng / mở lại app vẫn có dữ liệu cũ.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

try:
    from backend.exceptions import WeatherError          # chỗ đúng: định nghĩa trong backend/exceptions.py
except ImportError:
    try:
        from gui.contracts import WeatherError           # nếu gui đã nằm trong sys.path
    except ImportError:
        class WeatherError(Exception):                   # dự phòng để app vẫn chạy
            """Lỗi thời tiết (dự phòng, nên chuyển vào backend/exceptions.py)."""

try:
    from config import WEATHER_REFRESH_MINUTES
except ImportError:
    WEATHER_REFRESH_MINUTES = 15

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT = 10
FORECAST_DAYS = 5                        # UI hiển thị dự báo 5 ngày
HOURS_SHOWN = 24                         # biểu đồ "24 giờ tới"
MAX_CACHED_LOCATIONS = 20
# TTL hơi nhỏ hơn chu kỳ tự cập nhật của UI để lần tự cập nhật luôn lấy dữ liệu mới
CACHE_TTL = max(30, WEATHER_REFRESH_MINUTES * 60 - 5)

CURRENT_KEYS = ["temperature_2m", "apparent_temperature", "relative_humidity_2m",
                "wind_speed_10m", "rain", "weather_code", "is_day"]
HOURLY_KEYS = CURRENT_KEYS + ["precipitation_probability"]
DAILY_KEYS = ["weather_code", "temperature_2m_max", "temperature_2m_min",
              "precipitation_probability_max", "precipitation_sum"]

DEFAULT_LOC = {"name": "Hà Nội", "lat": 21.0, "lon": 105.8}

# WMO code -> (mô tả, kind). kind phải thuộc: clear, partly, cloudy, fog, rain, snow, thunder
_WMO = {
    1: ("Ít mây", "partly"), 2: ("Có mây", "partly"), 3: ("Nhiều mây", "cloudy"),
    45: ("Sương mù", "fog"), 48: ("Sương mù", "fog"),
    51: ("Mưa phùn nhẹ", "rain"), 53: ("Mưa phùn", "rain"), 55: ("Mưa phùn dày", "rain"),
    56: ("Mưa phùn lạnh", "rain"), 57: ("Mưa phùn lạnh", "rain"),
    61: ("Mưa nhỏ", "rain"), 63: ("Mưa vừa", "rain"), 65: ("Mưa to", "rain"),
    66: ("Mưa lạnh", "rain"), 67: ("Mưa lạnh", "rain"),
    71: ("Tuyết nhẹ", "snow"), 73: ("Tuyết", "snow"), 75: ("Tuyết dày", "snow"), 77: ("Tuyết hạt", "snow"),
    80: ("Mưa rào nhẹ", "rain"), 81: ("Mưa rào", "rain"), 82: ("Mưa rào lớn", "rain"),
    85: ("Tuyết rơi", "snow"), 86: ("Tuyết rơi dày", "snow"),
    95: ("Dông", "thunder"), 96: ("Dông, mưa đá", "thunder"), 99: ("Dông, mưa đá lớn", "thunder"),
}


def _wmo(code, is_day=True):
    if code == 0:
        return ("Nắng", "clear") if is_day else ("Trời quang", "clear")
    return _WMO.get(code, ("Không rõ", "cloudy"))


def _r(v):
    return None if v is None else round(v)


def _advice(cur, nxt):
    """Gợi ý vận hành bãi xe -> list[(level, text)], level: danger | warn | info | ok."""
    out = []
    pmax = max((x["rain_prob"] for x in nxt), default=0)
    if cur["kind"] == "thunder" or any(x["kind"] == "thunder" for x in nxt):
        out.append(("danger", "Có dông trong vài giờ tới: đưa xe vào khu có mái che, "
                              "không để nhân viên đứng ngoài trời."))
    if cur["rain_mm"] > 0:
        out.append(("warn", f"Đang có mưa ({cur['rain_mm']:.1f} mm/giờ): che bạt khu để xe ngoài trời, "
                            "nhắc nhân viên dắt xe cẩn thận, sàn trơn."))
    elif pmax >= 60:
        out.append(("warn", f"Khả năng mưa {pmax}% trong 6 giờ tới: chuẩn bị bạt che và áo mưa."))
    elif pmax >= 30:
        out.append(("info", f"Có thể có mưa ({pmax}% trong 6 giờ tới): theo dõi thêm."))
    if cur["feels"] >= 38:
        out.append(("danger", f"Nắng nóng gay gắt (cảm giác {cur['feels']}°C): ưu tiên xếp xe vào khu có mái che, "
                              "bố trí nghỉ giải lao cho nhân viên."))
    elif cur["feels"] >= 35:
        out.append(("warn", f"Trời nóng (cảm giác {cur['feels']}°C): hạn chế để xe ngoài nắng lâu."))
    if cur["wind"] >= 40:
        out.append(("danger", f"Gió rất mạnh ({cur['wind']} km/h): cố định mái che, biển báo, giữ xe máy đứng vững."))
    elif cur["wind"] >= 25:
        out.append(("warn", f"Gió mạnh ({cur['wind']} km/h): kiểm tra mái che và biển báo."))
    if not out:
        out.append(("ok", "Thời tiết thuận lợi, bãi xe hoạt động bình thường."))
    return out


class WeatherService:
    def __init__(self, cache_path=None):
        self._path = cache_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather_cache.json")
        self._last_loc = dict(DEFAULT_LOC)
        self._cache = {}                 # key -> {"data", "saved_at": datetime}
        self._load()

    # ------------------------------------------------------------------ lưu JSON
    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            if raw.get("last_location"):
                self._last_loc = raw["last_location"]
            for k, v in raw.get("entries", {}).items():
                self._cache[k] = {"data": v["data"], "saved_at": datetime.fromisoformat(v["saved_at"])}
        except (OSError, ValueError, KeyError, TypeError):
            pass                         # chưa có file hoặc file hỏng: bỏ qua

    def _save(self):
        if len(self._cache) > MAX_CACHED_LOCATIONS:
            for k in sorted(self._cache, key=lambda x: self._cache[x]["saved_at"])[:-MAX_CACHED_LOCATIONS]:
                del self._cache[k]
        payload = {
            "last_location": self._last_loc,
            "entries": {k: {"saved_at": v["saved_at"].isoformat(), "data": v["data"]}
                        for k, v in self._cache.items()},
        }
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError:
            pass                         # không ghi được file thì vẫn dùng cache trong RAM

    # ------------------------------------------------------------------ HTTP
    @staticmethod
    def _http_get(url, params):
        full = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full, headers={"User-Agent": "ParkingApp/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _error_text(e):
        if isinstance(e, urllib.error.HTTPError):
            return f"Máy chủ thời tiết trả về lỗi {e.code}"
        if isinstance(e, (urllib.error.URLError, OSError)):
            return "Không kết nối được mạng"
        return f"Dữ liệu thời tiết không hợp lệ ({e})"

    # ------------------------------------------------------------------ build
    @staticmethod
    def _build_data(raw, loc):
        h = raw["hourly"]
        times = h["time"]

        # vị trí của giờ hiện tại trong mảng hourly (giờ địa phương của địa điểm, nhờ timezone=auto)
        cur_raw = raw.get("current")
        stamp = cur_raw["time"] if cur_raw and cur_raw.get("time") else datetime.now().strftime("%Y-%m-%dT%H")
        now_hour = stamp[:13] + ":00"
        i0 = times.index(now_hour) if now_hour in times else 0

        src = cur_raw or {k: h[k][i0] for k in CURRENT_KEYS}
        is_day = bool(src["is_day"])
        desc, kind = _wmo(src["weather_code"], is_day)
        current = {
            "temp": round(src["temperature_2m"]),
            "desc": desc,
            "kind": kind,
            "is_day": is_day,
            "feels": round(src["apparent_temperature"]),
            "humidity": round(src["relative_humidity_2m"]),
            "wind": round(src["wind_speed_10m"]),
            "rain_mm": src["rain"] or 0,
        }

        hourly = []                      # 24 giờ tới, bắt đầu từ giờ hiện tại
        for i in range(i0, min(i0 + HOURS_SHOWN, len(times))):
            d, k = _wmo(h["weather_code"][i], bool(h["is_day"][i]))
            hourly.append({
                "time": times[i],
                "temp": h["temperature_2m"][i],
                "feels": h["apparent_temperature"][i],
                "humidity": h["relative_humidity_2m"][i],
                "wind": h["wind_speed_10m"][i],
                "rain_mm": h["rain"][i] or 0,
                "rain_prob": h["precipitation_probability"][i] or 0,
                "desc": d,
                "kind": k,
            })

        daily = []
        dd = raw.get("daily") or {}
        for i, day in enumerate(dd.get("time", [])[:FORECAST_DAYS]):
            d, k = _wmo(dd["weather_code"][i], True)
            daily.append({
                "date": day,
                "tmax": _r(dd["temperature_2m_max"][i]),
                "tmin": _r(dd["temperature_2m_min"][i]),
                "rain_prob": dd["precipitation_probability_max"][i],
                "rain_mm": dd["precipitation_sum"][i],
                "desc": d,
                "kind": k,
            })

        return {
            "current": current,
            "location": loc,
            "daily": daily,
            "hourly": hourly,
            "advice": _advice(current, hourly[:6]),
        }

    @staticmethod
    def _key(loc):
        return f"{loc['lat']:.3f},{loc['lon']:.3f}"

    @staticmethod
    def _result(entry, loc, stale, error, from_cache):
        return {
            "data": dict(entry["data"], location=loc),   # tên địa điểm theo lựa chọn hiện tại của người dùng
            "saved_at": entry["saved_at"],
            "stale": stale,
            "error": error,
            "from_cache": from_cache,
        }

    # ------------------------------------------------------------------ public
    def last_location(self):
        return self._last_loc

    def get(self, loc, force=False):
        key = self._key(loc)
        cached = self._cache.get(key)

        if cached and not force and (datetime.now() - cached["saved_at"]).total_seconds() < CACHE_TTL:
            return self._result(cached, loc, False, None, True)

        try:
            raw = self._http_get(FORECAST_URL, {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current": ",".join(CURRENT_KEYS),
                "hourly": ",".join(HOURLY_KEYS),
                "daily": ",".join(DAILY_KEYS),
                "timezone": "auto",
                "forecast_days": FORECAST_DAYS,
            })
            data = self._build_data(raw, loc)
        except Exception as e:
            msg = self._error_text(e)
            if cached:                   # mất mạng: dùng dữ liệu đã lưu và báo là dữ liệu cũ
                return self._result(cached, loc, True, msg, True)
            raise WeatherError(msg)

        entry = {"data": data, "saved_at": datetime.now()}
        self._cache[key] = entry
        self._last_loc = {"name": loc["name"], "lat": loc["lat"], "lon": loc["lon"]}
        self._save()
        return self._result(entry, loc, False, None, False)

    def search_location(self, q):
        q = (q or "").strip()
        if len(q) < 2:
            raise WeatherError("Nhập ít nhất 2 ký tự.")
        try:
            raw = self._http_get(GEOCODE_URL, {"name": q, "count": 8, "language": "vi", "format": "json"})
        except Exception as e:
            raise WeatherError(self._error_text(e))
        out = []
        for r in raw.get("results") or []:
            label = r["name"]
            if r.get("admin1"):
                label += f", {r['admin1']}"
            if r.get("country"):
                label += f", {r['country']}"
            out.append({"name": label, "lat": r["latitude"], "lon": r["longitude"]})
        if not out:
            raise WeatherError(f"Không tìm thấy địa điểm nào khớp với '{q}'.")
        return out