@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0"
set "LOG_DIR=%ROOT%logs\runtime"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "SERVER_LOG=%LOG_DIR%\review_page.log"
set "URL=http://127.0.0.1:8765"

where py >nul 2>nul
if errorlevel 1 (
    echo 找不到 py。核对页要用 py -3，不要改用 Anaconda。
    pause
    exit /b 1
)

call :health
if not errorlevel 1 (
    start "" "%URL%"
    exit /b 0
)

start "核对题页" /min cmd /c "cd /d ""%ROOT%"" && py -3 serve.py >> ""%SERVER_LOG%"" 2>&1"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$deadline=(Get-Date).AddSeconds(30);" ^
    "while((Get-Date) -lt $deadline) {" ^
    "  try { $r=Invoke-RestMethod -TimeoutSec 2 'http://127.0.0.1:8765/api/health'; if($r.ok -eq $true) { exit 0 } } catch {}" ^
    "  Start-Sleep -Milliseconds 400" ^
    "}" ^
    "exit 1"

if errorlevel 1 (
    echo 核对页没有在 30 秒内起来。
    echo 8765 可能被题库或其他程序占用。两个不要同时用这个端口。
    echo 日志：%SERVER_LOG%
    pause
    exit /b 1
)

start "" "%URL%"
exit /b 0

:health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -TimeoutSec 2 'http://127.0.0.1:8765/api/health'; if ($r.ok -eq $true) { exit 0 } else { exit 1 } } catch { exit 1 }"
exit /b %errorlevel%
