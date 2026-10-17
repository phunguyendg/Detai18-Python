"""Tab Thanh toán & Ca: trạng thái ca, doanh thu theo hình thức, lịch sử giao dịch, hóa đơn."""
import csv
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk, messagebox, filedialog

from config import (PAYMENT_METHODS, TXN_KINDS, DATA_DIR, COLOR_CARD, COLOR_BORDER, COLOR_MUTED, COLOR_SUCCESS,
                    COLOR_DANGER, COLOR_TEXT, FONT_BASE, FONT_BOLD, FONT_SMALL, FONT_TITLE, ROW_COLORS)
from gui.contracts import ParkingError
from gui.payment_dialog import ReceiptDialog
from gui.shift_dialogs import OpenShiftDialog, CloseShiftDialog, ShiftHistoryDialog
from gui.utils import format_money, format_dt, parse_date

COLUMNS = [("id", "Mã GD", 125), ("time", "Thời gian", 135), ("kind", "Loại", 85), ("plate", "Biển số", 100),
           ("desc", "Nội dung", 200), ("amount", "Số tiền", 95), ("method", "Hình thức", 160),
           ("ref", "Mã tham chiếu", 125), ("cashier", "Thu ngân", 80), ("shift", "Ca", 110)]
ALL = "Tất cả"


