"""Tab THỜI TIẾT: hiển thị dữ liệu từ API Open-Meteo (do WeatherService cung cấp).

- Gọi API ở LUỒNG NỀN (threading + queue + after) nên cửa sổ không bị đứng khi mạng chậm.
- Hiện: thời tiết hiện tại, gợi ý vận hành bãi xe, biểu đồ 24 giờ (Canvas), dự báo 5 ngày, nguồn dữ liệu.
- Mất mạng: dùng dữ liệu đã lưu (JSON) và báo rõ là dữ liệu cũ. Có thể tìm địa điểm khác theo tên.
GUI chỉ gọi: weather.get(location, force), weather.search_location(text), weather.last_location().
"""
import math
import queue
import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk, messagebox

from config import (WEATHER_LOCATIONS, WEATHER_REFRESH_MINUTES, WEATHER_SOURCE, COLOR_CARD, COLOR_BORDER,
                    COLOR_MUTED, COLOR_TEXT, COLOR_PRIMARY, COLOR_ORANGE, COLOR_SUCCESS, COLOR_DANGER, COLOR_BG,
                    FONT_BASE, FONT_BOLD, FONT_SMALL, FONT_BIG)
from gui.contracts import WeatherError

WEEKDAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]
LEVEL_COLORS = {"danger": "#C62828", "warn": COLOR_ORANGE, "info": COLOR_PRIMARY, "ok": COLOR_SUCCESS}


                                                                                            
def _cloud(c, cx, cy, r, color):
    c.create_oval(cx - .75 * r, cy - .1 * r, cx - .1 * r, cy + .5 * r, fill=color, outline="")
    c.create_oval(cx - .45 * r, cy - .55 * r, cx + .35 * r, cy + .35 * r, fill=color, outline="")
    c.create_oval(cx + .05 * r, cy - .25 * r, cx + .8 * r, cy + .5 * r, fill=color, outline="")
    c.create_rectangle(cx - .45 * r, cy, cx + .45 * r, cy + .5 * r, fill=color, outline="")


