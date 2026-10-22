"""Dịch vụ khách hàng: liên kết xe, yêu cầu vé tháng, lịch sử và hóa đơn."""
import json
from datetime import datetime
from config import DATA_DIR
from backend.exceptions import ParkingError

class CustomerService:
    FILE=DATA_DIR / 'customer_data.json'
    def __init__(self, manager, monthly, auth=None, payments=None):
        self.manager=manager; self.monthly=monthly; self.auth=auth; self.payments=payments
        self._vehicles=[]; self._requests=[]; self.load()
    def load(self):
        try:
            d=json.loads(self.FILE.read_text(encoding='utf-8')) if self.FILE.exists() else {}
            self._vehicles=d.get('vehicles',[]); self._requests=d.get('requests',[])
        except (ValueError,TypeError): self._vehicles=[]; self._requests=[]
    def save(self):
        self.FILE.parent.mkdir(parents=True,exist_ok=True); tmp=self.FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps({'vehicles':self._vehicles,'requests':self._requests},ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(self.FILE)
    def _username(self): return getattr(getattr(self.auth,'_current_user',None),'username',None)
    def get_public_status(self):
        slots=self.manager.lot.get_all_slots(); empty=sum(s.status=='empty' for s in slots); occupied=sum(s.status=='occupied' for s in slots)
        return {'empty':empty,'occupied':occupied,'occupancy_rate':occupied/len(slots)*100 if slots else 0}
    def get_public_slots(self): return self.manager.lot.get_all_slots()
    def get_my_vehicles(self):
        u = self._username()
        raw_list = [v for v in self._vehicles if (not u or v.get('username') == u)]
        result = []
        parked_tickets = {t.plate: t for t in getattr(self.manager, 'tickets', []) if getattr(t, 'status', '') == 'parked'}
        for v in raw_list:
            item = dict(v)
            t = parked_tickets.get(item['plate'])
            if t:
                item['parked'] = True
                item['slot_id'] = t.slot_id
                item['ticket_id'] = t.ticket_id
                item['entry_time'] = t.entry_time.isoformat() if hasattr(t.entry_time, 'isoformat') else str(t.entry_time)
                now = datetime.now()
                mins = int((now - t.entry_time).total_seconds() / 60) if hasattr(t, 'entry_time') and t.entry_time else 0
                item['minutes'] = max(0, mins)
                try:
                    item['fee'] = t.calculate_fee(self.manager.get_prices())
                except Exception:
                    item['fee'] = 0
            else:
                item['parked'] = False
                item['slot_id'] = None
                item['ticket_id'] = None
                item['minutes'] = 0
                item['fee'] = 0

            if hasattr(self, 'monthly') and self.monthly:
                try:
                    m_ticket = self.monthly._tickets.get(item['plate'])
                    if m_ticket:
                        item['monthly_end'] = m_ticket.end_date
                except Exception:
                    pass
            result.append(item)
        return result

    def get_pending_vehicles(self):
        return [v for v in self._vehicles if v.get('status') == 'pending']

    def link_vehicle(self, plate, vtype):
        plate = plate.strip().upper()
        u = self._username()
        if not plate:
            raise ParkingError('Biển số không được để trống.')
        if not u:
            raise ParkingError('Vui lòng đăng nhập trước khi liên kết xe.')
        for v in self._vehicles:
            if v['plate'] == plate:
                if v.get('username') == u:
                    if v.get('status') == 'rejected':
                        v['status'] = 'pending'
                        v['vehicle_type'] = vtype
                        v['created_at'] = datetime.now().isoformat()
                        self.save()
                        return False
                    elif v.get('status') == 'verified':
                        raise ParkingError(f"Xe {plate} đã được liên kết và xác minh rồi. Bạn có thể tự gửi xe vào bãi.")
                    else:
                        raise ParkingError(f"Xe {plate} đang chờ nhân viên quầy xác minh. Vui lòng mang giấy tờ đến quầy.")
                else:
                    raise ParkingError(f"Xe {plate} đã được liên kết bởi tài khoản khác.")
        
        # Tự động xác minh nếu chủ xe đã có vé tháng
        verified = False
        user_phone = getattr(getattr(self.auth, '_current_user', None), 'phone', '')
        if self.monthly and user_phone:
            for mt in self.monthly.get_all_monthly_tickets():
                if mt.plate == plate and mt.phone == user_phone:
                    verified = True
                    break

        new_v = {
            'username': u,
            'plate': plate,
            'vehicle_type': vtype,
            'status': 'verified' if verified else 'pending',
            'created_at': datetime.now().isoformat()
        }
        self._vehicles.append(new_v)
        self.save()
        return verified

    def self_entry(self, plate, slot_id=None):
        """Khách hàng tự gửi xe của mình vào bãi."""
        plate = plate.strip().upper()
        my_vehicles = self.get_my_vehicles()
        v = next((x for x in my_vehicles if x['plate'] == plate), None)
        if not v:
            raise ParkingError(f"Xe {plate} chưa được liên kết với tài khoản của bạn.")
        if not (v.get('status') in ('verified', 'approved', 'ready') or v.get('verified') is True):
            raise ParkingError(f"Xe {plate} đang chờ nhân viên quầy xác minh, chưa thể tự vào bãi.")
        if v.get('parked', False):
            raise ParkingError(f"Xe {plate} hiện đã ở trong bãi (ô {v.get('slot_id')}).")
        if self.payments and not self.payments.current_shift():
            try:
                self.payments.open_shift("hethong", 0)
            except Exception:
                pass
        
        ticket = self.manager.vehicle_entry(plate, v.get('vehicle_type', 'motorbike'), slot_id)
        return ticket
    def verify_vehicle(self, plate, approved=True):
        for v in self._vehicles:
            if v['plate']==plate.upper(): v['status']='verified' if approved else 'rejected'; self.save(); return v
        raise ParkingError('Không tìm thấy yêu cầu liên kết xe.')
    def unlink_vehicle(self, plate):
        u=self._username(); before=len(self._vehicles); self._vehicles=[v for v in self._vehicles if not (v['plate']==plate.upper() and (not u or v['username']==u))]
        if len(self._vehicles)==before: raise ParkingError('Không tìm thấy xe đã liên kết.')
        self.save(); return True
    def get_requests(self,status='pending'): return [r for r in self._requests if not status or r['status']==status]
    def get_my_requests(self):
        username = self._username()
        if not username:
            return []
        return [r for r in self._requests
            if r.get("username") == username]
    def submit_monthly_request(self,plate,months):
        if months not in (1,3,6,12): raise ParkingError('Gói vé tháng chỉ nhận 1, 3, 6 hoặc 12 tháng.')
        u=self._username(); plate=plate.strip().upper()
        if not u or not plate: raise ParkingError('Vui lòng đăng nhập và nhập biển số.')
        if any(r['plate']==plate and r['status']=='pending' for r in self._requests): raise ParkingError('Xe đã có yêu cầu đang chờ xử lý.')
        req={'request_id':f"REQ-{datetime.now():%y%m%d%H%M%S%f}",'username':u,'plate':plate,'months':months,'status':'pending','note':'','created_at':datetime.now().isoformat()}; self._requests.append(req); self.save(); return req
    def resolve_request(self,rid,status,note=''):
        if status not in ('approved','rejected'): raise ParkingError('Trạng thái xử lý không hợp lệ.')
        for r in self._requests:
            if r['request_id']==rid: r['status']=status; r['note']=note; r['resolved_at']=datetime.now().isoformat(); self.save(); return r
        raise ParkingError('Không tìm thấy yêu cầu.')
    def get_my_monthly_tickets(self):
        plates={v['plate'] for v in self.get_my_vehicles() if v.get('status')=='verified'}
        return [t for t in self.monthly.get_all_monthly_tickets() if t.plate in plates]
    def get_my_history(self):
        plates={v['plate'] for v in self.get_my_vehicles()}
        return [t for t in self.manager.get_history() if t.plate in plates]
    def get_my_payments(self):
        plates={v['plate'] for v in self.get_my_vehicles()}
        return [p for p in self.payments.get_transactions() if p.plate in plates] if self.payments else []
    def get_my_receipt(self,pid):
        p=next((p for p in self.get_my_payments() if p.payment_id==pid),None)
        if not p: raise ParkingError('Không tìm thấy hóa đơn của tài khoản này.')
        return self.payments.build_receipt(pid)
