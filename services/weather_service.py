"""Dịch vụ thời tiết (CHỨC NĂNG API của đề tài).

- Nguồn: Open-Meteo (https://open-meteo.com) - không cần API key, miễn phí cho mục đích phi thương mại (CC BY 4.0).
- Gọi API bằng urllib (thư viện chuẩn), có timeout; xử lý: mất mạng, hết thời gian chờ, HTTP lỗi, JSON hỏng, thiếu trường.
- LÀM SẠCH + KIỂM TRA + CHUYỂN ĐỔI: bỏ giá trị thiếu/ngoài miền hợp lệ, đổi mã WMO -> mô tả tiếng Việt.
- LƯU kết quả vào file JSON (ghi an toàn: ghi file tạm rồi thay thế) và dùng lại khi không có mạng.
Không phụ thuộc giao diện nên có thể kiểm thử độc lập (xem tests/test_weather_service.py).
"""
import json
import os
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date

USER_AGENT = "ParkingApp/1.0 (do an Python - sinh vien)"
MAX_BODY = 2_000_000                                               


class WeatherError(Exception):
    """Lỗi lấy/xử lý dữ liệu thời tiết; str(e) là thông báo tiếng Việt cho người dùng."""


                                                                                         
WMO = {
    0: ("Trời quang", "clear"), 1: ("Gần như quang đãng", "clear"), 2: ("Có mây rải rác", "partly"),
    3: ("Nhiều mây", "cloudy"), 45: ("Sương mù", "fog"), 48: ("Sương mù đóng băng", "fog"),
    51: ("Mưa phùn nhẹ", "rain"), 53: ("Mưa phùn vừa", "rain"), 55: ("Mưa phùn dày", "rain"),
    56: ("Mưa phùn băng giá nhẹ", "rain"), 57: ("Mưa phùn băng giá dày", "rain"),
    61: ("Mưa nhỏ", "rain"), 63: ("Mưa vừa", "rain"), 65: ("Mưa to", "rain"),
    66: ("Mưa băng giá nhẹ", "rain"), 67: ("Mưa băng giá to", "rain"),
    71: ("Tuyết nhẹ", "snow"), 73: ("Tuyết vừa", "snow"), 75: ("Tuyết dày", "snow"), 77: ("Hạt tuyết", "snow"),
    80: ("Mưa rào nhẹ", "rain"), 81: ("Mưa rào vừa", "rain"), 82: ("Mưa rào rất to", "rain"),
    85: ("Mưa tuyết nhẹ", "snow"), 86: ("Mưa tuyết to", "snow"),
    95: ("Dông", "thunder"), 96: ("Dông kèm mưa đá nhẹ", "thunder"), 97: ("Dông mạnh", "thunder"),
    99: ("Dông kèm mưa đá to", "thunder"),
}

CURRENT_VARS = "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m"
HOURLY_VARS = "temperature_2m,precipitation_probability,weather_code"
DAILY_VARS = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
              "precipitation_sum,uv_index_max")


                                                                                      
