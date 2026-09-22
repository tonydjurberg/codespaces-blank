@echo off
py -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onedir --windowed --name IndustritorgetScraper IndustritorgetScraper.py
copy /Y industritorget_scraper.py dist\IndustritorgetScraper\industritorget_scraper.py
