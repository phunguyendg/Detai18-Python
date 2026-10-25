"""Nhân viên / quản trị: xử lý yêu cầu vé tháng và xác minh biển số do khách gửi."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from config import VEHICLE_TYPES
from gui.contracts import ParkingError
from gui.dialog_base import BaseDialog
from gui.purchase_dialog import MonthlyPurchaseDialog
from gui.utils import format_dt


class StaffRequestsDialog(BaseDialog):
    def __init__(self, parent, customers, manager, monthly, payments, on_done, get_cashier, on_switch_payment=None):
        super().__init__(parent, "Yêu cầu & xác minh từ khách hàng", "Khách gửi yêu cầu, nhân viên thu tiền tại quầy hoặc tab Thu ngân & Thanh toán")
        self.customers, self.manager, self.monthly, self.payments = customers, manager, monthly, payments
        self.on_done, self.get_cashier = on_done, get_cashier
        self.on_switch_payment = on_switch_payment
        self.nb = ttk.Notebook(self.body)
        self.nb.grid(row=0, column=0, sticky="nsew")
        self.f_req, self.t_req = self._tab(self.nb, "Yêu cầu vé tháng", [
            ("id", "Mã YC", 80), ("name", "Khách hàng", 130), ("phone", "SĐT", 95), ("plate", "Biển số", 95),
            ("months", "Gói", 70), ("time", "Gửi lúc", 125)],
            [("Xử lý (thu tiền)", "Primary.TButton", self.handle_request), ("Từ chối", "Danger.TButton", self.reject_request)])
        self.f_veh, self.t_veh = self._tab(self.nb, "Xe chờ xác minh", [
            ("plate", "Biển số", 110), ("type", "Loại xe", 90), ("user", "Tài khoản khách", 140)],
            [("Xác minh (đã đối chiếu giấy tờ)", "Primary.TButton", lambda: self.verify(True)),
             ("Từ chối", "Danger.TButton", lambda: self.verify(False))])
        self.reload()

    def _tab(self, nb, title, cols, buttons):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=title)
        t = ttk.Treeview(f, columns=[c[0] for c in cols], show="headings", height=8, selectmode="browse")
        for cid, text, w in cols:
            t.heading(cid, text=text)
            t.column(cid, width=w, anchor="center")
        t.grid(row=0, column=0, columnspan=len(buttons) + 1, sticky="nsew")
        for i, (label, style, cmd) in enumerate(buttons):
            ttk.Button(f, text=label, style=style, command=cmd).grid(row=1, column=i + 1, padx=4, pady=(8, 0), sticky="e")
        f.columnconfigure(0, weight=1)
        return f, t

    def reload(self):
        self.t_req.delete(*self.t_req.get_children())
        pending_reqs = self.customers.get_requests("pending") if self.customers else []
        for r in pending_reqs:
            full_name = r.get("full_name") or r.get("username", "Khách hàng")
            phone = r.get("phone") or "—"
            months = r.get("months", 1)
            self.t_req.insert("", "end", iid=r.get("request_id"), values=(
                r.get("request_id"), full_name, phone, r.get("plate"), f"{months} tháng", format_dt(r.get("created_at", ""))))

        self.t_veh.delete(*self.t_veh.get_children())
        pending_vehs = self.customers.get_pending_vehicles() if self.customers else []
        for v in pending_vehs:
            vt = VEHICLE_TYPES.get(v.get("vehicle_type", "motorbike"), v.get("vehicle_type", "Xe máy"))
            self.t_veh.insert("", "end", iid=v.get("plate"), values=(v.get("plate"), vt, v.get("username", "Khách")))

        try:
            self.nb.tab(0, text=f"Yêu cầu vé tháng ({len(pending_reqs)})")
            self.nb.tab(1, text=f"Xe chờ xác minh ({len(pending_vehs)})")
            if len(pending_reqs) == 0 and len(pending_vehs) > 0:
                self.nb.select(1)
        except Exception:
            pass

    def _sel(self, tree):
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn một dòng trong danh sách.", parent=self)
            return None
        return sel[0]

    def handle_request(self):
        rid = self._sel(self.t_req)
        if not rid:
            return
        pending = self.customers.get_requests("pending")
        req = next((r for r in pending if r.get("request_id") == rid), None)
        if not req:
            messagebox.showwarning("Không tìm thấy", "Yêu cầu này không còn tồn tại.", parent=self)
            return

        prefill = {
            "mode": "monthly",
            "request_id": req.get("request_id"),
            "plate": req.get("plate"),
            "owner": req.get("full_name") or req.get("username"),
            "phone": req.get("phone", ""),
            "vehicle_type": req.get("vehicle_type", "motorbike"),
            "months": req.get("months", 1),
            "amount": req.get("amount", 0),
        }

        # Nếu có callback chuyển sang tab thanh toán QR (Thu ngân & Thanh toán)
        if self.on_switch_payment:
            self.destroy()
            self.on_switch_payment(prefill)
            return

        pay = MonthlyPurchaseDialog(self, self.manager, self.monthly, self.payments, self.on_done,
                                    self.get_cashier, prefill).show()
        if pay:
            try:
                self.customers.resolve_request(rid, "done", f"Đã thu tiền {pay.payment_id}")
            except ParkingError as e:
                messagebox.showerror("Lỗi", str(e), parent=self)
            self.reload()

    def reject_request(self):
        rid = self._sel(self.t_req)
        if not rid:
            return
        reason = simpledialog.askstring("Từ chối yêu cầu", "Lý do từ chối (bắt buộc):", parent=self)
        if reason is None:
            return
        try:
            self.customers.resolve_request(rid, "rejected", reason)
        except ParkingError as e:
            messagebox.showwarning("Không thể từ chối", str(e), parent=self)
            return
        self.reload()
        self.on_done()

    def verify(self, approve):
        plate = self._sel(self.t_veh)
        if not plate:
            return
        if not approve and not messagebox.askyesno("Xác nhận", f"Từ chối và gỡ xe {plate} khỏi tài khoản khách?", parent=self):
            return
        try:
            self.customers.verify_vehicle(plate, approve)
        except ParkingError as e:
            messagebox.showwarning("Không thể thực hiện", str(e), parent=self)
            return
        self.reload()
        self.on_done()
