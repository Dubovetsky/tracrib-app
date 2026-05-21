$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $repoRoot "frontend")

$env:VITE_API_BASE = if ($env:VITE_API_BASE) { $env:VITE_API_BASE } else { "http://127.0.0.1:8000" }

npm run dev
