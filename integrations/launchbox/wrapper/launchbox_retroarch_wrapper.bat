@echo off
setlocal
set SCRIPT_DIR=%~dp0

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT_DIR%launchbox_retroarch_wrapper.py" %*
  exit /b %errorlevel%
)

py -3 "%SCRIPT_DIR%launchbox_retroarch_wrapper.py" %*
exit /b %errorlevel%
