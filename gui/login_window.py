"""Đăng nhập / Đăng ký (khách hàng) và Đổi mật khẩu (kể cả bắt buộc đổi lần đầu)."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import APP_TITLE, FONT_TITLE, FONT_SMALL, COLOR_MUTED, COLOR_HEADER, COLOR_PRIMARY, COLOR_BG
from gui.contracts import AuthError


class LoginDialog(tk.Toplevel):
    """Sau khi đóng: self.user có .username, .role, .full_name, .must_change_password (None nếu hủy)."""

    def __init__(self, parent, auth):
        super().__init__(parent)
        self.auth = auth
        self.user = None
        self.title(f"{APP_TITLE} - Đăng nhập")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.configure(bg=COLOR_BG)
        band = tk.Frame(self, bg=COLOR_HEADER)
        band.grid(row=0, column=0, sticky="ew")
        tk.Label(band, text="P", bg=COLOR_PRIMARY, fg="white", font=("Segoe UI", 18, "bold"),
                 width=2).grid(row=0, column=0, rowspan=2, padx=(18, 12), pady=14)
        tk.Label(band, text="QUẢN LÝ BÃI ĐỖ XE", bg=COLOR_HEADER, fg="white", font=FONT_TITLE).grid(
            row=0, column=1, sticky="sw", padx=(0, 30), pady=(14, 0))
        tk.Label(band, text="Nhân viên · Quản trị · Khách hàng", bg=COLOR_HEADER, fg="#8FA9C7",
                 font=FONT_SMALL).grid(row=1, column=1, sticky="nw", pady=(0, 14))
        nb = ttk.Notebook(self)
        nb.grid(row=1, column=0, padx=16, pady=8)
        self._build_login(nb)
        self._build_register(nb)
        ttk.Label(self, text="Tài khoản quản trị ban đầu được cấu hình trong backend.",
                  foreground=COLOR_MUTED, font=FONT_SMALL).grid(row=2, column=0, pady=(0, 12))
        self.update_idletasks()
        x = parent.winfo_screenwidth() // 2 - self.winfo_reqwidth() // 2
        y = parent.winfo_screenheight() // 2 - self.winfo_reqheight() // 2
        self.geometry(f"+{x}+{y}")
        self.ent_user.focus_set()

    def _build_login(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="Đăng nhập")
        self.v_user, self.v_pass = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="Tên đăng nhập:").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_user = ttk.Entry(f, textvariable=self.v_user, width=28)
        self.ent_user.grid(row=0, column=1, pady=5)
        ttk.Label(f, text="Mật khẩu:").grid(row=1, column=0, sticky="w", pady=5)
        e = ttk.Entry(f, textvariable=self.v_pass, show="*", width=28)
        e.grid(row=1, column=1, pady=5)
        e.bind("<Return>", lambda _e: self.do_login())
        ttk.Button(f, text="Đăng nhập", style="Primary.TButton", command=self.do_login).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(f, text="Tài khoản nhân viên do quản trị viên cấp.\nKhách hàng: dùng tab 'Đăng ký khách hàng'.",
                  foreground=COLOR_MUTED, font=FONT_SMALL).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_register(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="Đăng ký khách hàng")
        self.r_user, self.r_name, self.r_phone = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.r_pass, self.r_pass2 = tk.StringVar(), tk.StringVar()
        fields = [("Tên đăng nhập:", self.r_user, ""), ("Họ và tên:", self.r_name, ""),
                  ("Số điện thoại:", self.r_phone, ""), ("Mật khẩu:", self.r_pass, "*"),
                  ("Nhập lại mật khẩu:", self.r_pass2, "*")]
        for i, (text, var, show) in enumerate(fields):
            ttk.Label(f, text=text).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=var, show=show, width=28).grid(row=i, column=1, pady=4)
        ttk.Label(f, text="Mật khẩu ≥ 8 ký tự, gồm cả chữ và số.", foreground=COLOR_MUTED, font=FONT_SMALL).grid(
            row=5, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Tạo tài khoản khách hàng", command=self.do_register).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def do_login(self):
        try:
            self.user = self.auth.login(self.v_user.get(), self.v_pass.get())
        except AuthError as e:
            messagebox.showerror("Đăng nhập thất bại", str(e), parent=self)
            self.v_pass.set("")
            return
        self.destroy()

    def do_register(self):
        if self.r_pass.get() != self.r_pass2.get():
            messagebox.showwarning("Mật khẩu không khớp", "Hai lần nhập mật khẩu phải giống nhau.", parent=self)
            return
        try:
            self.auth.register(self.r_user.get(), self.r_pass.get(), self.r_name.get(), self.r_phone.get())
        except AuthError as e:
            messagebox.showwarning("Không thể tạo tài khoản", str(e), parent=self)
            return
        messagebox.showinfo("Thành công", "Đã tạo tài khoản khách hàng. Hãy đăng nhập.", parent=self)
        self.v_user.set(self.r_user.get().strip())
        for v in (self.r_user, self.r_name, self.r_phone, self.r_pass, self.r_pass2):
            v.set("")


class ChangePasswordDialog(tk.Toplevel):
    """forced=True: bắt buộc đổi (lần đăng nhập đầu / sau khi quản trị đặt lại) - không có nút Hủy."""

    def __init__(self, parent, auth, username, forced=False):
        super().__init__(parent)
        self.auth, self.username, self.forced = auth, username, forced
        self.changed = False
        self.title("Đổi mật khẩu bắt buộc" if forced else "Đổi mật khẩu")
        self.resizable(False, False)
        if parent.winfo_viewable():
            self.transient(parent)
        self.v_old, self.v_new, self.v_new2 = tk.StringVar(), tk.StringVar(), tk.StringVar()
        f = ttk.Frame(self, padding=16)
        f.grid(row=0, column=0)
        r = 0
        if forced:
            ttk.Label(f, text="Đây là lần đăng nhập đầu hoặc mật khẩu vừa được đặt lại.\nHãy đặt mật khẩu mới để tiếp tục.",
                      foreground=COLOR_MUTED).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
            r = 1
        for i, (text, var) in enumerate([("Mật khẩu hiện tại:", self.v_old), ("Mật khẩu mới:", self.v_new),
                                         ("Nhập lại mật khẩu mới:", self.v_new2)], start=r):
            ttk.Label(f, text=text).grid(row=i, column=0, sticky="w", pady=5)
            ttk.Entry(f, textvariable=var, show="*", width=24).grid(row=i, column=1, pady=5)
        row = ttk.Frame(f)
        row.grid(row=r + 3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        if not forced:
            ttk.Button(row, text="Hủy", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="Đổi mật khẩu", style="Primary.TButton", command=self.submit).grid(row=0, column=1, padx=4)
        if forced:
            self.protocol("WM_DELETE_WINDOW", lambda: None)                                   
        self.update_idletasks()
        if parent.winfo_viewable():
            self.geometry(f"+{parent.winfo_rootx() + 140}+{parent.winfo_rooty() + 120}")
        else:
            self.geometry(f"+{self.winfo_screenwidth() // 2 - 160}+{self.winfo_screenheight() // 3}")

    def submit(self):
        if self.v_new.get() != self.v_new2.get():
            messagebox.showwarning("Không khớp", "Mật khẩu mới nhập lại không giống nhau.", parent=self)
            return
        try:
            self.auth.change_password(self.username, self.v_old.get(), self.v_new.get())
        except AuthError as e:
            messagebox.showwarning("Không thể đổi mật khẩu", str(e), parent=self)
            return
        messagebox.showinfo("Thành công", "Đã đổi mật khẩu.", parent=self)
        self.changed = True
        self.destroy()

    def show(self):
        self.wait_visibility()
        self.grab_set()
        self.wait_window(self)
        return self.changed
