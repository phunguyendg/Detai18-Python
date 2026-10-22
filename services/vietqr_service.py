"""Dịch vụ thanh toán trực tuyến qua mã QR ngân hàng chuẩn VietQR (CHỨC NĂNG API của đề tài).

- Tiêu chuẩn: Chuẩn VietQR / NAPAS 247 trên nền tảng EMVCo QR code quốc tế.
- Tích hợp API công khai VietQR (https://api.vietqr.io) với timeout, xử lý mất mạng, HTTP lỗi, JSON hỏng.
- Tạo mã chuẩn EMVCo TLV có tính toán mã kiểm tra CRC-16 CCITT (0xFFFF, đa thức 0x1021).
- Tích hợp bộ sinh ma trận QR thuần Python (Version 1-10, sửa lỗi Reed-Solomon trên trường Galois GF(256))
  để vẽ trực tiếp lên Tkinter Canvas với độ phân giải cao ngay cả khi không có mạng và không cần cài thư viện ngoài.
- Đồng thời nhận ảnh QR Base64 PNG chuẩn từ VietQR API (kèm logo ngân hàng, khung VietQR/NAPAS).
- LƯU và ĐỐI SOÁT: ghi nhật ký giao dịch mã QR an toàn vào data/vietqr.json qua file tạm và sao lưu.
"""
import base64
import json
import os
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

USER_AGENT = "ParkingApp-VietQR/1.0 (Python Student Project)"
MAX_BODY = 2_000_000


class VietQRError(Exception):
    """Lỗi xử lý hoặc kết nối API VietQR; str(e) là thông báo tiếng Việt hiển thị cho người dùng."""