def draw_icon(c, kind, cx, cy, r, is_day=True, bg=COLOR_CARD):
    """Vẽ biểu tượng thời tiết: clear, partly, cloudy, fog, rain, snow, thunder."""
    def sun(x, y, rr):
        for i in range(8):
            a = i * math.pi / 4
            c.create_line(x + math.cos(a) * rr * .65, y + math.sin(a) * rr * .65,
                          x + math.cos(a) * rr * .92, y + math.sin(a) * rr * .92, fill="#FFB300", width=max(2, rr // 9))
        c.create_oval(x - rr * .45, y - rr * .45, x + rr * .45, y + rr * .45, fill="#FFB300", outline="")

    def moon(x, y, rr):
        c.create_oval(x - rr * .5, y - rr * .5, x + rr * .5, y + rr * .5, fill="#FFE082", outline="")
        c.create_oval(x - rr * .22, y - rr * .6, x + rr * .72, y + rr * .4, fill=bg, outline="")

    if kind == "clear":
        sun(cx, cy, r) if is_day else moon(cx, cy, r)
    elif kind == "partly":
        sun(cx - .3 * r, cy - .3 * r, r * .75) if is_day else moon(cx - .3 * r, cy - .3 * r, r * .75)
        _cloud(c, cx + .1 * r, cy + .2 * r, r * .85, "#CFD8DC")
    elif kind == "cloudy":
        _cloud(c, cx, cy, r, "#B0BEC5")
    elif kind == "fog":
        _cloud(c, cx, cy - .25 * r, r * .8, "#CFD8DC")
        for i in range(3):
            c.create_line(cx - .7 * r, cy + (.35 + i * .22) * r, cx + .7 * r, cy + (.35 + i * .22) * r,
                          fill="#90A4AE", width=max(2, r // 10))
    elif kind in ("rain", "snow", "thunder"):
        _cloud(c, cx, cy - .25 * r, r * .85, "#78909C" if kind == "thunder" else "#B0BEC5")
        if kind == "rain":
            for i in range(3):
                x = cx - .4 * r + i * .4 * r
                c.create_line(x, cy + .35 * r, x - .12 * r, cy + .8 * r, fill="#1E88E5", width=max(2, r // 9))
        elif kind == "snow":
            for i in range(3):
                x = cx - .4 * r + i * .4 * r
                c.create_oval(x - 3, cy + .5 * r, x + 3, cy + .5 * r + 6, fill="white", outline="#64B5F6")
        else:
            c.create_polygon(cx + .05 * r, cy + .25 * r, cx - .3 * r, cy + .65 * r, cx - .02 * r, cy + .62 * r,
                             cx - .2 * r, cy + 1.0 * r, cx + .3 * r, cy + .5 * r, cx + .03 * r, cy + .52 * r,
                             fill="#FDD835", outline="#F9A825")


def _fmt(v, unit="", digits=0):
    return "—" if v is None else f"{v:.{digits}f}{unit}"


class WeatherTab(ttk.Frame):
    def __init__(self, master, weather, on_update=None):
        super().__init__(master, padding=10)
        self.weather, self.on_update = weather, on_update
        self._data, self._meta = None, {}
        self._busy, self._auto_job = False, None
        self._locations = {l["name"]: dict(l) for l in WEATHER_LOCATIONS}
        last = weather.last_location()
        if last and last["name"] not in self._locations:
            self._locations[last["name"]] = last
        self.var_loc = tk.StringVar(value=last["name"] if last else WEATHER_LOCATIONS[0]["name"])
        self.var_search = tk.StringVar()
        self.var_status = tk.StringVar(value="Chưa có dữ liệu")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_toolbar()
        self._build_top()
        self.chart = tk.Canvas(self, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, height=210)
        self.chart.grid(row=2, column=0, sticky="nsew", pady=8)
        self.rowconfigure(2, minsize=190)
        self.chart.bind("<Configure>", lambda _e: self._draw_chart())
        self.daily_frame = ttk.Frame(self)
        self.daily_frame.grid(row=3, column=0, sticky="ew")
        ttk.Label(self, text=f"Nguồn dữ liệu thời tiết: {WEATHER_SOURCE} · chỉ mang tính tham khảo",
                  foreground=COLOR_MUTED, font=FONT_SMALL).grid(row=4, column=0, sticky="w", pady=(8, 0))

                                                                            
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, text="Địa điểm:").grid(row=0, column=0, padx=(0, 4))
        self.cbo = ttk.Combobox(bar, textvariable=self.var_loc, state="readonly", width=28,
                                values=list(self._locations))
        self.cbo.grid(row=0, column=1, padx=(0, 14))
        self.cbo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(bar, text="Tìm địa điểm khác:").grid(row=0, column=2, padx=(0, 4))
        e = ttk.Entry(bar, textvariable=self.var_search, width=18)
        e.grid(row=0, column=3, padx=(0, 4))
        e.bind("<Return>", lambda _e: self.search())
        ttk.Button(bar, text="Tìm", command=self.search).grid(row=0, column=4, padx=(0, 10))
        self.btn_refresh = ttk.Button(bar, text="Cập nhật", style="Primary.TButton", command=lambda: self.refresh(force=True))
        self.btn_refresh.grid(row=0, column=5)
        self.lbl_status = ttk.Label(bar, textvariable=self.var_status, foreground=COLOR_MUTED, anchor="e")
        self.lbl_status.grid(row=1, column=0, columnspan=8, sticky="w", pady=(6, 0))
        self.bar = ttk.Progressbar(bar, mode="indeterminate", length=90)

    def _build_top(self):
        top = ttk.Frame(self)
        top.grid(row=1, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        card = tk.Frame(top, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, padx=14, pady=10)
        card.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.icon = tk.Canvas(card, width=80, height=80, bg=COLOR_CARD, highlightthickness=0)
        self.icon.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        self.lbl_temp = tk.Label(card, text="--°C", bg=COLOR_CARD, fg=COLOR_TEXT, font=("Segoe UI", 26, "bold"))
        self.lbl_temp.grid(row=0, column=1, sticky="w")
        self.lbl_desc = tk.Label(card, text="", bg=COLOR_CARD, fg=COLOR_PRIMARY, font=FONT_BOLD)
        self.lbl_desc.grid(row=1, column=1, sticky="nw")
        self.lbl_stats = tk.Label(card, text="", bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_BASE, justify="left", anchor="w")
        self.lbl_stats.grid(row=0, column=2, rowspan=2, sticky="w", padx=(18, 0))
        self.advice_box = ttk.Frame(top)
        self.advice_box.grid(row=0, column=1, sticky="nsew")
        self.advice_box.columnconfigure(0, weight=1)

                                                                           
    def _run_async(self, fn, on_ok, on_err):
        q = queue.Queue()

        def worker():
            try:
                q.put(("ok", fn()))
            except WeatherError as e:
                q.put(("err", str(e)))
            except Exception as e:                                                                      
                q.put(("err", f"Lỗi không xác định: {e}"))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if not self.winfo_exists():
                return
            try:
                kind, val = q.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            (on_ok if kind == "ok" else on_err)(val)

        self.after(100, poll)

    def _set_busy(self, busy):
        self._busy = busy
        self.btn_refresh.state(["disabled"] if busy else ["!disabled"])
        if busy:
            self.bar.grid(row=0, column=7, padx=(8, 0))
            self.bar.start(12)
            self.var_status.set("Đang tải dữ liệu thời tiết...")
        else:
            self.bar.stop()
            self.bar.grid_remove()

                                                                           
    def start(self):
        """Gọi một lần sau khi tab được dựng: tải dữ liệu và bật tự cập nhật định kỳ."""
        if self.on_update:
            self.on_update("Đang tải thời tiết...", [])
        self.refresh()
        self._auto_job = self.after(WEATHER_REFRESH_MINUTES * 60 * 1000, self._auto)

    def _auto(self):
        self.refresh()
        self._auto_job = self.after(WEATHER_REFRESH_MINUTES * 60 * 1000, self._auto)

    def destroy(self):
        if self._auto_job:
            try:
                self.after_cancel(self._auto_job)
            except tk.TclError:
                pass
        super().destroy()

    def refresh(self, force=False):
        loc = self._locations.get(self.var_loc.get())
        if self._busy or not loc:
            return
        self._set_busy(True)
        self._run_async(lambda: self.weather.get(loc, force=force), self._on_ok, self._on_err)

    def _on_ok(self, result):
        self._set_busy(False)
        self._data, self._meta = result["data"], result
        saved = result["saved_at"].strftime("%H:%M %d/%m")
        if result["stale"]:
            self.lbl_status.config(foreground=COLOR_ORANGE)
            self.var_status.set(f"Đang dùng dữ liệu cũ (lưu {saved}) - {result['error']}")
        else:
            self.lbl_status.config(foreground=COLOR_MUTED)
            self.var_status.set(("Dữ liệu đã lưu lúc " if result["from_cache"] else "Đã cập nhật lúc ") + saved)
        self._render()

    def _on_err(self, msg):
        self._set_busy(False)
        self.lbl_status.config(foreground=COLOR_DANGER)
        self.var_status.set(msg)
        if not self._data:
            self._render()
            if self.on_update:
                self.on_update("Thời tiết: không có dữ liệu", [])

    def search(self):
        q = self.var_search.get().strip()
        if len(q) < 2:
            messagebox.showwarning("Tìm địa điểm", "Nhập ít nhất 2 ký tự (ví dụ: Hải Phòng).")
            return
        if self._busy:
            return
        self._set_busy(True)

        def ok(results):
            self._set_busy(False)
            for r in results:
                self._locations[r["name"]] = r
            self.cbo["values"] = list(self._locations)
            self.var_loc.set(results[0]["name"])
            self.var_search.set("")
            self.refresh(force=True)

        def err(msg):
            self._set_busy(False)
            self.var_status.set("")
            messagebox.showwarning("Không tìm được địa điểm", msg)

        self._run_async(lambda: self.weather.search_location(q), ok, err)

                                                                           
    def reload(self):
        """Gọi khi làm mới chung (F5 / sau thao tác): chỉ vẽ lại từ dữ liệu đang có, KHÔNG gọi mạng."""
        if self._data:
            self._render()

    def _render(self):
        d = self._data
        self.icon.delete("all")
        if not d:
            self.lbl_temp.config(text="--°C")
            self.lbl_desc.config(text="Chưa có dữ liệu")
            self.lbl_stats.config(text="Bấm 'Cập nhật'\nđể thử lại.")
            self._set_advice([("info", "Không có dữ liệu thời tiết. Kiểm tra kết nối mạng rồi bấm 'Cập nhật'.")])
            self._draw_chart()
            self._build_daily([])
            return
        cur = d["current"]
        draw_icon(self.icon, cur["kind"], 40, 42, 32, cur["is_day"])
        self.lbl_temp.config(text=f"{cur['temp']:.0f}°C")
        self.lbl_desc.config(text=f"{cur['desc']} · {d['location']['name']}")
        self.lbl_stats.config(text=(f"Cảm giác như: {_fmt(cur['feels'], '°C')}\nĐộ ẩm: {_fmt(cur['humidity'], '%')}\n"
                                    f"Gió: {_fmt(cur['wind'], ' km/h')}\nMưa: {_fmt(cur['rain_mm'], ' mm', 1)}"))
        advice = d.get("advice") or []
        self._set_advice(advice)
        self._build_daily(d["daily"])
        self._draw_chart()
        if self.on_update:
            self.on_update(f"{cur['temp']:.0f}°C · {cur['desc']} · {d['location']['name'].split(',')[0]}", advice)

    def _set_advice(self, advice):
        for w in self.advice_box.winfo_children():
            w.destroy()
        tk.Label(self.advice_box, text="GỢI Ý VẬN HÀNH BÃI XE", bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_SMALL,
                 anchor="w").grid(row=0, column=0, sticky="ew")
        for i, (level, text) in enumerate(advice, start=1):
            tk.Label(self.advice_box, text=text, bg=LEVEL_COLORS.get(level, COLOR_PRIMARY), fg="white", font=FONT_BOLD,
                     anchor="w", justify="left", wraplength=640, padx=12, pady=6).grid(row=i, column=0, sticky="ew", pady=(3, 0))

    def _build_daily(self, days):
        for w in self.daily_frame.winfo_children():
            w.destroy()
        today = date.today()
        for i, day in enumerate(days):
            self.daily_frame.columnconfigure(i, weight=1, uniform="day")
            card = tk.Frame(self.daily_frame, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER,
                            padx=6, pady=6)
            card.grid(row=0, column=i, sticky="ew", padx=3)
            dt = date.fromisoformat(day["date"])
            name = "Hôm nay" if dt == today else f"{WEEKDAYS[dt.weekday()]} {dt:%d/%m}"
            tk.Label(card, text=name, bg=COLOR_CARD, font=FONT_BOLD).pack()
            ic = tk.Canvas(card, width=50, height=42, bg=COLOR_CARD, highlightthickness=0)
            ic.pack()
            draw_icon(ic, day["kind"], 25, 22, 17)
            tk.Label(card, text=f"{_fmt(day['tmax'], '°')} / {_fmt(day['tmin'], '°')}", bg=COLOR_CARD, font=FONT_BASE).pack()
            tk.Label(card, text=f"Mưa {_fmt(day['rain_prob'], '%')}", bg=COLOR_CARD, fg="#1E88E5", font=FONT_SMALL).pack()

    def _draw_chart(self):
        c = self.chart
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 120 or h < 100:
            return
        hours = self._data["hourly"] if self._data else []
        c.create_text(16, 16, text="Dự báo 24 giờ tới: nhiệt độ (°C) và xác suất mưa (%)", anchor="w", font=FONT_BOLD, fill=COLOR_TEXT)
        c.create_rectangle(w - 250, 10, w - 238, 22, fill=COLOR_ORANGE, outline="")
        c.create_text(w - 232, 16, text="Nhiệt độ", anchor="w", font=FONT_SMALL, fill=COLOR_MUTED)
        c.create_rectangle(w - 160, 10, w - 148, 22, fill="#90CAF9", outline="")
        c.create_text(w - 142, 16, text="Xác suất mưa", anchor="w", font=FONT_SMALL, fill=COLOR_MUTED)
        if not hours:
            c.create_text(w / 2, h / 2, text="Không có dữ liệu theo giờ", fill=COLOR_MUTED, font=FONT_BASE)
            return
        left, right, top, bottom = 46, 46, 38, 30
        pw, ph = w - left - right, h - top - bottom
        temps = [x["temp"] for x in hours]
        tmin, tmax = math.floor(min(temps)) - 1, math.ceil(max(temps)) + 1
        step = pw / len(hours)
        for i in range(5):
            y = top + ph * i / 4
            c.create_line(left, y, w - right, y, fill="#E8ECF1")
            c.create_text(left - 6, y, text=f"{tmax - (tmax - tmin) * i / 4:.0f}°", anchor="e", font=FONT_SMALL, fill=COLOR_MUTED)
            c.create_text(w - right + 6, y, text=f"{100 - 25 * i}%", anchor="w", font=FONT_SMALL, fill="#64B5F6")
        pts = []
        for i, x in enumerate(hours):
            p = x["rain_prob"]
            if p:
                c.create_rectangle(left + i * step + step * .18, top + ph * (1 - p / 100),
                                   left + (i + 1) * step - step * .18, top + ph, fill="#90CAF9", outline="")
            pts += [left + i * step + step / 2, top + ph * (1 - (x["temp"] - tmin) / (tmax - tmin))]
            if i % 2 == 0:
                hh = datetime.fromisoformat(x["time"]).hour
                c.create_text(left + i * step + step / 2, top + ph + 14, text=f"{hh}h", font=FONT_SMALL,
                              fill=COLOR_ORANGE if i == 0 else COLOR_MUTED)
        if len(pts) >= 4:
            c.create_line(*pts, fill=COLOR_ORANGE, width=3, smooth=True)
        for i in range(0, len(hours), 3):
            px, py = pts[2 * i], pts[2 * i + 1]
            c.create_oval(px - 3, py - 3, px + 3, py + 3, fill=COLOR_ORANGE, outline="white")
            c.create_text(px, py - 12, text=f"{hours[i]['temp']:.0f}°", font=FONT_SMALL, fill=COLOR_TEXT)