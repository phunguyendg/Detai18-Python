"""Tab Thống kê & Báo cáo: thẻ số liệu, thanh công suất, biểu đồ cột vẽ bằng Canvas."""
import math
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog

from config import (DATA_DIR, COLOR_CARD, COLOR_MUTED, COLOR_PRIMARY, COLOR_BORDER, COLOR_TEXT, COLOR_SUCCESS,
                    COLOR_DANGER, COLOR_ORANGE, COLOR_WARNING, FONT_BIG, FONT_BASE, FONT_BOLD, FONT_SMALL, SLOT_COLORS)
from gui.contracts import ParkingError
from gui.utils import format_money


class StatsTab(ttk.Frame):
    CARDS = [("total_slots", "Tổng số chỗ"), ("empty", "Chỗ trống"), ("occupied", "Đang sử dụng"),
             ("maintenance", "Bảo trì"), ("occupancy_rate", "Công suất"), ("vehicles_in", "Xe vào hôm nay"),
             ("vehicles_out", "Xe ra hôm nay"), ("revenue", "Doanh thu hôm nay")]

    ACCENTS = {"total_slots": COLOR_PRIMARY, "empty": SLOT_COLORS["empty"], "occupied": SLOT_COLORS["occupied"],
               "maintenance": SLOT_COLORS["maintenance"], "occupancy_rate": COLOR_WARNING,
               "vehicles_in": "#0097A7", "vehicles_out": "#7B1FA2", "revenue": COLOR_ORANGE}

    def __init__(self, master, stats_service):
        super().__init__(master, padding=8)
        self.stats = stats_service
        self._data = {}
        self._vars = {k: tk.StringVar(value="-") for k, _ in self.CARDS}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_cards()
        self._build_occupancy()
        self.chart = tk.Canvas(self, bg=COLOR_CARD, highlightthickness=1, highlightbackground="#CFD8DC")
        self.chart.grid(row=2, column=0, sticky="nsew", pady=8)
        self.chart.bind("<Configure>", lambda _e: self._draw_chart())
        self._build_buttons()

    def _build_cards(self):
        holder = ttk.Frame(self)
        holder.grid(row=0, column=0, sticky="ew")
        for i, (key, title) in enumerate(self.CARDS):
            holder.columnconfigure(i % 4, weight=1, uniform="card")
            card = tk.Frame(holder, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
            card.grid(row=i // 4, column=i % 4, sticky="ew", padx=5, pady=5)
            tk.Frame(card, bg=self.ACCENTS[key], width=6).pack(side="left", fill="y")      # vạch màu bên trái
            body = tk.Frame(card, bg=COLOR_CARD, padx=12, pady=9)
            body.pack(side="left", fill="both", expand=True)
            tk.Label(body, text=title.upper(), bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_SMALL).pack(anchor="w")
            tk.Label(body, textvariable=self._vars[key], bg=COLOR_CARD, fg=COLOR_TEXT, font=FONT_BIG).pack(anchor="w")

    def _build_occupancy(self):
        row = ttk.Frame(self)
        row.grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=5)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="Tỷ lệ lấp đầy", font=FONT_BOLD).grid(row=0, column=0, padx=(0, 10))
        self.bar = ttk.Progressbar(row, maximum=100, mode="determinate", style="Ok.Horizontal.TProgressbar")
        self.bar.grid(row=0, column=1, sticky="ew")
        self.lbl_pct = ttk.Label(row, text="0%", font=FONT_BOLD)
        self.lbl_pct.grid(row=0, column=2, padx=(10, 0))

    def _build_buttons(self):
        row = ttk.Frame(self)
        row.grid(row=3, column=0, sticky="e")
        ttk.Button(row, text="Làm mới", command=self.reload).grid(row=0, column=0, padx=4)
        self.btn_export = ttk.Button(row, text="Xuất báo cáo ca (CSV)", style="Primary.TButton",
                                     command=self.on_export)
        self.btn_export.grid(row=0, column=1, padx=4)

    def apply_permissions(self, is_admin):
        self.btn_export.state(["!disabled"] if is_admin else ["disabled"])

    # ------------------------------------------------------------ dữ liệu
    def reload(self):
        self._data = self.stats.get_statistics()
        d = self._data
        for key, _ in self.CARDS:
            val = d.get(key, 0)
            if key == "revenue":
                text = format_money(val)
            elif key == "occupancy_rate":
                text = f"{val:.0f}%"
            else:
                text = str(val)
            self._vars[key].set(text)
        rate = d.get("occupancy_rate", 0)
        self.bar["value"] = rate
        self.bar.config(style="Ok.Horizontal.TProgressbar" if rate < 60 else
                        "Warn.Horizontal.TProgressbar" if rate < 85 else "Crit.Horizontal.TProgressbar")
        self.lbl_pct.config(text=f"{rate:.0f}%")
        self._draw_chart()

    def _draw_chart(self):
        c = self.chart
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 80 or h < 80:
            return
        data = {int(k): v for k, v in self._data.get("hourly_counts", {}).items()}
        left, right, top, bottom = 45, 15, 35, 30
        pw, ph = w - left - right, h - top - bottom
        peak = max(list(data.values()) + [1])
        top_val = max(4, math.ceil(peak / 4) * 4)
        c.create_text(left, 16, text="Số lượt xe vào theo giờ", font=FONT_BOLD, anchor="w", fill=COLOR_TEXT)
        c.create_rectangle(w - right - 150, 11, w - right - 138, 23, fill=COLOR_ORANGE, outline="")
        c.create_text(w - right - 132, 17, text="Giờ hiện tại", font=FONT_SMALL, anchor="w", fill=COLOR_MUTED)
        now_hour = datetime.now().hour
        for i in range(5):                                   # lưới ngang + nhãn trục Y
            y = top + ph * (1 - i / 4)
            c.create_line(left, y, w - right, y, fill="#E8ECF1")
            c.create_text(left - 6, y, text=str(top_val * i // 4), anchor="e", fill=COLOR_MUTED, font=("Segoe UI", 8))
        bw = pw / 24
        for hour in range(24):
            v = data.get(hour, 0)
            x1, x2 = left + hour * bw + 3, left + (hour + 1) * bw - 3
            y1 = top + ph * (1 - v / top_val)
            if v:
                c.create_rectangle(x1, y1, x2, top + ph, fill=COLOR_ORANGE if hour == now_hour else COLOR_PRIMARY,
                                   outline="")
                c.create_text((x1 + x2) / 2, y1 - 8, text=str(v), font=("Segoe UI", 8))
            c.create_text((x1 + x2) / 2, top + ph + 12, text=str(hour), font=FONT_SMALL,
                          fill=COLOR_ORANGE if hour == now_hour else COLOR_MUTED)
        c.create_line(left, top + ph, w - right, top + ph, fill="#90A4AE")

    def on_export(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default = f"shift_report_{datetime.now():%Y%m%d_%H%M}.csv"
        path = filedialog.asksaveasfilename(title="Lưu báo cáo ca", initialdir=DATA_DIR, initialfile=default,
                                            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            saved = self.stats.export_shift_report(path)
        except (ParkingError, OSError) as e:
            messagebox.showerror("Xuất báo cáo thất bại", str(e))
            return
        messagebox.showinfo("Thành công", f"Đã xuất báo cáo ca:\n{saved}")
