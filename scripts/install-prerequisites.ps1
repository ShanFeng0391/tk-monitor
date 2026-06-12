# TikTok Monitor 环境安装脚本 (Windows)
# 以管理员身份运行 PowerShell 后执行: .\scripts\install-prerequisites.ps1

$ErrorActionPreference = "Continue"

Write-Host "=== 安装 TikTok Monitor 运行环境 ===" -ForegroundColor Cyan
Write-Host ""

# Node.js (前端构建备用)
Write-Host "[1/2] 安装 Node.js LTS..." -ForegroundColor Yellow
winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --disable-interactivity

# Docker Desktop
Write-Host "[2/2] 安装 Docker Desktop（体积较大，请耐心等待）..." -ForegroundColor Yellow
winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements --disable-interactivity

Write-Host ""
Write-Host "=== 安装命令已执行 ===" -ForegroundColor Green
Write-Host ""
Write-Host "接下来请手动完成：" -ForegroundColor Yellow
Write-Host "  1. 若提示重启，请先重启电脑" -ForegroundColor White
Write-Host "  2. 打开「Docker Desktop」，完成首次初始化" -ForegroundColor White
Write-Host "  3. 进入项目目录，运行: .\scripts\start.ps1" -ForegroundColor White
Write-Host ""
Write-Host "  cd C:\Users\Administrator\Projects\tiktok-monitor" -ForegroundColor Gray
Write-Host "  .\scripts\start.ps1" -ForegroundColor Gray
