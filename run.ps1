param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AppArgs)
$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Run .\scripts\setup.ps1 first."
}
$env:PYTHONPATH = Join-Path $projectRoot "src"
& $pythonPath -m yuzufile @AppArgs
exit $LASTEXITCODE

