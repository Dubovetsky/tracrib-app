$ErrorActionPreference = "Stop"

$response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 10
$response | ConvertTo-Json -Compress
