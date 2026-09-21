@echo off
setlocal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name SocialPoster SocialPoster.py
if exist dist\SocialPoster.exe echo BUILD OK: dist\SocialPoster.exe
pause
