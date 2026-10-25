"""Tab Nhật ký hoạt động (chỉ Quản trị): ai làm gì, lúc nào - phục vụ kiểm soát."""
import csv
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog

from config import AUDIT_ACTIONS, ROLE_LABELS, DATA_DIR, COLOR_MUTED, ROW_COLORS
from gui.utils import format_dt, parse_date

ALL = "Tất cả"
BAD = ("login_failed", "lockout")


class AuditTab(ttk.Frame):
    def __init__(self, master, audit):
        super().__init__(master, padding=8)
        self.audit = audit
        self.var_actor, self.var_action = tk.StringVar(), tk.StringVar(value=ALL)
        self.var_from, self.var_to = tk.StringVar(), tk.StringVar()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        bar = ttk.LabelFrame(self, text=" Lọc nhật ký ", padding=8)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, text="Người thao tác:").grid(row=0, column=0, padx=(0, 4))
        e = ttk.Entry(bar, textvariable=self.var_actor, width=14)
        e.grid(row=0, column=1, padx=(0, 10))
        e.bind("<Return>", lambda _e: self.reload())
        ttk.Label(bar, text="Hành động:").grid(row=0, column=2, padx=(0, 4))
        ttk.Combobox(bar, textvariable=self.var_action, state="readonly", width=26,
                     values=[ALL] + list(AUDIT_ACTIONS.values())).grid(row=0, column=3, padx=(0, 10))
        ttk.Label(bar, text="Từ:").grid(row=0, column=4, padx=(0, 4))
        ttk.Entry(bar, textvariable=self.var_from, width=11).grid(row=0, column=5, padx=(0, 6))
        ttk.Label(bar, text="đến:").grid(row=0, column=6, padx=(0, 4))
        ttk.Entry(bar, textvariable=self.var_to, width=11).grid(row=0, column=7, padx=(0, 10))
        ttk.Button(bar, text="Lọc", style="Primary.TButton", command=self.reload).grid(row=0, column=8, padx=3)
        ttk.Button(bar, text="Xóa lọc", command=self.clear).grid(row=0, column=9, padx=3)
        ttk.Label(bar, text="Ngày dạng dd/mm/yyyy", foreground=COLOR_MUTED).grid(row=1, column=4, columnspan=4, sticky="w")

        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        cols = [("time", "Thời gian", 135), ("actor", "Người thao tác", 110), ("role", "Vai trò", 120),
                ("action", "Hành động", 190), ("detail", "Chi tiết", 420)]
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings")
        for cid, t, w in cols:
            self.tree.heading(cid, text=t)
            self.tree.column(cid, width=w, anchor="w" if cid == "detail" else "center")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("bad", background=ROW_COLORS["parked"])
        foot = ttk.Frame(self)
        foot.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        foot.columnconfigure(0, weight=1)
        self.lbl = ttk.Label(foot, text="")
        self.lbl.grid(row=0, column=0, sticky="w")
        ttk.Button(foot, text="Xuất nhật ký (CSV)", command=self.export).grid(row=0, column=1)

    def clear(self):
        self.var_actor.set("")
        self.var_action.set(ALL)
        self.var_from.set("")
        self.var_to.set("")
        self.reload()

    def reload(self):
        if hasattr(self.audit, 'load'):
            try:
                self.audit.load()
            except Exception:
                pass
        f = {}
        try:
            if self.var_actor.get().strip():
                f["actor"] = self.var_actor.get().strip()
            for k, v in AUDIT_ACTIONS.items():
                if self.var_action.get() == v:
                    f["action"] = k
            d1, d2 = parse_date(self.var_from.get(), "'Từ'"), parse_date(self.var_to.get(), "'Đến'")
            if d1 and d2 and d1 > d2:
                raise ValueError("'Từ' phải nhỏ hơn hoặc bằng 'Đến'.")
            if d1:
                f["date_from"] = d1
            if d2:
                f["date_to"] = d2
        except ValueError as e:
            messagebox.showwarning("Bộ lọc không hợp lệ", str(e))
            return
        rows = self.audit.get_entries(f)
        self.tree.delete(*self.tree.get_children())
        for e in rows:
            self.tree.insert("", "end", tags=("bad" if e.action in BAD else "",), values=(
                format_dt(e.time), e.actor, ROLE_LABELS.get(e.role, e.role), AUDIT_ACTIONS.get(e.action, e.action), e.detail))
        bad = sum(e.action in BAD for e in rows)
        self.lbl.config(text=f"{len(rows)} bản ghi · {bad} sự kiện đăng nhập bất thường (tô đỏ)")

    def export(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(title="Xuất nhật ký", initialdir=DATA_DIR, defaultextension=".csv",
                                            initialfile=f"nhat_ky_{datetime.now():%Y%m%d_%H%M}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Thời gian", "Người thao tác", "Vai trò", "Hành động", "Chi tiết"])
                for iid in self.tree.get_children():
                    w.writerow(self.tree.item(iid, "values"))
        except OSError as e:
            messagebox.showerror("Xuất thất bại", str(e))
            return
        messagebox.showinfo("Thành công", f"Đã xuất nhật ký:\n{path}")
