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
                    VIETQR_SOURCE, PAYMENT_METHODS, QUICK_CASH, CASH_METHOD, ROLE_USER, VEHICLE_TYPES)
from gui import validators
from gui.contracts import VietQRError, ParkingError
from gui.payment_dialog import ReceiptDialog, ensure_shift
from gui.shift_dialogs import money_text
from gui.utils import format_money, format_duration, format_dt


class VietQRTab(ttk.Frame):
    def __init__(self, master, vietqr_service, on_update=None, manager=None, payments=None,
                 monthly=None, get_cashier=None, on_data_changed=None, customers=None, user_role=None):
        super().__init__(master, padding=10)
        self.vietqr = vietqr_service
        self.on_update = on_update
        self.manager = manager
        self.payments = payments
        self.monthly = monthly
        self.customers = customers
        self.user_role = user_role
        self.get_cashier = get_cashier or (lambda: "admin")
        self.on_data_changed = on_data_changed or (lambda: None)
        self._monthly_data = None

        self._queue = queue.Queue()
        self._busy = False
        self._last_result = None
        self._selected_ticket = None

        # Biến trạng thái
        self.var_mode = tk.StringVar(value="exit_pay")  # "exit_pay", "monthly_pay" hoặc "custom_qr"
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
        self.rowconfigure(0, weight=1)

        # Setup container có thanh cuộn dọc (Canvas + Scrollbar)
        self.canvas_scroll = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=COLOR_BG)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas_scroll.yview)
        self.scrollable_content = ttk.Frame(self.canvas_scroll, padding=4)

        self._content_window = self.canvas_scroll.create_window((0, 0), window=self.scrollable_content, anchor="nw")
        self.scrollable_content.bind("<Configure>", self._on_content_configure)
        self.canvas_scroll.bind("<Configure>", self._on_canvas_configure)
        self.canvas_scroll.configure(yscrollcommand=self.scrollbar.set)

        self.canvas_scroll.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.bind("<Enter>", self._bind_mousewheel)
        self.bind("<Leave>", self._unbind_mousewheel)

        self.scrollable_content.columnconfigure(0, weight=1)
        self.scrollable_content.columnconfigure(1, weight=1)

        self._build_header_card()
        self._build_pending_exits_card()
        self._build_payment_card()
        self._build_qr_display_card()
        self._build_history_card()

        self._load_banks_async()
        self._process_queue()
        self.reload()

    def _on_content_configure(self, _event=None):
        if self.canvas_scroll.winfo_exists():
            self.canvas_scroll.configure(scrollregion=self.canvas_scroll.bbox("all"))

    def _on_canvas_configure(self, event):
        if self.canvas_scroll.winfo_exists():
            self.canvas_scroll.itemconfig(self._content_window, width=event.width)

    def _on_mousewheel(self, event):
        if self.canvas_scroll.winfo_exists():
            self.canvas_scroll.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_up_linux(self, _event=None):
        if self.canvas_scroll.winfo_exists():
            self.canvas_scroll.yview_scroll(-1, "units")

    def _on_mousewheel_down_linux(self, _event=None):
        if self.canvas_scroll.winfo_exists():
            self.canvas_scroll.yview_scroll(1, "units")

    def _bind_mousewheel(self, _event=None):
        self.canvas_scroll.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas_scroll.bind_all("<Button-4>", self._on_mousewheel_up_linux)
        self.canvas_scroll.bind_all("<Button-5>", self._on_mousewheel_down_linux)

    def _unbind_mousewheel(self, _event=None):
        self.canvas_scroll.unbind_all("<MouseWheel>")
        self.canvas_scroll.unbind_all("<Button-4>")
        self.canvas_scroll.unbind_all("<Button-5>")

    def is_customer(self):
        role_str = str(getattr(self.user_role, 'value', self.user_role) or '').lower()
        cashier = str(self.get_cashier() or '').lower()
        if cashier in ('hung', 'khach', 'khach01', 'customer', 'user') or 'khach' in cashier:
            return True
        if role_str in ('user', 'customer', 'khach01', 'khachhang', 'khach'):
            return True
        if role_str not in ('admin', 'staff', 'manager', 'nhanvien', 'quantri'):
            return True
        return False

    def start(self):
        """Khởi động tab và thông báo trạng thái VietQR lên thanh tiêu đề."""
        bname = BANK_INFO.get("bank_name", "MBBank")
        if self.on_update:
            self.on_update(f"💳 Thanh toán VietQR: {bname} ({BANK_INFO['account']})")

    def reload(self):
        """Tải lại danh sách xe đang đỗ, yêu cầu mở barie và lịch sử giao dịch."""
        if self.var_mode.get() != "monthly_pay":
            self._refresh_parked_vehicles()
        self._refresh_history()
        self._refresh_pending_exits()

    def select_plate(self, plate):
        """Chọn trước biển số xe (khi click từ sơ đồ bãi xe)."""
        self.var_selected_plate.set(plate)
        self._on_plate_changed()

    def _build_header_card(self):
        card = tk.Frame(self.scrollable_content, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        card.columnconfigure(1, weight=1)

        bar = tk.Frame(card, bg=COLOR_PRIMARY, width=6)
        bar.grid(row=0, column=0, rowspan=2, sticky="ns")

        body = tk.Frame(card, bg=COLOR_CARD, padx=10, pady=6)
        body.grid(row=0, column=1, sticky="ew")
        body.columnconfigure(3, weight=1)

        tk.Label(body, text="CỔNG THANH TOÁN BÃI ĐỖ XE & VIETQR (NAPAS 247)",
                 bg=COLOR_CARD, fg=COLOR_PRIMARY, font=FONT_BOLD).grid(row=0, column=0, columnspan=4, sticky="w")

        tk.Label(body, text=f"Ngân hàng thụ hưởng: {BANK_INFO.get('bank_name', 'MBBank')}",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=FONT_BASE).grid(row=1, column=0, sticky="w", pady=(2, 0), padx=(0, 16))
        tk.Label(body, text=f"Số tài khoản: {BANK_INFO.get('account', '0987654321')}",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=FONT_BOLD).grid(row=1, column=1, sticky="w", pady=(2, 0), padx=(0, 16))
        tk.Label(body, text=f"Chủ TK: {BANK_INFO.get('holder', 'BAI DO XE THONG MINH')}",
                 bg=COLOR_CARD, fg=COLOR_MUTED, font=FONT_BASE).grid(row=1, column=2, sticky="w", pady=(2, 0))

        lbl_src = tk.Label(body, text=f"Chuẩn: {VIETQR_SOURCE} · Tiền mặt / VietQR / MoMo / POS",
                           bg=COLOR_CARD, fg=COLOR_SUCCESS, font=FONT_SMALL)
        lbl_src.grid(row=1, column=3, sticky="e", pady=(2, 0))

    def setup_monthly_payment(self, data):
        """Kích hoạt giao diện thu tiền vé tháng phù hợp trong tab thanh toán."""
        self._monthly_data = data
        self.var_mode.set("monthly_pay")
        plate = data.get("plate", "").upper()
        self.var_selected_plate.set(plate)
        fee = int(data.get("amount", 0))
        self.var_calc_fee.set(fee)
        self.var_received.set(money_text(fee))  # Điền sẵn đủ số tiền để không bị báo thiếu tiền

        owner = data.get("owner") or data.get("full_name") or "Khách hàng"
        phone = data.get("phone", "")
        months = data.get("months", 1)
        vtype = VEHICLE_TYPES.get(data.get("vehicle_type", "motorbike"), data.get("vehicle_type", "Xe"))

        # Chuyển đổi khung hiển thị sang giao diện vé tháng riêng biệt
        if hasattr(self, 'f_mode_exit') and hasattr(self, 'f_mode_monthly'):
            self.f_mode_exit.grid_remove()
            self.f_mode_monthly.grid()
        if hasattr(self, 'box_payment'):
            self.box_payment.config(text=" 🎫 Thu tiền & Kích hoạt Vé tháng ")

        if hasattr(self, 'lbl_m_plate'):
            self.lbl_m_plate.config(text=f"Biển số: {plate} ({vtype})")
        if hasattr(self, 'lbl_m_owner'):
            self.lbl_m_owner.config(text=f"Chủ xe: {owner}   ·   SĐT: {phone or '—'}")
        if hasattr(self, 'lbl_m_months'):
            self.lbl_m_months.config(text=f"Gói đăng ký: {months} tháng   ·   Ghi chú: {data.get('note', 'Đăng ký vé tháng')}")
        if hasattr(self, 'lbl_m_amount'):
            self.lbl_m_amount.config(text=f"TỔNG THU: {format_money(fee)}")

        memo = f"VETHANG {plate}"
        if hasattr(self, 'lbl_qr_title'):
            self.lbl_qr_title.config(text="Mã VietQR thu tiền vé tháng")
        self._request_qr_async(self.var_bank_code.get(), self.var_account.get(),
                               fee, memo, self.var_holder.get())
        self._update_change_label()
        self._update_checkout_btn_text()

    def setup_exit_payment(self):
        """Quay lại giao diện thu phí xe ra bãi thông thường."""
        self._monthly_data = None
        self.var_mode.set("exit_pay")
        if hasattr(self, 'f_mode_monthly') and hasattr(self, 'f_mode_exit'):
            self.f_mode_monthly.grid_remove()
            self.f_mode_exit.grid()
        if hasattr(self, 'box_payment'):
            self.box_payment.config(
                text=" Thanh toán phí giữ xe Online " if self.is_customer() else " Thu phí giữ xe & Cho xe ra bãi "
            )
        if hasattr(self, 'lbl_qr_title'):
            self.lbl_qr_title.config(text="Mã VietQR chuẩn NAPAS 247")
        self._refresh_parked_vehicles()
        self._update_checkout_btn_text()

    def _update_checkout_btn_text(self):
        m = self.var_method.get()
        m_label = PAYMENT_METHODS.get(m, "thanh toán")
        fee = self.var_calc_fee.get()
        if hasattr(self, 'btn_checkout'):
            if self.var_mode.get() == "monthly_pay":
                self.btn_checkout.config(text=f"✔ XÁC NHẬN THU {format_money(fee)} & KÍCH HOẠT VÉ THÁNG")
            elif self.is_customer():
                self.btn_checkout.config(text=f"✔ XÁC NHẬN THANH TOÁN ONLINE ({m_label})")
            else:
                self.btn_checkout.config(text=f"✔ XÁC NHẬN THANH TOÁN ({m_label})")

        if hasattr(self, 'btn_qr_checkout'):
            if self.var_mode.get() == "monthly_pay":
                self.btn_qr_checkout.config(text=f"✔ ĐÃ NHẬN {format_money(fee)} & KÍCH HOẠT VÉ THÁNG")
            elif self.is_customer():
                self.btn_qr_checkout.config(text="✔ TÔI ĐÃ CHUYỂN KHOẢN (CHỜ XÁC THỰC)")
            else:
                self.btn_qr_checkout.config(text="✔ ĐÃ NHẬN TIỀN CHUYỂN KHOẢN")

    def _build_pending_exits_card(self):
        """Khung duyệt xe đã thanh toán online chờ nhân viên mở Barie (chỉ hiển thị phía nhân viên/quản trị)."""
        self.f_pending_exits = tk.Frame(self.scrollable_content, bg="#FEF3C7", highlightthickness=2, highlightbackground="#F59E0B", padx=10, pady=6)
        self.f_pending_exits.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.f_pending_exits.grid_remove()

    def _refresh_pending_exits(self):
        """Cập nhật danh sách các xe đã thanh toán online đang chờ mở barie."""
        if not hasattr(self, 'f_pending_exits'):
            return
        for child in self.f_pending_exits.winfo_children():
            child.destroy()

        if self.is_customer() or not self.customers:
            self.f_pending_exits.grid_remove()
            return

        pending = self.customers.get_pending_exits()
        if not pending:
            self.f_pending_exits.grid_remove()
            return

        self.f_pending_exits.grid()

        # Tiêu đề cảnh báo
        hdr_f = tk.Frame(self.f_pending_exits, bg="#FEF3C7")
        hdr_f.pack(fill="x", pady=(0, 4))
        tk.Label(hdr_f, text=f"🚨 YÊU CẦU MỞ BARIE: CÓ {len(pending)} XE ĐÃ THANH TOÁN ONLINE ĐANG CHỜ XÁC THỰC RA BÃI!",
                 font=FONT_BOLD, fg="#B45309", bg="#FEF3C7").pack(side="left")

        # Khung danh sách xe
        items_f = tk.Frame(self.f_pending_exits, bg="#FEF3C7")
        items_f.pack(fill="x")

        for item in pending:
            plate = item.get("plate", "")
            slot_id = item.get("slot_id", "")
            amount = item.get("amount", 0)
            m = item.get("method", "bank_transfer")
            m_label = PAYMENT_METHODS.get(m, m)
            cust = item.get("customer", "")
            paid_at = item.get("paid_at", "")
            ref = item.get("ref", "")

            row_card = tk.Frame(items_f, bg="white", highlightthickness=1, highlightbackground="#FCD34D", padx=10, pady=5)
            row_card.pack(fill="x", pady=2)
            row_card.columnconfigure(0, weight=1)

            txt = f"🚗 Biển số: {plate}   ·   Ô đỗ: {slot_id}   ·   Khách hàng: {cust}   ·   Thời gian: {paid_at}\n" \
                  f"💰 Đã thanh toán: {format_money(amount)} ({m_label})   ·   Mã GD: {ref}"
            lbl = tk.Label(row_card, text=txt, justify="left", anchor="w", font=FONT_BASE, bg="white", fg="#1F2937")
            lbl.grid(row=0, column=0, sticky="w", padx=(0, 10))

            btn = tk.Button(row_card, text=f"✔ XÁC THỰC & MỞ BARIE ({plate})", font=FONT_BOLD,
                            bg="#059669", fg="white", activebackground="#047857", activeforeground="white",
                            padx=10, pady=4, relief="flat", cursor="hand2",
                            command=lambda p=plate: self._approve_pending_exit(p))
            btn.grid(row=0, column=1, sticky="e")

    def _approve_pending_exit(self, plate):
        """Nhân viên xác nhận mở barie cho xe đã thanh toán online rời bãi."""
        if not messagebox.askyesno("Xác nhận mở Barie", f"Xác nhận xe {plate} đã đối soát thanh toán online hợp lệ.\nMỞ BARIE cho xe rời bãi?"):
            return
        try:
            if self.customers:
                self.customers.approve_pending_exit(plate, cashier=self.get_cashier())
            elif self.manager:
                self.manager.vehicle_exit(plate)
            messagebox.showinfo("Đã mở Barie", f"✔ Đã xác thực thanh toán Online và mở Barie cho xe {plate} ra bãi thành công!", parent=self)
            self.on_data_changed()
            self.reload()
        except Exception as e:
            messagebox.showerror("Lỗi cho xe ra", str(e), parent=self)

    def _build_payment_card(self):
        self.box_payment = ttk.LabelFrame(
            self.scrollable_content,
            text=" Thanh toán phí giữ xe Online " if self.is_customer() else " Thu phí & Cho xe ra bãi ",
            padding=6
        )
        self.box_payment.grid(row=2, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        self.box_payment.columnconfigure(1, weight=1)

        r = 0
        # Thông báo quy định dành riêng cho khách hàng
        if self.is_customer():
            lbl_cust_warn = tk.Label(
                self.box_payment,
                text="📢 THÔNG BÁO QUY ĐỊNH LẤY XE:\nKhách hàng chỉ thanh toán Online. Sau khi bấm thanh toán, vui lòng chờ nhân viên (hoặc quản trị viên) xác thực để mở barie mới được lấy xe rời đi!",
                bg="#FFF3CD", fg="#856404", font=FONT_BOLD, padx=8, pady=4, wraplength=340, justify="left", relief="solid", bd=1
            )
            lbl_cust_warn.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 4))
            r += 1

        # KHUNG 1: GIAO DIỆN THU PHÍ GIỮ XE RA BÃI (MẶC ĐỊNH)
        self.f_mode_exit = ttk.Frame(self.box_payment)
        self.f_mode_exit.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.f_mode_exit.columnconfigure(1, weight=1)
        r += 1

        ttk.Label(self.f_mode_exit, text="Chọn xe đang đỗ:", font=FONT_BOLD).grid(row=0, column=0, sticky="w", pady=2)
        self.cbo_parked = ttk.Combobox(self.f_mode_exit, textvariable=self.var_selected_plate, font=("Segoe UI", 10, "bold"))
        self.cbo_parked.grid(row=0, column=1, sticky="ew", pady=2)
        self.cbo_parked.bind("<<ComboboxSelected>>", self._on_plate_changed)
        self.cbo_parked.bind("<Return>", lambda _e: self._on_plate_changed())

        if not self.is_customer():
            lost_chk = ttk.Checkbutton(self.f_mode_exit, text="Khách mất vé (phụ thu theo bảng giá)", variable=self.var_lost,
                                      command=self._on_plate_changed)
            lost_chk.grid(row=1, column=0, columnspan=2, sticky="w", pady=(1, 2))

        self.lbl_info_calc = tk.Label(self.f_mode_exit, textvariable=self.var_exit_info, justify="left", anchor="w",
                                      bg="#EAF2FD", fg=COLOR_PRIMARY, font=FONT_BASE, padx=8, pady=4, wraplength=340)
        self.lbl_info_calc.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 4))

        # KHUNG 2: GIAO DIỆN THU TIỀN VÉ THÁNG (KHI BẤM XỬ LÝ VÉ THÁNG - HÌNH 2)
        self.f_mode_monthly = ttk.Frame(self.box_payment)
        self.f_mode_monthly.columnconfigure(0, weight=1)

        # Header và nút quay lại thu xe ra bãi
        top_m = ttk.Frame(self.f_mode_monthly)
        top_m.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        top_m.columnconfigure(0, weight=1)
        ttk.Label(top_m, text="🎫 ĐĂNG KÝ VÉ THÁNG", font=FONT_BOLD, foreground=COLOR_PRIMARY).grid(row=0, column=0, sticky="w")
        ttk.Button(top_m, text="⬅ Thu xe ra bãi", command=self.setup_exit_payment).grid(row=0, column=1, sticky="e")

        card_m = tk.Frame(self.f_mode_monthly, bg="#EFF6FF", relief="solid", bd=1, padx=8, pady=6)
        card_m.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        card_m.columnconfigure(1, weight=1)

        self.lbl_m_plate = tk.Label(card_m, text="Biển số: —", bg="#EFF6FF", fg=COLOR_PRIMARY_DARK, font=FONT_BOLD)
        self.lbl_m_plate.grid(row=0, column=0, columnspan=2, sticky="w")

        self.lbl_m_owner = tk.Label(card_m, text="Chủ xe: —", bg="#EFF6FF", fg=COLOR_TEXT, font=FONT_BASE)
        self.lbl_m_owner.grid(row=1, column=0, columnspan=2, sticky="w", pady=(1, 0))

        self.lbl_m_months = tk.Label(card_m, text="Gói đăng ký: —", bg="#EFF6FF", fg=COLOR_MUTED, font=FONT_BASE)
        self.lbl_m_months.grid(row=2, column=0, sticky="w", pady=(1, 0))

        self.lbl_m_amount = tk.Label(card_m, text="TỔNG THU: 0 đ", bg="#EFF6FF", fg=COLOR_ORANGE, font=FONT_BIG)
        self.lbl_m_amount.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Ban đầu ẩn khung vé tháng
        self.f_mode_monthly.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.f_mode_monthly.grid_remove()

        # NÚT XÁC NHẬN THANH TOÁN (BỎ HOÀN TOÀN CHỮ "CHO XE RA" CHO KHÁCH VÀ VÉ THÁNG)
        self.btn_checkout = ttk.Button(self.box_payment, text="",
                                       style="Primary.TButton", command=self.on_checkout_exit)
        self.btn_checkout.grid(row=r + 1, column=0, columnspan=2, sticky="ew", pady=(3, 6))
        r += 2

        # Chọn hình thức thanh toán (Khách hàng chỉ được online)
        methods_to_show = {k: v for k, v in PAYMENT_METHODS.items() if k in ("bank_transfer", "momo", "zalopay")} if self.is_customer() else PAYMENT_METHODS
        ttk.Label(self.box_payment, text="Hình thức thanh toán:" + (" (Chỉ Online)" if self.is_customer() else ""), font=FONT_BOLD).grid(row=r, column=0, columnspan=2, sticky="w", pady=(1, 1))
        r += 1

        m_frame = ttk.Frame(self.box_payment)
        m_frame.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        for i, (key, label) in enumerate(methods_to_show.items()):
            ttk.Radiobutton(m_frame, text=label, value=key, variable=self.var_method,
                            command=self._on_method_changed).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 10), pady=1)
        r += 1

        # Khung thanh toán tiền mặt
        self.f_cash = ttk.Frame(self.box_payment)
        self.f_cash.grid(row=r, column=0, columnspan=2, sticky="ew", pady=1)
        self.f_cash.columnconfigure(1, weight=1)

        ttk.Label(self.f_cash, text="Khách đưa (đ):").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=1)
        self.ent_received = ttk.Entry(self.f_cash, textvariable=self.var_received, font=("Segoe UI", 10, "bold"))
        self.ent_received.grid(row=0, column=1, sticky="ew", pady=1)
        self.ent_received.bind("<KeyRelease>", self._update_change_label)

        quick_f = ttk.Frame(self.f_cash)
        quick_f.grid(row=1, column=0, columnspan=2, sticky="w", pady=1)
        ttk.Button(quick_f, text="Đủ tiền", width=6, command=self._set_exact_cash).pack(side="left", padx=1)
        for v in (20000, 50000, 100000, 200000, 500000):
            ttk.Button(quick_f, text=money_text(v), width=5,
                       command=lambda val=v: self._set_quick_cash(val)).pack(side="left", padx=1)

        self.lbl_change = tk.Label(self.f_cash, text="", font=FONT_BOLD, anchor="w", bg=COLOR_BG)
        self.lbl_change.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(1, 1))

        # Khung quẹt thẻ POS
        self.f_card = ttk.Frame(self.box_payment)
        self.f_card.grid(row=r, column=0, columnspan=2, sticky="ew", pady=1)
        self.f_card.columnconfigure(1, weight=1)
        ttk.Label(self.f_card, text="Mã chuẩn chi (POS):").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.ent_card = ttk.Entry(self.f_card, textvariable=self.var_ref_card)
        self.ent_card.grid(row=0, column=1, sticky="ew")

        self._on_method_changed()

    def _build_qr_display_card(self):
        box = ttk.LabelFrame(self.scrollable_content, text=" Mã VietQR thanh toán tự động ", padding=6)
        box.grid(row=2, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        box.columnconfigure(0, weight=1)

        self.canvas_qr = tk.Canvas(box, width=140, height=140, bg="white",
                                   highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.canvas_qr.grid(row=0, column=0, pady=(0, 2))

        self.lbl_qr_title = tk.Label(box, text="Mã VietQR chuẩn NAPAS 247", font=FONT_BOLD, fg=COLOR_PRIMARY)
        self.lbl_qr_title.grid(row=1, column=0)

        self.lbl_qr_sub = tk.Label(box, text="Chọn xe để tự động tạo mã thanh toán",
                                   fg=COLOR_MUTED, font=FONT_SMALL, wraplength=280)
        self.lbl_qr_sub.grid(row=2, column=0, sticky="ew")

        ref_f = ttk.Frame(box)
        ref_f.grid(row=3, column=0, sticky="ew", pady=2)
        ref_f.columnconfigure(1, weight=1)
        ttk.Label(ref_f, text="Mã GD nhận:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(ref_f, textvariable=self.var_ref_code).grid(row=0, column=1, sticky="ew")

        act_f = ttk.Frame(box)
        act_f.grid(row=4, column=0, pady=2)
        ttk.Button(act_f, text="Sao chép nội dung", command=self._copy_memo).pack(side="left", padx=2)
        ttk.Button(act_f, text="Sao chép EMVCo", command=self._copy_emvco).pack(side="left", padx=2)
        ttk.Button(act_f, text="Lưu mã QR", command=self._save_qr_info).pack(side="left", padx=2)

        # Nút xác nhận thanh toán trực tiếp ngay dưới mã VietQR
        btn_qr_text = "✔ TÔI ĐÃ CHUYỂN KHOẢN (CHỜ XÁC THỰC)" if self.is_customer() else "✔ ĐÃ NHẬN TIỀN CHUYỂN KHOẢN"
        self.btn_qr_checkout = ttk.Button(box, text=btn_qr_text,
                                          style="Primary.TButton", command=self.on_checkout_exit)
        self.btn_qr_checkout.grid(row=5, column=0, sticky="ew", pady=(4, 2))

    def _build_history_card(self):
        box = ttk.LabelFrame(self.scrollable_content, text=" Nhật ký thanh toán & Đối soát gần đây ", padding=4)
        box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(2, 0))
        box.columnconfigure(0, weight=1)
        self.scrollable_content.rowconfigure(3, weight=0)

        cols = [
            ("time", "Thời gian", 130),
            ("plate", "Biển số", 110),
            ("amount", "Số tiền (đ)", 110),
            ("method", "Phương thức", 140),
            ("cashier", "Thu ngân", 100),
            ("ref", "Mã giao dịch / Ghi chú", 220),
        ]
        self.tree_hist = ttk.Treeview(box, columns=[c[0] for c in cols], show="headings", height=2)
        for cid, title, w in cols:
            self.tree_hist.heading(cid, text=title)
            self.tree_hist.column(cid, width=w, anchor="center")

        vsb = ttk.Scrollbar(box, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=vsb.set)
        self.tree_hist.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def _refresh_parked_vehicles(self):
        if not self.manager or self.var_mode.get() == "monthly_pay":
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
        if self.var_mode.get() == "monthly_pay":
            return
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
        self._update_checkout_btn_text()

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

    def _draw_matrix(self, matrix, canvas_size=140, padding=6):
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
        """Xác nhận thanh toán và cho xe ra bãi (hoặc thu tiền vé tháng)."""
        fee = self.var_calc_fee.get()
        m = self.var_method.get()

        # =========================================================================
        # TRƯỜNG HỢP 1: PHÍA KHÁCH HÀNG (YÊU CẦU 1 - HÌNH 1)
        # Bỏ chữ "cho xe ra", không kiểm tra ca trực nhân viên, hiện thông báo chờ xác thực
        # =========================================================================
        if self.is_customer():
            raw = self.var_selected_plate.get().strip()
            if not raw:
                messagebox.showwarning("Chưa chọn xe", "Vui lòng chọn xe cần thanh toán.", parent=self)
                return
            plate = raw.split(" ")[0].upper()

            if m not in ("bank_transfer", "momo", "zalopay"):
                messagebox.showwarning("Phương thức thanh toán",
                                       "Khách hàng chỉ thanh toán Online (VietQR / MoMo / ZaloPay).\nNếu thanh toán tiền mặt hoặc thẻ, vui lòng gặp nhân viên tại quầy.",
                                       parent=self)
                return

            # Ghi nhận thanh toán online vào hệ thống (không đòi hỏi ca trực của nhân viên)
            ref_code = f"CUST-ONL-{datetime.now():%y%m%d%H%M%S}"
            p = None
            if self.payments and fee > 0:
                try:
                    p = self.payments.create_payment(
                        kind="parking",
                        plate=plate,
                        amount=fee,
                        method=m,
                        received=fee,
                        reference=ref_code,
                        description=f"Khách thanh toán online xe {plate} (Chờ nhân viên/quản trị xác thực)"
                    )
                except Exception:
                    pass

            # Gửi yêu cầu mở barie tới phòng trực của nhân viên / quản trị
            if self.customers:
                try:
                    self.customers.add_pending_exit(
                        plate=plate,
                        amount=fee,
                        method=m,
                        ref=ref_code,
                        customer=self.get_cashier()
                    )
                except Exception:
                    pass

            messagebox.showinfo(
                "Chờ nhân viên (hoặc quản trị) xác thực",
                f"✅ ĐÃ THANH TOÁN ONLINE THÀNH CÔNG!\n\n"
                f"• Biển số xe: {plate}\n"
                f"• Số tiền: {format_money(fee)} ({PAYMENT_METHODS.get(m, m)})\n\n"
                f"📢 ĐÃ GỬI THÔNG BÁO TỚI PHÒNG TRỰC CỔNG!\n"
                f"Vui lòng chờ nhân viên (hoặc quản trị viên) xác thực mở barie để lấy xe rời đi. "
                f"Tuyệt đối không tự ý vượt cổng khi Barie chưa mở.",
                parent=self
            )
            self.on_data_changed()
            self.reload()
            return

        # =========================================================================
        # TRƯỜNG HỢP 2: THU TIỀN VÉ THÁNG (YÊU CẦU 2 - HÌNH 2)
        # Giao diện vé tháng phù hợp, bỏ chữ "cho xe ra", kích hoạt vé tháng
        # =========================================================================
        if self.var_mode.get() == "monthly_pay" and self._monthly_data:
            data = self._monthly_data
            plate = data.get("plate", "").upper()
            cashier = self.get_cashier()

            # Quản trị viên luôn có quyền thu; nhân viên cần ca trực
            if self.payments and not ensure_shift(self, self.payments, cashier):
                return

            received = fee
            ref = None

            if m == "cash":
                val = self.var_received.get().strip()
                if not val:
                    received = fee
                    self.var_received.set(money_text(fee))
                else:
                    try:
                        received = validators.parse_money(val)
                    except ValueError:
                        received = fee
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

            p = None
            if self.payments and fee > 0:
                try:
                    p = self.payments.create_payment(
                        kind="monthly",
                        plate=plate,
                        amount=fee,
                        method=m,
                        received=received,
                        reference=ref,
                        description=f"Thu tiền vé tháng {data.get('months', 1)} tháng cho xe {plate}"
                    )
                except Exception as e:
                    messagebox.showerror("Lỗi thanh toán", str(e), parent=self)
                    return

            from datetime import date, timedelta
            start_d = date.today()
            end_d = start_d + timedelta(days=30 * data.get("months", 1))
            self.monthly.add_monthly_ticket(
                plate=plate,
                owner=data.get("owner", "Khách hàng"),
                phone=data.get("phone", ""),
                vehicle_type=data.get("vehicle_type", "motorbike"),
                start_date=start_d,
                end_date=end_d
            )

            if self.customers and data.get("request_id"):
                try:
                    self.customers.resolve_request(data["request_id"], "approved", f"Đã thu tiền {p.payment_id if p else ''}")
                except Exception:
                    pass

            if self.customers:
                try:
                    self.customers.verify_vehicle(plate, True)
                except Exception:
                    pass

            messagebox.showinfo("Thành công", f"✔ Đã thu {format_money(fee)} ({PAYMENT_METHODS.get(m, m)}) và kích hoạt vé tháng thành công cho xe {plate}!", parent=self)
            if p:
                ReceiptDialog(self, self.payments.build_receipt(p.payment_id), filename=f"VeThang_{plate}.txt").show()

            self.setup_exit_payment()
            self.on_data_changed()
            self.reload()
            return

        # TRƯỜNG HỢP 3: NHÂN VIÊN THU TIỀN GIỮ XE & CHO XE RA BÃI
        raw = self.var_selected_plate.get().strip()
        if not raw:
            messagebox.showwarning("Chưa chọn xe", "Vui lòng chọn xe cần thanh toán.", parent=self)
            return
        plate = raw.split(" ")[0].upper()
        cashier = self.get_cashier()

        # Đảm bảo có ca trực cho nhân viên thu ngân
        if self.payments and not ensure_shift(self, self.payments, cashier):
            return

        received = fee
        ref = None

        if m == "cash":
            val = self.var_received.get().strip()
            if not val:
                received = fee
                self.var_received.set(money_text(fee))
            else:
                try:
                    received = validators.parse_money(val)
                except ValueError:
                    received = fee
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
