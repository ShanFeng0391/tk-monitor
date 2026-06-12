# Restart TikTok Monitor backend (kills orphaned uvicorn workers on Windows)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $projectRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$dataDir = Join-Path $projectRoot 'data'

Copy-Item (Join-Path $projectRoot '.env.local') (Join-Path $projectRoot '.env') -Force

$spawnWorkers = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*multiprocessing-fork*' -and $_.CommandLine -like '*spawn_main*' }

foreach ($proc in $spawnWorkers) {
    if ($proc.CommandLine -match 'parent_pid=(\d+)') {
        $parentId = [int]$Matches[1]
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
        if ($parent -and $parent.CommandLine -like '*uvicorn*app.main*') {
            Write-Host "Stopping worker PID $($proc.ProcessId) (parent $parentId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*uvicorn*app.main*' -and $_.CommandLine -like '*tiktok-monitor*' } |
    ForEach-Object {
        Write-Host "Stopping uvicorn PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 2

$env:DATA_DIR = $dataDir
$env:LOCAL_MODE = 'true'
Write-Host 'Starting backend on http://127.0.0.1:8000 ...'
Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $backend `
    -WindowStyle Normal

Start-Sleep -Seconds 3
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/health' -TimeoutSec 10
    Write-Host "Backend: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host 'Backend still starting...' -ForegroundColor Yellow
}
