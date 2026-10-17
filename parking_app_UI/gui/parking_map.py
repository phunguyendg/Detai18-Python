"""Custom Widget: sơ đồ bãi xe vẽ bằng Canvas (kế thừa tk.Canvas)."""
import tkinter as tk

from config import (SLOT_COLORS, STATUS_LABELS, STATUS_OCCUPIED, COLS_PER_ROW,
                    FONT_BASE, FONT_BOLD, FONT_SMALL, COLOR_MUTED, COLOR_PRIMARY, COLOR_TEXT, COLOR_BORDER)
from gui.utils import format_dt

LANE_COLOR = "#DDE3EB"
SHADOW_COLOR = "#CBD3DE"


class ParkingMapCanvas(tk.Canvas):
    """Chỉ lo VẼ và phát sự kiện click; không chứa nghiệp vụ.

    on_slot_click(slot_id)         : click trái vào ô
    on_slot_menu(slot_id, event)   : click phải vào ô
    """

    def __init__(self, master, on_slot_click=None, on_slot_menu=None, show_plates=True, **kw):
        super().__init__(master, bg="#F7F9FC", highlightthickness=1, highlightbackground=COLOR_BORDER, **kw)
        self._slots = []
        self._by_id = {}
        self._selected = None
        self._hover = None
        self._mine = set()                # ô có xe của chính khách (chế độ khách hàng)
        self.show_plates = show_plates     # False: bản dành cho khách hàng, không hiện biển số xe khác
        self._on_slot_click = on_slot_click
        self._on_slot_menu = on_slot_menu
        self.bind("<Configure>", lambda _e: self.render(self._slots))
        self.bind("<Button-1>", self._handle_click)
        self.bind("<Button-3>", self._handle_right_click)
        self.bind("<Button-2>", self._handle_right_click)      # macOS
        self.bind("<Motion>", self._handle_motion)
        self.bind("<Leave>", self._handle_leave)

    # ------------------------------------------------------------ vẽ
    def _round_rect(self, x1, y1, x2, y2, r=10, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def render(self, slots):
        self._slots = list(slots)
        self._by_id = {s.slot_id: s for s in self._slots}
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or h < 50:                       # chưa hiển thị xong
            w, h = 700, 380
        pad = 22
        cell_w = (w - 2 * pad) / COLS_PER_ROW
        cell_h = max(64, min(120, (h - 3 * pad - 70) / 2))
        row_y = {"A": pad + 26, "B": h - pad - cell_h - 6}

        # nhãn hàng dạng "pill"
        for key, y in (("A", row_y["A"] - 16), ("B", row_y["B"] - 16)):
            self._round_rect(pad, y - 9, pad + 62, y + 9, r=8, fill="#E3E9F1", outline="")
            self.create_text(pad + 31, y, text=f"HÀNG {key}", font=FONT_SMALL, fill=COLOR_MUTED)

        # làn xe chạy ở giữa
        lane_top, lane_bot = row_y["A"] + cell_h + 12, row_y["B"] - 28
        self.create_rectangle(pad, lane_top, w - pad, lane_bot, fill=LANE_COLOR, outline="")
        mid = (lane_top + lane_bot) / 2
        self.create_line(pad + 10, mid, w - pad - 10, mid, dash=(10, 8), fill="white", width=2)
        self.create_text(w / 2, mid, text="  LỐI ĐI  ", fill="#78909C", font=FONT_BOLD, anchor="center",
                         tags="lane_label")
        bx = self.bbox("lane_label")
        if bx:
            rect = self.create_rectangle(bx[0], bx[1], bx[2], bx[3], fill=LANE_COLOR, outline="")
            self.tag_lower(rect, "lane_label")

        for s in self._slots:
            col = int(s.slot_id[1:]) - 1
            x1 = pad + col * cell_w + 5
            x2 = x1 + cell_w - 10
            y1 = row_y[s.slot_id[0]]
            y2 = y1 + cell_h
            tag = f"slot_{s.slot_id}"
            color = SLOT_COLORS.get(s.status, "#BDBDBD")
            selected = s.slot_id == self._selected
            hovered = s.slot_id == self._hover
            self._round_rect(x1 + 2, y1 + 3, x2 + 2, y2 + 3, fill=SHADOW_COLOR, outline="", tags=(tag,))   # bóng
            self._round_rect(x1, y1, x2, y2, tags=(tag,), fill=color,
                             outline="#FFB300" if selected else ("#90CAF9" if hovered else color),
                             width=4 if selected else (3 if hovered else 1))
            self.create_text((x1 + x2) / 2, y1 + 17, text=s.slot_id, fill="white",
                             font=("Segoe UI", 12, "bold"), tags=(tag,))
            cy = (y1 + y2) / 2 + 14
            if s.status == STATUS_OCCUPIED and s.slot_id in self._mine:
                pw = max(44, cell_w - 22)
                self._round_rect((x1 + x2) / 2 - pw / 2, cy - 17, (x1 + x2) / 2 + pw / 2, cy + 17,
                                 r=5, fill="white", outline="", tags=(tag,))
                self.create_text((x1 + x2) / 2, cy, text="XE CỦA\nBẠN", fill=COLOR_PRIMARY, justify="center",
                                 font=("Segoe UI", 8, "bold"), tags=(tag,))
            elif s.status == STATUS_OCCUPIED and not self.show_plates:
                self.create_text((x1 + x2) / 2, cy, text=STATUS_LABELS[STATUS_OCCUPIED], fill="white",
                                 font=("Segoe UI", 9), tags=(tag,))
            elif s.status == STATUS_OCCUPIED:
                # biển số hiển thị trong "tấm biển" trắng
                plate = s.current_plate.replace("-", "-\n", 1)
                pw = max(44, cell_w - 22)
                self._round_rect((x1 + x2) / 2 - pw / 2, cy - 17, (x1 + x2) / 2 + pw / 2, cy + 17,
                                 r=5, fill="white", outline="", tags=(tag,))
                self.create_text((x1 + x2) / 2, cy, text=plate, fill=COLOR_TEXT, justify="center",
                                 font=("Segoe UI", 8, "bold"), tags=(tag,))
            else:
                self.create_text((x1 + x2) / 2, cy, text=STATUS_LABELS.get(s.status, ""),
                                 fill="white", font=("Segoe UI", 9), tags=(tag,))

    def set_mine(self, slot_ids):
        self._mine = set(slot_ids)
        self.render(self._slots)

    def set_selected(self, slot_id):
        self._selected = slot_id
        self.render(self._slots)

    # ------------------------------------------------------------ sự kiện
    def _slot_id_at(self, x, y):
        for item in reversed(self.find_overlapping(x, y, x, y)):
            for t in self.gettags(item):
                if t.startswith("slot_"):
                    return t[5:]
        return None

    def _handle_click(self, e):
        sid = self._slot_id_at(e.x, e.y)
        if sid:
            self.set_selected(sid)
            if self._on_slot_click:
                self._on_slot_click(sid)

    def _handle_right_click(self, e):
        sid = self._slot_id_at(e.x, e.y)
        if sid and self._on_slot_menu:
            self._on_slot_menu(sid, e)

    def _handle_leave(self, _e):
        self.delete("tip")
        if self._hover is not None:
            self._hover = None
            self.render(self._slots)

    def _handle_motion(self, e):
        sid = self._slot_id_at(e.x, e.y)
        self.config(cursor="hand2" if sid else "")
        if sid != self._hover:                       # đổi ô đang rê chuột -> vẽ lại viền sáng
            self._hover = sid
            self.render(self._slots)
        self.delete("tip")
        if not sid:
            return
        s = self._by_id[sid]
        lines = [f"Ô {sid}: {STATUS_LABELS.get(s.status, s.status)}"]
        if s.status == STATUS_OCCUPIED and self.show_plates:
            lines += [f"Biển số: {s.current_plate}", f"Vào lúc: {format_dt(s.entry_time)}"]
        if s.status == "maintenance" and self.show_plates and getattr(s, "note", ""):
            lines.append(f"Lý do: {s.note}")
        flip = e.x > self.winfo_width() - 190
        tid = self.create_text(e.x - 12 if flip else e.x + 14, e.y + 14, text="\n".join(lines),
                               anchor="ne" if flip else "nw", font=FONT_BASE, fill="white", tags=("tip",))
        x1, y1, x2, y2 = self.bbox(tid)
        rect = self._round_rect(x1 - 8, y1 - 5, x2 + 8, y2 + 5, r=6, fill="#263238", outline="", tags=("tip",))
        self.tag_raise(tid, rect)
