"""Tab Lịch sử gửi xe: bộ lọc + Treeview có sắp xếp theo cột."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from config import VEHICLE_TYPES, TICKET_STATUS_LABELS, ROW_COLORS
from gui.utils import format_dt, format_money, parse_date

COLUMNS = [                          
    ("ticket_id", "Mã vé", 120), ("plate", "Biển số", 110), ("type", "Loại xe", 80),
    ("slot", "Chỗ", 60), ("entry", "Giờ vào", 130), ("exit", "Giờ ra", 130),
    ("fee", "Phí", 100), ("status", "Trạng thái", 110),
]
ALL = "Tất cả"


class HistoryTab(ttk.Frame):
    def __init__(self, master, manager):
        super().__init__(master, padding=8)
        self.manager = manager
        self._rows = []                                      
        self._sort_state = {}
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self._build_filter()
        self._build_tree()

    def _build_filter(self):
        bar = ttk.LabelFrame(self, text=" Tìm kiếm / Lọc ", padding=8)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.var_plate = tk.StringVar()
        self.var_type = tk.StringVar(value=ALL)
        self.var_status = tk.StringVar(value=ALL)
        self.var_from = tk.StringVar()
        self.var_to = tk.StringVar()

        ttk.Label(bar, text="Biển số:").grid(row=0, column=0, padx=(0, 4))
        e = ttk.Entry(bar, textvariable=self.var_plate, width=14)
        e.grid(row=0, column=1, padx=(0, 10))
        e.bind("<Return>", lambda _e: self.reload())
        ttk.Label(bar, text="Loại xe:").grid(row=0, column=2, padx=(0, 4))
        ttk.Combobox(bar, textvariable=self.var_type, state="readonly", width=9,
                     values=[ALL] + list(VEHICLE_TYPES.values())).grid(row=0, column=3, padx=(0, 10))
        ttk.Label(bar, text="Trạng thái:").grid(row=0, column=4, padx=(0, 4))
        ttk.Combobox(bar, textvariable=self.var_status, state="readonly", width=9,
                     values=[ALL] + list(TICKET_STATUS_LABELS.values())).grid(row=0, column=5, padx=(0, 10))
        ttk.Label(bar, text="Từ ngày:").grid(row=1, column=0, pady=(6, 0), padx=(0, 4))
        ttk.Entry(bar, textvariable=self.var_from, width=14).grid(row=1, column=1, pady=(6, 0), padx=(0, 10))
        ttk.Label(bar, text="Đến ngày:").grid(row=1, column=2, pady=(6, 0), padx=(0, 4))
        ttk.Entry(bar, textvariable=self.var_to, width=11).grid(row=1, column=3, pady=(6, 0), padx=(0, 10))
        ttk.Label(bar, text="(dd/mm/yyyy)", foreground="#757575").grid(row=1, column=4, pady=(6, 0))
        ttk.Button(bar, text="Lọc", style="Primary.TButton", command=self.reload).grid(row=0, column=6, padx=6)
        ttk.Button(bar, text="Xóa lọc", command=self.clear_filter).grid(row=1, column=6, padx=6, pady=(6, 0))

    def _build_tree(self):
        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for i, (cid, title, width) in enumerate(COLUMNS):
            self.tree.heading(cid, text=title, command=lambda idx=i: self._sort_by(idx))
            self.tree.column(cid, width=width, anchor="center", stretch=True)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.tag_configure("parked", background=ROW_COLORS["parked"])
        self.tree.tag_configure("closed", background=ROW_COLORS["closed"])
        self.lbl_count = ttk.Label(self, text="")
        self.lbl_count.grid(row=2, column=0, sticky="w", pady=(6, 0))

                                                                        
    def clear_filter(self):
        self.var_plate.set("")
        self.var_type.set(ALL)
        self.var_status.set(ALL)
        self.var_from.set("")
        self.var_to.set("")
        self.reload()

    def _collect_filters(self):
        f = {}
        if self.var_plate.get().strip():
            f["plate"] = self.var_plate.get().strip()
        for key, label in VEHICLE_TYPES.items():
            if self.var_type.get() == label:
                f["vehicle_type"] = key
        for key, label in TICKET_STATUS_LABELS.items():
            if self.var_status.get() == label:
                f["status"] = key
        d_from = parse_date(self.var_from.get(), "'Từ ngày'")
        d_to = parse_date(self.var_to.get(), "'Đến ngày'")
        if d_from and d_to and d_from > d_to:
            raise ValueError("'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")
        if d_from:
            f["date_from"] = d_from
        if d_to:
            f["date_to"] = d_to
        return f

    def reload(self):
        try:
            filters = self._collect_filters()
        except ValueError as e:
            messagebox.showwarning("Bộ lọc không hợp lệ", str(e))
            return
        tickets = self.manager.get_history(filters)
        self._rows = []
        for t in tickets:
            values = (t.ticket_id, t.plate, VEHICLE_TYPES.get(t.vehicle_type, t.vehicle_type), t.slot_id or "—",
                      format_dt(t.entry_time), format_dt(t.exit_time),
                      format_money(t.fee) if t.exit_time else "—",
                      TICKET_STATUS_LABELS.get(t.status, t.status) + (" (vé tháng)" if t.is_monthly else ""))
            keys = (t.ticket_id, t.plate, values[2], (t.slot_id[0], int(t.slot_id[1:] or 0)) if t.slot_id else ("", 0),
                    t.entry_time, t.exit_time or datetime.min, t.fee, values[7])
            self._rows.append((values, keys, t.status))
        self._fill()

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        for values, _keys, tag in self._rows:
            self.tree.insert("", "end", values=values, tags=(tag,))
        self.lbl_count.config(text=f"Tổng số lượt: {len(self._rows)}   (bấm tiêu đề cột để sắp xếp)")

    def _sort_by(self, idx):
        reverse = self._sort_state.get(idx, False)
        self._rows.sort(key=lambda r: r[1][idx], reverse=reverse)
        self._sort_state = {idx: not reverse}
        self._fill()
