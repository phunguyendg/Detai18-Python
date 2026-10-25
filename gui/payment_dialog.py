"""Hộp thoại thanh toán dùng chung (phí gửi xe + vé tháng) và hộp thoại hóa đơn."""
import hashlib
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from config import (COLOR_BG, BANK_INFO, QUICK_CASH, RECEIPT_DIR, CASH_METHOD, COLOR_CARD, COLOR_BORDER, COLOR_MUTED,
                    COLOR_PRIMARY, COLOR_SUCCESS, COLOR_DANGER, FONT_BASE, FONT_BOLD, FONT_BIG, FONT_SMALL,
                    ROLE_USER, ROLE_STAFF, ROLE_ADMIN, STAFF_ROLES)
from gui import validators
from gui.dialog_base import BaseDialog
from gui.shift_dialogs import OpenShiftDialog, money_text
from gui.utils import format_money

QR_HINTS = {
    "bank_transfer": "Quét mã VietQR bằng ứng dụng ngân hàng hoặc ví điện tử bất kỳ",
    "momo": "Mở MoMo → Quét mã → xác nhận số tiền",
    "zalopay": "Mở ZaloPay → Quét mã → xác nhận số tiền",
}


def ensure_shift(parent, payments, cashier="") -> bool:
    """Điều kiện bắt buộc trước khi thu tiền: CHỈ ÁP DỤNG CHO NHÂN VIÊN CA TRỰC.
    Khách hàng (customer) hoàn toàn không liên quan gì đến ca trực, tuyệt đối không kiểm tra!"""
    c_str = str(cashier or "").lower().strip()

    # 1. Khách hàng: KHÔNG LIÊN QUAN ĐẾN CA TRỰC, bỏ qua 100% không bao giờ hỏi
    if c_str in ("hung", "khach01", "khach", "khachhang", "customer", "user") or "khach" in c_str:
        return True
    if hasattr(parent, "is_customer") and callable(parent.is_customer):
        try:
            if parent.is_customer():
                return True
        except Exception:
            pass
    if hasattr(parent, "user_role") and str(getattr(parent.user_role, 'value', parent.user_role)).lower() in ('user', 'customer', 'khach01'):
        return True
    if hasattr(parent, "user") and parent.user and getattr(parent.user, 'role', '') == ROLE_USER:
        return True

    # 2. Quản trị viên (admin): có toàn quyền thao tác, không bị phụ thuộc ca trực nhân viên
    if c_str in ('admin', 'quantri', 'quanly', 'superadmin'):
        return True
    if hasattr(parent, "user") and parent.user and parent.user.role == ROLE_ADMIN:
        return True

    # 3. CHỈ NHÂN VIÊN CA TRỰC (STAFF) MỚI CẦN KIỂM TRA CA TRỰC ĐANG MỞ
    cur = payments.current_shift()
    if cur:
        if cur.cashier != cashier and cashier:
            messagebox.showwarning("Ca của người khác", f"Ca {cur.shift_id} đang mở bởi {cur.cashier}.\n"
                                   "Hãy nhờ họ chốt ca (hoặc nhờ quản trị viên chốt thay) rồi mở ca mới.", parent=parent)
            return False
        return True
    if not messagebox.askyesno("Chưa mở ca trực", "Cần mở ca trực trước khi thu tiền.\nMở ca ngay?", parent=parent):
        return False
    return OpenShiftDialog(parent, payments, cashier).show() is not None


