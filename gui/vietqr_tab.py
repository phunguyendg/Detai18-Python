"""Tab THANH TOÁN & VIETQR: Trung tâm thanh toán tập trung của bãi xe.

- Hỗ trợ đầy đủ các phương thức thanh toán:
  1. Chuyển khoản VietQR (Chuẩn NAPAS 247 / EMVCo, tạo mã QR động đúng số tiền và biển số).
  2. Tiền mặt (Tính tiền thối, các phím số tiền nhanh).
  3. Ví điện tử MoMo, ZaloPay.
  4. Thẻ POS (Quẹt thẻ và nhập mã chuẩn chi).
- Tích hợp tính phí đỗ xe tự động theo thời gian gửi và loại xe, xử lý mất vé.
- Xác nhận thanh toán và cho xe ra bãi, giải phóng ô đỗ ngay trong một thao tác.
- Xuất hóa đơn (ReceiptDialog) và lưu nhật ký giao dịch vào ca trực để đối soát.
"""
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog

from config import (BANK_INFO, COLOR_CARD, COLOR_BORDER, COLOR_MUTED, COLOR_TEXT,
                    COLOR_PRIMARY, COLOR_PRIMARY_DARK, COLOR_ORANGE, COLOR_SUCCESS,
                    COLOR_DANGER, COLOR_BG, FONT_BASE, FONT_BOLD, FONT_SMALL, FONT_BIG,
                    VIETQR_SOURCE, PAYMENT_METHODS, QUICK_CASH, CASH_METHOD)
from gui import validators
from gui.contracts import VietQRError, ParkingError
from gui.payment_dialog import ReceiptDialog, ensure_shift
from gui.shift_dialogs import money_text
from gui.utils import format_money, format_duration, format_dt


