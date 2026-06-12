# 日志轮转：server.log / server.err.log 超过阈值则归档
# Usage: .\scripts\rotate-logs.ps1 [-MaxSizeMB 10]

param(
    [int]$MaxSizeMB = 10
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir = Join-Path $ProjectRoot 'data\logs'
$ArchiveDir = Join-Path $LogDir 'archive'
$MaxBytes = $MaxSizeMB * 1MB

if (-not (Test-Path $LogDir)) {
    exit 0
}

New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null

foreach ($name in @('server.log', 'server.err.log')) {
    $path = Join-Path $LogDir $name
    if (-not (Test-Path $path)) { continue }
    $size = (Get-Item $path).Length
    if ($size -lt $MaxBytes) { continue }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $archive = Join-Path $ArchiveDir "$($name -replace '\.','-$stamp.')"
    Move-Item $path $archive -Force
    New-Item -ItemType File -Path $path -Force | Out-Null
    Write-Host "已轮转 $name -> $(Split-Path $ArchiveDir -Leaf)\$(Split-Path $archive -Leaf)" -ForegroundColor Green
}

Get-ChildItem $ArchiveDir -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    ForEach-Object { Remove-Item $_.FullName -Force }
