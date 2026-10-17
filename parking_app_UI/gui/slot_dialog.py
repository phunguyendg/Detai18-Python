"""Hộp thoại sửa trạng thái ô đỗ (Nhân viên & Quản trị): Trống <-> Bảo trì (bảo trì phải có lý do)."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import (SLOT_COLORS, STATUS_LABELS, STATUS_EMPTY, STATUS_OCCUPIED, STATUS_MAINTENANCE, COLOR_MUTED,
                    MIN_MAINTENANCE_REASON, FONT_BOLD)
from gui.contracts import ParkingError
from gui.dialog_base import BaseDialog


class SlotStatusDialog(BaseDialog):
    def __init__(self, parent, manager, slot_id):
        super().__init__(parent, f"Sửa trạng thái ô {slot_id}", "Ô có xe không đổi được trạng thái")
        self.manager, self.slot_id = manager, slot_id
        slot = manager.get_slot(slot_id)
        self.occupied = slot.status == STATUS_OCCUPIED
        self.var_status = tk.StringVar(value=slot.status if not self.occupied else STATUS_EMPTY)
        self.var_reason = tk.StringVar(value=slot.note)
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text="Trạng thái hiện tại:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        tk.Label(b, text=f"  {STATUS_LABELS[slot.status]}  ", bg=SLOT_COLORS[slot.status], fg="white",
                 font=FONT_BOLD).grid(row=0, column=1, sticky="w")
        if self.occupied:
            ttk.Label(b, text=f"Ô đang có xe {slot.current_plate}. Hãy cho xe ra trước khi đổi trạng thái.",
                      foreground=COLOR_MUTED, wraplength=320).grid(row=1, column=0, columnspan=2, sticky="w", pady=10)
        else:
            ttk.Label(b, text="Đổi thành:").grid(row=1, column=0, sticky="nw", pady=(10, 0))
            box = ttk.Frame(b)
            box.grid(row=1, column=1, sticky="w", pady=(8, 0))
            ttk.Radiobutton(box, text="Trống (sẵn sàng nhận xe)", value=STATUS_EMPTY, variable=self.var_status,
                            command=self._toggle).grid(row=0, column=0, sticky="w")
            ttk.Radiobutton(box, text="Bảo trì (không nhận xe)", value=STATUS_MAINTENANCE, variable=self.var_status,
                            command=self._toggle).grid(row=1, column=0, sticky="w")
            ttk.Label(b, text="Lý do bảo trì:").grid(row=2, column=0, sticky="w", pady=(10, 0))
            self.ent_reason = ttk.Entry(b, textvariable=self.var_reason, width=30)
            self.ent_reason.grid(row=2, column=1, sticky="ew", pady=(10, 0))
            self._toggle()
        row = ttk.Frame(b)
        row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(row, text="Đóng", command=self.destroy).grid(row=0, column=0, padx=4)
        if not self.occupied:
            ttk.Button(row, text="Lưu thay đổi", style="Primary.TButton", command=self.confirm).grid(row=0, column=1, padx=4)

    def _toggle(self):
        self.ent_reason.state(["!disabled"] if self.var_status.get() == STATUS_MAINTENANCE else ["disabled"])

    def confirm(self):
        flag = self.var_status.get() == STATUS_MAINTENANCE
        try:
            self.manager.set_slot_maintenance(self.slot_id, flag, self.var_reason.get())
        except ParkingError as e:
            messagebox.showwarning("Không thể đổi trạng thái", str(e), parent=self)
            return
        self.result = flag
        self.destroy()
