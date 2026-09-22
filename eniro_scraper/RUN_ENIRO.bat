@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
py -m playwright install chromium
py eniro_private_people.py
pause
