@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo Khyrat Marketplace - Remote Access Setup
echo ==============================================
echo.
echo This setup uses Cloudflare Tunnel + Cloudflare Access.
echo It does NOT open a router port.
echo.
echo Prerequisites:
echo 1. A Cloudflare account
2. A domain managed by Cloudflare
3. cloudflared installed and available in PATH
4. A Cloudflare Tunnel with an Access-protected hostname
5. The Tunnel token from Cloudflare

echo.
set /p "TOKEN=Paste the Cloudflare Tunnel token (input is hidden only by your terminal limitations): "
if "%TOKEN%"=="" (
  echo No token entered. Nothing changed.
  pause
  exit /b 1
)
set /p "URL=Enter the protected dashboard URL (for example https://marketplace.example.com): "
if "%URL%"=="" (
  echo No URL entered. Nothing changed.
  pause
  exit /b 1
)

setx MARKETPLACE_CLOUDFLARE_TUNNEL_TOKEN "%TOKEN%" >nul
setx MARKETPLACE_REMOTE_URL "%URL%" >nul

echo.
echo Saved the settings to your Windows user environment.
echo Close and reopen Command Prompt before launching the dashboard.
echo.
echo IMPORTANT: The hostname must already be protected by Cloudflare Access.
echo Never use a public Quick Tunnel for this private dashboard.
echo.
pause
endlocal
