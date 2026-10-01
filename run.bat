@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto check
py -3.12 -m venv .venv
if errorlevel 1 goto failed
:check
".venv\Scripts\python.exe" -c "import PySide6.QtWebEngineWidgets, PySide6.QtWebChannel" >nul 2>nul
if not errorlevel 1 goto run
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Failed. Check the messages above, Python 3.12, and network access.
pause
exit /b 1
