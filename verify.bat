@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title HEEH-V1 DICOM Viewer - Verification

echo.
echo ================================================================
echo   HEEH-V1 DICOM Viewer - Project Verification
echo ================================================================
echo.

if not exist "app.py" (
    echo [FAIL] app.py was not found.
    exit /b 1
)

set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

echo [1/7] Checking Python...
"%PYTHON_EXE%" --version
if errorlevel 1 (
    echo [FAIL] Python is unavailable.
    exit /b 1
)

echo.
echo [2/7] Checking required imports and ONNX...
"%PYTHON_EXE%" -c "import streamlit, pydicom, nibabel, SimpleITK, torch, onnx, onnxruntime, ml_dtypes; import app; print('Imports and ONNX: OK')"
if errorlevel 1 (
    echo [FAIL] Required imports or application import failed.
    exit /b 1
)

echo.
echo [3/7] Checking dependency consistency...
"%PYTHON_EXE%" -m pip check
if errorlevel 1 (
    echo [FAIL] Dependency check failed.
    exit /b 1
)

echo.
echo [4/7] Running Ruff...
if exist "%~dp0.venv\Scripts\ruff.exe" (
    "%~dp0.venv\Scripts\ruff.exe" check .
    if errorlevel 1 (
        echo [FAIL] Ruff reported issues.
        exit /b 1
    )
) else (
    echo [SKIP] Ruff executable was not found.
)

echo.
echo [5/7] Compiling Python modules...
"%PYTHON_EXE%" -m compileall -q app.py core engines tests utils scripts
if errorlevel 1 (
    echo [FAIL] Python compilation failed.
    exit /b 1
)

echo.
echo [6/7] Running the complete test suite...
"%PYTHON_EXE%" -m pytest -q
if errorlevel 1 (
    echo [FAIL] Test suite failed.
    exit /b 1
)

echo.
echo [7/7] Verifying launcher and project metadata...
if not exist "app.bat" (
    echo [FAIL] app.bat is missing.
    exit /b 1
)
if not exist "requirements.lock" (
    echo [FAIL] requirements.lock is missing.
    exit /b 1
)
if not exist "pyproject.toml" (
    echo [FAIL] pyproject.toml is missing.
    exit /b 1
)

echo.
echo ================================================================
echo   VERIFICATION PASSED
echo   The local environment, imports, ONNX, lint, compilation,
echo   dependencies, tests, and launcher metadata are valid.
echo ================================================================
exit /b 0
