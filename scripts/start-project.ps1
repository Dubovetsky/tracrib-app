$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot ".runtime"
$logDir = Join-Path $runtimeDir "logs"
$pidFile = Join-Path $runtimeDir "project-pids.json"
$backendUrl = "http://127.0.0.1:8000/api/health"
$frontendUrl = "http://127.0.0.1:5173"

New-Item -ItemType Directory -Force -Path $runtimeDir, $logDir | Out-Null

Write-Host "Stopping old project processes..."
& (Join-Path $PSScriptRoot "stop-project.ps1") -Quiet

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            Invoke-RestMethod -Uri $Url -TimeoutSec 3 | Out-Null
            return $true
        } catch {
            Start-Sleep -Milliseconds 700
        }
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Wait-TcpPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            return $true
        }
        Start-Sleep -Milliseconds 700
    } while ((Get-Date) -lt $deadline)

    return $false
}

$backendOut = Join-Path $logDir "backend.out.log"
$backendErr = Join-Path $logDir "backend.err.log"
$frontendOut = Join-Path $logDir "frontend.out.log"
$frontendErr = Join-Path $logDir "frontend.err.log"

Remove-Item -LiteralPath $backendOut, $backendErr, $frontendOut, $frontendErr -ErrorAction SilentlyContinue

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
$backendProcess = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "run-backend.ps1")
    ) `
    -WorkingDirectory $repoRoot `
    -WindowStyle Minimized `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru

if (-not (Wait-HttpOk -Url $backendUrl -TimeoutSeconds 90)) {
    Write-Host "Backend did not become healthy. Last backend error log:"
    if (Test-Path $backendErr) {
        Get-Content -LiteralPath $backendErr -Tail 80
    }
    throw "Backend startup failed"
}

Write-Host "Starting frontend on http://127.0.0.1:5173 ..."
$frontendProcess = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "run-frontend.ps1")
    ) `
    -WorkingDirectory (Join-Path $repoRoot "frontend") `
    -WindowStyle Minimized `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

if (-not (Wait-TcpPort -Port 5173 -TimeoutSeconds 60)) {
    Write-Host "Frontend did not open port 5173. Last frontend error log:"
    if (Test-Path $frontendErr) {
        Get-Content -LiteralPath $frontendErr -Tail 80
    }
    throw "Frontend startup failed"
}

@{
    BackendPid = $backendProcess.Id
    FrontendPid = $frontendProcess.Id
    StartedAt = (Get-Date).ToString("o")
    BackendUrl = "http://127.0.0.1:8000"
    FrontendUrl = $frontendUrl
    LogDir = $logDir
} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

Start-Process $frontendUrl

Write-Host ""
Write-Host "Project is running."
Write-Host "Frontend: $frontendUrl"
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Logs:     $logDir"
Write-Host "Stop:     .\stop-project.cmd"
