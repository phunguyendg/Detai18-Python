"""Cổng KHÁCH HÀNG: chỉ xem tình trạng bãi, xe/vé/lịch sử/hóa đơn của chính mình, gửi yêu cầu gia hạn vé tháng.
Khách KHÔNG có các tab của nhân viên (xe vào/ra, thu tiền, ca, thống kê doanh thu...)."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import (AUTO_SLOT_LABEL, VEHICLE_TYPES, TICKET_STATUS_LABELS, TXN_KINDS, PAYMENT_METHODS, SLOT_COLORS, COLOR_CARD,
                    COLOR_BORDER, COLOR_MUTED, COLOR_PRIMARY, COLOR_TEXT, COLOR_SUCCESS, COLOR_DANGER, COLOR_ORANGE,
                    FONT_BASE, FONT_BOLD, FONT_BIG, FONT_SMALL, ROW_COLORS, EXPIRING_DAYS)
from gui import validators
from gui.contracts import ParkingError
from gui.parking_map import ParkingMapCanvas
from gui.payment_dialog import ReceiptDialog
from gui.utils import format_money, format_dt, format_date, format_duration
from datetime import date

REQ_LABELS = {"pending": "Chờ xử lý", "done": "Đã hoàn tất", "rejected": "Bị từ chối"}


def _tree(parent, cols, height=8):
    frame = ttk.Frame(parent)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    t = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", height=height, selectmode="browse")
    for cid, title, w in cols:
        t.heading(cid, text=title)
        t.column(cid, width=w, anchor="center")
    vsb = ttk.Scrollbar(frame, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=vsb.set)
    t.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    return frame, t


class CustomerStatusTab(ttk.Frame):
    """Tình trạng bãi (chỉ trạng thái ô, KHÔNG hiện biển số xe khác) + khách TỰ GỬI XE: chọn ô trống hoặc để tự động."""

    def __init__(self, master, customers, manager, on_changed):
        super().__init__(master, padding=10)
        self.customers, self.manager, self.on_changed = customers, manager, on_changed
        self.var_plate, self.var_slot = tk.StringVar(), tk.StringVar(value=AUTO_SLOT_LABEL)
        self._vars = {k: tk.StringVar(value="-") for k in ("empty", "occupied", "occupancy_rate")}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        cards = ttk.Frame(self)
        cards.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        for i, (key, title, color) in enumerate([("empty", "CHỖ TRỐNG", SLOT_COLORS["empty"]),
                                                 ("occupied", "ĐANG CÓ XE", SLOT_COLORS["occupied"]),
                                                 ("occupancy_rate", "CÔNG SUẤT", COLOR_ORANGE)]):
            cards.columnconfigure(i, weight=1, uniform="c")
            card = tk.Frame(cards, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
            card.grid(row=0, column=i, sticky="ew", padx=4)
            tk.Frame(card, bg=color, width=6).pack(side="left", fill="y")
            body = tk.Frame(card, bg=COLOR_CARD, padx=12, pady=8)
            body.pack(side="left")
            tk.Label(body, text=title, bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_SMALL).pack(anchor="w")
            tk.Label(body, textvariable=self._vars[key], bg=COLOR_CARD, fg=COLOR_TEXT, font=FONT_BIG).pack(anchor="w")
        self.map = ParkingMapCanvas(self, on_slot_click=self.on_slot_click, show_plates=False)
        self.map.grid(row=1, column=0, sticky="nsew", padx=(0, 12))

        side = tk.Frame(self, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        side.grid(row=1, column=1, sticky="n")
        tk.Label(side, text="▶  GỬI XE CỦA TÔI", bg=COLOR_PRIMARY, fg="white", font=FONT_BOLD, anchor="w",
                 padx=10, pady=5).grid(row=0, column=0, sticky="ew")
        body = ttk.Frame(side, style="Card.TFrame", padding=12)
        body.grid(row=1, column=0)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Xe", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        self.cbo_plate = ttk.Combobox(body, textvariable=self.var_plate, state="readonly", width=24)
        self.cbo_plate.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(body, text="Chỗ đỗ", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.cbo_slot = ttk.Combobox(body, textvariable=self.var_slot, state="readonly", width=24)
        self.cbo_slot.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Button(body, text="VÀO BÃI", style="Primary.TButton", command=self.enter).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        self.var_info = tk.StringVar()
        tk.Label(body, textvariable=self.var_info, bg="#EAF2FD", fg=COLOR_PRIMARY, font=FONT_BASE, justify="left",
                 anchor="w", wraplength=230, padx=10, pady=8).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(body, text="Chọn một ô trống trên sơ đồ hoặc để hệ thống tự chọn. Khi lấy xe ra, "
                             "thanh toán tại quầy với nhân viên.", style="Card.TLabel", foreground=COLOR_MUTED,
                  wraplength=230).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.lbl_price = ttk.Label(self, text="", foreground=COLOR_PRIMARY, font=FONT_BOLD)
        self.lbl_price.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def reload(self):
        st = self.customers.get_public_status()
        self._vars["empty"].set(str(st["empty"]))
        self._vars["occupied"].set(str(st["occupied"]))
        self._vars["occupancy_rate"].set(f"{st['occupancy_rate']:.0f}%")
        slots = self.customers.get_public_slots()
        mine = self.customers.get_my_vehicles()
        self.map.render(slots)
        self.map.set_mine([v["slot_id"] for v in mine
                if v.get("parked", False) and v.get("slot_id")])
        ready = [v["plate"] for v in mine
                if (v.get("status") in ("verified", "approved", "ready") or v.get("verified") is True)
                and not v.get("parked", False)]
        self.cbo_plate["values"] = ready
        if self.var_plate.get() not in ready:
            self.var_plate.set(ready[0] if ready else "")
        free = [s.slot_id for s in slots if s.status == "empty"]
        self.cbo_slot["values"] = [AUTO_SLOT_LABEL] + free
        if self.var_slot.get() not in self.cbo_slot["values"]:
            self.var_slot.set(AUTO_SLOT_LABEL)
        parked = [v for v in mine if v.get("parked", False) and v.get("slot_id")]
        if parked:
            lines = ["📍 VỊ TRÍ XE CỦA BẠN TRÊN SƠ ĐỒ:"]
            for v in parked:
                lines.append(f"• Xe {v['plate']} đang ở ô {v['slot_id']}")
            self.var_info.set("\n".join(lines))
        elif not ready:
            self.var_info.set("Bạn chưa có xe sẵn sàng gửi. Thêm xe ở tab 'Xe của tôi'.")
        else:
            self.var_info.set("Sẵn sàng gửi xe. Chọn ô trống trên sơ đồ rồi bấm 'VÀO BÃI'.")
        p = self.manager.get_prices()
        self.lbl_price.config(text=(
            f"Giá giờ: Xe máy {format_money(p['hourly']['motorbike'])} · Ô tô {format_money(p['hourly']['car'])}"
            f" (miễn phí {p['free_minutes']} phút đầu)   |   Vé tháng: Xe máy {format_money(p['monthly']['motorbike'])}"
            f" · Ô tô {format_money(p['monthly']['car'])}"))

    def on_slot_click(self, slot_id):
        if slot_id in self.cbo_slot["values"]:                                      
            self.var_slot.set(slot_id)
        else:
            self.var_info.set(f"Ô {slot_id} không trống - hãy chọn ô màu xanh.")

    def enter(self):
        if not self.var_plate.get():
            messagebox.showwarning("Chưa có xe", "Không có xe nào sẵn sàng. Hãy thêm/xác minh xe ở tab 'Xe của tôi' "
                                                 "(xe đang đỗ trong bãi không chọn lại được).")
            return
        slot = self.var_slot.get()
        slot = None if slot == AUTO_SLOT_LABEL else slot
        try:
            t = self.customers.self_entry(self.var_plate.get(), slot)
        except ParkingError as e:
            messagebox.showerror("Không thể vào bãi", str(e))
            self.on_changed()
            return
        messagebox.showinfo("Vào bãi thành công",
                            f"Xe {t.plate} đã vào ô {t.slot_id}.\nMã vé: {t.ticket_id}\nGiờ vào: {format_dt(t.entry_time)}\n\n"
                            "Khi lấy xe, thanh toán tại quầy với nhân viên.")
        self.on_changed()


class MyVehiclesTab(ttk.Frame):
    def __init__(self, master, customers, on_changed):
        super().__init__(master, padding=10)
        self.customers, self.on_changed = customers, on_changed
        self.var_plate, self.var_type = tk.StringVar(), tk.StringVar(value="motorbike")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        box = ttk.LabelFrame(self, text=" Thêm xe của tôi ", padding=8)
        box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(box, text="Biển số:").grid(row=0, column=0, padx=(0, 4))
        e = ttk.Entry(box, textvariable=self.var_plate, width=16)
        e.grid(row=0, column=1, padx=(0, 12))
        e.bind("<Return>", lambda _e: self.add())
        for i, (k, v) in enumerate(VEHICLE_TYPES.items()):
            ttk.Radiobutton(box, text=v, value=k, variable=self.var_type).grid(row=0, column=2 + i, padx=(0, 8))
        ttk.Button(box, text="Thêm xe", style="Primary.TButton", command=self.add).grid(row=0, column=4, padx=8)
        ttk.Label(box, text="Xe có vé tháng đứng tên SĐT của bạn được xác minh tự động; xe khác cần nhân viên xác minh tại quầy "
                            "(mang giấy tờ xe).", foreground=COLOR_MUTED, wraplength=720).grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        frame, self.tree = _tree(self, [("plate", "Biển số", 110), ("type", "Loại xe", 80), ("verify", "Xác minh", 120),
                                        ("status", "Tình trạng hiện tại", 330), ("fee", "Phí tạm tính", 100),
                                        ("monthly", "Vé tháng", 190)])
        frame.grid(row=1, column=0, sticky="nsew")
        self.tree.tag_configure("pending", background=ROW_COLORS["expiring"])
        self.tree.tag_configure("parked", background=ROW_COLORS["parked"])
        ttk.Button(self, text="Gỡ xe đã chọn", command=self.remove).grid(row=2, column=0, sticky="e", pady=(8, 0))

    def reload(self):
        self.tree.delete(*self.tree.get_children())
        today = date.today()
        for v in self.customers.get_my_vehicles():
            is_ver = v.get("status") in ("verified", "approved", "ready") or v.get("verified") is True
            if not is_ver:
                status, fee, monthly, tag = "Chưa thể xem - chờ xác minh", "—", "—", "pending"
            else:
                tag = "parked" if v.get("parked", False) else ""
                status = (f"Đang đỗ ô {v.get('slot_id')} từ {format_dt(v.get('entry_time'))} ({format_duration(v.get('minutes'))})"
                          if v.get("parked", False) else "Không ở trong bãi")
                fee = format_money(v.get("fee")) if v.get("parked", False) else "—"
                end = v.get("monthly_end")
                if not end:
                    monthly = "Chưa có"
                elif end < today:
                    monthly = f"Đã hết hạn {format_date(end)}"
                else:
                    monthly = f"Đến {format_date(end)} ({(end - today).days} ngày)"
            self.tree.insert("", "end", iid=v["plate"], tags=(tag,), values=(
                v["plate"], VEHICLE_TYPES[v["vehicle_type"]], "Đã xác minh" if v.get("status") == "verified" else "Chờ xác minh",
                status, fee, monthly))

    def add(self):
        plate = validators.normalize_plate(self.var_plate.get())
        if not validators.is_valid_plate(plate):
            messagebox.showwarning("Biển số không hợp lệ", "Ví dụ hợp lệ: 59A1-123.45")
            return
        try:
            verified = self.customers.link_vehicle(plate, self.var_type.get())
        except ParkingError as e:
            messagebox.showwarning("Không thể thêm xe", str(e))
            return
        self.var_plate.set("")
        messagebox.showinfo("Đã thêm xe", "Xe đã được xác minh tự động." if verified else
                            "Xe đang chờ nhân viên xác minh. Hãy mang giấy tờ xe đến quầy.")
        self.on_changed()

    def remove(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn xe cần gỡ.")
            return
        if not messagebox.askyesno("Xác nhận", f"Gỡ xe {sel[0]} khỏi tài khoản của bạn?"):
            return
        try:
            self.customers.unlink_vehicle(sel[0])
        except ParkingError as e:
            messagebox.showwarning("Không thể gỡ xe", str(e))
            return
        self.on_changed()


class MyMonthlyTab(ttk.Frame):
    def __init__(self, master, customers, manager, on_changed):
        super().__init__(master, padding=10)
        self.customers, self.manager, self.on_changed = customers, manager, on_changed
        self.var_plate, self.var_months, self.var_est = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self._months, self._types = [], {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text="Vé tháng của tôi", font=FONT_BOLD).grid(row=0, column=0, sticky="w")
        f1, self.t_tickets = _tree(self, [("plate", "Biển số", 110), ("owner", "Chủ xe", 160), ("start", "Bắt đầu", 100),
                                          ("end", "Hết hạn", 100), ("state", "Tình trạng", 180)], 4)
        f1.grid(row=1, column=0, sticky="nsew", pady=(2, 8))
        self.t_tickets.tag_configure("expiring", background=ROW_COLORS["expiring"])
        self.t_tickets.tag_configure("expired", background=ROW_COLORS["expired"])

        box = ttk.LabelFrame(self, text=" Gửi yêu cầu mua / gia hạn vé tháng ", padding=8)
        box.grid(row=2, column=0, sticky="ew")
        ttk.Label(box, text="Xe:").grid(row=0, column=0, padx=(0, 4))
        self.cbo_plate = ttk.Combobox(box, textvariable=self.var_plate, state="readonly", width=14)
        self.cbo_plate.grid(row=0, column=1, padx=(0, 10))
        ttk.Label(box, text="Gói:").grid(row=0, column=2, padx=(0, 4))
        self.cbo_months = ttk.Combobox(box, textvariable=self.var_months, state="readonly", width=20)
        self.cbo_months.grid(row=0, column=3, padx=(0, 10))
        ttk.Button(box, text="Gửi yêu cầu", style="Primary.TButton", command=self.submit).grid(row=0, column=4)
        ttk.Label(box, textvariable=self.var_est, foreground=COLOR_PRIMARY, font=FONT_BOLD).grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))
        ttk.Label(box, text="Thanh toán trực tiếp tại quầy với nhân viên ca trực sau khi yêu cầu được tiếp nhận.",
                  foreground=COLOR_MUTED).grid(row=2, column=0, columnspan=5, sticky="w")
        for v in (self.var_plate, self.var_months):
            v.trace_add("write", self._estimate)

        ttk.Label(self, text="Yêu cầu đã gửi", font=FONT_BOLD).grid(row=2, column=0, sticky="sw", pady=(0, 0))
        f2, self.t_req = _tree(self, [("id", "Mã YC", 80), ("plate", "Biển số", 110), ("months", "Gói", 80),
                                      ("time", "Gửi lúc", 130), ("status", "Trạng thái", 110), ("note", "Ghi chú", 260)], 4)
        f2.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        self.rowconfigure(4, weight=1)
        self.grid_rowconfigure(3, weight=0)

    def _estimate(self, *_):
        try:
            months = self._months[self.cbo_months["values"].index(self.var_months.get())]
            vt = self._types.get(self.var_plate.get())
            p = self.manager.get_prices()
            base = p["monthly"][vt] * months
            discount = float(str(p["monthly_discount"][months]).replace("%", "").strip())
            base = float(base)
            discount = float(p["monthly_discount"][months])
            total = base - base * discount / 100
            total = round(total, 0)  # làm tròn số tiền
            self.var_est.set(f"Giá dự kiến: {format_money(total)} (có thể thay đổi theo bảng giá lúc thanh toán)")
        except (ValueError, KeyError, IndexError):
            self.var_est.set("")

    def reload(self):
        today = date.today()
        vehicles = [v for v in self.customers.get_my_vehicles() if v.get("status") == "verified"]
        self._types = {v["plate"]: v["vehicle_type"] for v in vehicles}
        self.cbo_plate["values"] = [v["plate"] for v in vehicles]
        if self.var_plate.get() not in self._types:
            self.var_plate.set(vehicles[0]["plate"] if vehicles else "")
        disc = self.manager.get_prices()["monthly_discount"]
        self._months = sorted(disc)
        labels = [f"{m} tháng" + (f" (giảm {disc[m]}%)" if disc[m] else "") for m in self._months]
        self.cbo_months["values"] = labels
        if self.var_months.get() not in labels:
            self.var_months.set(labels[0])
        self.t_tickets.delete(*self.t_tickets.get_children())
        for t in self.customers.get_my_monthly_tickets():
            days = (t.end_date - today).days
            tag, state = (("expired", "Đã hết hạn") if days < 0 else
                          ("expiring", f"Sắp hết hạn ({days} ngày)") if days <= EXPIRING_DAYS else ("", f"Còn hạn ({days} ngày)"))
            self.t_tickets.insert("", "end", tags=(tag,), values=(t.plate, t.owner, format_date(t.start_date),
                                                                  format_date(t.end_date), state))
        self.t_req.delete(*self.t_req.get_children())
        for r in self.customers.get_my_requests():
            self.t_req.insert("", "end", values=(r["request_id"], r["plate"], f"{r['months']} tháng",
                                                 format_dt(r["created_at"]), REQ_LABELS[r["status"]], r["note"] or "—"))
        self._estimate()

    def submit(self):
        if not self.var_plate.get():
            messagebox.showwarning("Chưa có xe", "Bạn cần có xe đã được xác minh để gửi yêu cầu.")
            return
        months = self._months[self.cbo_months["values"].index(self.var_months.get())]
        try:
            req = self.customers.submit_monthly_request(self.var_plate.get(), months)
        except ParkingError as e:
            messagebox.showwarning("Không thể gửi yêu cầu", str(e))
            return
        messagebox.showinfo("Đã gửi yêu cầu", f"Mã yêu cầu {req['request_id']}. Vui lòng đến quầy để thanh toán.")
        self.on_changed()


class MyHistoryTab(ttk.Frame):
    def __init__(self, master, customers):
        super().__init__(master, padding=10)
        self.customers = customers
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text="Lịch sử gửi xe của tôi", font=FONT_BOLD).grid(row=0, column=0, sticky="w")
        f1, self.t_hist = _tree(self, [("id", "Mã vé", 120), ("plate", "Biển số", 100), ("slot", "Ô", 50),
                                       ("in", "Giờ vào", 130), ("out", "Giờ ra", 130), ("fee", "Phí", 90),
                                       ("status", "Trạng thái", 110)], 6)
        f1.grid(row=1, column=0, sticky="nsew", pady=(2, 8))
        self.t_hist.tag_configure("parked", background=ROW_COLORS["parked"])
        ttk.Label(self, text="Hóa đơn của tôi (bấm đúp để xem)", font=FONT_BOLD).grid(row=2, column=0, sticky="w")
        f2, self.t_pay = _tree(self, [("id", "Mã GD", 120), ("time", "Thời gian", 130), ("kind", "Loại", 90),
                                      ("plate", "Biển số", 100), ("amount", "Số tiền", 100), ("method", "Hình thức", 160)], 6)
        f2.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        self.t_pay.bind("<Double-1>", lambda _e: self.view_receipt())

    def reload(self):
        self.t_hist.delete(*self.t_hist.get_children())
        for t in self.customers.get_my_history():
            self.t_hist.insert("", "end", tags=("parked" if t.status == "parked" else "",), values=(
                t.ticket_id, t.plate, t.slot_id or "—", format_dt(t.entry_time), format_dt(t.exit_time),
                format_money(t.fee) if t.exit_time else "—", TICKET_STATUS_LABELS[t.status]))
        self.t_pay.delete(*self.t_pay.get_children())
        for p in self.customers.get_my_payments():
            self.t_pay.insert("", "end", iid=p.payment_id, values=(
                p.payment_id, format_dt(p.created_at), TXN_KINDS[p.kind], p.plate, format_money(p.amount),
                PAYMENT_METHODS[p.method]))

    def view_receipt(self):
        sel = self.t_pay.selection()
        if not sel:
            return
        try:
            text = self.customers.get_my_receipt(sel[0])
        except ParkingError as e:
            messagebox.showerror("Không xem được", str(e))
            return
        ReceiptDialog(self, text, f"{sel[0]}.txt").show()
