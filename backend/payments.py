"""Quản lý thanh toán, hóa đơn và ca trực; dữ liệu được lưu bằng JSON."""
import json
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from backend.exceptions import ParkingError, PaymentError
from config import DATA_DIR, PAYMENT_METHODS, PARKING_NAME, DEFAULT_OPENING_CASH

@dataclass
class Payment:
    payment_id: str
    created_at: datetime
    kind: str
    plate: str
    amount: int
    method: str
    reference_code: str | None = None
    description: str = ""
    cashier: str = "admin"
    shift_id: str = "S01"
    received: int = 0
    change: int = 0

@dataclass
class Shift:
    shift_id: str
    cashier: str
    opened_at: datetime
    opening_cash: int
    closed_at: datetime | None = None
    counted_cash: int | None = None
    expected_cash: int | None = None
    difference: int | None = None
    note: str = ""
    @property
    def is_open(self): return self.closed_at is None

class PaymentService:
    PAYMENTS_FILE = DATA_DIR / "payments.json"
    SHIFTS_FILE = DATA_DIR / "shifts.json"
    def __init__(self, audit=None):
        self.audit = audit
        self.payments=[]; self.shifts=[]; self.current_shift_obj=None; self.load()
    def _write(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp=path.with_suffix(path.suffix+'.tmp')
        tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=lambda x:x.isoformat() if hasattr(x,'isoformat') else str(x)),encoding='utf-8')
        tmp.replace(path)
    def load(self):
        self.PAYMENTS_FILE.parent.mkdir(parents=True,exist_ok=True)
        try:
            rows=json.loads(self.PAYMENTS_FILE.read_text(encoding='utf-8')) if self.PAYMENTS_FILE.exists() else []
            self.payments=[]
            for d in rows:
                d['created_at']=datetime.fromisoformat(d['created_at']); self.payments.append(Payment(**d))
        except (ValueError,TypeError,KeyError): self.payments=[]
        try:
            rows=json.loads(self.SHIFTS_FILE.read_text(encoding='utf-8')) if self.SHIFTS_FILE.exists() else []
            self.shifts=[]
            for d in rows:
                d['opened_at']=datetime.fromisoformat(d['opened_at'])
                if d.get('closed_at'): d['closed_at']=datetime.fromisoformat(d['closed_at'])
                self.shifts.append(Shift(**d))
        except (ValueError,TypeError,KeyError): self.shifts=[]
        self.current_shift_obj=next((s for s in reversed(self.shifts) if s.is_open),None)
    def _save_payments(self): self._write(self.PAYMENTS_FILE,[asdict(p) for p in self.payments])
    def _save_shifts(self): self._write(self.SHIFTS_FILE,[asdict(s) for s in self.shifts])
    def get_payment_methods(self): return list(PAYMENT_METHODS.items())
    def current_shift(self): return self.current_shift_obj
    def get_shifts(self): return list(reversed(self.shifts))
    def open_shift(self,cashier,opening_cash=DEFAULT_OPENING_CASH):
        if self.current_shift_obj: raise ParkingError('Đang có ca trực chưa chốt.')
        if int(opening_cash)<0: raise ParkingError('Tiền đầu ca không được âm.')
        n=max([int(s.shift_id[1:]) for s in self.shifts if s.shift_id[1:].isdigit()] or [0])+1
        sh=Shift(f'S{n:02d}',cashier,datetime.now(),int(opening_cash)); self.shifts.append(sh); self.current_shift_obj=sh; self._save_shifts()
        if hasattr(self, 'audit') and self.audit:
            self.audit.log("shift_open", f"Mở ca trực {sh.shift_id}, tiền đầu ca {sh.opening_cash:,.0f} đ", actor=cashier)
        return sh
    def shift_summary(self,shift_id):
        rows=[p for p in self.payments if p.shift_id==shift_id]
        by={k:sum(p.amount for p in rows if p.method==k) for k in PAYMENT_METHODS}
        return {'total':sum(p.amount for p in rows),'count':len(rows),'cash':by.get('cash',0),'by_method':by}
    def close_shift(self,counted,note=''):
        sh=self.current_shift_obj
        if not sh: raise ParkingError('Không có ca nào đang mở.')
        sh.closed_at=datetime.now(); sh.counted_cash=int(counted); sh.expected_cash=sh.opening_cash+self.shift_summary(sh.shift_id)['cash']; sh.difference=sh.counted_cash-sh.expected_cash; sh.note=note or ''; self.current_shift_obj=None; self._save_shifts()
        if hasattr(self, 'audit') and self.audit:
            self.audit.log("shift_close", f"Chốt ca trực {sh.shift_id}: lệch {sh.difference:,.0f} đ (thực tế {sh.counted_cash:,.0f} đ)", actor=sh.cashier)
        return sh
    def create_payment(self,kind,plate,amount,method,received=None,reference=None,description=''):
        amount=int(amount)
        if amount<0: raise PaymentError('Số tiền không hợp lệ.')
        if method not in PAYMENT_METHODS: raise PaymentError('Phương thức thanh toán không hợp lệ.')
        sh=self.current_shift_obj
        if method=='cash' and received is not None and int(received)<amount: raise PaymentError('Tiền khách đưa chưa đủ.')
        now=datetime.now(); pid=f"PAY-{now.strftime('%y%m%d%H%M%S%f')}"
        p=Payment(pid,now,kind,str(plate).upper(),amount,method,reference,description,sh.cashier if sh else 'admin',sh.shift_id if sh else 'S00',int(received if received is not None else amount),max(0,int(received if received is not None else amount)-amount))
        self.payments.append(p); self._save_payments()
        if hasattr(self, 'audit') and self.audit:
            m_name = PAYMENT_METHODS.get(method, method)
            self.audit.log("payment", f"{p.payment_id}: Thu {amount:,.0f} đ ({m_name}) - Xe {plate}", actor=p.cashier)
        return p
    def get_transactions(self,filters=None):
        rows=list(self.payments); f=filters or {}
        if f.get('plate'): rows=[p for p in rows if f['plate'].upper() in p.plate]
        if f.get('kind'): rows=[p for p in rows if p.kind==f['kind']]
        if f.get('method'): rows=[p for p in rows if p.method==f['method']]
        if f.get('date_from'): rows=[p for p in rows if p.created_at.date()>=f['date_from']]
        if f.get('date_to'): rows=[p for p in rows if p.created_at.date()<=f['date_to']]
        return sorted(rows,key=lambda p:p.created_at,reverse=True)
    def revenue_by_method(self,d): return {k:sum(p.amount for p in self.payments if p.created_at.date()==d and p.method==k) for k in PAYMENT_METHODS}
    def build_receipt(self,pid):
        p=next((x for x in self.payments if x.payment_id==pid),None)
        if not p: raise ParkingError('Không tìm thấy hóa đơn.')
        return f"--- {PARKING_NAME} ---\nMã: {p.payment_id}\nBiển số: {p.plate}\nNội dung: {p.description or p.kind}\nThời gian: {p.created_at:%d/%m/%Y %H:%M:%S}\nPhương thức: {PAYMENT_METHODS[p.method]}\nSố tiền: {p.amount:,} đ\nTiền nhận: {p.received:,} đ\nTiền thối: {p.change:,} đ\nThu ngân: {p.cashier}"
