@echo off
title Exness Bot System Launcher
color 0A

echo ===================================================
echo      🚀 Starting Exness MT5 Bot System...
echo ===================================================

echo.
echo [1/2] Starting Streamlit Dashboard (app.py)...
start "Dashboard (app.py)" cmd /k "venv\Scripts\activate && streamlit run app.py --server.port 80 --server.address 0.0.0.0"

timeout /t 3 >nul

echo [2/2] Starting Bot Backend (bot.py)...
start "Bot Backend (bot.py)" cmd /k "venv\Scripts\activate && python bot.py"

echo.
echo ✅ System is running! 
echo Dashboard will open in your browser automatically.
echo You can close this launcher window now.
echo ===================================================
pause