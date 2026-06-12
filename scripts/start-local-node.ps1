# TikTok Monitor - 本地计算节点（API + Worker，不跑 Beat）
# Beat 仅在轻量 #2 运行
# Usage: .\scripts\start-local-node.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if (-not (Test-Path ".env.hybrid")) {
    Write-Host "缺少 .env.hybrid" -ForegroundColor Red
    exit 1
}
Copy-Item ".env.hybrid" ".env" -Force

$envLines = @(
    "COMPUTE_NODE_ID=local",
    "COMPUTE_NODE_LABEL=本地电脑",
    "BEAT_ENABLED_ON_NODE=false",
    "CELERY_WORKER_NODE_PREFIX=local",
    "POSTGRES_BACKUP_ENABLED=false"
)
$raw = Get-Content ".env" -Raw
foreach ($line in $envLines) {
    $key = ($line -split "=")[0]
    if ($raw -notmatch "(?m)^$key=") {
        Add-Content ".env" $line
    }
}

& "$ProjectRoot\scripts\stop-hybrid.ps1" 2>$null

Set-Location "$ProjectRoot\backend"
$logDir = "$ProjectRoot\data\logs"
$pidDir = "$ProjectRoot\data\hybrid"
$python = ".\.venv\Scripts\python.exe"
$celery = ".\.venv\Scripts\celery.exe"
$envContent = Get-Content "$ProjectRoot\.env" -Raw

$concurrency = 24
if ($envContent -match "CELERY_WORKER_CONCURRENCY\s*=\s*(\d+)") {
    $concurrency = [int]$Matches[1]
}

Write-Host "启动本地 API..." -ForegroundColor Cyan
$apiProc = Start-Process -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory "$ProjectRoot\backend" -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$logDir\local-api.log" `
    -RedirectStandardError "$logDir\local-api.err.log"
$apiProc.Id | Out-File "$pidDir\api.pid" -Encoding ascii

Write-Host "本地不启动 Beat（调度在轻量#2）" -ForegroundColor Yellow

Write-Host "启动本地 Worker x$concurrency ..." -ForegroundColor Cyan
$workerProc = Start-Process -FilePath $celery `
    -ArgumentList @(
        "-A", "app.tasks.celery_app", "worker", "-Q", "scrape",
        "--pool=threads", "-c", "$concurrency", "--loglevel=info", "-n", "local@%h"
    ) `
    -WorkingDirectory "$ProjectRoot\backend" -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$logDir\local-worker.log" `
    -RedirectStandardError "$logDir\local-worker.err.log"
$workerProc.Id | Out-File "$pidDir\worker.pid" -Encoding ascii

Write-Host "=== 本地计算节点已启动 ===" -ForegroundColor Green
Write-Host "  API:    http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  Worker: local@%h x$concurrency" -ForegroundColor Gray
Write-Host "  监控:   管理后台 -> 集群监控" -ForegroundColor Cyan
