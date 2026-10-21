<#
.SYNOPSIS
    J.A.R.V.I.S. Mark VII - PowerShell 1-Click Launcher
.DESCRIPTION
    Launches Stark Industries J.A.R.V.I.S. Mark VII with automatic Python detection,
    dependency checks, and parameter forwarding.
#>

param(
    [switch]$gui,
    [switch]$voice,
    [switch]$ptt,
    [switch]$text,
    [switch]$diag,
    [switch]$dryRun,
    [switch]$debugMode,
    [switch]$reset,
    [switch]$listMics
)

$Host.UI.RawUI.WindowTitle = "J.A.R.V.I.S. Mark VII - Stark Industries"
Set-Location -Path $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  STARK INDUSTRIES J.A.R.V.I.S. MARK VII - LAUNCHER" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Detect Python
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py -3"
} else {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $pythonCmd = $c
            break
        }
    }
}

if (-not $pythonCmd) {
    Write-Host "[ERROR] Python 3 was not found on your system." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

$pyVersion = & $pythonCmd --version 2>&1
Write-Host "[SYS] Python detected: $pyVersion" -ForegroundColor Green

# 2. Check .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "[SYS] Generating default .env from .env.example..." -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
    }
} else {
    Write-Host "[SYS] Configuration (.env) verified." -ForegroundColor Green
}

# 3. Assemble arguments
$argsList = @()
if ($gui)      { $argsList += "--gui" }
if ($voice)    { $argsList += "--voice" }
if ($ptt)      { $argsList += "--ptt" }
if ($text)     { $argsList += "--text" }
if ($diag)     { $argsList += "--diag" }
if ($dryRun)   { $argsList += "--dry-run" }
if ($debugMode) { $argsList += "--debug" }
if ($reset)    { $argsList += "--reset" }
if ($listMics) { $argsList += "--list-mics" }

# Default to GUI if no mode flags provided
if ($argsList.Count -eq 0) {
    Write-Host "[SYS] Launching default Holographic HUD GUI..." -ForegroundColor Cyan
    & $pythonCmd main.py
} else {
    Write-Host "[SYS] Launching with parameters: $argsList" -ForegroundColor Cyan
    & $pythonCmd main.py $argsList
}

exit $LASTEXITCODE
