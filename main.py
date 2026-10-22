"""Điểm khởi chạy ứng dụng Quản lý bãi đỗ xe tích hợp cổng thanh toán trực tuyến VietQR."""

from config import (
    VIETQR_CACHE, VIETQR_API_URL, VIETQR_BANKS_API_URL,
    VIETQR_TIMEOUT, VIETQR_TEMPLATE
)

from gui.app import MainWindow
from services.vietqr_service import VietQRService

from backend.parking_manager import ParkingLot, ParkingManager
from backend.monthly import MonthlyManager
from backend.payments import PaymentService
from backend.stats import StatsService
from backend.auth import AuthService
from backend.customers import CustomerService
from backend.audit import AuditService


def main():
    parking_lot = ParkingLot()
    manager = ParkingManager(parking_lot)

    payments = PaymentService()
    auth = AuthService()

    monthly = MonthlyManager(prices_provider=manager.get_prices, payment_service=payments)

    customers = CustomerService(
        manager=manager,
        monthly=monthly,
        auth=auth,
        payments=payments)

    audit = AuditService()

    stats = StatsService(
        parking_lot=parking_lot,
        tickets_provider=manager,
        payments_service=payments)

    # Khởi tạo dịch vụ tạo mã QR thanh toán ngân hàng chuẩn VietQR (thay thế dịch vụ thời tiết cũ)
    vietqr = VietQRService(
        cache_path=VIETQR_CACHE,
        api_url=VIETQR_API_URL,
        banks_url=VIETQR_BANKS_API_URL,
        timeout=VIETQR_TIMEOUT,
        template=VIETQR_TEMPLATE
    )

    MainWindow(manager, monthly, stats, auth, payments, customers, audit, vietqr=vietqr).run()


if __name__ == "__main__":
    main()