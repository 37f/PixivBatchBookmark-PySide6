@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 goto failed
echo Build complete: dist\PixivBatchBookmark\PixivBatchBookmark.exe
echo Distribute the entire dist\PixivBatchBookmark folder.
pause
exit /b 0
:failed
echo Build failed. Check the messages above.
pause
exit /b 1
