"""Điểm nhập khẩu duy nhất cho các exception của backend.
"""
try:
    from backend.exceptions import (                
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
    class ShiftNotOpenError(ParkingError): ...                                           
    class PaymentError(ParkingError): ...                                                             
    class PermissionDeniedError(ParkingError): ...                                              

try:
    from backend.exceptions import AuthError                
except ImportError:
    class AuthError(Exception):
        """Lỗi đăng nhập / đăng ký / đổi mật khẩu."""

try:
    from services.vietqr_service import VietQRError
except ImportError:
    class VietQRError(Exception):
        """Lỗi tạo mã QR thanh toán hoặc kết nối API VietQR: str(e) là thông báo tiếng Việt."""
