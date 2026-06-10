@echo off
:: 💡 ล็อกให้อยู่ในโฟลเดอร์ของบอทเสมอ (แก้ปัญหาหาไฟล์ไม่เจอ)
cd /d "%~dp0"

echo =========================================
echo    Starting MT5 Pro Sniper Bot System
echo =========================================

:: 1. เปิดหน้าเว็บ Dashboard (ลองเปลี่ยน Port กลับเป็น 8501 ก่อนเพื่อทดสอบ)
echo [1/3] Starting Streamlit Dashboard...
start "Dashboard_App" cmd /k "venv\Scripts\activate && streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.enableCORS false"

:: 2. เปิดตัวบอทหลัก
echo [2/3] Starting Bot Backend...
start "Bot_Backend" cmd /k "venv\Scripts\activate && python bot.py"

:: 3. เปิดสุนัขเฝ้ายาม
echo [3/3] Starting Watchdog System...
start "Watchdog_System" cmd /k "venv\Scripts\activate && python _watchdog.py"

echo [3/3] Starting Caddy System...
start "Caddy" cmd /k "caddy run"

echo.
echo All systems are UP! You can now access the dashboard in your browser.
exit