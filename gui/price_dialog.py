"""Bảng giá (chỉ Quản trị): giá giờ, phút miễn phí, phụ thu mất vé, giá vé tháng, % giảm giá."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import VEHICLE_TYPES
from gui.contracts import ParkingError
from gui.dialog_base import BaseDialog


class PriceDialog(BaseDialog):
    def __init__(self, parent, manager):
        super().__init__(parent, "Bảng giá", "Đơn vị: đồng. Áp dụng ngay cho các giao dịch mới")
        self.manager = manager
        p = manager.get_prices()
        self._vars = {}
        b = self.body
        ttk.Label(b, text="").grid(row=0, column=0)
        for i, (key, label) in enumerate(VEHICLE_TYPES.items(), start=1):
            ttk.Label(b, text=label, font=("Segoe UI", 10, "bold")).grid(row=0, column=i, padx=8)
        rows = [("hourly", "Giá mỗi giờ gửi"), ("lost_ticket", "Phụ thu mất vé"), ("monthly", "Giá vé tháng (1 tháng)")]
        for r, (group, title) in enumerate(rows, start=1):
            ttk.Label(b, text=title + ":").grid(row=r, column=0, sticky="w", pady=4, padx=(0, 12))
            for c, vt in enumerate(VEHICLE_TYPES, start=1):
                var = tk.StringVar(value=str(p[group][vt]))
                self._vars[(group, vt)] = var
                ttk.Entry(b, textvariable=var, width=12).grid(row=r, column=c, padx=8, pady=4)
        r = len(rows) + 1
        ttk.Label(b, text="Miễn phí N phút đầu:").grid(row=r, column=0, sticky="w", pady=4)
        self._free = tk.StringVar(value=str(p["free_minutes"]))
        ttk.Entry(b, textvariable=self._free, width=12).grid(row=r, column=1, padx=8, pady=4)
        r += 1
        ttk.Label(b, text="Giảm giá vé tháng (%):", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(10, 2))
        self._disc = {}
        r += 1
        discounts = p["monthly_discount"]
        for c, months in enumerate(m for m in sorted(discounts) if m != 1):
            ttk.Label(b, text=f"{months} tháng").grid(row=r, column=1 + c, pady=2)
            var = tk.StringVar(value=str(discounts[months]))
            self._disc[months] = var
            ttk.Entry(b, textvariable=var, width=8).grid(row=r + 1, column=1 + c, padx=8, pady=2)
        r += 2
        row = ttk.Frame(b)
        row.grid(row=r, column=0, columnspan=4, sticky="e", pady=(14, 0))
        ttk.Button(row, text="Hủy", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="Lưu bảng giá", style="Primary.TButton", command=self.save).grid(row=0, column=1, padx=4)

    def save(self):
        try:
            prices = {g: {} for g in ("hourly", "lost_ticket", "monthly")}
            for (group, vt), var in self._vars.items():
                prices[group][vt] = int(var.get().replace(".", "").strip())
            prices["free_minutes"] = int(self._free.get().strip())
            prices["monthly_discount"] = {1: 0, **{m: int(v.get().strip()) for m, v in self._disc.items()}}
        except ValueError:
            messagebox.showwarning("Dữ liệu không hợp lệ", "Mọi ô giá phải là số nguyên không âm.", parent=self)
            return
        try:
            self.manager.set_prices(prices)
        except ParkingError as e:
            messagebox.showwarning("Không thể lưu bảng giá", str(e), parent=self)
            return
        self.result = prices
        messagebox.showinfo("Thành công", "Đã cập nhật bảng giá.", parent=self)
        self.destroy()