class VietQRTab(ttk.Frame):
    def __init__(self, master, vietqr_service, on_update=None, manager=None, payments=None,
                 monthly=None, get_cashier=None, on_data_changed=None):
        super().__init__(master, padding=10)
        self.vietqr = vietqr_service
        self.on_update = on_update
        self.manager = manager
        self.payments = payments
        self.monthly = monthly
        self.get_cashier = get_cashier or (lambda: "admin")
        self.on_data_changed = on_data_changed or (lambda: None)

        self._queue = queue.Queue()
        self._busy = False
        self._last_result = None
        self._selected_ticket = None

        # Biến trạng thái
        self.var_mode = tk.StringVar(value="exit_pay")  # "exit_pay" hoặc "custom_qr"
        self.var_selected_plate = tk.StringVar()
        self.var_lost = tk.BooleanVar(value=False)
        self.var_exit_info = tk.StringVar(value="Chọn xe đang đỗ để tính phí.")
        self.var_calc_fee = tk.IntVar(value=0)

        # Phương thức thanh toán
        self.var_method = tk.StringVar(value="bank_transfer")
        self.var_received = tk.StringVar()
        self.var_ref_code = tk.StringVar()
        self.var_ref_card = tk.StringVar()

        # Cấu hình VietQR
        self.var_bank_code = tk.StringVar(value=BANK_INFO.get("bank_code", "MB"))
        self.var_account = tk.StringVar(value=BANK_INFO.get("account", "0987654321"))
        self.var_holder = tk.StringVar(value=BANK_INFO.get("holder", "BAI DO XE THONG MINH"))
        self.var_custom_amount = tk.StringVar(value="15000")
        self.var_custom_plate = tk.StringVar()
        self.var_custom_memo = tk.StringVar(value="THANH TOAN BAI XE")
        self.var_emvco = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header_card()
        self._build_payment_card()
        self._build_qr_display_card()
        self._build_history_card()

        self._load_banks_async()
        self._process_queue()
        self.reload()

    def start(self):
        """Khởi động tab và thông báo trạng thái VietQR lên thanh tiêu đề."""
        bname = BANK_INFO.get("bank_name", "MBBank")
        if self.on_update:
            self.on_update(f"💳 Thanh toán VietQR: {bname} ({BANK_INFO['account']})")

    def reload(self):
        """Tải lại danh sách xe đang đỗ và lịch sử giao dịch."""
        self._refresh_parked_vehicles()
        self._refresh_history()

    def select_plate(self, plate):
        """Chọn trước biển số xe (khi click từ sơ đồ bãi xe)."""
        self.var_selected_plate.set(plate)
        self._on_plate_changed()

    def _build_header_card(self):
        card = tk.Frame(self, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        card.columnconfigure(1, weight=1)

        bar = tk.Frame(card, bg=COLOR_PRIMARY, width=6)
        bar.grid(row=0, column=0, rowspan=2, sticky="ns")

        body = tk.Frame(card, bg=COLOR_CARD, padx=12, pady=8)
        body.grid(row=0, column=1, sticky="ew")
        body.columnconfigure(3, weight=1)

        tk.Label(body, text="CỔNG THANH TOÁN BÃI ĐỖ XE & VIETQR (NAPAS 247)",
                 bg=COLOR_CARD, fg=COLOR_PRIMARY, font=FONT_BOLD).grid(row=0, column=0, columnspan=4, sticky="w")

        tk.Label(body, text=f"Ngân hàng thụ hưởng: {BANK_INFO.get('bank_name', 'MBBank')}",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=FONT_BASE).grid(row=1, column=0, sticky="w", pady=(3, 0), padx=(0, 20))
        tk.Label(body, text=f"Số tài khoản: {BANK_INFO.get('account', '0987654321')}",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=FONT_BOLD).grid(row=1, column=1, sticky="w", pady=(3, 0), padx=(0, 20))
        tk.Label(body, text=f"Chủ TK: {BANK_INFO.get('holder', 'BAI DO XE THONG MINH')}",
                 bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_BASE).grid(row=1, column=2, sticky="w", pady=(3, 0))

        lbl_src = tk.Label(body, text=f"Chuẩn: {VIETQR_SOURCE} · Tiền mặt / VietQR / MoMo / POS",
                           bg=COLOR_CARD, fg=COLOR_SUCCESS, font=FONT_SMALL)
        lbl_src.grid(row=1, column=3, sticky="e", pady=(3, 0))

    def _build_payment_card(self):
        box = ttk.LabelFrame(self, text=" Thu phí & Cho xe ra bãi ", padding=8)
        box.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 4))
        box.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(box, text="Chọn xe đang đỗ:", font=FONT_BOLD).grid(row=r, column=0, sticky="w", pady=2)
        self.cbo_parked = ttk.Combobox(box, textvariable=self.var_selected_plate, font=("Segoe UI", 10, "bold"))
        self.cbo_parked.grid(row=r, column=1, sticky="ew", pady=2)
        self.cbo_parked.bind("<<ComboboxSelected>>", self._on_plate_changed)
        self.cbo_parked.bind("<Return>", lambda _e: self._on_plate_changed())
        r += 1

        lost_chk = ttk.Checkbutton(box, text="Khách mất vé (phụ thu theo bảng giá)", variable=self.var_lost,
                                  command=self._on_plate_changed)
        lost_chk.grid(row=r, column=0, columnspan=2, sticky="w", pady=(1, 3))
        r += 1

        self.lbl_info_calc = tk.Label(box, textvariable=self.var_exit_info, justify="left", anchor="w",
                                      bg="#EAF2FD", fg=COLOR_PRIMARY, font=FONT_BASE, padx=8, pady=6, wraplength=340)
        self.lbl_info_calc.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(2, 6))
        r += 1

        # NÚT XÁC NHẬN THANH TOÁN & CHO XE RA - Đặt ngay vị trí trung tâm, luôn hiển thị 100%
        self.btn_checkout = ttk.Button(box, text="✔ XÁC NHẬN THANH TOÁN & CHO XE RA",
                                       style="Primary.TButton", command=self.on_checkout_exit)
        self.btn_checkout.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        r += 1

        # Chọn hình thức thanh toán
        ttk.Label(box, text="Hình thức thanh toán:", font=FONT_BOLD).grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 2))
        r += 1

        m_frame = ttk.Frame(box)
        m_frame.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        for i, (key, label) in enumerate(PAYMENT_METHODS.items()):
            ttk.Radiobutton(m_frame, text=label, value=key, variable=self.var_method,
                            command=self._on_method_changed).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 14), pady=1)
        r += 1

        # Khung thanh toán tiền mặt
        self.f_cash = ttk.Frame(box)
        self.f_cash.grid(row=r, column=0, columnspan=2, sticky="ew", pady=2)
        self.f_cash.columnconfigure(1, weight=1)

        ttk.Label(self.f_cash, text="Khách đưa (đ):").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        self.ent_received = ttk.Entry(self.f_cash, textvariable=self.var_received, font=("Segoe UI", 11, "bold"))
        self.ent_received.grid(row=0, column=1, sticky="ew", pady=2)
        self.ent_received.bind("<KeyRelease>", self._update_change_label)

        quick_f = ttk.Frame(self.f_cash)
        quick_f.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Button(quick_f, text="Đủ tiền", width=7, command=self._set_exact_cash).pack(side="left", padx=2)
        for v in (20000, 50000, 100000, 200000, 500000):
            ttk.Button(quick_f, text=money_text(v), width=6,
                       command=lambda val=v: self._set_quick_cash(val)).pack(side="left", padx=2)

        self.lbl_change = tk.Label(self.f_cash, text="", font=FONT_BOLD, anchor="w", bg=COLOR_BG)
        self.lbl_change.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 2))

        # Khung quẹt thẻ POS
        self.f_card = ttk.Frame(box)
        self.f_card.grid(row=r, column=0, columnspan=2, sticky="ew", pady=2)
        self.f_card.columnconfigure(1, weight=1)
        ttk.Label(self.f_card, text="Mã chuẩn chi (POS):").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.ent_card = ttk.Entry(self.f_card, textvariable=self.var_ref_card)
        self.ent_card.grid(row=0, column=1, sticky="ew")

        self._on_method_changed()

    def _build_qr_display_card(self):
        box = ttk.LabelFrame(self, text=" Mã VietQR thanh toán tự động ", padding=8)
        box.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 4))
        box.columnconfigure(0, weight=1)

        self.canvas_qr = tk.Canvas(box, width=180, height=180, bg="white",
                                   highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.canvas_qr.grid(row=0, column=0, pady=(0, 2))

        self.lbl_qr_title = tk.Label(box, text="Mã VietQR chuẩn NAPAS 247", font=FONT_BOLD, fg=COLOR_PRIMARY)
        self.lbl_qr_title.grid(row=1, column=0)

        self.lbl_qr_sub = tk.Label(box, text="Chọn xe để tự động tạo mã thanh toán",
                                   fg=COLOR_MUTED, font=FONT_SMALL, wraplength=280)
        self.lbl_qr_sub.grid(row=2, column=0, sticky="ew")

        ref_f = ttk.Frame(box)
        ref_f.grid(row=3, column=0, sticky="ew", pady=4)
        ref_f.columnconfigure(1, weight=1)
        ttk.Label(ref_f, text="Mã GD nhận:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(ref_f, textvariable=self.var_ref_code).grid(row=0, column=1, sticky="ew")

        act_f = ttk.Frame(box)
        act_f.grid(row=4, column=0, pady=2)
        ttk.Button(act_f, text="Sao chép nội dung CK", command=self._copy_memo).pack(side="left", padx=3)
        ttk.Button(act_f, text="Sao chép EMVCo", command=self._copy_emvco).pack(side="left", padx=3)
        ttk.Button(act_f, text="Lưu mã QR", command=self._save_qr_info).pack(side="left", padx=3)

        # Nút xác nhận thanh toán trực tiếp ngay dưới mã VietQR
        self.btn_qr_checkout = ttk.Button(box, text="✔ ĐÃ NHẬN TIỀN & CHO XE RA BÃI",
                                          style="Primary.TButton", command=self.on_checkout_exit)
        self.btn_qr_checkout.grid(row=5, column=0, sticky="ew", pady=(6, 2))

    def _build_history_card(self):
        box = ttk.LabelFrame(self, text=" Nhật ký thanh toán & Đối soát gần đây ", padding=6)
        box.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
        box.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=0)

        cols = [
            ("time", "Thời gian", 130),
            ("plate", "Biển số", 110),
            ("amount", "Số tiền (đ)", 110),
            ("method", "Phương thức", 140),
            ("cashier", "Thu ngân", 100),
            ("ref", "Mã giao dịch / Ghi chú", 220),
        ]
        self.tree_hist = ttk.Treeview(box, columns=[c[0] for c in cols], show="headings", height=3)
        for cid, title, w in cols:
            self.tree_hist.heading(cid, text=title)
            self.tree_hist.column(cid, width=w, anchor="center")

        vsb = ttk.Scrollbar(box, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=vsb.set)
        self.tree_hist.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def _refresh_parked_vehicles(self):
        if not self.manager:
            return
        tickets = [t for t in self.manager.tickets if t.status == "parked"]
        choices = [f"{t.plate} (Ô {t.slot_id} - {'Ô tô' if t.vehicle_type == 'car' else 'Xe máy'})" for t in tickets]
        self.cbo_parked["values"] = choices
        if choices and not self.var_selected_plate.get():
            self.var_selected_plate.set(choices[0])
            self._on_plate_changed()
        elif not choices:
            self.var_selected_plate.set("")
            self.var_exit_info.set("Hiện không có xe nào đang đỗ trong bãi.")
            self.var_calc_fee.set(0)

    def _on_plate_changed(self, _e=None):
        raw = self.var_selected_plate.get().strip()
        if not raw or not self.manager:
            return
        plate = raw.split(" ")[0].upper()
        try:
            mins, fee = self.manager.estimate_fee(plate, lost_ticket=self.var_lost.get())
            self.var_calc_fee.set(fee)
            lost_txt = " · KHÁCH MẤT VÉ (phụ thu)" if self.var_lost.get() else ""
            self.var_exit_info.set(
                f"Xe {plate} · Đỗ {format_duration(mins)}{lost_txt}\n"
                f"SỐ TIỀN CẦN THU: {format_money(fee)}"
            )
            self._set_exact_cash()
            self._generate_qr_for_checkout(plate, fee)
        except Exception as e:
            self.var_exit_info.set(f"Không tìm thấy thông tin xe: {e}")
            self.var_calc_fee.set(0)

    def _on_method_changed(self):
        m = self.var_method.get()
        if m == "cash":
            self.f_cash.grid()
            self.f_card.grid_remove()
            self.ent_received.focus_set()
        elif m == "card":
            self.f_cash.grid_remove()
            self.f_card.grid()
        else:
            self.f_cash.grid_remove()
            self.f_card.grid_remove()
        self._update_change_label()
        m_label = PAYMENT_METHODS.get(m, "thanh toán")
        if hasattr(self, 'btn_checkout'):
            self.btn_checkout.config(text=f"✔ XÁC NHẬN ({m_label}) & CHO XE RA")

    def _set_exact_cash(self):
        fee = self.var_calc_fee.get()
        self.var_received.set(money_text(fee) if fee > 0 else "0")
        self._update_change_label()

    def _set_quick_cash(self, val):
        self.var_received.set(money_text(val))
        self._update_change_label()

    def _update_change_label(self, *_):
        if self.var_method.get() != "cash":
            return
        fee = self.var_calc_fee.get()
        try:
            v = validators.parse_money(self.var_received.get())
        except ValueError:
            self.lbl_change.config(text="Nhập số tiền khách đưa", fg=COLOR_MUTED)
            return
        if v >= fee:
            self.lbl_change.config(text=f"Tiền thối lại: {format_money(v - fee)}", fg=COLOR_SUCCESS)
        else:
            self.lbl_change.config(text=f"Còn thiếu: {format_money(fee - v)}", fg=COLOR_DANGER)

    def _generate_qr_for_checkout(self, plate, fee):
        memo = f"BAIXE {''.join(ch for ch in plate if ch.isalnum())}"
        self._last_memo = memo
        self.var_ref_code.set(f"VQR-{datetime.now():%y%m%d%H%M%S}")

        bank_bin = BANK_INFO.get("bank_bin", "970422")
        acc = BANK_INFO.get("account", "0987654321")
        holder = BANK_INFO.get("holder", "BAI DO XE THONG MINH")
        bname = BANK_INFO.get("bank_name", "MBBank")

        def worker():
            try:
                res = self.vietqr.generate_qr(amount=fee, memo=memo, plate=plate,
                                             bank_bin=bank_bin, account_no=acc,
                                             account_name=holder, bank_name=bname)
                self._queue.put(("qr_ready", res))
            except Exception as e:
                self._queue.put(("qr_err", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_qr_ready(self, res):
        self._last_result = res
        self.var_emvco.set(res["qr_code"])
        matrix = res.get("matrix")
        if matrix:
            self._draw_matrix(matrix)
        self.lbl_qr_sub.config(
            text=f"Quét mã VietQR · {format_money(res['amount'])} · {res['memo']}",
            fg=COLOR_SUCCESS
        )

    def _draw_matrix(self, matrix, canvas_size=190, padding=10):
        c = self.canvas_qr
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

    def on_checkout_exit(self):
        """Xác nhận thanh toán và cho xe ra bãi."""
        raw = self.var_selected_plate.get().strip()
        if not raw:
            messagebox.showwarning("Chưa chọn xe", "Vui lòng chọn xe cần thanh toán.", parent=self)
            return
        plate = raw.split(" ")[0].upper()
        fee = self.var_calc_fee.get()
        m = self.var_method.get()
        cashier = self.get_cashier()

        # Đảm bảo có ca trực
        if self.payments and not ensure_shift(self, self.payments, cashier):
            return

        received = fee
        ref = None

        if m == "cash":
            try:
                received = validators.parse_money(self.var_received.get())
            except ValueError as e:
                messagebox.showwarning("Số tiền không hợp lệ", str(e), parent=self)
                return
            if received < fee:
                messagebox.showwarning("Chưa đủ tiền", f"Khách đưa còn thiếu {format_money(fee - received)}.", parent=self)
                return
        elif m == "card":
            ref = self.var_ref_card.get().strip()
            if not validators.is_valid_reference(ref):
                messagebox.showwarning("Thiếu mã chuẩn chi", "Vui lòng nhập mã chuẩn chi từ máy POS.", parent=self)
                return
        else:
            ref = self.var_ref_code.get().strip() or f"VQR-{datetime.now():%y%m%d%H%M%S}"

        # Ghi nhận thanh toán
        p = None
        if self.payments and fee > 0:
            try:
                p = self.payments.create_payment(
                    kind="parking",
                    plate=plate,
                    amount=fee,
                    method=m,
                    received=received,
                    reference=ref,
                    description=f"Thu phí đỗ xe {plate}"
                )
            except Exception as e:
                messagebox.showerror("Lỗi thanh toán", str(e), parent=self)
                return

        # Cho xe ra bãi
        try:
            ticket = self.manager.vehicle_exit(plate, lost_ticket=self.var_lost.get())
        except ParkingError as e:
            messagebox.showerror("Lỗi cho xe ra", str(e), parent=self)
            return

        # Hiển thị thông báo thành công
        msg = f"Đã thanh toán {format_money(fee)} qua {PAYMENT_METHODS.get(m, m)} và cho xe {plate} ra bãi thành công!"
        messagebox.showinfo("Thành công", msg, parent=self)

        # Xuất hóa đơn nếu có thu tiền
        if fee > 0:
            receipt_text = (
                f"========================================\n"
                f"           HÓA ĐƠN THU TIỀN             \n"
                f"             BÃI ĐỖ XE                  \n"
                f"========================================\n"
                f"Mã vé: {ticket.ticket_id}\n"
                f"Biển số: {ticket.plate}\n"
                f"Loại xe: {ticket.vehicle_type}\n"
                f"Thời gian vào: {format_dt(ticket.entry_time)}\n"
                f"Thời gian ra:  {format_dt(ticket.exit_time)}\n"
                f"Hình thức: {PAYMENT_METHODS.get(m, m)}\n"
                f"Mã giao dịch / Ref: {ref or '—'}\n"
                f"Thu ngân: {cashier}\n"
                f"----------------------------------------\n"
                f"SỐ TIỀN THANH TOÁN: {format_money(fee)}\n"
                f"Tiền khách đưa: {format_money(received)}\n"
                f"Tiền thối lại:  {format_money(max(0, received - fee))}\n"
                f"========================================\n"
                f"      Cảm ơn quý khách và hẹn gặp lại!  \n"
            )
            ReceiptDialog(self, receipt_text, filename=f"Hoadon_{plate}.txt").show()

        self.on_data_changed()
        self.reload()

    def _load_banks_async(self):
        def worker():
            try:
                banks = self.vietqr.get_banks()
                self._queue.put(("banks_loaded", banks))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _process_queue(self):
        try:
            while True:
                msg, data = self._queue.get_nowait()
                if msg == "qr_ready":
                    self._on_qr_ready(data)
                elif msg == "banks_loaded":
                    pass
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def _copy_memo(self):
        memo = getattr(self, "_last_memo", None) or f"BAIXE {self.var_selected_plate.get()}"
        try:
            self.clipboard_clear()
            self.clipboard_append(memo)
            messagebox.showinfo("Đã sao chép", f"Đã sao chép nội dung: {memo}", parent=self)
        except Exception:
            pass

    def _copy_emvco(self):
        text = self.var_emvco.get().strip()
        if not text:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Đã sao chép", "Đã sao chép chuỗi mã VietQR EMVCo.", parent=self)
        except Exception:
            pass

    def _save_qr_info(self):
        if not self._last_result:
            return
        res = self._last_result
        lines = [
            "THÔNG TIN THANH TOÁN VIETQR",
            f"Thời gian: {res['created_at']}",
            f"Ngân hàng: {res['bank_name']} ({res['bank_bin']})",
            f"Số tài khoản: {res['account_no']}",
            f"Chủ tài khoản: {res['account_name']}",
            f"Số tiền: {res['amount']} VND",
            f"Nội dung: {res['memo']}",
            f"Chuỗi EMVCo: {res['qr_code']}",
        ]
        path = filedialog.asksaveasfilename(parent=self, title="Lưu thông tin mã QR",
                                            initialfile=f"vietqr_{res.get('plate','xe')}.txt",
                                            defaultextension=".txt")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                messagebox.showinfo("Đã lưu", path, parent=self)
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=self)

    def _refresh_history(self):
        for item in self.tree_hist.get_children():
            self.tree_hist.delete(item)
        if self.payments:
            try:
                txns = self.payments.get_transactions()
                for p in txns[:20]:
                    dt_str = p.created_at.strftime("%d/%m/%Y %H:%M:%S")
                    m_label = PAYMENT_METHODS.get(p.method, p.method)
                    self.tree_hist.insert("", "end", values=[
                        dt_str,
                        p.plate,
                        format_money(p.amount),
                        m_label,
                        p.cashier,
                        p.reference_code or p.description or "—"
                    ])
            except Exception:
                pass