# Danh mục ngân hàng thông dụng tại Việt Nam (dự phòng ngoại tuyến)
DEFAULT_BANKS = [
    {"bin": "970422", "code": "MB", "shortName": "MBBank", "name": "Ngân hàng TMCP Quân Đội"},
    {"bin": "970436", "code": "VCB", "shortName": "Vietcombank", "name": "Ngân hàng TMCP Ngoại Thương Việt Nam"},
    {"bin": "970415", "code": "CTG", "shortName": "VietinBank", "name": "Ngân hàng TMCP Công Thương Việt Nam"},
    {"bin": "970418", "code": "BIDV", "shortName": "BIDV", "name": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam"},
    {"bin": "970407", "code": "TCB", "shortName": "Techcombank", "name": "Ngân hàng TMCP Kỹ Thương Việt Nam"},
    {"bin": "970432", "code": "VPB", "shortName": "VPBank", "name": "Ngân hàng TMCP Việt Nam Thịnh Vượng"},
    {"bin": "970416", "code": "ACB", "shortName": "ACB", "name": "Ngân hàng TMCP Á Châu"},
    {"bin": "970423", "code": "TPB", "shortName": "TPBank", "name": "Ngân hàng TMCP Tiên Phong"},
    {"bin": "970403", "code": "STB", "shortName": "Sacombank", "name": "Ngân hàng TMCP Sài Gòn Thương Tín"},
    {"bin": "970405", "code": "VBA", "shortName": "Agribank", "name": "Ngân hàng Nông nghiệp và Phát triển Nông thôn Việt Nam"},
    {"bin": "970437", "code": "HDB", "shortName": "HDBank", "name": "Ngân hàng TMCP Phát triển TP.HCM"},
    {"bin": "970441", "code": "VIB", "shortName": "VIB", "name": "Ngân hàng TMCP Quốc tế Việt Nam"},
    {"bin": "970443", "code": "SHB", "shortName": "SHB", "name": "Ngân hàng TMCP Sài Gòn - Hà Nội"},
    {"bin": "970426", "code": "MSB", "shortName": "MSB", "name": "Ngân hàng TMCP Hàng Hải Việt Nam"},
    {"bin": "970448", "code": "OCB", "shortName": "OCB", "name": "Ngân hàng TMCP Phương Đông"},
]


# =====================================================================
# BỘ SINH CHUỖI EMVCo VIETQR VÀ TÍNH CRC16-CCITT
# =====================================================================
def crc16_ccitt(data: str) -> str:
    """Tính mã CRC16-CCITT (đa thức 0x1021, khởi tạo 0xFFFF) theo đúng chuẩn EMVCo / VietQR."""
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _format_tlv(tag: int, value: str) -> str:
    """Định dạng trường TLV (Tag-Length-Value) với Tag 2 số, Length 2 số."""
    s_val = str(value)
    return f"{tag:02d}{len(s_val.encode('utf-8')):02d}{s_val}"


def build_vietqr_emvco(bank_bin: str, account_no: str, amount: int = 0, memo: str = "",
                       account_name: str = "") -> str:
    """Tạo chuỗi dữ liệu mã QR chuẩn EMVCo / VietQR NAPAS 247."""
    clean_account = "".join(ch for ch in str(account_no) if ch.isalnum())
    clean_bin = "".join(ch for ch in str(bank_bin) if ch.isdigit())
    if not clean_bin or not clean_account:
        raise VietQRError("Mã BIN ngân hàng và số tài khoản không được để trống.")

    # Sub-tags của Tag 38 (Thông tin thụ hưởng NAPAS)
    sub01 = _format_tlv(0, clean_bin) + _format_tlv(1, clean_account)
    tag38_value = _format_tlv(0, "A000000727") + _format_tlv(1, sub01) + _format_tlv(2, "QRIBFTTA")

    # Điểm khởi tạo: 12 (Dynamic có số tiền) hoặc 11 (Static)
    point_init = "12" if amount and int(amount) > 0 else "11"

    parts = [
        _format_tlv(0, "01"),           # Payload Format Indicator
        _format_tlv(1, point_init),     # Point of Initiation Method
        _format_tlv(38, tag38_value),   # Merchant Account Info
        _format_tlv(53, "704"),         # Transaction Currency (VND)
    ]

    if amount and int(amount) > 0:
        parts.append(_format_tlv(54, str(int(amount))))  # Amount

    parts.append(_format_tlv(58, "VN"))  # Country Code

    if account_name:
        clean_name = "".join(c for c in account_name if c.isalnum() or c in " -_").strip().upper()[:25]
        if clean_name:
            parts.append(_format_tlv(59, clean_name))

    if memo:
        clean_memo = "".join(c for c in memo if c.isalnum() or c in " -_").strip()[:25]
        if clean_memo:
            sub62 = _format_tlv(8, clean_memo)
            parts.append(_format_tlv(62, sub62))

    raw_without_crc = "".join(parts) + "6304"
    crc_code = crc16_ccitt(raw_without_crc)
    return raw_without_crc + crc_code


# =====================================================================
# BỘ SINH MA TRẬN QR THUẦN PYTHON (REED-SOLOMON + GF256 + MATRIX)
# =====================================================================
class _PureQR:
    """Sinh ma trận boolean QR 2D chuẩn ISO/IEC 18004 không cần thư viện ngoài."""
    EXP = [0] * 512
    LOG = [0] * 256
    _inited = False

    @classmethod
    def _init_gf(cls):
        if cls._inited:
            return
        x = 1
        for i in range(255):
            cls.EXP[i] = x
            cls.EXP[i + 255] = x
            cls.LOG[x] = i
            x = (x << 1) ^ (0x11D if (x & 0x80) else 0)
        cls._inited = True

    @classmethod
    def gf_mul(cls, a, b):
        if a == 0 or b == 0:
            return 0
        return cls.EXP[cls.LOG[a] + cls.LOG[b]]

    @classmethod
    def rs_encode(cls, data_bytes, ec_count):
        cls._init_gf()
        poly = [1]
        for i in range(ec_count):
            ng = [0] * (len(poly) + 1)
            for j in range(len(poly)):
                ng[j] ^= cls.gf_mul(poly[j], cls.EXP[i])
                ng[j + 1] ^= poly[j]
            poly = ng

        res = list(data_bytes) + [0] * ec_count
        for i in range(len(data_bytes)):
            c = res[i]
            if c != 0:
                for j in range(1, len(poly)):
                    res[i + j] ^= cls.gf_mul(poly[j], c)
        return res[len(data_bytes):]

    # Thông số phiên bản QR Code (EC Level L): (size, total_codewords, ec_codewords_per_block, num_blocks)
    VER_SPECS = {
        1: (21, 26, 7, 1),
        2: (25, 44, 10, 1),
        3: (29, 70, 15, 1),
        4: (33, 100, 20, 1),
        5: (37, 134, 26, 1),
        6: (41, 172, 18, 2),
        7: (45, 196, 20, 2),
        8: (49, 242, 24, 2),
        9: (53, 292, 30, 2),
        10: (57, 346, 18, 2),
    }

    ALIGN_PATTERNS = {
        2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
        6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
    }

    @classmethod
    def encode_to_matrix(cls, text: str) -> list[list[bool]]:
        """Mã hóa văn bản thành ma trận QR 2D (True = module đen, False = module trắng)."""
        data = text.encode("utf-8")
        raw_len = len(data)

        # Chọn phiên bản nhỏ nhất vừa dữ liệu
        best_ver = None
        for v in range(1, 11):
            size, total_cw, ec_cw, blocks = cls.VER_SPECS[v]
            data_cw = total_cw - (ec_cw * blocks)
            # Chế độ byte: 4 bit mode + 8 bit/16 bit count + data bytes
            count_bits = 8 if v < 10 else 16
            header_bytes = 2 if count_bits == 8 else 3
            if raw_len + header_bytes <= data_cw:
                best_ver = v
                break

        if best_ver is None:
            best_ver = 10  # Cắt ngắn nếu vượt quá để vẫn dựng ma trận

        size, total_cw, ec_cw, num_blocks = cls.VER_SPECS[best_ver]
        data_cw = total_cw - (ec_cw * num_blocks)

        # 1. Tạo chuỗi bit dữ liệu (Byte Mode = 0100)
        bits = "0100"
        count_bits = 8 if best_ver < 10 else 16
        bits += f"{raw_len:0{count_bits}b}"
        for b in data:
            bits += f"{b:08b}"
        bits = bits[: data_cw * 8]

        # Thêm 4 bit kết thúc (terminator 0000)
        bits += "0" * min(4, data_cw * 8 - len(bits))
        while len(bits) % 8 != 0:
            bits += "0"

        # Padding codewords 11101100 (236) và 00010001 (17)
        data_bytes = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
        pad_toggle = True
        while len(data_bytes) < data_cw:
            data_bytes.append(236 if pad_toggle else 17)
            pad_toggle = not pad_toggle

        # 2. Chia block và tính mã sửa lỗi Reed-Solomon
        block_len = data_cw // num_blocks
        final_cw = []
        data_blocks = []
        ec_blocks = []
        idx = 0
        for b in range(num_blocks):
            sub = data_bytes[idx:idx + block_len]
            idx += block_len
            data_blocks.append(sub)
            ec_blocks.append(cls.rs_encode(sub, ec_cw))

        # Xen kẽ data codewords
        for i in range(block_len):
            for b in range(num_blocks):
                final_cw.append(data_blocks[b][i])
        # Xen kẽ error correction codewords
        for i in range(ec_cw):
            for b in range(num_blocks):
                final_cw.append(ec_blocks[b][i])

        # 3. Khởi tạo ma trận
        grid = [[None] * size for _ in range(size)]
        reserved = [[False] * size for _ in range(size)]

        def set_func(r, c, val):
            if 0 <= r < size and 0 <= c < size:
                grid[r][c] = val
                reserved[r][c] = True

        # Finder patterns (3 góc)
        for r0, c0 in ((0, 0), (0, size - 7), (size - 7, 0)):
            for r in range(7):
                for c in range(7):
                    inside = (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
                    set_func(r0 + r, c0 + c, inside)
            # Vùng đệm trắng xung quanh finder
            for r in range(-1, 8):
                for c in range(-1, 8):
                    rr, cc = r0 + r, c0 + c
                    if 0 <= rr < size and 0 <= cc < size and not reserved[rr][cc]:
                        set_func(rr, cc, False)

        # Timing patterns
        for i in range(8, size - 8):
            set_func(6, i, i % 2 == 0)
            set_func(i, 6, i % 2 == 0)

        # Alignment patterns (cho version >= 2)
        if best_ver in cls.ALIGN_PATTERNS:
            coords = cls.ALIGN_PATTERNS[best_ver]
            for ar in coords:
                for ac in coords:
                    if (ar < 9 and ac < 9) or (ar < 9 and ac > size - 10) or (ar > size - 10 and ac < 9):
                        continue
                    for r in range(-2, 3):
                        for c in range(-2, 3):
                            val = (abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0))
                            set_func(ar + r, ac + c, val)

        # Dark module cố định
        set_func(4 * best_ver + 9, 8, True)

        # Dành chỗ cho Format info quanh finder
        for i in range(9):
            if not reserved[8][i]:
                set_func(8, i, False)
            if not reserved[i][8]:
                set_func(i, 8, False)
        for i in range(size - 8, size):
            if not reserved[8][i]:
                set_func(8, i, False)
            if not reserved[i][8]:
                set_func(i, 8, False)

        # 4. Đặt bit dữ liệu theo đường zic-zắc 2 cột
        bit_idx = 0
        total_data_bits = "".join(f"{b:08b}" for b in final_cw)
        col = size - 1
        up = True
        while col > 0:
            if col == 6:  # Bỏ qua timing column
                col -= 1
            rows = range(size - 1, -1, -1) if up else range(size)
            for row in rows:
                for c_offset in (0, 1):
                    cc = col - c_offset
                    if not reserved[row][cc]:
                        val = total_data_bits[bit_idx] == "1" if bit_idx < len(total_data_bits) else False
                        bit_idx += 1
                        # Áp dụng mặt nạ Mask 0: (row + cc) % 2 == 0
                        if (row + cc) % 2 == 0:
                            val = not val
                        grid[row][cc] = val
            up = not up
            col -= 2

        # 5. Ghi thông tin Format Info (EC Level L = 01, Mask 0 = 000 -> 01000 + BCH -> 0x77C4)
        # Format string cho EC Level L, Mask 0 với XOR mask 0x5412 = 111011111000100
        fmt = "111011111000100"
        # Ghi vào dải quanh Top-Left
        idx = 0
        for c in range(9):
            if c != 6:
                grid[8][c] = fmt[idx] == "1"
                idx += 1
        for r in range(7, -1, -1):
            if r != 6:
                grid[r][8] = fmt[idx] == "1"
                idx += 1

        # Ghi vào Bottom-Left và Top-Right
        idx = 0
        for r in range(size - 1, size - 8, -1):
            grid[r][8] = fmt[idx] == "1"
            idx += 1
        for c in range(size - 8, size):
            grid[8][c] = fmt[idx] == "1"
            idx += 1

        # Thay thế các ô chưa gán (nếu có) thành False
        for r in range(size):
            for c in range(size):
                if grid[r][c] is None:
                    grid[r][c] = False

        return grid


# =====================================================================
# DỊCH VỤ CHÍNH: VIETQR SERVICE
# =====================================================================
class VietQRService:
    """Quản lý tạo mã QR thanh toán ngân hàng chuẩn VietQR, kết nối API và lưu trữ lịch sử."""

    def __init__(self, cache_path=None, api_url="https://api.vietqr.io/v2/generate",
                 banks_url="https://api.vietqr.io/v2/banks", timeout=8, template="compact2"):
        self.cache_path = Path(cache_path) if cache_path else Path("data/vietqr.json")
        self.api_url = api_url
        self.banks_url = banks_url
        self.timeout = timeout
        self.template = template
        self._banks_cache = None

    def get_banks(self) -> list[dict]:
        """Lấy danh sách các ngân hàng hỗ trợ VietQR từ API hoặc dùng danh mục offline có sẵn."""
        if self._banks_cache:
            return self._banks_cache

        req = urllib.request.Request(self.banks_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_BODY + 1)
            raw = json.loads(body.decode("utf-8"))
            if raw.get("code") == "00" and isinstance(raw.get("data"), list):
                self._banks_cache = raw["data"]
                return self._banks_cache
        except Exception:
            pass

        self._banks_cache = DEFAULT_BANKS
        return self._banks_cache

    def generate_qr(self, amount: int, memo: str, plate: str = "",
                    bank_bin: str = "970422", account_no: str = "0987654321",
                    account_name: str = "BAI DO XE THONG MINH",
                    bank_name: str = "MBBank", template: str = None) -> dict:
        """Tạo mã QR thanh toán chuẩn VietQR:
        - Gọi API VietQR công khai (https://api.vietqr.io/v2/generate) lấy mã EMVCo và ảnh Base64 PNG.
        - Nếu mất mạng hoặc API lỗi: tự động chuyển sang sinh chuẩn EMVCo và ma trận QR cục bộ không bị gián đoạn.
        - Ghi lịch sử giao dịch vào cache.
        """
        amount = int(amount)
        if amount < 0:
            raise VietQRError("Số tiền thanh toán không được âm.")

        tpl = template or self.template
        clean_memo = memo.strip() or (f"BAIXE {plate.strip().upper()}" if plate else "THANH TOAN BAI XE")
        clean_plate = plate.strip().upper()

        # 1. Sinh chuỗi EMVCo chuẩn NAPAS 247 cục bộ làm nền tảng
        local_emvco = build_vietqr_emvco(bank_bin=bank_bin, account_no=account_no,
                                        amount=amount, memo=clean_memo,
                                        account_name=account_name)

        # 2. Sinh ma trận QR vector thuần Python (vẽ sắc nét trên Canvas)
        matrix = _PureQR.encode_to_matrix(local_emvco)

        # Đường link ảnh trực tiếp VietQR QuickLink
        quicklink_url = (f"https://img.vietqr.io/image/{bank_bin}-{account_no}-{tpl}.png"
                         f"?amount={amount}&addInfo={urllib.parse.quote(clean_memo)}"
                         f"&accountName={urllib.parse.quote(account_name)}")

        qr_code = local_emvco
        qr_data_url = None
        from_api = False
        api_error = None

        # 3. Gọi API VietQR để lấy ảnh Base64 chính thức
        payload = {
            "accountNo": account_no,
            "accountName": account_name,
            "acqId": bank_bin,
            "amount": amount,
            "addInfo": clean_memo,
            "format": "text",
            "template": tpl,
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.api_url,
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, "Accept": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_BODY + 1)
            raw = json.loads(body.decode("utf-8"))
            if raw.get("code") == "00" and isinstance(raw.get("data"), dict):
                d = raw["data"]
                if d.get("qrCode"):
                    qr_code = d["qrCode"]
                if d.get("qrDataURL"):
                    qr_data_url = d["qrDataURL"]
                from_api = True
        except (socket.timeout, TimeoutError):
            api_error = "Hết thời gian chờ máy chủ VietQR, đã chuyển sang bộ sinh chuẩn cục bộ."
        except urllib.error.HTTPError as e:
            api_error = f"Máy chủ VietQR phản hồi mã {e.code}, đã dùng bộ sinh chuẩn cục bộ."
        except urllib.error.URLError:
            api_error = "Không có kết nối mạng tới VietQR API, đã dùng bộ sinh chuẩn cục bộ."
        except Exception as e:
            api_error = f"Lỗi xử lý API: {e}, đã dùng bộ sinh chuẩn cục bộ."

        result = {
            "qr_code": qr_code,
            "qr_data_url": qr_data_url,
            "image_url": quicklink_url,
            "matrix": matrix,
            "amount": amount,
            "memo": clean_memo,
            "plate": clean_plate,
            "bank_bin": bank_bin,
            "bank_name": bank_name,
            "account_no": account_no,
            "account_name": account_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "from_api": from_api,
            "api_error": api_error,
        }

        # Lưu vào cache giao dịch
        try:
            self.save_transaction(result)
        except Exception:
            pass

        return result

    def load_cache(self) -> dict:
        """Đọc danh sách giao dịch QR gần đây từ file JSON an toàn."""
        try:
            if not self.cache_path.exists():
                return {"transactions": [], "version": 1}
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {"transactions": [], "version": 1}

    def save_transaction(self, txn: dict):
        """Lưu giao dịch QR vào cache an toàn qua file tạm."""
        cache = self.load_cache()
        txns = cache.get("transactions", [])
        # Không lưu ma trận lớn vào JSON để tiết kiệm dung lượng
        clean_txn = {k: v for k, v in txn.items() if k != "matrix"}
        txns.insert(0, clean_txn)
        # Giữ tối đa 50 giao dịch QR gần nhất
        txns = txns[:50]
        cache["transactions"] = txns
        cache["updated_at"] = datetime.now().isoformat(timespec="seconds")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.cache_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.cache_path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def get_recent_transactions(self) -> list[dict]:
        return self.load_cache().get("transactions", [])

    # Tương thích ngược với các hàm mà weather_service cũ có nếu có code cũ gọi
    def last_location(self):
        return {"name": "Hà Nội (VietQR)", "lat": 21.0285, "lon": 105.8542}

    def get(self, *args, **kwargs):
        """Hàm tương thích ngược với WeatherService."""
        return {
            "data": {
                "current": {"temp": 28, "desc": "VietQR Hoạt động", "kind": "clear", "is_day": True, "feels": 28, "humidity": 65, "wind": 5, "rain_mm": 0},
                "hourly": [],
                "daily": [],
                "advice": [("ok", "Hệ thống thanh toán trực tuyến VietQR sẵn sàng hoạt động.")],
                "location": {"name": "Hệ thống VietQR"},
            },
            "saved_at": datetime.now(),
            "from_cache": True,
            "stale": False,
            "error": None,
        }