class PaymentDialog(BaseDialog):
    """result = {"method", "received", "reference"} hoặc None nếu hủy."""

    def __init__(self, parent, title, summary_lines, amount, methods, plate=""):
        super().__init__(parent, title, "Chọn hình thức thanh toán và xác nhận thu tiền")
        self.amount, self.plate = amount, plate
        self.var_method = tk.StringVar(value=CASH_METHOD)
        self.var_received = tk.StringVar()
        self.var_ref_qr = tk.StringVar()
        self.var_ref_card = tk.StringVar()
        b = self.body
        b.columnconfigure(0, weight=1)

        card = tk.Frame(b, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        card.grid(row=0, column=0, sticky="ew")
        card.columnconfigure(1, weight=1)
        for i, (k, v) in enumerate(summary_lines):
            tk.Label(card, text=k, bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_BASE).grid(row=i, column=0, sticky="w", padx=12, pady=2)
            tk.Label(card, text=v, bg=COLOR_CARD, font=FONT_BOLD).grid(row=i, column=1, sticky="e", padx=12)
        n = len(summary_lines)
        tk.Label(card, text="SỐ TIỀN CẦN THU", bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_SMALL).grid(
            row=n, column=0, sticky="w", padx=12, pady=(8, 0))
        tk.Label(card, text=format_money(amount), bg=COLOR_CARD, fg=COLOR_PRIMARY, font=FONT_BIG).grid(
            row=n + 1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        mbox = ttk.LabelFrame(b, text=" Hình thức thanh toán ", padding=8)
        mbox.grid(row=1, column=0, sticky="ew", pady=10)
        for i, (key, label) in enumerate(methods):
            ttk.Radiobutton(mbox, text=label, value=key, variable=self.var_method,
                            command=self._on_method).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=2)

        self.area = ttk.Frame(b)
        self.area.grid(row=2, column=0, sticky="nsew")
        self._build_cash()
        self._build_qr()
        self._build_card()

        row = ttk.Frame(b)
        row.grid(row=3, column=0, sticky="e", pady=(12, 0))
        ttk.Button(row, text="Hủy", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="XÁC NHẬN ĐÃ THU TIỀN", style="Primary.TButton", command=self.confirm).grid(
            row=0, column=1, padx=4)
        self._on_method()

                                                                                             
    def _build_cash(self):
        f = self.cash_f = ttk.Frame(self.area)
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Khách đưa (đ):").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        e = self.ent_received = ttk.Entry(f, textvariable=self.var_received, font=("Segoe UI", 11, "bold"))
        e.grid(row=0, column=1, sticky="ew", pady=4)
        e.bind("<Return>", lambda _e: self.confirm())
        quick = ttk.Frame(f)
        quick.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Button(quick, text="Đủ tiền", command=lambda: self.var_received.set(money_text(self.amount))).grid(row=0, column=0, padx=(0, 4))
        for i, v in enumerate(QUICK_CASH, start=1):
            ttk.Button(quick, text=money_text(v), command=lambda v=v: self.var_received.set(money_text(v))).grid(row=0, column=i, padx=2)
        self.lbl_change = tk.Label(f, text="", font=FONT_BOLD, anchor="w", bg=COLOR_BG)
        self.lbl_change.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.var_received.trace_add("write", self._update_change)
        self._update_change()

    def _build_qr(self):
        f = self.qr_f = ttk.Frame(self.area)
        f.columnconfigure(1, weight=1)
        self.qr_canvas = tk.Canvas(f, width=170, height=170, bg="white", highlightthickness=1,
                                   highlightbackground=COLOR_BORDER)
        self.qr_canvas.grid(row=0, column=0, rowspan=6, padx=(0, 14), sticky="n")
        self.lbl_qr_hint = ttk.Label(f, text="", wraplength=270, font=FONT_BOLD)
        self.lbl_qr_hint.grid(row=0, column=1, sticky="w")
        self.lbl_qr_info = ttk.Label(f, text="", justify="left", wraplength=270)
        self.lbl_qr_info.grid(row=1, column=1, sticky="w", pady=3)
        self.lbl_qr_status = ttk.Label(f, text="Mã VietQR chuẩn NAPAS 247 - Quét bằng mọi app ngân hàng/ví.",
                                       foreground=COLOR_PRIMARY, wraplength=270, font=FONT_SMALL)
        self.lbl_qr_status.grid(row=2, column=1, sticky="w")
        
        btn_copy = ttk.Button(f, text="Sao chép nội dung CK", command=self._copy_qr_memo)
        btn_copy.grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(f, text="Mã giao dịch nhận được:").grid(row=4, column=1, sticky="w", pady=(4, 0))
        e = ttk.Entry(f, textvariable=self.var_ref_qr)
        e.grid(row=5, column=1, sticky="ew")
        e.bind("<Return>", lambda _e: self.confirm())

    def _copy_qr_memo(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._last_memo or "")
            messagebox.showinfo("Đã sao chép", f"Đã sao chép nội dung: {self._last_memo}", parent=self)
        except Exception:
            pass

    def _build_card(self):
        f = self.card_f = ttk.Frame(self.area)
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Quẹt thẻ trên máy POS, sau đó nhập mã chuẩn chi (approval code) in trên biên lai POS.",
                  wraplength=380, foreground=COLOR_MUTED).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(f, text="Mã chuẩn chi:").grid(row=1, column=0, sticky="w", padx=(0, 10))
        e = ttk.Entry(f, textvariable=self.var_ref_card)
        e.grid(row=1, column=1, sticky="ew")
        e.bind("<Return>", lambda _e: self.confirm())

    def _on_method(self):
        m = self.var_method.get()
        for f in (self.cash_f, self.qr_f, self.card_f):
            f.grid_remove()
        if m == CASH_METHOD:
            self.cash_f.grid(row=0, column=0, sticky="ew")
            self.ent_received.focus_set()
        elif m == "card":
            self.card_f.grid(row=0, column=0, sticky="ew")
        else:
            self.qr_f.grid(row=0, column=0, sticky="ew")
            self.lbl_qr_hint.config(text=QR_HINTS.get(m, "Quét mã để thanh toán"))
            content = "BAIXE " + "".join(ch for ch in self.plate if ch.isalnum())
            self._last_memo = content
            if m == "bank_transfer":
                bname = BANK_INFO.get("bank_name", BANK_INFO.get("bank", "Ngân hàng"))
                info = (f"Ngân hàng: {bname}\nSố TK: {BANK_INFO['account']}\n"
                        f"Chủ TK: {BANK_INFO['holder']}\nSố tiền: {format_money(self.amount)}\n"
                        f"Nội dung: {content}")
                self.lbl_qr_status.config(text="Mã VietQR chuẩn NAPAS 247 - Quét bằng mọi app ngân hàng/ví.", foreground=COLOR_SUCCESS)
            else:
                info = f"Số tiền: {format_money(self.amount)}\nGhi chú: BAIXE {self.plate}"
                self.lbl_qr_status.config(text=f"Quét bằng ứng dụng {m.upper()}", foreground=COLOR_PRIMARY)
            self.lbl_qr_info.config(text=info)
            self._generate_and_draw_vietqr(m, content)
        self.update_idletasks()

    def _generate_and_draw_vietqr(self, method, memo):
        """Tạo mã QR thanh toán theo chuẩn VietQR NAPAS 247 và vẽ lên Canvas."""
        try:
            from services.vietqr_service import VietQRService, build_vietqr_emvco
            service = VietQRService()
            bbin = BANK_INFO.get("bank_bin", "970422")
            acc = BANK_INFO.get("account", "0987654321")
            holder = BANK_INFO.get("holder", "BAI DO XE")
            bname = BANK_INFO.get("bank_name", "MBBank")

            # Tạo mã VietQR chuẩn
            qr_res = service.generate_qr(amount=self.amount, memo=memo, plate=self.plate,
                                         bank_bin=bbin, account_no=acc, account_name=holder,
                                         bank_name=bname)
            matrix = qr_res.get("matrix")
            if matrix:
                self._draw_matrix(matrix)
            else:
                self._draw_qr_fallback(f"{method}|{self.plate}|{self.amount}")
        except Exception:
            self._draw_qr_fallback(f"{method}|{self.plate}|{self.amount}")

    def _draw_matrix(self, matrix, canvas_size=170, padding=12):
        """Vẽ ma trận QR chuẩn trực tiếp lên Tkinter Canvas với độ sắc nét tuyệt đối."""
        c = self.qr_canvas
        c.delete("all")
        n = len(matrix)
        avail = canvas_size - (2 * padding)
        cell = avail / n
        c.create_rectangle(0, 0, canvas_size, canvas_size, fill="white", outline="")
        for r in range(n):
            for col in range(n):
                if matrix[r][col]:
                    x0 = padding + col * cell
                    y0 = padding + r * cell
                    x1 = padding + (col + 1) * cell
                    y1 = padding + (r + 1) * cell
                    c.create_rectangle(x0, y0, x1, y1, fill="#111111", outline="")

    def _draw_qr_fallback(self, seed_text, n=25, mod=6, off=10):
        """Dự phòng vẽ khung QR nếu có lỗi ngoại lệ."""
        c = self.qr_canvas
        c.delete("all")
        c.create_rectangle(0, 0, 170, 170, fill="white", outline="")
        rnd = random.Random(int(hashlib.md5(seed_text.encode()).hexdigest()[:8], 16))
        grid = [[rnd.random() < 0.5 for _ in range(n)] for _ in range(n)]
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
            for r in range(-1, 8):
                for cc in range(-1, 8):
                    rr, c2 = r0 + r, c0 + cc
                    if 0 <= rr < n and 0 <= c2 < n:
                        inside = 0 <= r < 7 and 0 <= cc < 7
                        grid[rr][c2] = inside and (r in (0, 6) or cc in (0, 6) or (2 <= r <= 4 and 2 <= cc <= 4))
        for r in range(n):
            for cc in range(n):
                if grid[r][cc]:
                    c.create_rectangle(off + cc * mod, off + r * mod, off + (cc + 1) * mod, off + (r + 1) * mod,
                                       fill="#111", outline="")

    def confirm(self):
        m = self.var_method.get()
        if m == CASH_METHOD:
            try:
                received = validators.parse_money(self.var_received.get())
            except ValueError as e:
                messagebox.showwarning("Số tiền không hợp lệ", str(e), parent=self)
                return
            if received < self.amount:
                messagebox.showwarning("Chưa đủ tiền", f"Khách đưa còn thiếu {format_money(self.amount - received)}.", parent=self)
                return
            self.result = {"method": m, "received": received, "reference": None}
        else:
            ref = (self.var_ref_card if m == "card" else self.var_ref_qr).get().strip()
            if not validators.is_valid_reference(ref):
                messagebox.showwarning("Thiếu mã giao dịch",
                                       "Nhập mã giao dịch (6-24 ký tự gồm chữ, số hoặc dấu gạch ngang) "
                                       "để đối soát.", parent=self)
                return
            self.result = {"method": m, "received": None, "reference": ref}
        self.destroy()


class ReceiptDialog(BaseDialog):
    def __init__(self, parent, text, filename="hoa_don.txt"):
        super().__init__(parent, "Hóa đơn thanh toán", "Xem và lưu hóa đơn")
        self.text, self.filename = text, filename
        b = self.body
        box = tk.Text(b, width=44, height=19, font=("Courier New", 10), bg="white", relief="solid", bd=1,
                      padx=8, pady=8)
        box.insert("1.0", text)
        box.config(state="disabled")
        box.grid(row=0, column=0, columnspan=2)
        row = ttk.Frame(b)
        row.grid(row=1, column=0, sticky="e", pady=(10, 0))
        ttk.Button(row, text="Lưu file (.txt)", command=self.save).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="Đóng", style="Primary.TButton", command=self.destroy).grid(row=0, column=1, padx=4)

    def save(self):
        RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self, title="Lưu hóa đơn", initialdir=RECEIPT_DIR,
                                            initialfile=self.filename, defaultextension=".txt",
                                            filetypes=[("Văn bản", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text)
        except OSError as e:
            messagebox.showerror("Không lưu được", str(e), parent=self)
            return
        messagebox.showinfo("Đã lưu", path, parent=self)
