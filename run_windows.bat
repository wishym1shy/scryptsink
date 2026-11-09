@echo off
setlocal
cd /d "%~dp0"

rem Setup counts as finished only when this marker exists. It is written last, after the install
rem worked, and holds a copy of requirements.txt, so an updated app re-runs the install too (#12).
set "MARK=.venv\setup-complete.txt"
set "RETRIED="
if not exist ".venv\Scripts\pythonw.exe" goto setup
if not exist "%MARK%" goto setup
fc /b "%MARK%" requirements.txt >nul 2>nul
if errorlevel 1 goto setup
goto launch

:setup
echo.
if exist ".venv" goto resume
echo  First-time setup for ScryptSink. This takes a few minutes and needs internet.
echo  (It only happens once.)
goto setup_go
:resume
echo  Setup didn't finish last time, or ScryptSink was updated. Finishing it now.
:setup_go
echo  Please keep this window open until ScryptSink opens.
echo.
if exist "%MARK%" del /q "%MARK%"
rem Reuse a .venv whose Python works (saves re-downloading); otherwise start it again.
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul && goto install
:fresh
if exist ".venv" rmdir /s /q ".venv"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -m venv .venv
if errorlevel 1 goto fail

:install
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -c "import faster_whisper, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 goto broken
copy /y requirements.txt "%MARK%" >nul
if errorlevel 1 goto fail

:launch
start "" ".venv\Scripts\pythonw.exe" scriptsync_gui.py
exit /b 0

:broken
rem Installed but won't import (an earlier install was cut off half-way): rebuild once from scratch.
if defined RETRIED goto fail
set "RETRIED=1"
echo.
echo  Some parts of the last setup were incomplete. Starting setup again from scratch.
echo.
goto fresh

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
echo  Setup did not finish. Check the internet connection and double-click this file again;
echo  it picks up where it stopped. If it keeps failing, take a screenshot of this window and
echo  send it to whoever shared this tool with you.
echo.
pause
exit /b 1
