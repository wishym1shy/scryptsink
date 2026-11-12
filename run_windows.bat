@echo off
setlocal
cd /d "%~dp0"

rem Setup counts as finished only when this marker exists. It is written last, after the install
rem worked, and holds a copy of requirements.txt, so an updated app re-runs the install too (#12).
set "MARK=.venv\setup-complete.txt"
set "RETRIED="
rem Python versions ScryptSync can install on. Keep in step with PYTHON_MIN/PYTHON_MAX in scriptsync_core.py.
set "PYOK=import sys; sys.exit(not (3,9) <= sys.version_info[:2] <= (3,14))"
if not exist ".venv\Scripts\pythonw.exe" goto setup
if not exist "%MARK%" goto setup
fc /b "%MARK%" requirements.txt >nul 2>nul
if errorlevel 1 goto setup
goto launch

:setup
echo.
if exist ".venv" goto resume
echo  First-time setup for ScryptSync. This takes a few minutes and needs internet.
echo  (It only happens once.)
goto setup_go
:resume
echo  Setup didn't finish last time, or ScryptSync was updated. Finishing it now.
:setup_go
echo  Please keep this window open until ScryptSync opens.
echo.
if exist "%MARK%" del /q "%MARK%"
rem Reuse a .venv whose Python works and is a supported version (saves re-downloading);
rem otherwise start it again.
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "%PYOK%" >nul 2>nul && goto install
:fresh
if exist ".venv" rmdir /s /q ".venv"
call :findpy
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

:findpy
rem Newest supported Python first, so a computer with several versions uses one that works.
set "PY="
set "ANYPY="
where py >nul 2>nul && set "ANYPY=py"
for %%V in (3.14 3.13 3.12 3.11 3.10 3.9) do (
  if not defined PY py -%%V -c "%PYOK%" >nul 2>nul && set "PY=py -%%V"
)
if defined PY exit /b 0
if not defined ANYPY where python >nul 2>nul && set "ANYPY=python"
if not defined ANYPY exit /b 0
if "%ANYPY%"=="python" python -c "%PYOK%" >nul 2>nul && set "PY=python"
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
if defined ANYPY goto wrongpython
echo  Python is not installed yet.
echo  1. Go to https://www.python.org/downloads/ and install Python 3.14.
echo  2. On the first installer screen, tick "Add python.exe to PATH".
echo  3. Then double-click this file again.
echo.
pause
exit /b 1

:wrongpython
set "FOUNDV="
for /f "delims=" %%v in ('%ANYPY% -c "import platform; print(platform.python_version())" 2^>nul') do set "FOUNDV=%%v"
echo  ScryptSync can't use the Python on this computer (%FOUNDV%): part of the speech engine
echo  isn't available for that version yet. ScryptSync works with Python 3.9 to 3.14.
echo  1. Go to https://www.python.org/downloads/ and install Python 3.14
echo     (under "Looking for a specific release?"). You can keep the other version.
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
