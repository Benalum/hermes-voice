
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
$env:HV_MODE = "telegram"
$env:HV_SPEECH_BACKEND = "auto"
if (-not $env:HV_MAX_SPOKEN_CHARS) {
    $env:HV_MAX_SPOKEN_CHARS = "0"
}
& "$RepoRoot\.venv\Scripts\uvicorn.exe" hermes_voice.server.app:create_app --factory --host 127.0.0.1 --port 8990
