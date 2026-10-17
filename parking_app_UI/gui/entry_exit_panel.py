"""Form XE VÀO và XE RA (cột bên phải tab Tổng quan)."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import VEHICLE_TYPES, COLOR_SUCCESS, COLOR_PRIMARY, COLOR_ORANGE, COLOR_CARD, FONT_BOLD, FONT_BASE
from gui import validators
from gui.contracts import ParkingError
from gui.payment_dialog import PaymentDialog, ReceiptDialog, ensure_shift
from gui.utils import format_money, format_duration, format_dt

from config import AUTO_SLOT_LABEL as AUTO_SLOT   # "Tự động (hệ thống chọn)"


class EntryExitPanel(ttk.Frame):
    def __init__(self, master, manager, monthly, payments, on_data_changed, notify=None, get_cashier=None):
        super().__init__(master, style="Card.TFrame", padding=12)
        self.notify = notify          # notify(text, kind): thông báo nhanh không chặn thao tác
        self.manager = manager
        self.monthly = monthly
        self.payments = payments
        self.get_cashier = get_cashier or (lambda: "")
        self.on_data_changed = on_data_changed

        self.var_plate = tk.StringVar()
        self.var_type = tk.StringVar(value="motorbike")
        self.var_slot = tk.StringVar(value=AUTO_SLOT)
        self.var_monthly = tk.StringVar()
        self.var_exit_key = tk.StringVar()
        self.var_lost = tk.BooleanVar(value=False)
        self.var_exit_info = tk.StringVar(value="Nhập biển số hoặc mã vé rồi bấm 'Tính phí'.")

        self.columnconfigure(0, weight=1)
        self._build_entry_box()
        self._build_exit_box()
        self.refresh_slot_choices()

    # ------------------------------------------------------------ dựng giao diện
    def _section_header(self, row, text, color):
        tk.Label(self, text=text, bg=color, fg="white", font=FONT_BOLD, anchor="w", padx=10, pady=5).grid(
            row=row, column=0, sticky="ew")

    def _build_entry_box(self):
        self._section_header(0, "▶  XE VÀO", COLOR_PRIMARY)
        box = ttk.Frame(self, style="Card.TFrame", padding=(2, 10, 2, 4))
        box.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Biển số", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        self.ent_plate = ttk.Entry(box, textvariable=self.var_plate, font=("Segoe UI", 11, "bold"))
        self.ent_plate.grid(row=0, column=1, sticky="ew", pady=5)
        self.ent_plate.bind("<KeyRelease>", self._check_monthly)
        self.ent_plate.bind("<Return>", lambda _e: self.on_vehicle_entry())

        ttk.Label(box, text="Loại xe", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        types = ttk.Frame(box, style="Card.TFrame")
        types.grid(row=1, column=1, sticky="w")
        for i, (key, label) in enumerate(VEHICLE_TYPES.items()):
            ttk.Radiobutton(types, text=label, value=key, variable=self.var_type,
                            style="Card.TRadiobutton").grid(row=0, column=i, padx=(0, 14))

        ttk.Label(box, text="Chỗ đỗ", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.cbo_slot = ttk.Combobox(box, textvariable=self.var_slot, state="readonly", width=12)
        self.cbo_slot.grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(box, textvariable=self.var_monthly, style="Card.TLabel", foreground=COLOR_SUCCESS,
                  font=FONT_BOLD).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(box, text="NHẬN XE", style="Primary.TButton",
                   command=self.on_vehicle_entry).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _build_exit_box(self):
        self._section_header(2, "◀  XE RA", COLOR_ORANGE)
        box = ttk.Frame(self, style="Card.TFrame", padding=(2, 10, 2, 0))
        box.grid(row=3, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Biển số / Mã vé", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        ent = ttk.Entry(box, textvariable=self.var_exit_key, font=("Segoe UI", 11, "bold"))
        ent.grid(row=0, column=1, sticky="ew", pady=5)
        ent.bind("<Return>", lambda _e: self.on_estimate())

        ttk.Checkbutton(box, text="Khách mất vé (phụ thu theo bảng giá)", variable=self.var_lost,
                        style="Card.TCheckbutton", command=self._on_lost_toggle).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Button(box, text="Tính phí", command=self.on_estimate).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=5)
        info = tk.Label(box, textvariable=self.var_exit_info, wraplength=250, justify="left", anchor="w",
                        bg="#EAF2FD", fg=COLOR_PRIMARY, font=FONT_BASE, padx=10, pady=8)
        info.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Button(box, text="THANH TOÁN & CHO XE RA", style="Danger.TButton",
                   command=self.on_vehicle_exit).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    # ------------------------------------------------------------ API cho MainWindow
    def refresh_slot_choices(self):
        free = [s.slot_id for s in self.manager.get_all_slots() if s.status == "empty"]
        self.cbo_slot["values"] = [AUTO_SLOT] + free
        if self.var_slot.get() not in self.cbo_slot["values"]:
            self.var_slot.set(AUTO_SLOT)

    def set_entry_slot(self, slot_id):
        """Click ô trống trên sơ đồ -> điền vào form xe vào."""
        self.refresh_slot_choices()
        if slot_id in self.cbo_slot["values"]:
            self.var_slot.set(slot_id)
        self.ent_plate.focus_set()

    def set_exit_plate(self, plate):
        """Click ô có xe -> điền biển số vào form xe ra và tính phí luôn."""
        self.var_exit_key.set(plate)
        self.on_estimate()

    # ------------------------------------------------------------ xử lý
    def _check_monthly(self, _event=None):
        plate = validators.normalize_plate(self.var_plate.get())
        ok = validators.is_valid_plate(plate) and self.monthly.check_monthly_ticket(plate)
        self.var_monthly.set("✔ Xe có vé tháng hợp lệ (miễn phí)" if ok else "")

    def on_vehicle_entry(self):
        plate = validators.normalize_plate(self.var_plate.get())
        if not plate:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập biển số xe.")
            self.ent_plate.focus_set()
            return
        if not validators.is_valid_plate(plate):
            messagebox.showwarning("Biển số không hợp lệ", "Ví dụ hợp lệ: 59A1-123.45 hoặc 51F-123.45")
            return
        slot_id = self.var_slot.get()
        slot_id = None if slot_id == AUTO_SLOT else slot_id
        try:
            ticket = self.manager.vehicle_entry(plate, self.var_type.get(), slot_id)
        except ParkingError as e:
            messagebox.showerror("Không thể nhận xe", str(e))
            return
        note = "\nXe có vé tháng: miễn phí." if getattr(ticket, "is_monthly", False) else ""
        self._say("Nhận xe thành công",
                  f"Mã vé: {ticket.ticket_id}\nBiển số: {ticket.plate}\n"
                  f"Chỗ đỗ: {ticket.slot_id}\nGiờ vào: {format_dt(ticket.entry_time)}{note}",
                  f"✔ Nhận xe {ticket.plate} · Ô {ticket.slot_id} · Mã vé {ticket.ticket_id}"
                  + (" · Vé tháng" if note else ""))
        self.var_plate.set("")
        self.var_monthly.set("")
        self.var_slot.set(AUTO_SLOT)
        self.on_data_changed()

    def _say(self, title, long_text, short_text):
        """Có notify (toast trên header) thì dùng, không thì hiện hộp thoại."""
        if self.notify:
            self.notify(short_text, "success")
        else:
            messagebox.showinfo(title, long_text)

    def on_estimate(self):
        key = self.var_exit_key.get().strip()
        if not key:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập biển số hoặc mã vé.")
            return None
        try:
            minutes, fee = self.manager.estimate_fee(key, lost_ticket=self.var_lost.get())
        except ParkingError as e:
            self.var_exit_info.set("")
            messagebox.showerror("Không tìm thấy xe", str(e))
            return None
        extra = "\n(đã gồm phụ thu mất vé)" if self.var_lost.get() else ""
        self.var_exit_info.set(f"Thời gian gửi: {format_duration(minutes)}\nPhí tạm tính: {format_money(fee)}{extra}")
        return minutes, fee

    def _on_lost_toggle(self):
        if self.var_lost.get():
            messagebox.showinfo("Mất vé", "Hãy kiểm tra giấy tờ xe (cà vẹt/CCCD) trùng với chủ xe trước khi cho xe ra.")
        if self.var_exit_key.get().strip():
            self.on_estimate()

    def on_vehicle_exit(self):
        est = self.on_estimate()
        if est is None:
            return
        minutes, fee = est
        key, lost = self.var_exit_key.get().strip(), self.var_lost.get()
        if fee > 0:
            if not ensure_shift(self, self.payments, self.get_cashier()):
                return
            lines = [("Xe / vé", key), ("Thời gian gửi", format_duration(minutes))]
            if lost:
                lines.append(("Ghi chú", "Mất vé - có phụ thu"))
            pay = PaymentDialog(self, "Thanh toán phí gửi xe", lines, fee,
                                self.payments.get_payment_methods(), key).show()
            if not pay:
                return
        else:
            if not messagebox.askyesno("Xác nhận", f"Thời gian gửi: {format_duration(minutes)}\n"
                                       "Miễn phí (vé tháng hoặc trong thời gian miễn phí).\n\nCho xe ra?"):
                return
            pay = {"method": "cash", "received": None, "reference": None}
        try:
            ticket = self.manager.vehicle_exit(key, lost_ticket=lost, method=pay["method"],
                                               received=pay["received"], reference=pay["reference"])
        except ParkingError as e:
            messagebox.showerror("Không thể cho xe ra", str(e))
            return
        self.var_exit_key.set("")
        self.var_lost.set(False)
        self.var_exit_info.set("Nhập biển số hoặc mã vé rồi bấm 'Tính phí'.")
        self.on_data_changed()
        if self.notify:
            self.notify(f"✔ Xe {ticket.plate} đã ra · Thu {format_money(ticket.fee)} · Ô {ticket.slot_id} trống", "success")
        if ticket.payment_id:
            ReceiptDialog(self, self.payments.build_receipt(ticket.payment_id), f"{ticket.payment_id}.txt").show()
