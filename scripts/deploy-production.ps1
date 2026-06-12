# TikTok Monitor - 本地生产部署（单端口 8000，前后端一体）
# Usage: .\scripts\deploy-production.ps1
# 停止: .\scripts\stop-production.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "=== TikTok Monitor 生产部署 ===" -ForegroundColor Cyan

# 1. 环境配置
if (-not (Test-Path ".env.production")) {
    Write-Host "缺少 .env.production，可复制 .env.production.example" -ForegroundColor Red
    exit 1
}
Copy-Item ".env.production" ".env" -Force
New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\covers" | Out-Null
New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\logs" | Out-Null

$envContent = Get-Content ".env" -Raw
if ($envContent -match "your-api-key-here|your-ark-api-key|请替换|请设置强密码") {
    Write-Host "警告: .env.production 仍含占位符，请检查密钥与 ADMIN_PASSWORD" -ForegroundColor Yellow
}
if ($envContent -match "prod-change-me|change-me") {
    Write-Host "警告: SECRET_KEY / JWT_SECRET_KEY 仍为默认值" -ForegroundColor Yellow
}
if ($envContent -notmatch "SCRAPE_PROXY_URL=\s*\S+" -or $envContent -match "SCRAPE_PROXY_URL=\s*$") {
    Write-Host "提示: SCRAPE_PROXY_URL 未配置（代理池可用时可暂缓，见 DEPLOY.md）" -ForegroundColor Yellow
}

# 1b. 部署前备份与日志轮转
Write-Host "备份数据库..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\backup-database.ps1" | Out-Host
powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\rotate-logs.ps1" | Out-Host

# 2. 后端依赖
Write-Host "安装后端依赖..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\pip.exe" install -r requirements-local.txt -q

# 3. 前端构建
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

# 4. 停止旧进程
$pidFile = "$ProjectRoot\data\server.pid"
if (Test-Path $pidFile) {
    $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    }
}
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# 5. 启动后端
Write-Host "启动服务 http://0.0.0.0:8000 ..." -ForegroundColor Cyan
Set-Location "$ProjectRoot\backend"
$dataDir = "$ProjectRoot\data"
$logFile = "$ProjectRoot\data\logs\server.log"
$env:DATA_DIR = $dataDir

$proc = Start-Process `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") `
    -WorkingDirectory "$ProjectRoot\backend" `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError "$ProjectRoot\data\logs\server.err.log"
$proc.Id | Out-File $pidFile -Encoding ascii

Start-Sleep -Seconds 5

# 6. 健康检查
$healthOk = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/system/health" -TimeoutSec 20
    Write-Host "服务状态: $($health.status)" -ForegroundColor Green
    $healthOk = $health.status -eq 'healthy'
} catch {
    Write-Host "服务启动中或失败，请查看日志: $logFile" -ForegroundColor Yellow
    Get-Content $logFile -Tail 20 -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== 部署完成 ===" -ForegroundColor Green
Write-Host "  访问地址:  http://localhost:8000/" -ForegroundColor White
Write-Host "  健康检查:  http://127.0.0.1:8000/api/v1/system/health" -ForegroundColor Gray
Write-Host "  管理员:    见 .env.production 中 ADMIN_USERNAME / ADMIN_PASSWORD" -ForegroundColor White
Write-Host "  日志:      $logFile" -ForegroundColor Gray
Write-Host "  数据库备份: data\backups\" -ForegroundColor Gray
Write-Host "  停止:      .\scripts\stop-production.ps1" -ForegroundColor Gray
Write-Host "  守护进程:  .\scripts\watch-production.ps1" -ForegroundColor Gray
if ($healthOk) {
    Write-Host "  API 文档:  生产环境默认关闭（ENABLE_API_DOCS=true 可开启）" -ForegroundColor Gray
}
Write-Host ""
Write-Host "上线前建议:" -ForegroundColor Cyan
Write-Host "  1. 超级管理员 → 配置访问密钥，限制随意注册" -ForegroundColor Gray
Write-Host "  2. 公网部署请加 HTTPS 反向代理，并设置 CORS_ORIGINS" -ForegroundColor Gray
Write-Host "  3. 完成冒烟测试（采集 / 标注 / 收藏 / 仪表盘）" -ForegroundColor Gray
