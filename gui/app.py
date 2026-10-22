"""Cửa sổ chính: Menu + Notebook 4 tab + Status bar. Điều phối refresh_all()."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from config import (APP_TITLE, MIN_WINDOW_SIZE, COLOR_BG, COLOR_CARD, COLOR_PRIMARY, COLOR_PRIMARY_DARK,
                    COLOR_DANGER, COLOR_HEADER, COLOR_BORDER, COLOR_TEXT, COLOR_MUTED, COLOR_SUCCESS,
                    COLOR_WARNING, FONT_BASE, FONT_BOLD, FONT_SMALL, FONT_HEADER, SLOT_COLORS, STATUS_LABELS,
                    STATUS_EMPTY, STATUS_MAINTENANCE, STATUS_OCCUPIED, ROLE_ADMIN, ROLE_LABELS,
                    COLOR_ORANGE, EXPIRING_DAYS, ROLE_USER, ROLE_STAFF, STAFF_ROLES)
from gui.contracts import ParkingError
from gui.entry_exit_panel import EntryExitPanel
from gui.history_tab import HistoryTab
from gui.login_window import LoginDialog, ChangePasswordDialog
from gui.monthly_tab import MonthlyTab
from gui.payments_tab import PaymentsTab
from gui.price_dialog import PriceDialog
from gui.shift_dialogs import OpenShiftDialog
from gui.slot_dialog import SlotStatusDialog
from gui.utils import format_money
from gui.parking_map import ParkingMapCanvas
from gui.stats_tab import StatsTab
from gui.vietqr_tab import VietQRTab
try:
    from gui.weather_tab import WeatherTab
except ImportError:
    WeatherTab = VietQRTab
from gui.accounts_tab import AccountsTab
from gui.audit_tab import AuditTab
from gui.customer_portal import CustomerStatusTab, MyVehiclesTab, MyMonthlyTab, MyHistoryTab
from datetime import date


class MainWindow(tk.Tk):
    def __init__(self, manager, monthly, stats, auth, payments, customers, audit, vietqr=None, weather=None):
        super().__init__()
        self.manager, self.monthly, self.stats, self.auth, self.payments = manager, monthly, stats, auth, payments
        self.customers, self.audit = customers, audit
        self.vietqr = vietqr if vietqr is not None else weather
        self.weather = self.vietqr  # Tương thích ngược
        self.user = None
        self._last_weather_alert = None
        self._tab_widgets, self._reload_fns = [], []
        self.title(APP_TITLE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.geometry("1200x720")
        self.configure(bg=COLOR_BG)
        self._setup_style()
        self.config(menu=tk.Menu(self))                                                                     

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self._build_statusbar()

        self.bind("<F5>", lambda _e: self.refresh_all())
        self.protocol("WM_DELETE_WINDOW", self.on_quit)
        self._tick()

    def _build_tabs(self):
        """Dựng các tab theo vai trò: khách hàng KHÔNG có tab nhân viên; tab quản trị chỉ dành cho admin."""
        for w in self._tab_widgets:
            try:
                self.notebook.forget(w)
            except tk.TclError:
                pass
            w.destroy()
        self._tab_widgets, self._reload_fns = [], []

        def add(widget, title, reload_fn=None):
            self.notebook.add(widget, text=f"  {title}  ")
            self._tab_widgets.append(widget)
            if reload_fn:
                self._reload_fns.append(reload_fn)

        if self.user.role == ROLE_USER:
            st = CustomerStatusTab(self.notebook, self.customers, self.manager, self.refresh_all)
            veh = MyVehiclesTab(self.notebook, self.customers, self.refresh_all)
            mon = MyMonthlyTab(self.notebook, self.customers, self.manager, self.refresh_all)
            his = MyHistoryTab(self.notebook, self.customers)
            for w, t in ((st, "Tình trạng bãi & Gửi xe"), (veh, "Xe của tôi"), (mon, "Vé tháng của tôi"), (his, "Lịch sử & Hóa đơn")):
                add(w, t, w.reload)
            self._add_vietqr_tab(add)
            return
        self._build_overview()
        add(self.overview, "Tổng quan", self._reload_overview)
        self.history_tab = HistoryTab(self.notebook, self.manager)
        self.monthly_tab = MonthlyTab(self.notebook, self.monthly, self.refresh_all, manager=self.manager,
                                      payments=self.payments, get_cashier=self.get_cashier, customers=self.customers)
        self.payments_tab = PaymentsTab(self.notebook, self.payments, self.refresh_all, self.get_cashier,
                                        on_shift_closed=self._on_shift_closed)
        self.stats_tab = StatsTab(self.notebook, self.stats)
        add(self.history_tab, "Lịch sử", self.history_tab.reload)
        add(self.monthly_tab, "Vé tháng", self.monthly_tab.reload)
        add(self.payments_tab, "Thanh toán & Ca", self.payments_tab.reload)
        add(self.stats_tab, "Thống kê & Báo cáo", self.stats_tab.reload)
        self._add_vietqr_tab(add)
        if self.user.role == ROLE_ADMIN:                             
            self.accounts_tab = AccountsTab(self.notebook, self.auth, self.refresh_all, self.get_cashier)
            self.audit_tab = AuditTab(self.notebook, self.audit)
            add(self.accounts_tab, "Nhân sự & Tài khoản", self.accounts_tab.reload)
            add(self.audit_tab, "Nhật ký hoạt động", self.audit_tab.reload)

    def _add_vietqr_tab(self, add):
        """Tab Thanh toán VietQR dành cho MỌI vai trò (chuẩn NAPAS 247 / EMVCo)."""
        self.vietqr_tab = VietQRTab(self.notebook, self.vietqr, on_update=self._on_vietqr_update,
                                    manager=self.manager, payments=self.payments,
                                    monthly=self.monthly, get_cashier=self.get_cashier,
                                    on_data_changed=self.refresh_all)
        add(self.vietqr_tab, "Thanh toán VietQR", self.vietqr_tab.reload)
        self.vietqr_tab.start()

    def _add_weather_tab(self, add):
        """Hàm tương thích ngược với mã cũ."""
        self._add_vietqr_tab(add)

    def _on_vietqr_update(self, summary, advice=None):
        """Cập nhật thông tin VietQR trên thanh header."""
        self.var_weather.set(summary)

    def _on_weather_update(self, summary, advice=None):
        self._on_vietqr_update(summary, advice)                                                       

    def _reload_overview(self):
        self.map_canvas.render(self.manager.get_all_slots())
        self.panel.refresh_slot_choices()
        self._update_selection_label()

                                                                        
    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", font=FONT_BASE, background=COLOR_BG, foreground=COLOR_TEXT)
        for name in ("TFrame", "TLabel", "TLabelframe", "TRadiobutton", "TCheckbutton", "TNotebook"):
            s.configure(name, background=COLOR_BG)
        s.configure("TLabelframe", bordercolor=COLOR_BORDER, relief="solid", borderwidth=1)
        s.configure("TLabelframe.Label", background=COLOR_BG, font=FONT_BOLD, foreground=COLOR_PRIMARY)
                         
        s.configure("Card.TFrame", background=COLOR_CARD)
        s.configure("Card.TLabel", background=COLOR_CARD)
        s.configure("Card.TRadiobutton", background=COLOR_CARD)
        s.configure("Card.TCheckbutton", background=COLOR_CARD)
        s.map("Card.TCheckbutton", background=[("active", COLOR_CARD)])
        s.map("Card.TRadiobutton", background=[("active", COLOR_CARD)])
                                                         
        s.configure("TNotebook", tabmargins=(0, 0, 0, 0), borderwidth=0)
        s.configure("TNotebook.Tab", padding=(18, 9), font=FONT_BOLD, background="#DCE3EC",
                    foreground=COLOR_MUTED, borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", COLOR_CARD), ("active", "#E8EDF4")],
              foreground=[("selected", COLOR_PRIMARY)])
                      
        s.configure("Treeview", rowheight=28, background=COLOR_CARD, fieldbackground=COLOR_CARD,
                    bordercolor=COLOR_BORDER, borderwidth=1)
        s.configure("Treeview.Heading", font=FONT_BOLD, background="#E3E9F1", foreground=COLOR_TEXT,
                    relief="flat", padding=(6, 7))
        s.map("Treeview.Heading", background=[("active", "#D3DCE8")])
        s.map("Treeview", background=[("selected", "#CFE3FB")], foreground=[("selected", COLOR_TEXT)])
                                                                 
        for w in ("TEntry", "TCombobox"):
            s.configure(w, fieldbackground="white", bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER,
                        darkcolor=COLOR_BORDER, padding=5)
            s.map(w, bordercolor=[("focus", COLOR_PRIMARY)], lightcolor=[("focus", COLOR_PRIMARY)],
                  darkcolor=[("focus", COLOR_PRIMARY)])
        s.map("TCombobox", fieldbackground=[("readonly", "white")], selectbackground=[("readonly", "white")],
              selectforeground=[("readonly", COLOR_TEXT)])
                    
        s.configure("TButton", padding=(10, 6), background="#E3E9F1", bordercolor=COLOR_BORDER, relief="flat")
        s.map("TButton", background=[("active", "#D3DCE8"), ("disabled", "#F0F2F5")],
              foreground=[("disabled", "#A0A7B0")])
        for name, bg, active in (("Primary", COLOR_PRIMARY, COLOR_PRIMARY_DARK), ("Danger", COLOR_DANGER, "#A62323")):
            s.configure(f"{name}.TButton", background=bg, foreground="white", font=FONT_BOLD,
                        padding=(10, 8), bordercolor=bg, relief="flat")
            s.map(f"{name}.TButton", background=[("active", active), ("disabled", "#BDBDBD")],
                  foreground=[("disabled", "#F5F5F5")], bordercolor=[("active", active)])
                                            
        for level, color in (("Ok", COLOR_SUCCESS), ("Warn", COLOR_WARNING), ("Crit", COLOR_DANGER)):
            s.configure(f"{level}.Horizontal.TProgressbar", background=color, troughcolor="#DCE3EC",
                        bordercolor="#DCE3EC", lightcolor=color, darkcolor=color, thickness=16)
                       
        s.configure("Vertical.TScrollbar", background="#CBD3DE", troughcolor=COLOR_BG, bordercolor=COLOR_BG,
                    arrowcolor=COLOR_MUTED)
        s.configure("Horizontal.TScrollbar", background="#CBD3DE", troughcolor=COLOR_BG, bordercolor=COLOR_BG,
                    arrowcolor=COLOR_MUTED)
                                                               
        s.map("Treeview", **{k: [e for e in s.map("Treeview", query_opt=k) if e[:2] != ("!disabled", "!selected")]
                             for k in ("foreground", "background")})

                                                                                 
    def _build_header(self):
        bar = tk.Frame(self, bg=COLOR_HEADER)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(2, weight=1)
        tk.Label(bar, text="P", bg=COLOR_PRIMARY, fg="white", font=("Segoe UI", 16, "bold"),
                 width=2).grid(row=0, column=0, padx=(14, 10), pady=10)
        title = tk.Frame(bar, bg=COLOR_HEADER)
        title.grid(row=0, column=1, sticky="w")
        tk.Label(title, text="QUẢN LÝ BÃI ĐỖ XE", bg=COLOR_HEADER, fg="white", font=FONT_HEADER).pack(anchor="w")
        self.lbl_toast = tk.Label(bar, text="", bg=COLOR_HEADER, fg="white", font=FONT_BOLD, padx=12, pady=6, wraplength=460)
        self.lbl_toast.grid(row=0, column=2)
        self.var_user = tk.StringVar()
        self.var_clock = tk.StringVar()
        self.var_weather = tk.StringVar()
        right = tk.Frame(bar, bg=COLOR_HEADER)
        right.grid(row=0, column=3, padx=14, sticky="e")
        tk.Label(right, textvariable=self.var_user, bg="#1D4468", fg="white", font=FONT_BOLD,
                 padx=10, pady=3).pack(anchor="e")
        tk.Label(right, textvariable=self.var_weather, bg=COLOR_HEADER, fg="#CFE3FF", font=FONT_SMALL).pack(anchor="e")
        tk.Label(right, textvariable=self.var_clock, bg=COLOR_HEADER, fg="#8FA9C7", font=FONT_SMALL).pack(anchor="e")
        self._toast_job = None

    def toast(self, text, kind="success"):
        """Thông báo nhanh trên header, tự tắt sau 5 giây (không chặn thao tác)."""
        color = {"success": COLOR_SUCCESS, "error": COLOR_DANGER, "warn": COLOR_ORANGE}.get(kind, COLOR_PRIMARY)
        self.lbl_toast.config(text=text, bg=color)
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(5000, lambda: self.lbl_toast.config(text="", bg=COLOR_HEADER))

                                                                       
    def _build_menu(self):
        bar = tk.Menu(self)
        staff_side = self.user.role in STAFF_ROLES
        menu_file = tk.Menu(bar, tearoff=0)
        menu_file.add_command(label="Làm mới dữ liệu (F5)", command=self.refresh_all)
        if staff_side:
            menu_file.add_command(label="Xuất báo cáo ca (CSV)...", command=lambda: self.stats_tab.on_export())
        if self.user.role == ROLE_ADMIN:
            menu_file.add_command(label="Bảng giá...", command=self.show_prices)
            menu_file.add_command(label="Sao lưu dữ liệu (JSON)...", command=self.backup)
        menu_file.add_separator()
        menu_file.add_command(label="Thoát", command=self.on_quit)
        bar.add_cascade(label="Tệp", menu=menu_file)
        if staff_side:
            menu_shift = tk.Menu(bar, tearoff=0)
            menu_shift.add_command(label="Mở ca", command=lambda: self.payments_tab.open_shift())
            menu_shift.add_command(label="Chốt ca", command=lambda: self.payments_tab.close_shift())
            bar.add_cascade(label="Ca trực", menu=menu_shift)
        menu_acc = tk.Menu(bar, tearoff=0)
        menu_acc.add_command(label="Đổi mật khẩu...", command=lambda: ChangePasswordDialog(self, self.auth, self.user.username).show())
        menu_acc.add_command(label="Đăng xuất", command=self.logout)
        bar.add_cascade(label="Tài khoản", menu=menu_acc)
        menu_help = tk.Menu(bar, tearoff=0)
        menu_help.add_command(label="Hướng dẫn sử dụng", command=self.show_help)
        menu_help.add_command(label="Giới thiệu", command=lambda: messagebox.showinfo(
            "Giới thiệu", "Ứng dụng quản lý bãi đỗ xe\nĐề tài 18 - Python OOP + Tkinter"))
        bar.add_cascade(label="Trợ giúp", menu=menu_help)
        self.config(menu=bar)

    def get_cashier(self):
        return self.user.username if self.user else ""

    def show_prices(self):
        if PriceDialog(self, self.manager).show():
            self.refresh_all()

    def backup(self):
        from datetime import datetime
        from tkinter import filedialog
        from config import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(title="Sao lưu dữ liệu", initialdir=DATA_DIR, defaultextension=".json",
                                            initialfile=f"backup_{datetime.now():%Y%m%d_%H%M}.json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            saved = self.stats.backup_data(path)
        except (ParkingError, OSError) as e:
            messagebox.showerror("Sao lưu thất bại", str(e))
            return
        messagebox.showinfo("Thành công", f"Đã sao lưu dữ liệu:\n{saved}")

                                                                                
    def _build_overview(self):
        self.overview = ttk.Frame(self.notebook, padding=10)
        self.overview.columnconfigure(0, weight=1)
        self.overview.rowconfigure(1, weight=1)

        search = ttk.Frame(self.overview)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 8), padx=(0, 12))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Tìm xe đang đỗ:").grid(row=0, column=0, padx=(0, 8))
        self.var_find = tk.StringVar()
        ent = ttk.Entry(search, textvariable=self.var_find)
        ent.grid(row=0, column=1, sticky="ew")
        ent.bind("<Return>", lambda _e: self.find_vehicle())
        ttk.Button(search, text="Tìm", command=self.find_vehicle).grid(row=0, column=2, padx=(8, 0))

        self.map_canvas = ParkingMapCanvas(self.overview, on_slot_click=self.on_slot_click,
                                           on_slot_menu=self.on_slot_menu)
        self.map_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 12))

        legend = ttk.Frame(self.overview)
        legend.grid(row=2, column=0, sticky="w", pady=(8, 0))
        for i, status in enumerate((STATUS_EMPTY, STATUS_OCCUPIED, STATUS_MAINTENANCE)):
            tk.Label(legend, bg=SLOT_COLORS[status], width=2, height=1).grid(row=0, column=i * 2, padx=(0, 5))
            ttk.Label(legend, text=STATUS_LABELS[status]).grid(row=0, column=i * 2 + 1, padx=(0, 18))
        ttk.Label(legend, text="Click ô để điền form · Chuột phải hoặc nút bên dưới để sửa trạng thái ô",
                  foreground=COLOR_MUTED).grid(row=0, column=6)

        sel = tk.Frame(self.overview, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        sel.grid(row=3, column=0, sticky="ew", pady=(8, 0), padx=(0, 12))
        sel.columnconfigure(0, weight=1)
        self._selected_slot = None
        self.var_sel = tk.StringVar(value="Chưa chọn ô nào - click một ô trên sơ đồ")
        tk.Label(sel, textvariable=self.var_sel, bg=COLOR_CARD, font=FONT_BOLD, anchor="w", padx=10, pady=8).grid(
            row=0, column=0, sticky="ew")
        self.btn_slot = ttk.Button(sel, text="Sửa trạng thái ô...", command=lambda: self._edit_slot(self._selected_slot))
        self.btn_slot.grid(row=0, column=1, padx=8, pady=4)
        self.btn_slot.state(["disabled"])

        card = tk.Frame(self.overview, bg=COLOR_CARD, bd=0, highlightthickness=1,
                        highlightbackground=COLOR_BORDER, highlightcolor=COLOR_BORDER)
        card.grid(row=0, column=1, rowspan=4, sticky="n")
        self.panel = EntryExitPanel(card, self.manager, self.monthly, self.payments, self.refresh_all,
                                    notify=self.toast, get_cashier=self.get_cashier, customers=self.customers)
        self.panel.grid(row=0, column=0)

    def find_vehicle(self):
        q = self.var_find.get().strip().upper()
        if not q:
            return
        hits = [s for s in self.manager.get_all_slots() if s.status == STATUS_OCCUPIED and q in s.current_plate.upper()]
        if not hits:
            self.toast(f"Không có xe nào khớp '{q}' đang đỗ trong bãi", "error")
            return
        self.map_canvas.set_selected(hits[0].slot_id)
        extra = f" (+{len(hits) - 1} xe khác khớp)" if len(hits) > 1 else ""
        self.toast(f"Xe {hits[0].current_plate} đang ở ô {hits[0].slot_id}{extra}", "info")

    def on_slot_click(self, slot_id):
        self._selected_slot = slot_id
        self.btn_slot.state(["!disabled"])
        self._update_selection_label()
        slot = self.manager.get_slot(slot_id)
        if slot.status == STATUS_EMPTY:
            self.panel.set_entry_slot(slot_id)
        elif slot.status == STATUS_OCCUPIED:
            self.panel.set_exit_plate(slot.current_plate)
            if hasattr(self, 'vietqr_tab'):
                self.vietqr_tab.select_plate(slot.current_plate)

    def _update_selection_label(self):
        sid = getattr(self, "_selected_slot", None)
        if not sid:
            return
        slot = self.manager.get_slot(sid)
        text = f"Ô {sid}: {STATUS_LABELS[slot.status]}"
        if slot.status == STATUS_OCCUPIED:
            text += f" · xe {slot.current_plate}"
        elif slot.status == STATUS_MAINTENANCE and slot.note:
            text += f" · lý do: {slot.note}"
        self.var_sel.set(text)

    def on_slot_menu(self, slot_id, event):
        """Chuột phải: Nhân viên và Quản trị sửa trạng thái ô."""
        if self.user.role not in STAFF_ROLES:
            return
        self.map_canvas.set_selected(slot_id)
        self._selected_slot = slot_id
        self.btn_slot.state(["!disabled"])
        self._update_selection_label()
        slot = self.manager.get_slot(slot_id)
        menu = tk.Menu(self, tearoff=0)
        if slot.status == STATUS_OCCUPIED:
            menu.add_command(label=f"Ô {slot_id} đang có xe - không đổi được", state="disabled")
        else:
            menu.add_command(label=f"Sửa trạng thái ô {slot_id}...", command=lambda: self._edit_slot(slot_id))
        menu.tk_popup(event.x_root, event.y_root)

    def _edit_slot(self, slot_id):
        if not slot_id:
            return
        res = SlotStatusDialog(self, self.manager, slot_id).show()
        if res is not None:
            self.refresh_all()
            self.toast(f"✔ Ô {slot_id}: {'đã đặt bảo trì' if res else 'đã mở lại (Trống)'}", "success")

    def _on_shift_closed(self, shift):
        """Nhân viên chốt ca XONG thì tự động đăng xuất (quản trị chốt thay thì không)."""
        if self.user and self.user.role == ROLE_STAFF and shift.cashier == self.user.username:
            self.after(200, self._auto_logout)

    def _auto_logout(self):
        messagebox.showinfo("Kết thúc ca", "Ca trực đã được chốt. Hệ thống sẽ tự động đăng xuất.")
        self.auth.logout()
        self.user = None
        if not self.login_flow():
            self.destroy()

                                                                             
    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#263238")
        bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        bar.columnconfigure(0, weight=1)
        self.var_status = tk.StringVar()
        tk.Label(bar, textvariable=self.var_status, bg="#263238", fg="white", font=FONT_BASE,
                 anchor="w", padx=12, pady=5).grid(row=0, column=0, sticky="ew")

    def _update_status_bar(self):
        who = f"{self.user.full_name or self.user.username} · {ROLE_LABELS.get(self.user.role, self.user.role)}"
        self.var_user.set(who)
        d = self.stats.get_statistics() if self.user.role in STAFF_ROLES else self.customers.get_public_status()
        text = f"●  Trống: {d.get('empty', 0)}     ●  Đang dùng: {d.get('occupied', 0)}     ●  Bảo trì: {d.get('maintenance', 0)}" \
               f"     ●  Công suất: {d.get('occupancy_rate', 0):.0f}%"
        self.var_status.set(text)

    def _tick(self):
        self.var_clock.set(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self._tick_job = self.after(1000, self._tick)

    def destroy(self):
        job = getattr(self, "_tick_job", None)
        if job:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        super().destroy()

                                                                          
    def refresh_all(self):
        """MỌI thao tác thay đổi dữ liệu đều kết thúc bằng hàm này."""
        if not self.user:
            return
        for fn in self._reload_fns:
            fn()
        self._update_status_bar()

                                                                                         
    @property
    def is_admin(self):
        return bool(self.user and self.user.role == ROLE_ADMIN)

    def apply_permissions(self):
        """Admin: đầy đủ. Nhân viên: không sửa/xóa vé tháng nhập tay, không xuất giao dịch toàn hệ thống."""
        if self.user.role not in STAFF_ROLES:
            return
        self.monthly_tab.apply_permissions(self.is_admin)
        self.stats_tab.apply_permissions(True)                                                      
        self.payments_tab.apply_permissions(self.is_admin)

    def login_flow(self):
        """Hiện hộp thoại đăng nhập; trả về True nếu đăng nhập thành công."""
        self.withdraw()
        self.lbl_toast.config(text="", bg=COLOR_HEADER)                                      
        self._last_weather_alert = None
        dlg = LoginDialog(self, self.auth)
        dlg.wait_visibility()
        dlg.grab_set()
        self.wait_window(dlg)
        if dlg.user is None:
            return False
        self.user = dlg.user
        if self.user.must_change_password:                                                                     
            if not ChangePasswordDialog(self, self.auth, self.user.username, forced=True).show():
                self.auth.logout()
                self.user = None
                return self.login_flow()
        self._build_menu()
        self._build_tabs()
        self.apply_permissions()
        self.refresh_all()
        self.notebook.select(0)
        self.deiconify()
        self.update_idletasks()
        self._after_login()
        return True

    def _after_login(self):
        """Nhắc theo vai trò: khách được chào; nhân viên được nhắc mở ca / ca của người khác / việc tồn đọng."""
        if self.user.role == ROLE_USER:
            self.toast(f"Xin chào {self.user.full_name or self.user.username}", "info")
            return
        msg = None
        cur = self.payments.current_shift()
        if cur and cur.cashier != self.user.username:
            msg = (f"⚠ Ca {cur.shift_id} đang mở bởi {cur.cashier} - cần chốt ca đó (hoặc nhờ quản trị chốt thay) "
                   "trước khi bạn mở ca mới", "warn")
        elif not cur and messagebox.askyesno("Mở ca trực", "Hiện chưa có ca trực nào đang mở.\nMở ca ngay để bắt đầu thu tiền?"):
            if OpenShiftDialog(self, self.payments, self.get_cashier()).show():
                self.refresh_all()
        if not msg:
            pending = len(self.customers.get_requests("pending")) + len(self.customers.get_pending_vehicles())
            soon = [t for t in self.monthly.get_all_monthly_tickets() if 0 <= (t.end_date - date.today()).days <= EXPIRING_DAYS]
            if pending:
                msg = (f"● Có {pending} yêu cầu / xe của khách đang chờ xử lý (tab Vé tháng)", "info")
            elif soon:
                msg = (f"⚠ Có {len(soon)} vé tháng sắp hết hạn trong {EXPIRING_DAYS} ngày - xem tab Vé tháng", "warn")
        if msg:
            self.toast(*msg)

    def _confirm_open_shift_leave(self):
        """Ca của chính mình còn mở: nhắc chốt ca (đối soát tiền) trước khi rời."""
        if self.user and self.user.role in STAFF_ROLES:
            cur = self.payments.current_shift()
            if cur and cur.cashier == self.user.username:
                return messagebox.askyesno("Ca trực chưa chốt",
                                           "Ca trực của bạn vẫn đang mở. Nên chốt ca (đối soát tiền mặt) trước khi rời.\n\n"
                                           "Vẫn tiếp tục?")
        return True

    def logout(self):
        if not self._confirm_open_shift_leave():
            return
        if messagebox.askyesno("Đăng xuất", "Bạn muốn đăng xuất?"):
            self.auth.logout()
            self.user = None
            if not self.login_flow():
                self.destroy()

    def run(self):
        if self.login_flow():
            self.mainloop()
        else:
            self.destroy()

    def on_quit(self):
        if not self._confirm_open_shift_leave():
            return
        if messagebox.askyesno("Thoát", "Bạn có chắc muốn thoát chương trình?"):
            if self.user:
                self.auth.logout()
            self.destroy()

    def show_help(self):
        if self.user.role == ROLE_USER:
            text = ("1. Tab Tình trạng bãi: xem chỗ trống, công suất và bảng giá (không hiện biển số xe khác).\n"
                    "2. Xe của tôi: thêm biển số xe. Xe có vé tháng đứng tên SĐT của bạn được xác minh tự động;\n"
                    "   xe khác cần nhân viên xác minh tại quầy.\n"
                    "3. Vé tháng của tôi: xem hạn vé, gửi yêu cầu mua/gia hạn - thanh toán tại quầy.\n"
                    "4. Lịch sử & Hóa đơn: xem lượt gửi xe và hóa đơn của xe thuộc tài khoản bạn.")
        else:
            text = ("1. Đầu ca: mở ca trực (đứng tên tài khoản của bạn). Chưa mở ca thì không thu được tiền.\n"
                    "2. Xe vào: nhập biển số, chọn loại xe và chỗ, bấm NHẬN XE.\n"
                    "3. Xe ra: Tính phí, THANH TOÁN (tiền mặt, VietQR, MoMo, ZaloPay, thẻ). Tick 'Khách mất vé' nếu mất vé.\n"
                    "4. Vé tháng: MUA / GIA HẠN; xử lý yêu cầu và xác minh xe của khách.\n"
                    "5. Cuối ca: Thanh toán & Ca > Chốt ca (đối soát tiền mặt). Mỗi ca chỉ thu bởi thu ngân của ca đó.\n"
                    "6. Quản trị: tab Nhân sự & Tài khoản, Nhật ký hoạt động; chuột phải ô để đặt bảo trì; Tệp > Bảng giá, Sao lưu.\n"
                    "7. F5: làm mới dữ liệu.")
        messagebox.showinfo("Hướng dẫn sử dụng", text)
