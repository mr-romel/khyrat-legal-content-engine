@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=.;src
python src/marketplace/auto_dashboard.py
endlocal
