@echo off
echo =========================================
echo Building Twitch Pear Song Requests to EXE
echo =========================================
echo.

echo Installing PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo Error installing PyInstaller. Make sure Python/pip is installed and in your PATH.
    pause
    exit /b %errorlevel%
)

echo.
echo Running PyInstaller...
:: --noconfirm: overwrite existing build directories
:: --onefile: create a single executable file instead of a directory
:: --windowed: do not provide a console window for standard i/o
:: --hidden-import / --collect-binaries: ensure pywin32 credential manager modules work inside the EXE
:: --add-data "SOURCE;DEST": bundle the SVG file so it's available in the final exe
pyinstaller --noconfirm --onefile --windowed --icon="icon.ico" --hidden-import win32cred --hidden-import pywintypes --collect-binaries pywin32_system32 --add-data "app/ui/checkmark.svg;app/ui" --name "PearSongBot" main.py

if %errorlevel% neq 0 (
    echo.
    echo PyInstaller failed with an error.
    pause
    exit /b %errorlevel%
)

echo.
echo =========================================
echo Build Complete!
echo You can find the built program in the "dist\PearSongBot" folder.
echo =========================================
pause
