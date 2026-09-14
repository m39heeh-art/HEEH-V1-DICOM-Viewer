# HEEH-V1™ DICOM Viewer - All-In-One Launcher
# Version 1.0.0

Clear-Host
Write-Host "HEEH-V1™ DICOM Viewer (Research / Education)" -ForegroundColor White
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# --- Find the right Python ---
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonPath = $venvPython
    Write-Host "[OK] Using venv Python" -ForegroundColor Green
} else {
    $sysPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $sysPython) {
        Write-Host "[ERROR] Python not found in PATH. Install Python 3.11+ and try again." -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit 1
    }
    $pythonPath = $sysPython
    Write-Host "[OK] Using system Python: $sysPython" -ForegroundColor Green
}

# --- Verify streamlit is available ---
& $pythonPath -c "import streamlit" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] streamlit is not installed." -ForegroundColor Red
    Write-Host "  Install dependencies with:  pip install -r requirements.txt" -ForegroundColor Yellow
    Read-Host "Press Enter to exit..."
    exit 1
}

Write-Host ""
Write-Host "Launching HEEH-V1™ DICOM Viewer..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Local URL: http://localhost:8501" -ForegroundColor Green
Write-Host ""

& $pythonPath -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless false --browser.gatherUsageStats false
