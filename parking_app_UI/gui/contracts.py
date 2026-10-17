"""Điểm nhập khẩu duy nhất cho các exception của backend.

Khi Vĩ viết xong backend/exceptions.py, GUI tự dùng exception thật.
Nếu chưa có thì dùng bản dự phòng bên dưới (cùng tên) để GUI vẫn chạy.
"""
try:
    from backend.exceptions import (  # type: ignore
        ParkingError, InvalidPlateError, NoSlotAvailableError,
        VehicleAlreadyParkedError, TicketNotFoundError, DuplicateMonthlyTicketError,
        ShiftNotOpenError, PaymentError, PermissionDeniedError,
    )
except ImportError:
    class ParkingError(Exception):
        """Lỗi nghiệp vụ chung; str(e) là thông báo tiếng Việt hiển thị cho người dùng."""

    class InvalidPlateError(ParkingError): ...
    class NoSlotAvailableError(ParkingError): ...
    class VehicleAlreadyParkedError(ParkingError): ...
    class TicketNotFoundError(ParkingError): ...
    class DuplicateMonthlyTicketError(ParkingError): ...
    class ShiftNotOpenError(ParkingError): ...   # chưa mở ca trực -> không được thu tiền
    class PaymentError(ParkingError): ...        # thiếu tiền, thiếu mã tham chiếu, phương thức sai...
    class PermissionDeniedError(ParkingError): ...  # vai trò không được phép thực hiện thao tác

try:
    from backend.exceptions import AuthError  # type: ignore
except ImportError:
    class AuthError(Exception):
        """Lỗi đăng nhập / đăng ký / đổi mật khẩu."""

try:
    from services.weather_service import WeatherError  # type: ignore
except ImportError:
    class WeatherError(Exception):
        """Lỗi lấy dữ liệu thời tiết (API): str(e) là thông báo tiếng Việt."""
