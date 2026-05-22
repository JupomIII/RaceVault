@echo off
setlocal enableextensions enabledelayedexpansion
REM Simple, robust launcher for RaceVault GUI (Windows)
REM Creates venv if missing, installs requirements, activates and runs the app.

cd /d "%~dp0" || (
    echo Failed to change directory to script location.
    pause
    exit /b 1
)

REM Find python: try 'python', then 'py', otherwise prompt user
set "PYEXEC="
for /f "delims=" %%P in ('where python 2^>nul') do set "PYEXEC=python"
if not defined PYEXEC for /f "delims=" %%P in ('where py 2^>nul') do set "PYEXEC=py -3"

if not defined PYEXEC (
    echo Python executable not found on PATH.
    set /p "PYINPUT=Enter full path to python.exe (or press Enter to open download page): "
    if "%PYINPUT%"=="" (
        start "" "https://www.python.org/downloads/"
        echo Please install Python 3.8+ and then re-run this script.
        pause
        exit /b 1
    )
    if not exist "%PYINPUT%" (
        echo The path you entered does not exist: %PYINPUT%
        pause
        exit /b 1
    )
    set "PYEXEC=%PYINPUT%"
)

REM Create virtualenv if needed
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    "%PYEXEC%" -m venv "venv"
    if errorlevel 1 (
        echo Failed to create virtual environment using %PYEXEC%.
        pause
        exit /b 1
    )
    echo Upgrading pip and installing dependencies...
    "venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel >nul 2>&1
    if exist "requirements.txt" (
        echo Installing requirements from requirements.txt...
        "venv\Scripts\python.exe" -m pip install -r "requirements.txt"
    ) else (
        echo requirements.txt not found; skipping dependency install.
    )
)

REM Use venv python if present
if exist "venv\Scripts\python.exe" set "PYEXEC=venv\Scripts\python.exe"

echo Starting RaceVault GUI (Python: %PYEXEC%)
echo Logs: run_stdout.log run_error.log

"%PYEXEC%" -u -m app.gui 1> run_stdout.log 2> run_error.log
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% neq 0 (
    echo Application exited with error (code %EXITCODE%). See run_error.log for details.
    echo ------------------------------------------------------------
    type run_error.log
    echo ------------------------------------------------------------
    pause
    exit /b %EXITCODE%
)

echo Application exited normally. See run_stdout.log for output.
pause
endlocal
exit /b 0