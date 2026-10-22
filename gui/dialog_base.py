"""Lớp nền cho các hộp thoại modal: dải tiêu đề, căn giữa theo cửa sổ cha, show() trả về result."""
import tkinter as tk
from tkinter import ttk

from config import COLOR_BG, COLOR_HEADER, FONT_TITLE, FONT_SMALL


class BaseDialog(tk.Toplevel):
    def __init__(self, parent, title, subtitle=""):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)
        self.transient(parent.winfo_toplevel())
        self.columnconfigure(0, weight=1)
        band = tk.Frame(self, bg=COLOR_HEADER)
        band.grid(row=0, column=0, sticky="ew")
        tk.Label(band, text=title, bg=COLOR_HEADER, fg="white", font=FONT_TITLE, anchor="w").pack(
            anchor="w", padx=16, pady=(10, 0 if subtitle else 10))
        if subtitle:
            tk.Label(band, text=subtitle, bg=COLOR_HEADER, fg="#8FA9C7", font=FONT_SMALL, anchor="w").pack(
                anchor="w", padx=16, pady=(0, 10))
        self.body = ttk.Frame(self, padding=16)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

    def show(self):
        """Hiện hộp thoại modal, chờ đóng, trả về self.result (None nếu hủy)."""
        self.update_idletasks()
        top = self.parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.wait_visibility()
        self.grab_set()
        self.wait_window(self)
        return self.result