def _num(value, lo, hi):
    """Số hợp lệ trong [lo, hi] hoặc None (thiếu / sai kiểu / NaN / ngoài miền)."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or not lo <= value <= hi:
        return None
    return float(value)


def _code(value):
    v = _num(value, 0, 99)
    return int(v) if v is not None else None


def describe(code):
    """(mô tả, nhóm) của mã WMO; mã lạ/thiếu -> ('Không rõ', 'cloudy')."""
    return WMO.get(code, ("Không rõ", "cloudy"))


def _parse_time(text):
    try:
        return datetime.fromisoformat(str(text))
    except (ValueError, TypeError):
        return None


def validate_location(loc):
    try:
        lat, lon = float(loc["lat"]), float(loc["lon"])
        name = str(loc.get("name") or f"{lat:.2f}, {lon:.2f}").strip()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise WeatherError("Địa điểm không hợp lệ (thiếu tọa độ).") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise WeatherError("Tọa độ địa điểm nằm ngoài phạm vi hợp lệ.")
    return {"name": name or "Không tên", "lat": lat, "lon": lon}


def parse_forecast(raw, location):
    """Phản hồi JSON của Open-Meteo -> dict đã làm sạch. Ném WeatherError nếu thiếu dữ liệu cốt lõi."""
    if not isinstance(raw, dict):
        raise WeatherError("Dữ liệu thời tiết không đúng cấu trúc.")
    if raw.get("error"):
        raise WeatherError(f"Máy chủ từ chối yêu cầu: {raw.get('reason', 'không rõ lý do')}")
    cur = raw.get("current")
    if not isinstance(cur, dict):
        raise WeatherError("Dữ liệu thời tiết thiếu phần 'hiện tại'.")
    temp = _num(cur.get("temperature_2m"), -60, 60)
    if temp is None:
        raise WeatherError("Dữ liệu thời tiết thiếu nhiệt độ hợp lệ.")
    code = _code(cur.get("weather_code"))
    desc, kind = describe(code)
    current = {
        "time": str(cur.get("time", "")), "temp": temp,
        "feels": _num(cur.get("apparent_temperature"), -80, 80),
        "humidity": _num(cur.get("relative_humidity_2m"), 0, 100),
        "wind": _num(cur.get("wind_speed_10m"), 0, 400),
        "rain_mm": _num(cur.get("precipitation"), 0, 1000),
        "is_day": bool(cur.get("is_day", 1)), "code": code, "desc": desc, "kind": kind,
    }
    dropped = 0
    hourly = []
    h = raw.get("hourly") if isinstance(raw.get("hourly"), dict) else {}
    times = h.get("time") if isinstance(h.get("time"), list) else []
    for i, t in enumerate(times):
        dt = _parse_time(t)
        temps, probs, codes = (h.get(k) if isinstance(h.get(k), list) else [] for k in
                               ("temperature_2m", "precipitation_probability", "weather_code"))
        at = lambda arr: arr[i] if i < len(arr) else None
        tv = _num(at(temps), -60, 60)
        if dt is None or tv is None:
            dropped += 1
            continue
        c = _code(at(codes))
        hourly.append({"time": dt.isoformat(timespec="minutes"), "temp": tv,
                       "rain_prob": _num(at(probs), 0, 100), "code": c, "kind": describe(c)[1]})
    daily = []
    d = raw.get("daily") if isinstance(raw.get("daily"), dict) else {}
    days = d.get("time") if isinstance(d.get("time"), list) else []
    for i, t in enumerate(days):
        try:
            day = date.fromisoformat(str(t)[:10])
        except ValueError:
            dropped += 1
            continue
        get = lambda k: (d.get(k)[i] if isinstance(d.get(k), list) and i < len(d.get(k)) else None)
        c = _code(get("weather_code"))
        daily.append({"date": day.isoformat(), "code": c, "desc": describe(c)[0], "kind": describe(c)[1],
                      "tmax": _num(get("temperature_2m_max"), -60, 60), "tmin": _num(get("temperature_2m_min"), -60, 60),
                      "rain_prob": _num(get("precipitation_probability_max"), 0, 100),
                      "rain_mm": _num(get("precipitation_sum"), 0, 2000), "uv": _num(get("uv_index_max"), 0, 20)})
    return {"location": location, "source": "Open-Meteo.com (CC BY 4.0)", "timezone": str(raw.get("timezone", "")),
            "current": current, "hourly": hourly, "daily": daily, "dropped": dropped}


def build_advice(data):
    """Gợi ý vận hành bãi xe từ dữ liệu thời tiết: [(mức, nội dung)], mức: danger > warn > info > ok."""
    adv = []
    cur, hours, daily = data["current"], data["hourly"][:6], data["daily"]
    probs = [x["rain_prob"] for x in hours if x["rain_prob"] is not None]
    pmax = max(probs) if probs else 0
    kinds = {x["kind"] for x in hours} | {cur["kind"]}
    if "thunder" in kinds:
        adv.append(("danger", "Có dông trong vài giờ tới: không để khách đứng chờ ngoài trời, kiểm tra biển/cột trong bãi."))
    elif cur["kind"] == "rain" or pmax >= 60:
        adv.append(("warn", f"Sắp có mưa (xác suất tới {pmax:.0f}%): nhắc khách che chắn xe, chú ý lối đi trơn trượt."))
    elif pmax >= 30:
        adv.append(("info", f"Có khả năng mưa ({pmax:.0f}%) trong vài giờ tới."))
    hot = max(cur["temp"], cur["feels"] if cur["feels"] is not None else cur["temp"])
    if hot >= 37:
        adv.append(("warn", f"Nắng nóng (cảm giác {hot:.0f}°C): nhắc khách không để vật dễ cháy nổ trong xe."))
    if cur["wind"] is not None and cur["wind"] >= 40:
        adv.append(("warn", f"Gió mạnh ({cur['wind']:.0f} km/h): chú ý biển báo và xe máy dựng không chắc."))
    if daily and daily[0]["uv"] is not None and daily[0]["uv"] >= 8:
        adv.append(("info", f"Chỉ số UV cao ({daily[0]['uv']:.0f}): hạn chế đứng ngoài nắng lâu."))
    if not adv:
        adv.append(("ok", "Thời tiết thuận lợi cho hoạt động của bãi xe."))
    order = {"danger": 0, "warn": 1, "info": 2, "ok": 3}
    return sorted(adv, key=lambda a: order[a[0]])


                                                                          
class WeatherService:
    def __init__(self, cache_path, base_url="https://api.open-meteo.com/v1/forecast",
                 geocode_url="https://geocoding-api.open-meteo.com/v1/search", timeout=8,
                 max_age_minutes=30, timezone="Asia/Bangkok", forecast_days=5):
        self.cache_path, self.base_url, self.geocode_url = cache_path, base_url, geocode_url
        self.timeout, self.max_age_minutes = timeout, max_age_minutes
        self.timezone, self.forecast_days = timezone, forecast_days

               
    def _get_json(self, url, params):
        full = url + "?" + urllib.parse.urlencode(params, safe=",")
        req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise WeatherError("Phản hồi từ máy chủ thời tiết quá lớn.")
            return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:                                                                   
            reason = ""
            try:
                reason = json.loads(e.read(2000).decode("utf-8")).get("reason", "")
            except (ValueError, OSError, AttributeError):
                pass
            raise WeatherError(f"Máy chủ thời tiết trả lỗi {e.code}" + (f": {reason}" if reason else ".")) from None
        except (socket.timeout, TimeoutError):
            raise WeatherError(f"Hết thời gian chờ ({self.timeout} giây) - máy chủ thời tiết không phản hồi.") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise WeatherError(f"Hết thời gian chờ ({self.timeout} giây) - máy chủ thời tiết không phản hồi.") from None
            raise WeatherError("Không kết nối được máy chủ thời tiết. Hãy kiểm tra kết nối mạng.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WeatherError("Dữ liệu trả về không đúng định dạng JSON.") from None
        except OSError:
            raise WeatherError("Lỗi mạng khi lấy dữ liệu thời tiết.") from None

                      
    def fetch(self, location):
        loc = validate_location(location)
        raw = self._get_json(self.base_url, {
            "latitude": loc["lat"], "longitude": loc["lon"], "current": CURRENT_VARS, "hourly": HOURLY_VARS,
            "daily": DAILY_VARS, "timezone": self.timezone, "forecast_hours": 24, "forecast_days": self.forecast_days})
        data = parse_forecast(raw, loc)
        data["fetched_at"] = datetime.now().isoformat(timespec="seconds")
        data["advice"] = build_advice(data)
        return data

    def search_location(self, query):
        q = (query or "").strip()
        if len(q) < 2:
            raise WeatherError("Nhập ít nhất 2 ký tự để tìm địa điểm.")
        raw = self._get_json(self.geocode_url, {"name": q, "count": 5, "language": "vi", "format": "json"})
        results = raw.get("results") if isinstance(raw, dict) else None
        out = []
        for r in results or []:
            try:
                lat, lon = float(r["latitude"]), float(r["longitude"])
                name = str(r["name"])
            except (KeyError, TypeError, ValueError):
                continue                                                                      
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            extra = ", ".join(str(r[k]) for k in ("admin1", "country") if r.get(k))
            out.append({"name": f"{name}, {extra}" if extra else name, "lat": lat, "lon": lon})
        if not out:
            raise WeatherError(f"Không tìm thấy địa điểm '{q}'.")
        return out

                     
    def load_cache(self):
        """Đọc cache; file không có / rỗng / hỏng / sai cấu trúc -> None (không làm chương trình dừng)."""
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            data, loc = obj["data"], validate_location(obj["location"])
            if not isinstance(data, dict) or "current" not in data:
                return None
            return {"data": data, "location": loc, "saved_at": datetime.fromisoformat(obj["saved_at"])}
        except (OSError, ValueError, KeyError, TypeError, WeatherError):
            return None

    def save_cache(self, location, data):
        """Ghi an toàn: ghi file tạm rồi thay thế để không làm hỏng cache cũ nếu lỗi giữa chừng."""
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
        obj = {"version": 1, "saved_at": datetime.now().isoformat(timespec="seconds"), "location": location, "data": data}
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.cache_path)), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.cache_path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise WeatherError("Không ghi được file lưu thời tiết (kiểm tra quyền thư mục).") from None

    def last_location(self):
        c = self.load_cache()
        return c["location"] if c else None

    @staticmethod
    def _same(a, b):
        return abs(a["lat"] - b["lat"]) < 1e-4 and abs(a["lon"] - b["lon"]) < 1e-4

    def get(self, location, force=False):
        """Lấy thời tiết: dùng cache còn mới; nếu hết hạn/ép cập nhật thì gọi API; API lỗi thì dùng cache cũ (stale)."""
        loc = validate_location(location)
        cache = self.load_cache()
        usable = cache if cache and self._same(cache["location"], loc) else None
        if usable and not force:
            age = (datetime.now() - usable["saved_at"]).total_seconds() / 60
            if age < self.max_age_minutes:
                return {"data": usable["data"], "saved_at": usable["saved_at"], "from_cache": True, "stale": False, "error": None}
        try:
            data = self.fetch(loc)
        except WeatherError as e:
            if usable:
                return {"data": usable["data"], "saved_at": usable["saved_at"], "from_cache": True, "stale": True, "error": str(e)}
            raise
        try:
            self.save_cache(loc, data)
        except WeatherError:
            pass                                                                                                 
        return {"data": data, "saved_at": datetime.now(), "from_cache": False, "stale": False, "error": None}
