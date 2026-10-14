@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 (
  echo Build failed. Read the error above.
  pause
  exit /b 1
)
echo Build complete. See the dist folder.
pause
