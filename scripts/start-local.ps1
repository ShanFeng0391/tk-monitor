# TikTok Monitor - local dev mode (no Docker)
# Usage: .\scripts\start-local.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "=== TikTok Monitor Local Mode ===" -ForegroundColor Cyan

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Installing Python 3.11..." -ForegroundColor Yellow
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements --disable-interactivity
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# Node.js
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "Installing Node.js LTS..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --disable-interactivity
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

node --version
npm --version

# Config
Copy-Item ".env.local" ".env" -Force
New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\covers" | Out-Null
Write-Host "Checking sing-box (vmess/vless gateway)..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\install-singbox.ps1" | Out-Null
Write-Host "LOCAL_MODE enabled (SQLite + APScheduler)" -ForegroundColor Green

# Backend deps
Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\pip.exe" install -r requirements-local.txt -q

# Frontend deps
Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\frontend"
if (-not (Test-Path "node_modules")) {
    npm install
}

# Start backend
Write-Host "Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$dataDir = "$ProjectRoot\data"
$backendCmd = "Set-Location '$ProjectRoot\backend'; `$env:DATA_DIR='$dataDir'; `$env:LOCAL_MODE='true'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

Start-Sleep -Seconds 4

# Start frontend
Write-Host "Starting frontend on http://localhost:5173 ..." -ForegroundColor Cyan
$frontendCmd = "Set-Location '$ProjectRoot\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Start-Sleep -Seconds 6

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/system/health" -TimeoutSec 15
    Write-Host "Backend status: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "Backend still starting, wait a few seconds..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Local mode started ===" -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:5173/" -ForegroundColor White
Write-Host "  API docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Login:     admin / admin123" -ForegroundColor White
Write-Host ""
Write-Host "Close the two PowerShell windows to stop services." -ForegroundColor Gray
