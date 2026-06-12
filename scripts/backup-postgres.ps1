# PostgreSQL 备份到本地 + OSS（混合 / 自建 PG）
# Usage: .\scripts\backup-postgres.ps1
# 依赖：本机已安装 pg_dump 并加入 PATH

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if (Test-Path ".env.hybrid") {
    Copy-Item ".env.hybrid" ".env" -Force
} elseif (-not (Test-Path ".env")) {
    Write-Host "缺少 .env 或 .env.hybrid" -ForegroundColor Red
    exit 1
}

Set-Location "$ProjectRoot\backend"
if (-not (Test-Path ".venv")) {
    Write-Host "请先安装后端依赖（start-hybrid.ps1 或 pip install -r requirements.txt）" -ForegroundColor Red
    exit 1
}

& ".\.venv\Scripts\python.exe" -m app.services.postgres_backup
exit $LASTEXITCODE
