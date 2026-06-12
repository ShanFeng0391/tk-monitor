# Verify TikTok Monitor backend (uses project venv, not system Python)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $projectRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$pip = Join-Path $backend '.venv\Scripts\pip.exe'

if (-not (Test-Path $python)) {
    Write-Host 'Creating backend virtual environment...' -ForegroundColor Yellow
    Set-Location $backend
    python -m venv .venv
}

Write-Host 'Installing backend dependencies (requirements-local.txt)...' -ForegroundColor Cyan
& $pip install -r (Join-Path $backend 'requirements-local.txt') -q

Write-Host 'Checking imports...' -ForegroundColor Cyan
Push-Location $backend
& $python -c "import app.main; print('import ok')"
Pop-Location

Copy-Item (Join-Path $projectRoot '.env.local') (Join-Path $projectRoot '.env') -Force -ErrorAction SilentlyContinue

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/health' -TimeoutSec 5
    Write-Host "Backend running: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host 'Backend not running. Start with: .\scripts\restart-backend.ps1' -ForegroundColor Yellow
}

Write-Host 'Verify complete.' -ForegroundColor Green
