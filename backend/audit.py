"""Ghi và truy vấn nhật ký hoạt động bằng JSON."""
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from config import DATA_DIR

@dataclass
class AuditEntry:
    created_at: datetime
    action: str
    description: str
    username: str = "system"
    role: str = "system"
    detail: str = ""

class AuditService:
    FILE = DATA_DIR / "audit.json"
    def __init__(self): self.entries=[]; self.load()
    def load(self):
        try:
            raw=json.loads(self.FILE.read_text(encoding="utf-8")) if self.FILE.exists() else []
            self.entries=[AuditEntry(datetime.fromisoformat(x["created_at"]),x["action"],x["description"],x.get("username","system"),x.get("role","system"),x.get("detail","")) for x in raw]
        except (ValueError,KeyError,TypeError): self.entries=[]
    def log(self, action, description, username="system", role="system", detail=""):
        self.entries.append(AuditEntry(datetime.now(),action,description,username,role,detail)); self.FILE.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.FILE.with_suffix('.json.tmp'); tmp.write_text(json.dumps([dict(asdict(e),created_at=e.created_at.isoformat()) for e in self.entries],ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(self.FILE)
        return self.entries[-1]
    def get_entries(self, filters=None):
        rows=list(self.entries); f=filters or {}
        if f.get('action'): rows=[e for e in rows if e.action==f['action']]
        if f.get('username'): rows=[e for e in rows if f['username'].lower() in e.username.lower()]
        if f.get('keyword'):
            k=f['keyword'].lower(); rows=[e for e in rows if k in e.description.lower() or k in e.detail.lower()]
        if f.get('date_from'): rows=[e for e in rows if e.created_at.date()>=f['date_from']]
        if f.get('date_to'): rows=[e for e in rows if e.created_at.date()<=f['date_to']]
        return list(reversed(rows))
