param(
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot ".runtime"
$pidFile = Join-Path $runtimeDir "project-pids.json"
$ports = @(8000, 5173)

function Log {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Kill-Tree {
    param([int]$ProcessId)
    if ($ProcessId -le 0) {
        return
    }
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }
    Log "Killing process tree PID $ProcessId ($($process.ProcessName))"
    & taskkill.exe /PID $ProcessId /T /F | Out-Null
}

function Kill-PortOwners {
    param([int]$Port)

    $owners = @()
    try {
        $owners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -and $_.OwningProcess -gt 0 } |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        $owners = @()
    }

    if (-not $owners -or $owners.Count -eq 0) {
        $owners = netstat.exe -ano |
            Select-String -Pattern "127\.0\.0\.1:$Port\s|0\.0\.0\.0:$Port\s|\[::\]:$Port\s" |
            ForEach-Object {
                $parts = ($_.Line -replace "^\s+", "") -split "\s+"
                if ($parts.Count -ge 5 -and $parts[3] -eq "LISTENING") {
                    [int]$parts[4]
                }
            } |
            Where-Object { $_ -gt 0 } |
            Select-Object -Unique
    }

    foreach ($owner in $owners) {
        Log "Killing owner of port ${Port}: PID $owner"
        Kill-Tree -ProcessId ([int]$owner)
    }
}

if (Test-Path $pidFile) {
    try {
        $pids = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        Kill-Tree -ProcessId ([int]$pids.BackendPid)
        Kill-Tree -ProcessId ([int]$pids.FrontendPid)
    } catch {
        Log "Could not read PID file cleanly: $($_.Exception.Message)"
    }
}

foreach ($port in $ports) {
    Kill-PortOwners -Port $port
}

Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue

Log "Project processes stopped."
