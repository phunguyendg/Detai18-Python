"""Form XE VÀO và XE RA (cột bên phải tab Tổng quan)."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import VEHICLE_TYPES, COLOR_SUCCESS, COLOR_PRIMARY, COLOR_ORANGE, COLOR_CARD, FONT_BOLD, FONT_BASE
from gui import validators
from gui.contracts import ParkingError
from gui.payment_dialog import PaymentDialog, ReceiptDialog, ensure_shift
from gui.utils import format_money, format_duration, format_dt

from config import AUTO_SLOT_LABEL as AUTO_SLOT                              


class EntryExitPanel(ttk.Frame):
    def __init__(self, master, manager, monthly, payments, on_data_changed, notify=None, get_cashier=None, customers=None):
        super().__init__(master, style="Card.TFrame", padding=12)
        self.notify = notify                                                                   
        self.manager = manager
        self.monthly = monthly
        self.payments = payments
        self.customers = customers
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
        self.refresh_slot_choices()

    def _build_entry_box(self):
        header = tk.Label(self, text="▶  XE VÀO (NHẬN XE VÀO BÃI)", bg=COLOR_PRIMARY, fg="white", font=FONT_BOLD,
                          anchor="w", padx=10, pady=6, cursor="hand2")
        header.grid(row=0, column=0, sticky="ew")
        header.bind("<Button-1>", self.show_verified_vehicles)
        box = ttk.Frame(self, style="Card.TFrame", padding=(2, 12, 2, 8))
        box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
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
                  font=FONT_BOLD).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Button(box, text="NHẬN XE VÀO BÃI", style="Primary.TButton",
                   command=self.on_vehicle_entry).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        
        btn_veh = ttk.Button(box, text="📋 Xem xe đã xác minh...", command=self.show_verified_vehicles)
        btn_veh.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def show_verified_vehicles(self, _event=None):
        """Hiển thị các xe đã xác minh chưa vào bãi."""
        if self.customers is None:
            messagebox.showinfo("Xe đã xác minh", "Chưa có dữ liệu xe khách hàng.")
            return
        win = tk.Toplevel(self)
        win.title("Danh sách xe đã xác minh")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.geometry("560x420")
        win.minsize(500, 320)
        ttk.Label(win, text="Xe đã xác minh - sẵn sàng vào bãi", font=FONT_BOLD).pack(anchor="w", padx=14, pady=(12, 4))
        ttk.Label(win, text="Nhấp đúp vào dòng xe hoặc chọn xe rồi bấm nút bên dưới để nhận vào bãi.",
                  font=FONT_SMALL, foreground=COLOR_MUTED).pack(anchor="w", padx=14, pady=(0, 8))

        # Đặt thanh nút bấm ở DƯỚI CÙNG trước (side="bottom") để luôn hiển thị và không bao giờ bị che khuất
        btn_bar = ttk.Frame(win, padding=(14, 8, 14, 12))
        btn_bar.pack(side="bottom", fill="x")

        # Khung chứa bảng danh sách xe ở giữa (expand=True)
        frame = ttk.Frame(win, padding=(14, 0, 14, 4))
        frame.pack(side="top", fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("name", "plate", "type"), show="headings", height=8)
        tree.heading("name", text="Tên khách hàng")
        tree.heading("plate", text="Biển số")
        tree.heading("type", text="Loại xe")
        tree.column("name", width=200, anchor="w")
        tree.column("plate", width=140, anchor="center")
        tree.column("type", width=110, anchor="center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        
        # Lấy danh sách xe đã xác minh nhưng chưa ở trong bãi
        vehicles = getattr(self.customers, "_vehicles", [])
        if isinstance(vehicles, dict):
            veh_list = list(vehicles.values())
        else:
            veh_list = list(vehicles)

        parked_plates = {t.plate for t in getattr(self.manager, 'tickets', []) if getattr(t, 'status', '') == 'parked'}
        rows = []
        for v in veh_list:
            plate = v.get("plate", "")
            is_verified = v.get("status") in ("verified", "approved", "ready") or v.get("verified") is True
            if not is_verified or plate in parked_plates:
                continue
            username = v.get("username", "")
            vtype = VEHICLE_TYPES.get(v.get("vehicle_type", "motorbike"), "Xe máy")
            rows.append((username, plate, vtype))

        for u, p, vt in sorted(rows, key=lambda row: row[1]):
            tree.insert("", "end", values=(u, p, vt))
        if not rows:
            tree.insert("", "end", values=("Không có xe nào sẵn sàng", "—", "—"))

        def pick():
            sel = tree.selection()
            if sel:
                item = tree.item(sel[0])
                vals = item.get("values", [])
                if vals and vals[1] != "—":
                    self.var_plate.set(vals[1])
                    if vals[2] == "Ô tô":
                        self.var_type.set("car")
                    else:
                        self.var_type.set("motorbike")
                    win.destroy()
                    self.ent_plate.focus_set()

        def enter_now():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Chưa chọn xe", "Vui lòng chọn một xe trong danh sách.")
                return
            item = tree.item(sel[0])
            vals = item.get("values", [])
            if not vals or vals[1] == "—":
                messagebox.showinfo("Thông báo", "Không có xe hợp lệ được chọn.")
                return
            plate = vals[1]
            vtype = "car" if vals[2] == "Ô tô" else "motorbike"
            self.var_plate.set(plate)
            self.var_type.set(vtype)
            win.destroy()
            # Thực hiện nhận xe vào bãi ngay lập tức
            self.on_vehicle_entry()

        # Nút bấm hành động - Luôn nhìn thấy 100%
        btn_enter = ttk.Button(btn_bar, text="▶ CHO XE VÀO BÃI NGAY", style="Primary.TButton", command=enter_now)
        btn_enter.pack(side="left", padx=(0, 8))
        btn_pick = ttk.Button(btn_bar, text="Điền vào Form", command=pick)
        btn_pick.pack(side="left")
        ttk.Button(btn_bar, text="Đóng", command=win.destroy).pack(side="right")

        # Hỗ trợ nhấp đúp hoặc gõ phím Enter trên bảng để cho xe vào bãi ngay
        tree.bind("<Double-1>", lambda _e: enter_now())
        tree.bind("<Return>", lambda _e: enter_now())

        # Tự động chọn dòng đầu tiên nếu có dữ liệu
        all_items = tree.get_children()
        if all_items and rows:
            tree.selection_set(all_items[0])
            tree.focus(all_items[0])

                                                                                     
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
