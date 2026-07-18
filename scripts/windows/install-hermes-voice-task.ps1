param(
    [switch]$DryRun,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Launcher = Join-Path $RepoRoot "scripts\windows\start-hermes-voice.ps1"
$TaskName = "Hermes Voice"

if ($Uninstall) {
    if ($DryRun) {
        Write-Host "Would delete scheduled task: $TaskName"
        exit 0
    }
    schtasks.exe /Delete /TN $TaskName /F
    exit $LASTEXITCODE
}

if (-not (Test-Path $Launcher)) {
    throw "Missing launcher: $Launcher"
}

$TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Launcher`""
if ($DryRun) {
    Write-Host "Would create scheduled task: $TaskName"
    Write-Host $TaskCommand
    exit 0
}

schtasks.exe /Create /TN $TaskName /TR $TaskCommand /SC ONLOGON /F
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
schtasks.exe /Run /TN $TaskName
exit $LASTEXITCODE
