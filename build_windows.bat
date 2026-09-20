@echo off
py -3 -m pip install --upgrade pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name MaklarScraper_v1 google_maps_maklarscraper.py
echo EXE: dist\\MaklarScraper_v1.exe
pause
