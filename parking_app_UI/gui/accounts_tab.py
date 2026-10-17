"""Tab Nhân sự & Tài khoản (chỉ Quản trị): cấp/khóa tài khoản nhân viên, đặt lại mật khẩu, mở khóa đăng nhập."""
import tkinter as tk
from tkinter import ttk, messagebox

from config import ROLE_LABELS, ROLE_STAFF, ROLE_USER, ROLE_ADMIN, COLOR_MUTED, COLOR_DANGER, ROW_COLORS
from gui.contracts import ParkingError, AuthError
from gui.dialog_base import BaseDialog
from gui.utils import format_dt, gen_temp_password

ALL = "Tất cả"
COLUMNS = [("username", "Tài khoản", 110), ("name", "Họ tên", 170), ("phone", "SĐT", 100), ("role", "Vai trò", 130),
           ("status", "Trạng thái", 130), ("last", "Đăng nhập gần nhất", 135), ("by", "Người tạo", 90)]


class AddStaffDialog(BaseDialog):
    def __init__(self, parent, auth):
        super().__init__(parent, "Thêm nhân viên ca trực", "Nhân viên phải đổi mật khẩu ở lần đăng nhập đầu tiên")
        self.auth = auth
        self.v_user, self.v_name, self.v_phone = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_pass = tk.StringVar(value=gen_temp_password())
        b = self.body
        b.columnconfigure(1, weight=1)
        for i, (text, var) in enumerate([("Tên đăng nhập:", self.v_user), ("Họ và tên:", self.v_name),
                                         ("Số điện thoại:", self.v_phone), ("Mật khẩu tạm:", self.v_pass)]):
            ttk.Label(b, text=text).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 10))
            ttk.Entry(b, textvariable=var, width=28).grid(row=i, column=1, sticky="ew", pady=5)
        ttk.Button(b, text="Tạo ngẫu nhiên", command=lambda: self.v_pass.set(gen_temp_password())).grid(
            row=3, column=2, padx=(8, 0))
        row = ttk.Frame(b)
        row.grid(row=4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(row, text="Hủy", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(row, text="Tạo tài khoản", style="Primary.TButton", command=self.confirm).grid(row=0, column=1, padx=4)

    def confirm(self):
        try:
            acc = self.auth.create_staff(self.v_user.get(), self.v_name.get(), self.v_phone.get(), self.v_pass.get())
        except ParkingError as e:
            messagebox.showwarning("Không thể tạo tài khoản", str(e), parent=self)
            return
        except AuthError as e:
            messagebox.showwarning("Không thể tạo tài khoản", str(e), parent=self)
            return
        messagebox.showinfo("Đã tạo tài khoản",
                            f"Tài khoản: {acc.username}\nMật khẩu tạm: {self.v_pass.get()}\n\n"
                            "Hãy gửi thông tin này cho nhân viên. Mật khẩu tạm chỉ hiển thị một lần.", parent=self)
        self.result = acc
        self.destroy()


class AccountsTab(ttk.Frame):
    def __init__(self, master, auth, on_data_changed, get_username):
        super().__init__(master, padding=8)
        self.auth, self.on_data_changed, self.get_username = auth, on_data_changed, get_username
        self.var_role, self.var_kw = tk.StringVar(value=ALL), tk.StringVar()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()

    def _build(self):
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.columnconfigure(3, weight=1)
        ttk.Label(bar, text="Vai trò:").grid(row=0, column=0, padx=(0, 4))
        ttk.Combobox(bar, textvariable=self.var_role, state="readonly", width=18,
                     values=[ALL] + list(ROLE_LABELS.values())).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(bar, text="Tìm:").grid(row=0, column=2, padx=(0, 4))
        e = ttk.Entry(bar, textvariable=self.var_kw)
        e.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        e.bind("<Return>", lambda _e: self.reload())
        ttk.Button(bar, text="Lọc", command=self.reload).grid(row=0, column=4)

        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for cid, title, w in COLUMNS:
            self.tree.heading(cid, text=title)
            self.tree.column(cid, width=w, anchor="center")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("locked", background=ROW_COLORS["expired"], foreground=COLOR_MUTED)
        self.tree.tag_configure("temp", background=ROW_COLORS["expiring"])

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        btns.columnconfigure(0, weight=1)
        self.lbl_info = ttk.Label(btns, text="", foreground=COLOR_MUTED)
        self.lbl_info.grid(row=0, column=0, sticky="w")
        ttk.Button(btns, text="Thêm nhân viên", style="Primary.TButton", command=self.add_staff).grid(row=0, column=1, padx=3)
        ttk.Button(btns, text="Khóa / Mở khóa", command=self.toggle_active).grid(row=0, column=2, padx=3)
        ttk.Button(btns, text="Đặt lại mật khẩu", command=self.reset_password).grid(row=0, column=3, padx=3)
        ttk.Button(btns, text="Mở khóa đăng nhập tạm", command=self.unlock).grid(row=0, column=4, padx=3)

    def reload(self):
        role = next((k for k, v in ROLE_LABELS.items() if v == self.var_role.get()), None)
        rows = self.auth.list_accounts(role, self.var_kw.get())
        self.tree.delete(*self.tree.get_children())
        for a in rows:
            tag = "locked" if (not a.active or a.locked) else ("temp" if a.must_change else "")
            status = a.status_text + (" · chờ đổi MK" if a.must_change and a.active else "")
            self.tree.insert("", "end", iid=a.username, tags=(tag,), values=(
                a.username, a.full_name, a.phone, ROLE_LABELS[a.role], status, format_dt(a.last_login), a.created_by))
        n = {r: sum(1 for a in rows if a.role == r) for r in (ROLE_ADMIN, ROLE_STAFF, ROLE_USER)}
        self.lbl_info.config(text=f"{len(rows)} tài khoản · {n[ROLE_ADMIN]} quản trị · {n[ROLE_STAFF]} nhân viên · "
                                  f"{n[ROLE_USER]} khách hàng")

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Hãy chọn một tài khoản trong danh sách.")
            return None
        return sel[0]

    def _run(self, fn, ok_msg=None):
        try:
            fn()
        except (ParkingError, AuthError) as e:
            messagebox.showwarning("Không thể thực hiện", str(e))
            return False
        if ok_msg:
            messagebox.showinfo("Thành công", ok_msg)
        self.on_data_changed()
        return True

    def add_staff(self):
        if AddStaffDialog(self, self.auth).show():
            self.on_data_changed()

    def toggle_active(self):
        u = self._selected()
        if not u:
            return
        info = next(a for a in self.auth.list_accounts() if a.username == u)
        action = "mở khóa" if not info.active else "khóa"
        if messagebox.askyesno("Xác nhận", f"Bạn muốn {action} tài khoản {u}?"):
            self._run(lambda: self.auth.set_active(u, not info.active))

    def reset_password(self):
        u = self._selected()
        if not u:
            return
        temp = gen_temp_password()
        if messagebox.askyesno("Đặt lại mật khẩu", f"Đặt lại mật khẩu cho {u}?\nNgười dùng phải đổi mật khẩu ở lần đăng nhập tới."):
            self._run(lambda: self.auth.reset_password(u, temp),
                      f"Mật khẩu tạm của {u}: {temp}\n\nHãy gửi cho người dùng. Chỉ hiển thị một lần.")

    def unlock(self):
        u = self._selected()
        if u:
            self._run(lambda: self.auth.unlock_login(u), f"Đã mở khóa đăng nhập tạm cho {u}.")
