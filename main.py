"""File chạy chính của toàn bộ ứng dụng."""
import tkinter as tk
from tkinter import messagebox

# Import các service từ backend
from backend.parking_manager import ParkingLot, ParkingManager
from backend.monthly import MonthlyManager
from backend.stats import StatsService
from backend.auth import AuthService
from backend.payments import PaymentService
from backend.customers import CustomerService
from backend.audit import AuditService
from backend.weather_service import WeatherService

import sys
import os
# Trỏ thẳng vào thư mục parking_app_UI
sys.path.append(os.path.join(os.path.dirname(__file__), "parking_app_UI"))
from gui.app import MainWindow

def main():
    # 1. Khởi tạo các dịch vụ Backend
    lot = ParkingLot()
    manager = ParkingManager(lot)
    payments = PaymentService()
    auth = AuthService()
    monthly = MonthlyManager(prices_provider=manager.get_prices, payment_service=payments)
    stats = StatsService(lot, manager, payments)
    customers = CustomerService(manager, monthly)
    audit = AuditService()
    weather = WeatherService()

    # 2. Khởi tạo giao diện Tkinter
    try:
        app = MainWindow(
            manager=manager, 
            monthly=monthly, 
            stats=stats, 
            auth=auth, 
            payments=payments, 
            customers=customers, 
            audit=audit, 
            weather=weather
        )
        # 3. Chạy vòng lặp giao diện
        app.run()
    except Exception as e:
        messagebox.showerror("Lỗi khởi động", f"Không thể khởi động ứng dụng:\n{e}")

if __name__ == "__main__":
    main()