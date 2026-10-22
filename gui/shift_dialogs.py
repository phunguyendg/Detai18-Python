"""Mở ca, chốt ca (đối soát tiền mặt) và lịch sử ca trực."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import (DEFAULT_OPENING_CASH, PAYMENT_METHODS, COLOR_SUCCESS, COLOR_DANGER, COLOR_MUTED,
                    FONT_BOLD, FONT_BASE, ROW_COLORS)
from gui import validators
from gui.contracts import ParkingError
from gui.dialog_base import BaseDialog
from gui.utils import format_money, format_dt


def money_text(n) -> str:
    return f"{int(n):,}".replace(",", ".")


class OpenShiftDialog(BaseDialog):
    def __init__(self, parent, payments, cashier=""):
        super().__init__(parent, "Mở ca trực", "Đếm tiền lẻ đầu ca trước khi bắt đầu thu tiền")
        self.payments = payments
        self.var_cashier = tk.StringVar(value=cashier)
        self.var_cash = tk.StringVar(value=money_text(DEFAULT_OPENING_CASH))
        b = self.body
        b.columnconfigure(1, weight=1)
        ttk.Label(b, text="Thu ngân:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 10))
        ttk.Entry(b, textvariable=self.var_cashier, width=26, state="readonly").grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(b, text="Tiền lẻ đầu ca (đ):").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 10))
        e = ttk.Entry(b, textvariable=self.var_cash, width=26)
        e.grid(row=1, column=1, sticky="ew", pady=6)
        e.bind("<Return>", lambda _e: self.confirm())
        ttk.Label(b, text="Ca được mở đứng tên tài khoản của bạn. Chỉ thu ngân của ca mới được thu tiền gửi xe và bán vé tháng.",
                  foreground=COLOR_MUTED, wraplength=320).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 8))
        row = ttk.Frame(b)
        row.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(row, text="Hủy", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="Mở ca", style="Primary.TButton", command=self.confirm).grid(row=0, column=1, padx=4)

    def confirm(self):
        try:
            cash = validators.parse_money(self.var_cash.get())
            self.result = self.payments.open_shift(self.var_cashier.get(), cash)
        except (ValueError, ParkingError) as e:
            messagebox.showwarning("Không thể mở ca", str(e), parent=self)
            return
        self.destroy()


class CloseShiftDialog(BaseDialog):
    def __init__(self, parent, payments):
        super().__init__(parent, "Chốt ca trực", "Đối soát tiền mặt: đếm thực tế so với số liệu hệ thống")
        self.payments = payments
        sh = payments.current_shift()
        summ = payments.shift_summary(sh.shift_id)
        self.expected = sh.opening_cash + summ["cash"]
        self.var_counted = tk.StringVar()
        self.var_note = tk.StringVar()
        self.var_diff = tk.StringVar(value="Nhập số tiền đếm được")
        b = self.body
        b.columnconfigure(1, weight=1)
        lines = [("Ca", f"{sh.shift_id} · {sh.cashier}"), ("Mở lúc", format_dt(sh.opened_at)),
                 ("Tiền đầu ca", format_money(sh.opening_cash))]
        lines += [(f"Thu - {PAYMENT_METHODS[k]}", format_money(v)) for k, v in summ["by_method"].items() if v]
        lines += [("Tổng thu trong ca", f"{format_money(summ['total'])} ({summ['count']} giao dịch)"),
                  ("Tiền mặt dự kiến trong két", format_money(self.expected))]
        for i, (k, v) in enumerate(lines):
            last = i == len(lines) - 1
            ttk.Label(b, text=k + ":", font=FONT_BOLD if last else FONT_BASE).grid(row=i, column=0, sticky="w", pady=2, padx=(0, 16))
            ttk.Label(b, text=v, font=FONT_BOLD).grid(row=i, column=1, sticky="e", pady=2)
        r = len(lines)
        ttk.Separator(b).grid(row=r, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(b, text="Tiền mặt đếm thực tế (đ):").grid(row=r + 1, column=0, sticky="w", pady=4)
        e = ttk.Entry(b, textvariable=self.var_counted, width=20)
        e.grid(row=r + 1, column=1, sticky="ew", pady=4)
        self.var_counted.trace_add("write", self._update_diff)
        self.lbl_diff = ttk.Label(b, textvariable=self.var_diff, font=FONT_BOLD, foreground=COLOR_MUTED)
        self.lbl_diff.grid(row=r + 2, column=0, columnspan=2, sticky="w")
        ttk.Label(b, text="Ghi chú (bắt buộc nếu lệch):").grid(row=r + 3, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.var_note, width=20).grid(row=r + 3, column=1, sticky="ew", pady=4)
        row = ttk.Frame(b)
        row.grid(row=r + 4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(row, text="Hủy", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="Chốt ca", style="Danger.TButton", command=self.confirm).grid(row=0, column=1, padx=4)
        e.focus_set()

    def _update_diff(self, *_):
        try:
            diff = validators.parse_money(self.var_counted.get()) - self.expected
        except ValueError:
            self.var_diff.set("Nhập số tiền đếm được")
            self.lbl_diff.config(foreground=COLOR_MUTED)
            return
        if diff == 0:
            self.var_diff.set("✔ Khớp với hệ thống")
            self.lbl_diff.config(foreground=COLOR_SUCCESS)
        else:
            self.var_diff.set(("Thừa " if diff > 0 else "Thiếu ") + format_money(abs(diff)))
            self.lbl_diff.config(foreground=COLOR_DANGER)

    def confirm(self):
        try:
            counted = validators.parse_money(self.var_counted.get())
            if counted != self.expected and not self.var_note.get().strip():
                raise ValueError("Tiền đếm được lệch so với hệ thống - hãy nhập ghi chú giải trình.")
            if not messagebox.askyesno("Xác nhận chốt ca", "Chốt ca không thể hoàn tác. Tiếp tục?", parent=self):
                return
            self.result = self.payments.close_shift(counted, self.var_note.get())
        except (ValueError, ParkingError) as e:
            messagebox.showwarning("Không thể chốt ca", str(e), parent=self)
            return
        self.destroy()


class ShiftHistoryDialog(BaseDialog):
    COLS = [("id", "Mã ca", 120), ("cashier", "Thu ngân", 80), ("open", "Mở lúc", 120), ("close", "Chốt lúc", 120),
            ("opening", "Đầu ca", 90), ("expected", "Hệ thống", 100), ("counted", "Đếm thực tế", 100),
            ("diff", "Chênh lệch", 90), ("note", "Ghi chú", 160)]

    def __init__(self, parent, payments):
        super().__init__(parent, "Lịch sử ca trực")
        b = self.body
        b.columnconfigure(0, weight=1)
        tree = ttk.Treeview(b, columns=[c[0] for c in self.COLS], show="headings", height=10)
        for cid, title, w in self.COLS:
            tree.heading(cid, text=title)
            tree.column(cid, width=w, anchor="center")
        tree.tag_configure("bad", background=ROW_COLORS["parked"])
        tree.tag_configure("open", background=ROW_COLORS["expiring"])
        for s in payments.get_shifts():
            if s.is_open:
                vals = (s.shift_id, s.cashier, format_dt(s.opened_at), "Đang mở", format_money(s.opening_cash),
                        "—", "—", "—", "")
                tag = "open"
            else:
                vals = (s.shift_id, s.cashier, format_dt(s.opened_at), format_dt(s.closed_at),
                        format_money(s.opening_cash), format_money(s.expected_cash), format_money(s.counted_cash),
                        format_money(s.difference), s.note)
                tag = "bad" if s.difference else ""
            tree.insert("", "end", values=vals, tags=(tag,))
        tree.grid(row=0, column=0, sticky="nsew")
        ttk.Button(b, text="Đóng", command=self.destroy).grid(row=1, column=0, sticky="e", pady=(10, 0))
