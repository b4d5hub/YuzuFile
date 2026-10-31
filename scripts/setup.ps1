$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
    & .venv/Scripts/python.exe -m pip install --no-deps -r requirements-windows.lock
    if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned environment." }
    & .venv/Scripts/python.exe -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw "Could not install dependencies." }
    & .venv/Scripts/python.exe -m pdfai doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Install Tesseract with at least one recognition language before using OCR. See README.md."
    }
} finally {
    Pop-Location
}

