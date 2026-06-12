# TikTok Monitor 启动脚本 (Windows)
# 用法: 右键「使用 PowerShell 运行」或在项目目录执行 .\scripts\start.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

Write-Host "=== TikTok Monitor 启动检查 ===" -ForegroundColor Cyan

# 1. 检查 Docker
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    $dockerPath = "${env:ProgramFiles}\Docker\Docker\resources\bin\docker.exe"
    if (Test-Path $dockerPath) {
        $env:PATH = "${env:ProgramFiles}\Docker\Docker\resources\bin;$env:PATH"
    }
}

try {
    $dockerVersion = docker --version 2>&1
    Write-Host "[OK] Docker: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] 未检测到 Docker。" -ForegroundColor Red
    Write-Host ""
    Write-Host "请先安装 Docker Desktop，然后重新运行本脚本：" -ForegroundColor Yellow
    Write-Host "  winget install Docker.DockerDesktop" -ForegroundColor White
    Write-Host ""
    Write-Host "安装后：启动 Docker Desktop，等托盘图标变绿，再运行本脚本。" -ForegroundColor Yellow
    exit 1
}

# 2. 检查 Docker 守护进程
try {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "daemon not running" }
    Write-Host "[OK] Docker 守护进程运行中" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Docker Desktop 未启动。" -ForegroundColor Red
    Write-Host "请打开「Docker Desktop」，等待启动完成后再运行本脚本。" -ForegroundColor Yellow
    Start-Process "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe" -ErrorAction SilentlyContinue
    exit 1
}

# 3. 检查 .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[OK] 已从 .env.example 创建 .env" -ForegroundColor Green
}

# 4. 启动服务
Write-Host ""
Write-Host "正在启动 docker compose（首次可能需要几分钟构建镜像）..." -ForegroundColor Cyan
docker compose up -d --build

if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] docker compose 启动失败，请查看上方错误信息。" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "等待服务就绪..." -ForegroundColor Cyan
Start-Sleep -Seconds 8

# 5. 健康检查
try {
    $health = Invoke-RestMethod -Uri "http://localhost/api/v1/system/health" -TimeoutSec 10
    Write-Host "[OK] API 健康检查: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "[WARN] API 尚未就绪，可能仍在启动中。稍等 30 秒后访问 http://localhost/" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 启动完成 ===" -ForegroundColor Green
Write-Host "  前端:     http://localhost/" -ForegroundColor White
Write-Host "  API 文档: http://localhost/api/docs" -ForegroundColor White
Write-Host "  管理员:   admin / admin123" -ForegroundColor White
Write-Host ""
Write-Host "查看日志: docker compose logs -f" -ForegroundColor Gray
Write-Host "停止服务: docker compose down" -ForegroundColor Gray

docker compose ps
