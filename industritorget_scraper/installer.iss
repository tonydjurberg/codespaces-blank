[Setup]
AppName=Industritorget Scraper
AppVersion=1.0.0
DefaultDirName={autopf}\Industritorget Scraper
DefaultGroupName=Industritorget Scraper
OutputDir=installer
OutputBaseFilename=IndustritorgetScraper_Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Industritorget Scraper

[Files]
Source: "dist\IndustritorgetScraper\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Industritorget Scraper"; Filename: "{app}\IndustritorgetScraper.exe"
Name: "{autodesktop}\Industritorget Scraper"; Filename: "{app}\IndustritorgetScraper.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\IndustritorgetScraper.exe"; Description: "Launch Industritorget Scraper"; Flags: nowait postinstall skipifsilent
