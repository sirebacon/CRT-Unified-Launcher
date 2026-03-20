@echo off
setlocal
cd /d "%~dp0"

echo [CRT Station] Checking dependencies...
pip show customtkinter >nul 2>&1 || pip install customtkinter
pip show pyinstaller  >nul 2>&1 || pip install pyinstaller

echo.
echo [CRT Station] Building executable...
echo.

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "CRT Station" ^
  --icon "assets\crt_station.ico" ^
  --add-data "assets;assets" ^
  --add-data "gui\helpers\restore_defaults_runner.py;gui\helpers" ^
  --hidden-import customtkinter ^
  --hidden-import PIL._tkinter_finder ^
  crt_station_gui.py

echo.
if exist "dist\CRT Station.exe" (
    echo  Build succeeded:  dist\CRT Station.exe
    echo.
    echo  To create a desktop shortcut, right-click the .exe and choose
    echo  "Send to > Desktop (create shortcut)".
) else (
    echo  Build FAILED. Review the output above for errors.
    echo  Tip: remove --windowed temporarily to see startup errors.
)
echo.
pause
