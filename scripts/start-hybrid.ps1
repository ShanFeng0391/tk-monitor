# TikTok Monitor - 混合部署（兼容旧用法；双节点请用 start-local-node.ps1 + 轻量 start-compute-node.sh）
# Usage: .\scripts\start-hybrid.ps1
# 停止: .\scripts\stop-hybrid.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "=== TikTok Monitor 混合部署 ===" -ForegroundColor Cyan

if (-not (Test-Path ".env.hybrid")) {
    Write-Host "缺少 .env.hybrid，请从 .env.hybrid.example 复制并填写云 RDS/Redis/OSS 连接信息" -ForegroundColor Red
    exit 1
}
Copy-Item ".env.hybrid" ".env" -Force

$envContent = Get-Content ".env" -Raw
if ($envContent -match "LOCAL_MODE\s*=\s*true") {
    Write-Host "错误: 混合部署必须 LOCAL_MODE=false" -ForegroundColor Red
    exit 1
}
if ($envContent -match "请填写|your-ark-api-key|请替换|请设置强密码|rm-xxx|r-xxx") {
    Write-Host "警告: .env.hybrid 仍含占位符，请先创建云资源并填写连接串" -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\hybrid" | Out-Null

# 依赖（完整栈：postgres / redis / celery）
Write-Host "安装后端依赖..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\pip.exe" install -r requirements.txt -q

# 前端
Write-Host "构建前端..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\frontend"
if (-not (Test-Path "node_modules")) {
    npm install --silent
}
npm run build
if (-not (Test-Path "dist\index.html")) {
    Write-Host "前端构建失败" -ForegroundColor Red
    exit 1
}

# 停止旧进程
& "$ProjectRoot\scripts\stop-hybrid.ps1" 2>$null

Set-Location "$ProjectRoot\backend"
$logDir = "$ProjectRoot\data\logs"
$pidDir = "$ProjectRoot\data\hybrid"
$python = ".\.venv\Scripts\python.exe"
$celery = ".\.venv\Scripts\celery.exe"

Write-Host "启动 API (uvicorn :8000)..." -ForegroundColor Cyan
$apiProc = Start-Process -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory "$ProjectRoot\backend" `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$logDir\hybrid-api.log" `
    -RedirectStandardError "$logDir\hybrid-api.err.log"
$apiProc.Id | Out-File "$pidDir\api.pid" -Encoding ascii

$beatEnabled = $true
if ($envContent -match "BEAT_ENABLED_ON_NODE\s*=\s*false") {
    $beatEnabled = $false
}

$concurrency = 24
if ($envContent -match "CELERY_WORKER_CONCURRENCY\s*=\s*(\d+)") {
    $concurrency = [int]$Matches[1]
}

$workerPrefix = "local"
if ($envContent -match "CELERY_WORKER_NODE_PREFIX\s*=\s*(\S+)") {
    $workerPrefix = $Matches[1].Trim()
}

if ($beatEnabled) {
    Write-Host "启动 Beat (APScheduler)..." -ForegroundColor Cyan
    $beatProc = Start-Process -FilePath $python `
        -ArgumentList @("-m", "app.tasks.beat_runner") `
        -WorkingDirectory "$ProjectRoot\backend" `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$logDir\hybrid-beat.log" `
        -RedirectStandardError "$logDir\hybrid-beat.err.log"
    $beatProc.Id | Out-File "$pidDir\beat.pid" -Encoding ascii
} else {
    Write-Host "跳过 Beat（BEAT_ENABLED_ON_NODE=false，请确保轻量#2 已启动 Beat）" -ForegroundColor Yellow
    if (Test-Path "$pidDir\beat.pid") { Remove-Item "$pidDir\beat.pid" -Force }
}

Write-Host "启动 Celery Worker (并发 $concurrency, 节点前缀 $workerPrefix)..." -ForegroundColor Cyan
$workerProc = Start-Process -FilePath $celery `
    -ArgumentList @(
        "-A", "app.tasks.celery_app",
        "worker",
        "-Q", "scrape",
        "--pool=threads",
        "-c", "$concurrency",
        "--loglevel=info",
        "-n", "${workerPrefix}@%h"
    ) `
    -WorkingDirectory "$ProjectRoot\backend" `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput "$logDir\hybrid-worker.log" `
    -RedirectStandardError "$logDir\hybrid-worker.err.log"
$workerProc.Id | Out-File "$pidDir\worker.pid" -Encoding ascii

Start-Sleep -Seconds 8

$healthOk = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/system/health" -TimeoutSec 25
    Write-Host "健康检查: status=$($health.status) db=$($health.database) redis=$($health.redis) celery=$($health.celery)" -ForegroundColor Green
    $healthOk = $health.status -eq "healthy"
} catch {
    Write-Host "API 尚未就绪，请查看 $logDir\hybrid-api.err.log" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 混合部署已启动 ===" -ForegroundColor Green
Write-Host "  直连 API:  http://127.0.0.1:8000/" -ForegroundColor White
Write-Host "  健康检查:  http://127.0.0.1:8000/api/v1/system/health" -ForegroundColor Gray
Write-Host "  Worker:    并发 $concurrency (队列 scrape)" -ForegroundColor Gray
Write-Host "  日志目录:  $logDir\hybrid-*.log" -ForegroundColor Gray
Write-Host "  停止:      .\scripts\stop-hybrid.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "公网访问请配置 Nginx 反代，示例: nginx\nginx.hybrid.conf" -ForegroundColor Cyan
if (-not $healthOk) {
    Write-Host "提示: celery=no_workers 表示 Worker 尚未连上 Redis，稍等或查 hybrid-worker.err.log" -ForegroundColor Yellow
}
