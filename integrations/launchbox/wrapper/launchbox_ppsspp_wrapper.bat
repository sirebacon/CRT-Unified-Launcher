@echo off
setlocal
set SCRIPT_DIR=%~dp0
title CRT Launcher - PPSSPP Wrapper
echo [CRT Launcher] PPSSPP wrapper is active. Keep this window open while the game is running.

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT_DIR%launchbox_ppsspp_wrapper.py" %*
  exit /b %errorlevel%
)

py -3 "%SCRIPT_DIR%launchbox_ppsspp_wrapper.py" %*
exit /b %errorlevel%
