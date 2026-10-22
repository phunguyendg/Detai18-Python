"""Hộp thoại MUA / GIA HẠN vé tháng: báo giá trực tiếp -> thanh toán -> hóa đơn."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import VEHICLE_TYPES, COLOR_MUTED, COLOR_PRIMARY, FONT_BOLD
from gui import validators
from gui.contracts import ParkingError
from gui.dialog_base import BaseDialog
from gui.payment_dialog import PaymentDialog, ReceiptDialog, ensure_shift
from gui.utils import format_money, format_date, parse_date


class MonthlyPurchaseDialog(BaseDialog):
    def __init__(self, parent, manager, monthly, payments, on_done, get_cashier, prefill=None):
        super().__init__(parent, "Mua / Gia hạn vé tháng", "Báo giá tự động theo bảng giá, thanh toán và xuất hóa đơn")
        self.manager, self.monthly, self.payments = manager, monthly, payments
        self.on_done, self.get_cashier = on_done, get_cashier
        self.quote = None
        self._type_by_label = {v: k for k, v in VEHICLE_TYPES.items()}
        discounts = manager.get_prices()["monthly_discount"]
        self._months = sorted(discounts)
        self._month_labels = [f"{m} tháng" + (f" (giảm {discounts[m]}%)" if discounts[m] else "") for m in self._months]

        p = prefill or {}
        self.var_plate = tk.StringVar(value=p.get("plate", ""))
        self.var_owner = tk.StringVar(value=p.get("owner", ""))
        self.var_phone = tk.StringVar(value=p.get("phone", ""))
        self.var_type = tk.StringVar(value=p.get("vehicle_type", "motorbike"))
        pm = p.get("months")
        self.var_months = tk.StringVar(value=self._month_labels[self._months.index(pm)] if pm in self._months else self._month_labels[0])
        self.var_start = tk.StringVar(value=format_date(__import__("datetime").date.today()))
        self.var_quote = tk.StringVar()

        b = self.body
        b.columnconfigure(1, weight=1)
        r = 0
        for label, var in (("Biển số:", self.var_plate), ("Chủ xe:", self.var_owner), ("Số điện thoại:", self.var_phone)):
            ttk.Label(b, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 12))
            e = ttk.Entry(b, textvariable=var, width=30)
            e.grid(row=r, column=1, sticky="ew", pady=4)
            if label == "Biển số:":
                e.bind("<FocusOut>", self._autofill)
            r += 1
        ttk.Label(b, text="Loại xe:").grid(row=r, column=0, sticky="w", pady=4)
        tf = ttk.Frame(b)
        tf.grid(row=r, column=1, sticky="w")
        for i, (key, label) in enumerate(VEHICLE_TYPES.items()):
            ttk.Radiobutton(tf, text=label, value=key, variable=self.var_type).grid(row=0, column=i, padx=(0, 14))
        r += 1
        ttk.Label(b, text="Gói:").grid(row=r, column=0, sticky="w", pady=4)
        self.cbo_months = ttk.Combobox(b, textvariable=self.var_months, state="readonly", values=self._month_labels)
        self.cbo_months.grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        ttk.Label(b, text="Ngày bắt đầu:").grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(b, textvariable=self.var_start, width=30).grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        ttk.Label(b, text="Nếu xe đã có vé còn hạn: tự gia hạn nối tiếp ngày hết hạn cũ.", foreground=COLOR_MUTED).grid(
            row=r, column=0, columnspan=2, sticky="w")
        r += 1
        self.lbl_quote = tk.Label(b, textvariable=self.var_quote, justify="left", anchor="w", bg="#EAF2FD",
                                  fg=COLOR_PRIMARY, font=FONT_BOLD, padx=12, pady=10, wraplength=380)
        self.lbl_quote.grid(row=r, column=0, columnspan=2, sticky="ew", pady=10)
        r += 1
        row = ttk.Frame(b)
        row.grid(row=r, column=0, columnspan=2, sticky="e")
        ttk.Button(row, text="Đóng", command=self.destroy).grid(row=0, column=0, padx=4)
        self.btn_pay = ttk.Button(row, text="THANH TOÁN", style="Primary.TButton", command=self.on_pay)
        self.btn_pay.grid(row=0, column=1, padx=4)

        for v in (self.var_plate, self.var_type, self.var_months, self.var_start):
            v.trace_add("write", self._refresh_quote)
        self._refresh_quote()

                                                                          
    def _selected_months(self):
        return self._months[self._month_labels.index(self.var_months.get())]

    def _autofill(self, _e=None):
        plate = validators.normalize_plate(self.var_plate.get())
        for t in self.monthly.get_all_monthly_tickets():
            if t.plate == plate:
                if not self.var_owner.get().strip():
                    self.var_owner.set(t.owner)
                if not self.var_phone.get().strip():
                    self.var_phone.set(t.phone)
                self.var_type.set(t.vehicle_type)
                return

    def _refresh_quote(self, *_):
        try:
            plate = validators.normalize_plate(self.var_plate.get())
            if not validators.is_valid_plate(plate):
                raise ValueError("Nhập biển số hợp lệ (ví dụ 59A1-123.45) để xem báo giá.")
            start = parse_date(self.var_start.get(), "Ngày bắt đầu")
            q = self.monthly.quote_monthly(plate, self.var_type.get(), self._selected_months(), start)
        except (ValueError, ParkingError) as e:
            self.quote = None
            self.var_quote.set(str(e))
            self.btn_pay.state(["disabled"])
            return
        self.quote = q
        lines = [f"Giá gốc: {format_money(q['base'])}"]
        if q["discount"]:
            lines.append(f"Giảm giá {q['discount_pct']}%: -{format_money(q['discount'])}")
        lines += [f"TỔNG THANH TOÁN: {format_money(q['total'])}",
                  f"Hiệu lực: {format_date(q['start_date'])} → {format_date(q['end_date'])}"]
        if q["is_renewal"]:
            lines.append("(Gia hạn nối tiếp vé hiện tại)")
        self.var_quote.set("\n".join(lines))
        self.btn_pay.state(["!disabled"])

                                                                             
    def on_pay(self):
        if not self.quote:
            return
        plate = validators.normalize_plate(self.var_plate.get())
        owner, phone = self.var_owner.get().strip(), self.var_phone.get().strip()
        if not owner:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập tên chủ xe.", parent=self)
            return
        if not validators.is_valid_phone(phone):
            messagebox.showwarning("Số điện thoại không hợp lệ",
                                   "Nhập 10 số, bắt đầu bằng 0 hoặc +84.", parent=self)
            return
        if not ensure_shift(self, self.payments, self.get_cashier()):
            return
        q = self.quote
        lines = [("Biển số", plate), ("Chủ xe", owner), ("Gói", self.var_months.get()),
                 ("Hiệu lực", f"{format_date(q['start_date'])} → {format_date(q['end_date'])}"),
                 ("Giá gốc", format_money(q["base"]))]
        if q["discount"]:
            lines.append((f"Giảm giá {q['discount_pct']}%", "-" + format_money(q["discount"])))
        res = PaymentDialog(self, "Thanh toán vé tháng", lines, q["total"],
                            self.payments.get_payment_methods(), plate).show()
        if not res:
            return
        try:
            start = parse_date(self.var_start.get(), "Ngày bắt đầu")
            _ticket, pay = self.monthly.purchase_monthly_ticket(
                plate, owner, phone, self.var_type.get(), self._selected_months(), start,
                res["method"], res["received"], res["reference"])
        except (ValueError, ParkingError) as e:
            messagebox.showerror("Thanh toán không thành công", str(e), parent=self)
            return
        self.on_done()
        self.result = pay
        self.destroy()
        ReceiptDialog(self.parent, self.payments.build_receipt(pay.payment_id), f"{pay.payment_id}.txt").show()
