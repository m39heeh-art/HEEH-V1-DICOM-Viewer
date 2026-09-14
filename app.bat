@echo off
setlocal enableextensions
cd /d "%~dp0"
title HEEH-V1 DICOM Viewer
color 0B

set "APP_NAME=HEEH-V1 DICOM Viewer"
set "APP_VERSION=1.0.0"

echo.
echo   ========================================================================
echo.
echo                    ^|  /  ^|  _____   _____  ^|  /  ^|
echo                    ^| ^| ^| ^| ^|  ___^| ^|  ___^| ^| ^| ^| ^|
echo                    ^| ^| ^| ^| ^| ^|__   ^| ^|__   ^| ^| ^| ^|
echo                    ^|  \  ^| ^|  __^|  ^|  __^|  ^|  \  ^|
echo                    ^|_^| ^|_^| ^|_____^| ^|_____^| ^|_^| ^|_^|
echo.
echo                     H E E H - V 1   D I C O M   V I E W E R
echo                      Research / Education Tool
echo.
echo                  Health . Envisioning . Expertise
echo.
echo                              v%APP_VERSION%
echo   ========================================================================
echo.

REM ---------------------------------------------------------------
REM  Preflight checks
REM ---------------------------------------------------------------

echo   [1/3] Verifying workspace...
if not exist app.py (
    echo.
    echo   [FAIL] app.py not found in the current directory.
    echo          Run this script from the HEEH-V1 DICOM Viewer folder.
    echo.
    pause
    exit /b 1
)
echo   [ OK ] app.py found

echo.
echo   [2/3] Checking Python runtime...
set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [FAIL] Python was not found in PATH.
    echo          Install Python 3.11+ from https://www.python.org/
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PYVER=%%v"
echo   [ OK ] %PYVER%

echo.
echo   [3/3] Checking Streamlit...
"%PYTHON_EXE%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [FAIL] Streamlit is not installed.
    echo          Fix with:  "%PYTHON_EXE%" -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo   [ OK ] Streamlit ready

echo.
echo   All preflight checks passed - starting %APP_NAME%...
echo.

REM ---------------------------------------------------------------
REM  Launch
REM ---------------------------------------------------------------

echo   [RUN] Starting Streamlit server in the background...
if not exist logs mkdir logs
start /min "" cmd /c ""%PYTHON_EXE%" -m streamlit run "%~dp0app.py" --server.address 127.0.0.1 --server.port 8501 --server.headless true > "%~dp0logs\streamlit.log" 2>&1"

echo.
echo   ========================================================================
echo.
echo                      HEEH-V1 DICOM VIEWER IS RUNNING
echo.
echo   ========================================================================
echo.
echo      [WEB]     http://localhost:8501
echo      [LOG]     logs\streamlit.log
echo      [DOC]     README.md
echo.
echo      [STOP]    Close this window, then stop ONLY the python.exe
echo                process listening on port 8501:
echo                    netstat -ano ^| findstr :8501
echo                    taskkill /F /PID ^<PID^>
echo                Do NOT run:  taskkill /f /im python.exe
echo                (it also kills unrelated Python processes).
echo.
echo      Happy analyzing!
echo.

pause