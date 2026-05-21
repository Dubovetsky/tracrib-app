$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

foreach ($name in @(
    "HF_TOKEN",
    "DIARIZATION_ENABLED",
    "DIARIZATION_MIN_SPEAKERS",
    "DIARIZATION_MAX_SPEAKERS",
    "HF_HOME",
    "HUGGINGFACE_HUB_CACHE",
    "HF_HUB_DISABLE_XET"
)) {
    $value = [Environment]::GetEnvironmentVariable($name, "User")
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

$env:DIARIZATION_ENABLED = if ($env:DIARIZATION_ENABLED) { $env:DIARIZATION_ENABLED } else { "1" }
$env:DIARIZATION_MIN_SPEAKERS = if ($env:DIARIZATION_MIN_SPEAKERS) { $env:DIARIZATION_MIN_SPEAKERS } else { "2" }
$env:DIARIZATION_MAX_SPEAKERS = if ($env:DIARIZATION_MAX_SPEAKERS) { $env:DIARIZATION_MAX_SPEAKERS } else { "4" }
$env:HF_HUB_DISABLE_XET = "1"

foreach ($name in @("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")) {
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
}

python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
