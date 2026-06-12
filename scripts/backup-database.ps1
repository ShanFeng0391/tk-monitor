# 备份 SQLite 数据库（生产 LOCAL_MODE）
# Usage: .\scripts\backup-database.ps1 [-Keep 14]

param(
    [int]$Keep = 14
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DataDir = Join-Path $ProjectRoot 'data'
$DbFile = Join-Path $DataDir 'tiktok_monitor.db'
$BackupDir = Join-Path $DataDir 'backups'

if (-not (Test-Path $DbFile)) {
    Write-Host "未找到数据库: $DbFile" -ForegroundColor Yellow
    exit 0
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dest = Join-Path $BackupDir "tiktok_monitor-$stamp.db"
Copy-Item $DbFile $dest -Force
Write-Host "已备份: $dest" -ForegroundColor Green

Get-ChildItem $BackupDir -Filter 'tiktok_monitor-*.db' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "已清理旧备份: $($_.Name)" -ForegroundColor Gray
    }
