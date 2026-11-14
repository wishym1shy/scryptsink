@echo off
setlocal
cd /d "%~dp0"

rem Setup counts as finished only when this marker exists. It is written last, after the install
rem worked, and holds a copy of requirements.txt, so an updated app re-runs the install too (#12).
set "MARK=.venv\setup-complete.txt"
set "RETRIED="
set "SAC_OK="
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
call :smartappcontrol
if defined SAC_STOP exit /b 1
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
rem Check the speech engine really loads. Keep its error to show if it doesn't.
".venv\Scripts\python.exe" -c "import faster_whisper, imageio_ffmpeg" > ".venv\import-check.txt" 2>&1
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
rem Windows itself refused to load a file: reinstalling can't help, so say why instead of rebuilding.
find "DLL load failed" ".venv\import-check.txt" >nul 2>nul
if not errorlevel 1 goto blocked
rem Installed but won't import (an earlier install was cut off half-way): rebuild once from scratch.
if defined RETRIED goto importfail
set "RETRIED=1"
echo.
echo  Some parts of the last setup were incomplete. Starting setup again from scratch.
echo.
goto fresh

:importfail
echo.
echo  The speech engine was installed but doesn't load. The error was:
echo.
type ".venv\import-check.txt"
goto stuck

:blocked
echo.
echo  Windows refused to load part of the speech engine:
echo.
type ".venv\import-check.txt"
echo.
set "SAC="
call :sacstate
if "%SAC%"=="0x1" goto blocked_sac
echo  This usually means security software blocked it. If you use antivirus other than
echo  Microsoft Defender, allow this folder in it, then double-click this file again.
goto stuck
:blocked_sac
call :sacexplain
pause
exit /b 1

:smartappcontrol
rem Windows 11 Smart App Control blocks the speech engine (its ctranslate2.dll is not digitally signed).
rem 0x1 = On (blocks), 0x2 = Evaluation (doesn't block), 0x0 = Off. Warn before downloading anything.
set "SAC_STOP="
if defined SAC_OK exit /b 0
set "SAC="
call :sacstate
if not "%SAC%"=="0x1" exit /b 0
call :sacexplain
set "ANSWER="
set /p "ANSWER= To try the setup anyway, type Y and press Enter. To stop, just press Enter: "
if /i "%ANSWER%"=="Y" goto sac_go
set "SAC_STOP=1"
exit /b 0
:sac_go
set "SAC_OK=1"
echo.
exit /b 0

:sacstate
for /f "tokens=3" %%s in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy" /v VerifiedAndReputablePolicyState 2^>nul ^| find "VerifiedAndReputablePolicyState"') do set "SAC=%%s"
exit /b 0

:sacexplain
echo.
echo  Windows "Smart App Control" is turned on. It blocks part of the speech engine that
echo  ScryptSync uses, because that file is not digitally signed, so ScryptSync can't run.
echo.
echo  To use ScryptSync, turn it off:
echo    Windows Security ^> App ^& browser control ^> Smart App Control settings ^> Off
echo  Then double-click this file again.
echo.
echo  Please note: once Smart App Control is off, Windows can only turn it back on by
echo  reinstalling Windows. Microsoft Defender antivirus keeps protecting the PC either way.
echo  On a work computer, ask your IT team first.
echo.
exit /b 0

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

:stuck
echo.
echo  Setup did not finish. If it keeps failing, take a screenshot of this window and send it
echo  to whoever shared this tool with you.
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
