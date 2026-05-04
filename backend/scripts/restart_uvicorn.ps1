# Free TCP port 8000 (English or Russian netstat), then start uvicorn from backend/.
# Run:  powershell -ExecutionPolicy Bypass -File .\scripts\restart_uvicorn.ps1

$port = 8000
$ErrorActionPreference = "SilentlyContinue"

$pids = New-Object "System.Collections.Generic.HashSet[int]"
foreach ($line in (netstat -ano)) {
    if ($line -notmatch ":$port\s") { continue }
    # LISTENING (EN) or ПРОСЛУШИВАНИЕ (RU)
    if ($line -notmatch "LISTENING|ПРОСЛУШИВАНИЕ") { continue }
    if ($line -match "\s(\d+)\s*$") {
        [void]$pids.Add([int]$Matches[1])
    }
}

foreach ($listenPid in $pids) {
    if ($listenPid -le 0) { continue }
    Write-Host "Stopping PID $listenPid (was using port $port)"
    Stop-Process -Id $listenPid -Force
}

Start-Sleep -Seconds 1
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "Starting uvicorn on http://127.0.0.1:$port"
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port $port
