@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\prepare_resources.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean PixivBatchBookmark.spec
if errorlevel 1 goto failed
echo Build complete: dist\PixivBatchBookmark\PixivBatchBookmark.exe
echo Distribute the entire dist\PixivBatchBookmark folder.
pause
exit /b 0
:failed
echo Build failed. Check the messages above.
pause
exit /b 1
