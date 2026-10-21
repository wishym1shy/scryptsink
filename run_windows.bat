@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto launch

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

echo.
echo  First-time setup for Script Sync. This takes a few minutes and needs internet.
echo  (It only happens once.)
echo.
%PY% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail

:launch
start "" ".venv\Scripts\pythonw.exe" scriptsync_gui.py
exit /b 0

:nopython
echo.
echo  Python is not installed yet.
echo  1. Go to https://www.python.org/downloads/ and install Python 3.11 or newer.
echo  2. On the first installer screen, tick "Add python.exe to PATH".
echo  3. Then double-click this file again.
echo.
pause
exit /b 1

:fail
echo.
echo  Setup did not finish. Take a screenshot of this window and send it to whoever shared this tool with you.
echo.
rmdir /s /q ".venv" >nul 2>nul
pause
exit /b 1
