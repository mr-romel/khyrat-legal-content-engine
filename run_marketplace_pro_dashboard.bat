@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%;%CD%\src"
set "PYTHONUNBUFFERED=1"

echo ========================================
echo   Khyrat Marketplace - Pro Dashboard
echo ========================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo [ERROR] Python 3 is not installed or not in PATH.
        echo Install Python 3 and run this file again.
        pause
        exit /b 1
    )
)

echo [1/2] Checking Python packages...
%PY% -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages from requirements.txt...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Package installation failed.
        pause
        exit /b 1
    )
)

echo [2/2] Starting dashboard...
echo Open manually if needed: http://127.0.0.1:8766/
echo Keep this window open while using the dashboard.
echo.
%PY% src\marketplace\auto_dashboard.py

echo.
echo ========================================
echo Dashboard stopped. Review the error above.
echo ========================================
pause
endlocal
