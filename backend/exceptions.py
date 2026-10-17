"""Chứa tất cả các lỗi (Exception) của hệ thống."""
class ParkingError(Exception):
    """Lỗi nghiệp vụ chung."""
    pass

class InvalidPlateError(ParkingError): pass
class NoSlotAvailableError(ParkingError): pass
class VehicleAlreadyParkedError(ParkingError): pass
class TicketNotFoundError(ParkingError): pass
class DuplicateMonthlyTicketError(ParkingError): pass
class ShiftNotOpenError(ParkingError): pass
class PaymentError(ParkingError): pass
class PermissionDeniedError(ParkingError): pass
class AuthError(Exception): pass