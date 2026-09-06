@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py src\marketplace\server.py --seed-demo
) else (
  python src\marketplace\server.py --seed-demo
)
pause
