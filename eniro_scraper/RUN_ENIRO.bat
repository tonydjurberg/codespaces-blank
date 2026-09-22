@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
py -m playwright install chromium
set /p QUERY=Enter city or postcode (test: 21372): 
if "%QUERY%"=="" set QUERY=Stockholm
py eniro_private_people.py "%QUERY%"
pause
