"""Tab Vé tháng: CRUD + tìm kiếm."""
import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk, messagebox

from config import VEHICLE_TYPES, ROW_COLORS, EXPIRING_DAYS, COLOR_MUTED
from gui import validators
from gui.contracts import ParkingError
from gui.purchase_dialog import MonthlyPurchaseDialog
from gui.requests_dialog import StaffRequestsDialog
from gui.utils import format_date, format_money, parse_date

COLUMNS = [("plate", "Biển số", 110), ("owner", "Chủ xe", 150), ("phone", "SĐT", 100),
           ("type", "Loại xe", 70), ("start", "Bắt đầu", 90), ("end", "Hết hạn", 90), ("state", "Tình trạng", 170)]


class MonthlyTab(ttk.Frame):
    def __init__(self, master, monthly, on_data_changed, manager=None, payments=None, get_cashier=None, customers=None):
        super().__init__(master, padding=8)
        self.monthly = monthly
        self.on_data_changed = on_data_changed
        self.manager, self.payments, self.customers = manager, payments, customers
        self.get_cashier = get_cashier or (lambda: "")
        self._label_to_key = {v: k for k, v in VEHICLE_TYPES.items()}
        self.var_plate = tk.StringVar()
        self.var_owner = tk.StringVar()
        self.var_phone = tk.StringVar()
        self.var_type = tk.StringVar(value=VEHICLE_TYPES["motorbike"])
        self.var_start = tk.StringVar()
        self.var_end = tk.StringVar()
        self.var_search = tk.StringVar()
        self._admin_buttons = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_form()
        self._build_list()
        self.clear_form()

    # ------------------------------------------------------------ giao diện
    def _build_form(self):
        box = ttk.LabelFrame(self, text=" Thông tin vé tháng ", padding=10)
        box.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        box.columnconfigure(1, weight=1)
        rows = [("Biển số:", self.var_plate), ("Chủ xe:", self.var_owner), ("Số điện thoại:", self.var_phone)]
        for i, (text, var) in enumerate(rows):
            ttk.Label(box, text=text).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(box, textvariable=var, width=22).grid(row=i, column=1, sticky="ew", pady=4)
        self.ent_plate = box.grid_slaves(row=0, column=1)[0]
        ttk.Label(box, text="Loại xe:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(box, textvariable=self.var_type, state="readonly", width=20,
                     values=list(VEHICLE_TYPES.values())).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Ngày bắt đầu:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.var_start, width=22).grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Ngày hết hạn:").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.var_end, width=22).grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Định dạng ngày: dd/mm/yyyy", foreground=COLOR_MUTED).grid(
            row=6, column=0, columnspan=2, sticky="w")

        ttk.Button(box, text="MUA / GIA HẠN VÉ THÁNG", style="Primary.TButton", command=self.on_purchase).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(14, 2))
        self.btn_requests = ttk.Button(box, text="Yêu cầu & xác minh từ khách", command=self.on_requests)
        self.btn_requests.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(2, 2))
        self.lbl_price = ttk.Label(box, text="", foreground=COLOR_MUTED, justify="left", wraplength=250)
        self.lbl_price.grid(row=12, column=0, columnspan=2, sticky="w", pady=(8, 4))
        ttk.Separator(box).grid(row=9, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(box, text="Quản trị: nhập tay / chỉnh sửa", foreground=COLOR_MUTED).grid(
            row=10, column=0, columnspan=2, sticky="w")
        btns = ttk.Frame(box)
        btns.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        btns.columnconfigure((0, 1), weight=1)
        b_add = ttk.Button(btns, text="Thêm", style="Primary.TButton", command=self.on_add)
        b_upd = ttk.Button(btns, text="Sửa", command=self.on_update)
        b_del = ttk.Button(btns, text="Xóa", style="Danger.TButton", command=self.on_delete)
        b_clr = ttk.Button(btns, text="Làm mới form", command=self.clear_form)
        b_add.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        b_upd.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        b_del.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        b_clr.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        self._admin_buttons = [b_add, b_upd, b_del]

    def _build_list(self):
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        bar = ttk.Frame(right)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Tìm (biển số / chủ xe / SĐT):").grid(row=0, column=0, padx=(0, 6))
        e = ttk.Entry(bar, textvariable=self.var_search)
        e.grid(row=0, column=1, sticky="ew")
        e.bind("<Return>", lambda _e: self.reload())
        ttk.Button(bar, text="Tìm", command=self.reload).grid(row=0, column=2, padx=4)
        ttk.Button(bar, text="Tất cả", command=self._show_all).grid(row=0, column=3)

        frame = ttk.Frame(right)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for cid, title, width in COLUMNS:
            self.tree.heading(cid, text=title)
            self.tree.column(cid, width=width, anchor="center")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        for tag in ("valid", "expiring", "expired"):
            self.tree.tag_configure(tag, background=ROW_COLORS[tag])
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        ttk.Label(right, text="Vàng: sắp hết hạn (≤ 7 ngày)   Xám: đã hết hạn",
                  foreground=COLOR_MUTED).grid(row=2, column=0, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------ phân quyền
    def apply_permissions(self, is_admin):
        for b in self._admin_buttons:
            b.state(["!disabled"] if is_admin else ["disabled"])

    # ------------------------------------------------------------ xử lý
    def _show_all(self):
        self.var_search.set("")
        self.reload()

    def reload(self):
        if self.manager:
            pr = self.manager.get_prices()
            self.lbl_price.config(text="Bảng giá / 1 tháng:\n" + " · ".join(
                f"{VEHICLE_TYPES[k]} {format_money(v)}" for k, v in pr["monthly"].items()))
        if self.customers:
            n = len(self.customers.get_requests("pending")) + len(self.customers.get_pending_vehicles())
            self.btn_requests.config(text=f"Yêu cầu & xác minh từ khách ({n})")
        kw = self.var_search.get().strip()
        items = self.monthly.search_monthly_tickets(kw) if kw else self.monthly.get_all_monthly_tickets()
        self.tree.delete(*self.tree.get_children())
        today = date.today()
        for t in items:
            days = (t.end_date - today).days
            if days < 0:
                tag, state = "expired", "Đã hết hạn"
            elif days <= EXPIRING_DAYS:
                tag, state = "expiring", f"Sắp hết hạn ({days} ngày)"
            else:
                tag, state = "valid", f"Còn hạn ({days} ngày)"
            self.tree.insert("", "end", iid=t.plate, tags=(tag,), values=(
                t.plate, t.owner, t.phone, VEHICLE_TYPES.get(t.vehicle_type, t.vehicle_type),
                format_date(t.start_date), format_date(t.end_date), state))

    def on_purchase(self):
        if not (self.manager and self.payments):
            messagebox.showwarning("Chưa sẵn sàng", "Chức năng thanh toán chưa được kết nối.")
            return
        prefill = None
        if self.tree.selection():
            plate, owner, phone, vtype, *_ = self.tree.item(self.tree.selection()[0], "values")
            prefill = {"plate": plate, "owner": owner, "phone": phone, "vehicle_type": self._label_to_key[vtype]}
        MonthlyPurchaseDialog(self, self.manager, self.monthly, self.payments, self.on_data_changed,
                              self.get_cashier, prefill).show()

    def on_requests(self):
        StaffRequestsDialog(self, self.customers, self.manager, self.monthly, self.payments,
                            self.on_data_changed, self.get_cashier).show()
        self.on_data_changed()

    def clear_form(self):
        for v in (self.var_plate, self.var_owner, self.var_phone):
            v.set("")
        self.var_type.set(VEHICLE_TYPES["motorbike"])
        self.var_start.set(format_date(date.today()))
        self.var_end.set(format_date(date.today() + timedelta(days=30)))
        self.tree.selection_remove(self.tree.selection())
        self.ent_plate.state(["!disabled"])

    def _on_select(self, _e):
        sel = self.tree.selection()
        if not sel:
            return
        plate, owner, phone, vtype, start, end, _state = self.tree.item(sel[0], "values")
        self.var_plate.set(plate)
        self.var_owner.set(owner)
        self.var_phone.set(phone)
        self.var_type.set(vtype)
        self.var_start.set(start)
        self.var_end.set(end)

    def _read_form(self):
        """Đọc và kiểm tra form; ném ValueError kèm thông báo rõ ràng."""
        plate = validators.normalize_plate(self.var_plate.get())
        owner = self.var_owner.get().strip()
        phone = self.var_phone.get().strip()
        if not validators.is_valid_plate(plate):
            raise ValueError("Biển số không hợp lệ. Ví dụ: 59A1-123.45")
        if not owner:
            raise ValueError("Vui lòng nhập tên chủ xe.")
        if not validators.is_valid_phone(phone):
            raise ValueError("Số điện thoại không hợp lệ (10 số, bắt đầu bằng 0 hoặc +84).")
        start = parse_date(self.var_start.get(), "Ngày bắt đầu")
        end = parse_date(self.var_end.get(), "Ngày hết hạn")
        if not start or not end:
            raise ValueError("Vui lòng nhập đủ ngày bắt đầu và ngày hết hạn.")
        if end < start:
            raise ValueError("Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.")
        return plate, owner, phone, self._label_to_key[self.var_type.get()], start, end

    def on_add(self):
        try:
            data = self._read_form()
            self.monthly.add_monthly_ticket(*data)
        except (ValueError, ParkingError) as e:
            messagebox.showwarning("Không thể thêm vé tháng", str(e))
            return
        messagebox.showinfo("Thành công", f"Đã thêm vé tháng cho xe {data[0]}.")
        self.clear_form()
        self.on_data_changed()

    def on_update(self):
        if not self.tree.selection():
            messagebox.showwarning("Chưa chọn", "Hãy chọn một vé tháng trong danh sách để sửa.")
            return
        try:
            plate, owner, phone, vtype, start, end = self._read_form()
            self.monthly.update_monthly_ticket(plate, owner=owner, phone=phone, vehicle_type=vtype,
                                               start_date=start, end_date=end)
        except (ValueError, ParkingError) as e:
            messagebox.showwarning("Không thể cập nhật", str(e))
            return
        messagebox.showinfo("Thành công", f"Đã cập nhật vé tháng của xe {plate}.")
        self.on_data_changed()

    def on_delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn một vé tháng trong danh sách để xóa.")
            return
        plate = sel[0]
        if not messagebox.askyesno("Xác nhận xóa", f"Xóa vé tháng của xe {plate}?\nThao tác không thể hoàn tác."):
            return
        if self.monthly.remove_monthly_ticket(plate):
            self.clear_form()
            self.on_data_changed()
        else:
            messagebox.showerror("Lỗi", f"Không tìm thấy vé tháng của xe {plate}.")