class PaymentsTab(ttk.Frame):
    def __init__(self, master, payments, on_data_changed, get_cashier, on_shift_closed=None):
        super().__init__(master, padding=8)
        self.payments, self.on_data_changed, self.get_cashier = payments, on_data_changed, get_cashier
        self.on_shift_closed = on_shift_closed      # app dùng để tự đăng xuất nhân viên sau khi chốt ca
        self._card_vars = {}
        self._rows = []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self._build_shift_panel()
        self._build_revenue_cards()
        self._build_filter()
        self._build_tree()
        self._build_buttons()

    # ------------------------------------------------------------ giao diện
    def _build_shift_panel(self):
        card = tk.Frame(self, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        card.columnconfigure(0, weight=1)
        left = tk.Frame(card, bg=COLOR_CARD, padx=14, pady=10)
        left.grid(row=0, column=0, sticky="w")
        self.lbl_shift = tk.Label(left, text="", bg=COLOR_CARD, font=FONT_TITLE, anchor="w")
        self.lbl_shift.pack(anchor="w")
        self.lbl_shift_detail = tk.Label(left, text="", bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_BASE, anchor="w")
        self.lbl_shift_detail.pack(anchor="w")
        btns = tk.Frame(card, bg=COLOR_CARD, padx=14)
        btns.grid(row=0, column=1, sticky="e")
        self.btn_open = ttk.Button(btns, text="Mở ca", style="Primary.TButton", command=self.open_shift)
        self.btn_close = ttk.Button(btns, text="Chốt ca", style="Danger.TButton", command=self.close_shift)
        self.btn_open.grid(row=0, column=0, padx=4)
        self.btn_close.grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="Lịch sử ca", command=lambda: ShiftHistoryDialog(self, self.payments).show()).grid(
            row=0, column=2, padx=4)

    def _build_revenue_cards(self):
        holder = ttk.Frame(self)
        holder.grid(row=1, column=0, sticky="ew")
        keys = list(PAYMENT_METHODS) + ["total"]
        for i, k in enumerate(keys):
            holder.columnconfigure(i, weight=1, uniform="rc")
            card = tk.Frame(holder, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER, padx=10, pady=6)
            card.grid(row=0, column=i, sticky="ew", padx=3, pady=(0, 8))
            title = "TỔNG HÔM NAY" if k == "total" else PAYMENT_METHODS[k].upper()
            tk.Label(card, text=title, bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_SMALL).pack(anchor="w")
            self._card_vars[k] = tk.StringVar(value="0 đ")
            tk.Label(card, textvariable=self._card_vars[k], bg=COLOR_CARD, fg=COLOR_SUCCESS if k == "total" else COLOR_TEXT,
                     font=FONT_BOLD).pack(anchor="w")

    def _build_filter(self):
        bar = ttk.LabelFrame(self, text=" Lọc giao dịch ", padding=8)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.var_kind, self.var_method = tk.StringVar(value=ALL), tk.StringVar(value=ALL)
        self.var_plate, self.var_from, self.var_to = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(bar, text="Loại:").grid(row=0, column=0, padx=(0, 4))
        ttk.Combobox(bar, textvariable=self.var_kind, state="readonly", width=12,
                     values=[ALL] + list(TXN_KINDS.values())).grid(row=0, column=1, padx=(0, 10))
        ttk.Label(bar, text="Hình thức:").grid(row=0, column=2, padx=(0, 4))
        ttk.Combobox(bar, textvariable=self.var_method, state="readonly", width=22,
                     values=[ALL] + list(PAYMENT_METHODS.values())).grid(row=0, column=3, padx=(0, 10))
        ttk.Label(bar, text="Biển số:").grid(row=0, column=4, padx=(0, 4))
        e = ttk.Entry(bar, textvariable=self.var_plate, width=12)
        e.grid(row=0, column=5, padx=(0, 10))
        e.bind("<Return>", lambda _e: self.reload())
        ttk.Label(bar, text="Từ ngày:").grid(row=1, column=0, pady=(6, 0), padx=(0, 4))
        ttk.Entry(bar, textvariable=self.var_from, width=12).grid(row=1, column=1, pady=(6, 0), sticky="w")
        ttk.Label(bar, text="Đến ngày:").grid(row=1, column=2, pady=(6, 0), padx=(0, 4))
        ttk.Entry(bar, textvariable=self.var_to, width=12).grid(row=1, column=3, pady=(6, 0), sticky="w")
        ttk.Label(bar, text="(dd/mm/yyyy)", foreground=COLOR_MUTED).grid(row=1, column=4, pady=(6, 0))
        self.lbl_scope = ttk.Label(bar, text="", foreground=COLOR_MUTED)
        self.lbl_scope.grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Button(bar, text="Lọc", style="Primary.TButton", command=self.reload).grid(row=0, column=6, padx=6)
        ttk.Button(bar, text="Xóa lọc", command=self.clear_filter).grid(row=1, column=6, padx=6, pady=(6, 0))

    def _build_tree(self):
        frame = ttk.Frame(self)
        frame.grid(row=3, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for cid, title, w in COLUMNS:
            self.tree.heading(cid, text=title)
            self.tree.column(cid, width=w, anchor="center")
        self.tree.column("desc", anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.tag_configure("monthly", background="#EAF2FD")
        self.tree.bind("<Double-1>", lambda _e: self.view_receipt())

    def _build_buttons(self):
        row = ttk.Frame(self)
        row.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        row.columnconfigure(0, weight=1)
        self.lbl_total = ttk.Label(row, text="", font=FONT_BOLD)
        self.lbl_total.grid(row=0, column=0, sticky="w")
        ttk.Button(row, text="Xem hóa đơn", command=self.view_receipt).grid(row=0, column=1, padx=4)
        self.btn_export = ttk.Button(row, text="Xuất giao dịch (CSV)", command=self.export_csv)
        self.btn_export.grid(row=0, column=2, padx=4)

    def apply_permissions(self, is_admin):
        self.btn_export.state(["!disabled"] if is_admin else ["disabled"])
        self.lbl_scope.config(text="" if is_admin else "Bạn chỉ thấy giao dịch và ca do chính mình thực hiện.")

    # ------------------------------------------------------------ dữ liệu
    def clear_filter(self):
        for v in (self.var_plate, self.var_from, self.var_to):
            v.set("")
        self.var_kind.set(ALL)
        self.var_method.set(ALL)
        self.reload()

    def _filters(self):
        f = {}
        for k, label in TXN_KINDS.items():
            if self.var_kind.get() == label:
                f["kind"] = k
        for k, label in PAYMENT_METHODS.items():
            if self.var_method.get() == label:
                f["method"] = k
        if self.var_plate.get().strip():
            f["plate"] = self.var_plate.get().strip()
        d1 = parse_date(self.var_from.get(), "'Từ ngày'")
        d2 = parse_date(self.var_to.get(), "'Đến ngày'")
        if d1 and d2 and d1 > d2:
            raise ValueError("'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")
        if d1:
            f["date_from"] = d1
        if d2:
            f["date_to"] = d2
        return f

    def reload(self):
        self._reload_shift()
        today = self.payments.revenue_by_method(date.today())
        for k, v in today.items():
            self._card_vars[k].set(format_money(v))
        self._card_vars["total"].set(format_money(sum(today.values())))
        try:
            flt = self._filters()
        except ValueError as e:
            messagebox.showwarning("Bộ lọc không hợp lệ", str(e))
            return
        self._rows = self.payments.get_transactions(flt)
        self.tree.delete(*self.tree.get_children())
        for p in self._rows:
            self.tree.insert("", "end", iid=p.payment_id, tags=(p.kind,), values=(
                p.payment_id, format_dt(p.created_at), TXN_KINDS[p.kind], p.plate, p.description,
                format_money(p.amount), PAYMENT_METHODS[p.method], p.reference_code or "—", p.cashier, p.shift_id))
        self.lbl_total.config(text=f"{len(self._rows)} giao dịch · Tổng: {format_money(sum(p.amount for p in self._rows))}"
                                   "   (bấm đúp để xem hóa đơn)")

    def _reload_shift(self):
        sh = self.payments.current_shift()
        if sh:
            summ = self.payments.shift_summary(sh.shift_id)
            self.lbl_shift.config(text=f"● Ca đang mở: {sh.shift_id}", fg=COLOR_SUCCESS)
            self.lbl_shift_detail.config(
                text=f"Thu ngân {sh.cashier} · mở lúc {format_dt(sh.opened_at)} · đầu ca {format_money(sh.opening_cash)}"
                     f" · đã thu {format_money(summ['total'])} ({summ['count']} giao dịch)")
        else:
            self.lbl_shift.config(text="● Chưa mở ca trực", fg=COLOR_DANGER)
            self.lbl_shift_detail.config(text="Cần mở ca trước khi thu tiền gửi xe hoặc bán vé tháng.")
        self.btn_open.state(["disabled"] if sh else ["!disabled"])
        self.btn_close.state(["!disabled"] if sh else ["disabled"])

    # ------------------------------------------------------------ thao tác
    def open_shift(self):
        if OpenShiftDialog(self, self.payments, self.get_cashier()).show():
            self.on_data_changed()

    def close_shift(self):
        sh = CloseShiftDialog(self, self.payments).show()
        if sh:
            self.on_data_changed()
            msg = f"Đã chốt ca {sh.shift_id}.\nTiền hệ thống: {format_money(sh.expected_cash)}\n" \
                  f"Đếm thực tế: {format_money(sh.counted_cash)}\n" \
                  f"Chênh lệch: {format_money(sh.difference) if sh.difference >= 0 else '-' + format_money(-sh.difference)}"
            messagebox.showinfo("Chốt ca thành công", msg)
            if self.on_shift_closed:
                self.on_shift_closed(sh)

    def view_receipt(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn một giao dịch để xem hóa đơn.")
            return
        try:
            text = self.payments.build_receipt(sel[0])
        except ParkingError as e:
            messagebox.showerror("Lỗi", str(e))
            return
        ReceiptDialog(self, text, f"{sel[0]}.txt").show()

    def export_csv(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(title="Xuất giao dịch", initialdir=DATA_DIR,
                                            initialfile=f"giao_dich_{datetime.now():%Y%m%d_%H%M}.csv",
                                            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([c[1] for c in COLUMNS])
                for iid in self.tree.get_children():
                    w.writerow(self.tree.item(iid, "values"))
        except OSError as e:
            messagebox.showerror("Xuất thất bại", str(e))
            return
        messagebox.showinfo("Thành công", f"Đã xuất {len(self.tree.get_children())} giao dịch:\n{path}")
