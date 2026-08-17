# lra-mcp install + test runner (ASCII only)
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_conda.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_conda.ps1 -mirror
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

$EnvName = "lra"
$UseMirror = $args -contains "-mirror"

$Indexes = @()
if ($UseMirror) {
    $Indexes += "https://pypi.tuna.tsinghua.edu.cn/simple"
    $Indexes += "https://mirrors.aliyun.com/pypi/simple/"
    $Indexes += "https://pypi.org/simple"
} else {
    $Indexes += "https://pypi.org/simple"
    $Indexes += "https://pypi.tuna.tsinghua.edu.cn/simple"
    $Indexes += "https://mirrors.aliyun.com/pypi/simple/"
}

Write-Host "== 1/5 check conda env '$EnvName' ==" -ForegroundColor Cyan
conda run -n $EnvName python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] conda env '$EnvName' not found. Run lra's setup_conda.ps1 first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "== 2/5 install lra-mcp (no build isolation) ==" -ForegroundColor Cyan
$InstallOk = $false
foreach ($Index in $Indexes) {
    Write-Host "[pip] try index: $Index" -ForegroundColor DarkGray
    conda run -n $EnvName python -m pip install -e ".[dev]" --no-build-isolation -i $Index
    if ($LASTEXITCODE -eq 0) { $InstallOk = $true; break }
}
if (-not $InstallOk) {
    Write-Host "[FAILED] install failed. Copy the red output and send it to the captain." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "== 3/5 verify imports ==" -ForegroundColor Cyan
conda run -n $EnvName python -c "import lra_mcp.services, lra_mcp.security, lra_mcp.server; print('lra_mcp imports ok')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] import failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "== 4/5 pytest ==" -ForegroundColor Cyan
conda run -n $EnvName python -m pytest tests -q
Write-Host "pytest exit code: $LASTEXITCODE"

Write-Host ""
Write-Host "== 5/5 compileall ==" -ForegroundColor Cyan
conda run -n $EnvName python -m compileall lra_mcp
Write-Host "compileall exit code: $LASTEXITCODE"

Write-Host ""
Write-Host "Done. Copy this entire window output and send it to the captain." -ForegroundColor Green
Read-Host "Press Enter to exit"
