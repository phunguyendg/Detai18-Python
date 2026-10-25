"""Ghi và truy vấn nhật ký hoạt động bằng JSON (Chuẩn hóa hiển thị và tìm kiếm cho AuditTab)."""
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from config import DATA_DIR, ROLE_ADMIN, ROLE_STAFF, ROLE_USER


@dataclass
class AuditEntry:
    time: datetime
    actor: str
    role: str
    action: str
    detail: str = ""

    # Thuộc tính tương thích ngược
    @property
    def created_at(self):
        return self.time

    @property
    def username(self):
        return self.actor

    @property
    def description(self):
        return self.detail


class AuditService:
    FILE = DATA_DIR / "audit.json"

    def __init__(self):
        self.entries = []
        self.actor = None
        self.load()

    def set_actor(self, user):
        """Thiết lập người thao tác hiện tại khi đăng nhập."""
        self.actor = user

    def load(self):
        try:
            if not self.FILE.exists():
                self.entries = []
                return
            raw = json.loads(self.FILE.read_text(encoding="utf-8"))
            self.entries = []
            for x in raw:
                t_str = x.get("time") or x.get("created_at")
                t = datetime.fromisoformat(t_str) if t_str else datetime.now()
                act = x.get("actor") or x.get("username") or "system"
                r = x.get("role") or "system"
                action = x.get("action") or ""
                dt = x.get("detail") or x.get("description") or ""
                self.entries.append(AuditEntry(time=t, actor=act, role=r, action=action, detail=dt))
        except (ValueError, KeyError, TypeError):
            self.entries = []

    def save(self):
        self.FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.FILE.with_suffix('.json.tmp')
        rows = [
            {
                "time": e.time.isoformat(),
                "actor": e.actor,
                "role": e.role,
                "action": e.action,
                "detail": e.detail,
                "created_at": e.time.isoformat(),
                "username": e.actor,
                "description": e.detail
            }
            for e in self.entries
        ]
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.FILE)

    def log(self, action, detail="", actor=None, role=None, username=None, description=None):
        """Ghi một bản ghi nhật ký hoạt động."""
        u_actor = actor or username or getattr(self.actor, 'username', None) or "system"
        u_role = role or getattr(self.actor, 'role', None) or "system"
        msg = detail or description or ""
        entry = AuditEntry(time=datetime.now(), actor=str(u_actor), role=str(u_role), action=str(action), detail=str(msg))
        self.entries.append(entry)
        self.save()
        return entry

    def get_entries(self, filters=None):
        """Lọc và trả về danh sách bản ghi nhật ký (mới nhất xếp trước)."""
        rows = list(self.entries)
        f = filters or {}
        if f.get('action') and f['action'] != "Tất cả":
            rows = [e for e in rows if e.action == f['action']]
        act = f.get('actor') or f.get('username')
        if act:
            rows = [e for e in rows if act.lower() in e.actor.lower()]
        if f.get('keyword'):
            k = f['keyword'].lower()
            rows = [e for e in rows if k in e.detail.lower() or k in e.action.lower()]
        if f.get('date_from'):
            rows = [e for e in rows if e.time.date() >= f['date_from']]
        if f.get('date_to'):
            rows = [e for e in rows if e.time.date() <= f['date_to']]
        return list(reversed(rows))
