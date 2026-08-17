# lra-mcp test runner — delegates to run_tests.py so the log is clean UTF-8
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$EnvName = "lra"

Write-Host "== running tests via Python (env: $EnvName) ==" -ForegroundColor Cyan
conda run -n $EnvName python run_tests.py
Write-Host "pytest + compileall exit code: $LASTEXITCODE"
Read-Host "Press Enter to exit"
