# 在云 RDS 上初始化表结构（需已填写 .env.hybrid 并复制为 .env）

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if (-not (Test-Path ".env.hybrid")) {
    Write-Host "缺少 .env.hybrid" -ForegroundColor Red
    exit 1
}
Copy-Item ".env.hybrid" ".env" -Force

$envContent = Get-Content ".env" -Raw
if ($envContent -match "LOCAL_MODE\s*=\s*true") {
    Write-Host "init-hybrid-db 需要 LOCAL_MODE=false" -ForegroundColor Red
    exit 1
}

Set-Location "$ProjectRoot\backend"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\pip.exe" install -r requirements.txt -q

Write-Host "连接云 PostgreSQL 并执行迁移..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -c @"
import asyncio
from app.database_migrate import run_migrations
asyncio.run(run_migrations())
print('数据库迁移完成')
"@

Write-Host "完成。可执行 .\scripts\start-hybrid.ps1 启动服务" -ForegroundColor Green
