<#
.SYNOPSIS
    Creates a 1-Click Desktop Shortcut for J.A.R.V.I.S. Mark VII on Windows Desktop
#>

$ErrorActionPreference = "Stop"

$desktopPath = [Environment]::GetFolderPath("Desktop")
if (-not (Test-Path $desktopPath)) {
    Write-Host "[ERROR] Could not locate Windows Desktop path." -ForegroundColor Red
    exit 1
}

$targetBat = Join-Path $PSScriptRoot "run.bat"
$shortcutPath = Join-Path $desktopPath "J.A.R.V.I.S. Mark VII.lnk"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CREATING J.A.R.V.I.S. MARK VII DESKTOP SHORTCUT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

try {
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetBat
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = "Stark Industries J.A.R.V.I.S. Mark VII Autonomous AI Desktop Assistant"
    # Shell32 icon index 14 is a high-tech microprocessor / computer display
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
    $shortcut.Save()

    Write-Host "[SUCCESS] Shortcut created successfully on your Desktop:" -ForegroundColor Green
    Write-Host "          $shortcutPath" -ForegroundColor White
    Write-Host ""
    Write-Host "You can now launch J.A.R.V.I.S. Mark VII anytime by double-clicking the icon on your Desktop!" -ForegroundColor Cyan
} catch {
    Write-Host "[ERROR] Failed to create shortcut: $_" -ForegroundColor Red
    exit 1
}
