import json
import os
import tempfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from functools import wraps

from config import DATA_DIR, DEFAULT_PRICES, SLOT_ROWS, COLS_PER_ROW
from gui.mock_backend import ParkingSlot, ParkingTicket, MonthlyTicket, Payment, Shift
from gui.mock_accounts import Account, AuditEntry

DATA_FILE = DATA_DIR / "parking_data.json"
ACCOUNT_FILE = DATA_DIR / "accounts.json"


def _encode(value):
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if hasattr(value, "__dataclass_fields__"):
        return _encode(asdict(value))
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def _decode(value):
    if isinstance(value, dict):
        kind = value.get("__type__")
        if kind == "datetime":
            return datetime.fromisoformat(value["value"])
        if kind == "date":
            return date.fromisoformat(value["value"])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Cấu trúc JSON không hợp lệ")
        return data
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        backup = path.with_suffix(path.suffix + ".corrupt")
        try:
            os.replace(path, backup)
        except OSError:
            pass
        raise RuntimeError(f"File dữ liệu {path.name} bị lỗi định dạng. Bản lỗi được giữ lại nếu có thể: {exc}") from exc


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(_encode(data), ensure_ascii=False, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            try:
                shutil_copy(path, backup)
            except OSError:
                pass
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass


def shutil_copy(src, dst):
    import shutil
    shutil.copy2(src, dst)


def _restore_dataclass(cls, rows):
    return [cls(**_decode(row)) for row in rows]


def _restore_state(objects):
    manager, monthly, stats, auth, payments, customers, audit, prices = objects
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = _read(DATA_FILE)
    if data:
        try:
            prices._p = _decode(data.get("prices", DEFAULT_PRICES))
            saved_slots = data.get("slots", [])
            if saved_slots:
                manager._slots = {s.slot_id: s for s in _restore_dataclass(ParkingSlot, saved_slots)}
            manager._tickets = _restore_dataclass(ParkingTicket, data.get("tickets", []))
            manager._counter = int(data.get("ticket_counter", len(manager._tickets)))
            monthly._items = {t.plate: t for t in _restore_dataclass(MonthlyTicket, data.get("monthly_tickets", []))}
            payments._payments = _restore_dataclass(Payment, data.get("payments", []))
            payments._shifts = _restore_dataclass(Shift, data.get("shifts", []))
            payments._counter = int(data.get("payment_counter", len(payments._payments)))
            payments._shift_counter = int(data.get("shift_counter", len(payments._shifts)))
            customers._vehicles = _decode(data.get("vehicles", {}))
            customers._requests = _decode(data.get("requests", []))
            customers._req_counter = int(data.get("request_counter", 0))
            audit._entries = _restore_dataclass(AuditEntry, data.get("audit_entries", []))
        except (TypeError, KeyError, ValueError) as exc:
            raise RuntimeError(f"Không thể khôi phục dữ liệu bãi xe từ {DATA_FILE.name}: {exc}") from exc

    account_data = _read(ACCOUNT_FILE)
    if account_data and isinstance(account_data.get("accounts"), list):
        try:
            auth._users = {a.username: a for a in _restore_dataclass(Account, account_data["accounts"])}
        except (TypeError, KeyError, ValueError) as exc:
            raise RuntimeError(f"Không thể khôi phục tài khoản từ {ACCOUNT_FILE.name}: {exc}") from exc


def _save_state(objects):
    manager, monthly, stats, auth, payments, customers, audit, prices = objects
    payload = {
        "prices": prices._p,
        "slots": list(manager._slots.values()),
        "tickets": manager._tickets,
        "ticket_counter": manager._counter,
        "monthly_tickets": list(monthly._items.values()),
        "payments": payments._payments,
        "payment_counter": payments._counter,
        "shifts": payments._shifts,
        "shift_counter": payments._shift_counter,
        "vehicles": customers._vehicles,
        "requests": customers._requests,
        "request_counter": customers._req_counter,
        "audit_entries": audit._entries[-5000:],
    }
    _write(DATA_FILE, payload)
    _write(ACCOUNT_FILE, {"accounts": list(auth._users.values())})


def attach_json_persistence(manager, monthly, stats, auth, payments, customers, audit, prices):
    objects = (manager, monthly, stats, auth, payments, customers, audit, prices)
    _restore_state(objects)
    _save_state(objects)
    hooks = {
        manager: ("vehicle_entry", "vehicle_exit", "set_prices", "set_slot_maintenance"),
        monthly: ("add_monthly_ticket", "update_monthly_ticket", "remove_monthly_ticket", "purchase_monthly_ticket"),
        payments: ("open_shift", "close_shift", "collect"),
        auth: ("login", "register", "change_password", "create_staff", "set_active", "reset_password", "unlock_login", "logout"),
        customers: ("link_vehicle", "unlink_vehicle", "self_entry", "submit_monthly_request", "verify_vehicle", "resolve_request"),
        audit: (),
        prices: ("set_prices",),
    }
    for obj, names in hooks.items():
        for name in names:
            original = getattr(obj, name, None)
            if not callable(original):
                continue
            @wraps(original)
            def wrapped(*args, __original=original, **kwargs):
                result = __original(*args, **kwargs)
                _save_state(objects)
                return result
            setattr(obj, name, wrapped)
    return DATA_FILE, ACCOUNT_FILE
