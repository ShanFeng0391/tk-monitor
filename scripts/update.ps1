# TikTok Monitor - 上线后一键更新代码（拉取 → 依赖 → 构建 → 重启 → 验收）
# Usage:
#   .\scripts\update.ps1                    # 自动识别 production / hybrid-local
#   .\scripts\update.ps1 -BackendOnly     # 只更新后端（改 Python 时用）
#   .\scripts\update.ps1 -FrontendOnly    # 只构建前端（改 Vue 时用）
#   .\scripts\update.ps1 -Quick           # 跳过备份，更快
#   .\scripts\update.ps1 -SkipGitPull     # 不 git pull（已手动更新代码时）

param(
    [ValidateSet('auto', 'production', 'hybrid-local', 'hybrid-all')]
    [string]$Mode = 'auto',
    [switch]$SkipGitPull,
    [switch]$SkipBackup,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Quick
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if ($Quick) { $SkipBackup = $true }
if ($BackendOnly -and $FrontendOnly) {
    Write-Host '不能同时指定 -BackendOnly 与 -FrontendOnly' -ForegroundColor Red
    exit 1
}

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host ">> $Text" -ForegroundColor Cyan
}

function Resolve-UpdateMode {
    param([string]$Requested)
    if ($Requested -ne 'auto') { return $Requested }

    if (Test-Path '.env.hybrid') {
        $hybrid = Get-Content '.env.hybrid' -Raw
        if ($hybrid -match '(?m)^BEAT_ENABLED_ON_NODE\s*=\s*false\s*$') {
            return 'hybrid-local'
        }
        return 'hybrid-all'
    }
    if (Test-Path '.env.production') {
        return 'production'
    }
    Write-Host '未找到 .env.production 或 .env.hybrid，默认按 production 处理' -ForegroundColor Yellow
    return 'production'
}

function Invoke-GitPull {
    if ($SkipGitPull) {
        Write-Host '跳过 git pull（-SkipGitPull）' -ForegroundColor Gray
        return
    }
    if (-not (Test-Path '.git')) {
        Write-Host '当前目录不是 Git 仓库，跳过 git pull' -ForegroundColor Yellow
        return
    }
    $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
    if (-not $branch) { $branch = 'main' }
    Write-Host "拉取 origin/$branch ..." -ForegroundColor Gray
    git fetch origin $branch 2>&1 | Out-Host
    git pull --ff-only origin $branch 2>&1 | Out-Host
}

function Invoke-PreBackup {
    param([string]$UpdateMode)
    if ($SkipBackup) {
        Write-Host '跳过备份（-SkipBackup / -Quick）' -ForegroundColor Gray
        return
    }
    if ($UpdateMode -eq 'production') {
        & powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\backup-database.ps1" | Out-Host
        & powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\rotate-logs.ps1" | Out-Host
    } else {
        Write-Host '混合模式：SQLite 备份跳过（数据在云端 PG，备份见 backup-postgres）' -ForegroundColor Gray
    }
}

function Install-BackendDeps {
    param([string]$UpdateMode)
    Set-Location "$ProjectRoot\backend"
    if (-not (Test-Path '.venv')) {
        python -m venv .venv
    }
    $req = if ($UpdateMode -eq 'production') { 'requirements-local.txt' } else { 'requirements.txt' }
    & ".\.venv\Scripts\pip.exe" install -r $req -q
}

function Build-Frontend {
    Set-Location "$ProjectRoot\frontend"
    if (-not (Test-Path 'node_modules')) {
        npm install --silent
    }
    npm run build
    if (-not (Test-Path 'dist\index.html')) {
        throw '前端构建失败：缺少 frontend/dist/index.html'
    }
}

function Test-Health {
    param([int]$Retries = 6)
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/system/health' -TimeoutSec 12
            if ($health.status -eq 'healthy') {
                Write-Host "健康检查通过: $($health.status)" -ForegroundColor Green
                return $true
            }
        } catch {
            if ($i -eq $Retries) {
                Write-Host "健康检查失败（已重试 $Retries 次）" -ForegroundColor Red
                return $false
            }
            Start-Sleep -Seconds 3
        }
    }
    return $false
}

function Restart-Production {
    Copy-Item '.env.production' '.env' -Force
    New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\covers" | Out-Null
    New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\logs" | Out-Null

    $pidFile = "$ProjectRoot\data\server.pid"
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($oldPid) { Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue }
    }
    Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2

    $dataDir = "$ProjectRoot\data"
    $logFile = "$ProjectRoot\data\logs\server.log"
    $env:DATA_DIR = $dataDir
    Set-Location "$ProjectRoot\backend"
    $proc = Start-Process `
        -FilePath '.\.venv\Scripts\python.exe' `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000') `
        -WorkingDirectory "$ProjectRoot\backend" `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError "$ProjectRoot\data\logs\server.err.log"
    $proc.Id | Out-File $pidFile -Encoding ascii
}

function Restart-HybridLocal {
    Copy-Item '.env.hybrid' '.env' -Force
    & "$ProjectRoot\scripts\start-local-node.ps1"
}

function Restart-HybridAll {
    Copy-Item '.env.hybrid' '.env' -Force
    & "$ProjectRoot\scripts\start-hybrid.ps1"
}

$resolvedMode = Resolve-UpdateMode -Requested $Mode

Write-Host '=== TikTok Monitor 代码更新 ===' -ForegroundColor Cyan
Write-Host "模式: $resolvedMode" -ForegroundColor White
if ($BackendOnly) { Write-Host '范围: 仅后端' -ForegroundColor Gray }
elseif ($FrontendOnly) { Write-Host '范围: 仅前端' -ForegroundColor Gray }
else { Write-Host '范围: 后端 + 前端' -ForegroundColor Gray }

Write-Step '1/5 拉取最新代码'
Invoke-GitPull

Write-Step '2/5 更新前备份'
Invoke-PreBackup -UpdateMode $resolvedMode

if (-not $FrontendOnly) {
    Write-Step '3/5 安装后端依赖'
    Install-BackendDeps -UpdateMode $resolvedMode
} else {
    Write-Host '跳过 pip（-FrontendOnly）' -ForegroundColor Gray
}

if (-not $BackendOnly) {
    Write-Step '4/5 构建前端'
    Build-Frontend
} else {
    Write-Host '跳过 npm build（-BackendOnly）' -ForegroundColor Gray
}

Write-Step '5/5 重启服务'
switch ($resolvedMode) {
    'production' { Restart-Production }
    'hybrid-local' { Restart-HybridLocal }
    'hybrid-all' { Restart-HybridAll }
}

Start-Sleep -Seconds 4
$ok = Test-Health

Write-Host ''
if ($ok) {
    Write-Host '=== 更新完成 ===' -ForegroundColor Green
    Write-Host '  访问: http://127.0.0.1:8000/' -ForegroundColor White
    if ($resolvedMode -like 'hybrid*') {
        Write-Host '  轻量#2 也需更新: bash scripts/tencent-lightweight/update-code.sh' -ForegroundColor Yellow
    }
} else {
    Write-Host '=== 更新已执行，但健康检查未通过 ===' -ForegroundColor Yellow
    Write-Host '  请查看 data/logs/ 下最新日志' -ForegroundColor Gray
    exit 1
}
