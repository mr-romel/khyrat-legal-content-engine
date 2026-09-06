@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD=python"
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py"

rem Make the src package importable when launched directly from the repo root.
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

rem Start the dashboard as a Python module so package imports work reliably.
start "Khyrat Marketplace Dashboard" cmd /c "cd /d "%~dp0" && set "PYTHONPATH=%CD%\src;%PYTHONPATH%" && %PYTHON_CMD% -m marketplace.server --seed-demo"

echo.
echo Waiting for Marketplace Dashboard...
for /l %%I in (1,1,10) do (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/' -TimeoutSec 1 ^| Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 goto LOCAL_READY
  timeout /t 1 /nobreak >nul
)

echo.
echo [ERROR] Marketplace Dashboard did not start on http://127.0.0.1:8765
 echo Check the dashboard window for the Python error.
start "" http://127.0.0.1:8765
goto END

:LOCAL_READY
echo.
echo [LOCAL MODE]
echo Dashboard: http://127.0.0.1:8765
start "" http://127.0.0.1:8765

rem If a protected Cloudflare Tunnel token is configured, start remote access too.
where cloudflared >nul 2>nul
if errorlevel 1 goto NO_CLOUDFLARE
if "%MARKETPLACE_CLOUDFLARE_TUNNEL_TOKEN%"=="" goto NO_CLOUDFLARE

echo.
echo [REMOTE MODE]
echo Starting protected Cloudflare Tunnel...
start "Khyrat Marketplace Tunnel" cmd /c "cloudflared tunnel run --token %MARKETPLACE_CLOUDFLARE_TUNNEL_TOKEN%"
timeout /t 2 /nobreak >nul

if not "%MARKETPLACE_REMOTE_URL%"=="" (
  echo Remote Dashboard: %MARKETPLACE_REMOTE_URL%
  start "" "%MARKETPLACE_REMOTE_URL%"
) else (
  echo Tunnel started, but MARKETPLACE_REMOTE_URL is not configured.
  echo Configure it with setup_marketplace_remote.bat.
)

echo.
echo IMPORTANT: The Cloudflare hostname must be protected by Cloudflare Access.
goto END

:NO_CLOUDFLARE
echo.
echo [REMOTE MODE]
echo Not configured. Local dashboard remains available.
echo To enable mobile/online access, run setup_marketplace_remote.bat once.

goto END

:END
echo.
echo Local dashboard: http://127.0.0.1:8765
echo Keep the dashboard window running while using the dashboard.
pause
endlocal
