# 生产服务健康守护：8000 无响应时自动重新部署
# Usage: .\scripts\watch-production.ps1 [-IntervalSeconds 60]
# 建议：Windows 任务计划程序每 5 分钟运行一次，或长期开一个 PowerShell 窗口

param(
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DeployScript = Join-Path $ProjectRoot 'scripts\deploy-production.ps1'
$HealthUrl = 'http://127.0.0.1:8000/api/v1/system/health'

function Test-BackendHealthy {
    try {
        $resp = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 8
        return $resp.status -eq 'healthy'
    } catch {
        return $false
    }
}

Write-Host "守护进程启动，每 ${IntervalSeconds}s 检查 $HealthUrl" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止" -ForegroundColor Gray

while ($true) {
    if (Test-BackendHealthy) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK" -ForegroundColor DarkGreen
    } else {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 服务异常，正在重新部署..." -ForegroundColor Yellow
        & powershell -ExecutionPolicy Bypass -File $DeployScript
    }
    Start-Sleep -Seconds $IntervalSeconds
}
