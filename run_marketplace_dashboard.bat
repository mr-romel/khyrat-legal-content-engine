@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py"

start "Khyrat Marketplace Dashboard" cmd /c "%PYTHON_CMD% src\marketplace\server.py --seed-demo"
timeout /t 2 /nobreak >nul

where cloudflared >nul 2>nul
if %errorlevel%==0 if not "%MARKETPLACE_CLOUDFLARE_TUNNEL_TOKEN%"=="" goto REMOTE

echo.
echo [LOCAL MODE]
echo Dashboard: http://127.0.0.1:8765
echo Remote access is not configured.
start "" http://127.0.0.1:8765
goto END

:REMOTE
echo.
echo [REMOTE MODE]
echo Starting protected Cloudflare Tunnel...
start "Khyrat Marketplace Tunnel" cmd /c "cloudflared tunnel run --token %MARKETPLACE_CLOUDFLARE_TUNNEL_TOKEN%"

timeout /t 2 /nobreak >nul
if not "%MARKETPLACE_REMOTE_URL%"=="" (
  echo Remote Dashboard: %MARKETPLACE_REMOTE_URL%
  start "" "%MARKETPLACE_REMOTE_URL%"
) else (
  echo Tunnel is running. Set MARKETPLACE_REMOTE_URL to open the dashboard automatically.
)

echo.
echo IMPORTANT: Cloudflare Access must protect the hostname before this is used remotely.

goto END

:END
echo.
echo The Marketplace server window must remain running.
echo Press Ctrl+C in that window to stop the dashboard.
pause
endlocal
