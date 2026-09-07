@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=.;src
python src/marketplace/pro_dashboard.py --port 8766
endlocal
