@echo off
setlocal
cd /d "%~dp0"
title Khyrat Blogger Bootstrap
echo.
echo ==========================================
echo       KHYRAT BLOGGER BOOTSTRAP
echo ==========================================
echo.
python scripts\bootstrap_blogger_ui_state.py
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo ==========================================
  echo BOOTSTRAP FAILED - ERROR CODE %EXIT_CODE%
  echo ==========================================
) else (
  echo ==========================================
  echo BOOTSTRAP FINISHED
  echo ==========================================
)
echo.
pause
exit /b %EXIT_CODE%
