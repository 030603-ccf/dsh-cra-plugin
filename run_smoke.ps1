# Run lra-mcp local smoke test and save all output to E:\lra-mcp\smoke.log
# Usage:
#   powershell -ExecutionPolicy Bypass -File E:\lra-mcp\run_smoke.ps1
#   powershell -ExecutionPolicy Bypass -File E:\lra-mcp\run_smoke.ps1 -SkipReview
#   powershell -ExecutionPolicy Bypass -File E:\lra-mcp\run_smoke.ps1 -Install

param(
    [switch]$SkipTests,
    [switch]$SkipReview,
    [switch]$Install
)

$ErrorActionPreference = "Stop"

$LogDir = "E:\lra-mcp\logs"
$LogFile = "E:\lra-mcp\smoke.log"

function Main {
    param(
        [switch]$SkipTests,
        [switch]$SkipReview,
        [switch]$Install
    )

    $LraRepo = "E:\code-review-agent-langgraph"
    $McpRepo = "E:\lra-mcp"
    $RunsDir = "E:\lra-mcp-data\runs"
    $ConfigPath = "$LraRepo\config.yaml"
    $Profile = "cloud_api_deepseek-v4-flash"

    # 1. Locate python in the lra conda env.
    $PyCandidates = @(
        "E:\miniconda3\envs\lra\Scripts\python.exe",
        "E:\miniconda3\envs\lra\python.exe"
    )
    $Py = $null
    foreach ($c in $PyCandidates) {
        if (Test-Path $c) {
            $Py = $c
            break
        }
    }
    if (-not $Py) {
        $basePy = Get-Command python -ErrorAction SilentlyContinue
        if ($basePy) {
            $Py = $basePy.Source
        }
    }
    if (-not $Py) {
        Write-Host "[FATAL] lra conda env python not found." -ForegroundColor Red
        Write-Host "        Run: conda create -n lra python=3.11 -y"
        Write-Host "        Then: E:\miniconda3\envs\lra\Scripts\python.exe -m pip install -e E:\code-review-agent-langgraph"
        Write-Host "        Then: E:\miniconda3\envs\lra\Scripts\python.exe -m pip install -e 'E:\lra-mcp[dev]'"
        return 1
    }
    Write-Host "[INFO] Using python: $Py"

    # 2. Install if requested.
    if ($Install) {
        Write-Host "[INFO] Installing lra (editable) ..."
        & $Py -m pip install -e $LraRepo
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FATAL] lra install failed." -ForegroundColor Red
            return $LASTEXITCODE
        }
        Write-Host "[INFO] Installing lra-mcp (editable + dev) ..."
        & $Py -m pip install -e "$McpRepo[dev]"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FATAL] lra-mcp install failed." -ForegroundColor Red
            return $LASTEXITCODE
        }
    }

    # 3. Set environment for the MCP server.
    $env:LRA_MCP_CONFIG = $ConfigPath
    $env:LRA_MCP_PROFILE = $Profile
    $env:LRA_MCP_RUNS_DIR = $RunsDir
    $env:LRA_MCP_ALLOW_INLINE_KEY = "1"
    New-Item -ItemType Directory -Force -Path $RunsDir | Out-Null
    Write-Host "[INFO] LRA_MCP_CONFIG = $ConfigPath"
    Write-Host "[INFO] LRA_MCP_PROFILE = $Profile"
    Write-Host "[INFO] LRA_MCP_RUNS_DIR = $RunsDir"

    # 4. Run tests.
    if (-not $SkipTests) {
        Write-Host "[INFO] Running pytest ..."
        Push-Location $McpRepo
        try {
            & $Py -m pytest tests -q
            $testExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($testExit -ne 0) {
            Write-Host "[FATAL] Tests failed (exit $testExit)." -ForegroundColor Red
            Write-Host "        Try running with -Install first."
            return $testExit
        }
        Write-Host "[INFO] Tests passed."
    }

    # 5. MCP stdio smoke test.
    if ($SkipReview) {
        Write-Host "[INFO] Review smoke skipped."
        Write-Host "[INFO] Start server manually with: $Py -m lra_mcp.server"
    } else {
        Write-Host "[INFO] Smoke: initialize + tools/list + review_project (targets\smoke)"
        $requests = @(
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}',
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
            '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"review_project","arguments":{"path":"E:\\code-review-agent-langgraph\\targets\\smoke"}}}'
        )
        Push-Location $McpRepo
        try {
            $requests | & $Py -m lra_mcp.server
            $smokeExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($smokeExit -ne 0) {
            Write-Host "[FATAL] Smoke test failed (exit $smokeExit)." -ForegroundColor Red
            return $smokeExit
        }
        Write-Host "[INFO] Smoke test done."
    }

    return 0
}

# Save a complete log file next to the repo, then run.
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (Test-Path $LogFile) {
    Remove-Item $LogFile -Force
}
Start-Transcript -Path $LogFile | Out-Null
try {
    $exitCode = Main -SkipTests:$SkipTests.IsPresent -SkipReview:$SkipReview.IsPresent -Install:$Install.IsPresent
} catch {
    Write-Host "[FATAL] Unexpected error: $_" -ForegroundColor Red
    $exitCode = 1
} finally {
    Stop-Transcript | Out-Null
}
Write-Host "[INFO] Log saved to: $LogFile"
exit $exitCode
