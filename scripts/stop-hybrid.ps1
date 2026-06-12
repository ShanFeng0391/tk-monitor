# 停止混合部署进程（API / Beat / Worker）

$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pidDir = "$ProjectRoot\data\hybrid"

foreach ($name in @("api", "beat", "worker")) {
    $file = Join-Path $pidDir "$name.pid"
    if (Test-Path $file) {
        $pid = Get-Content $file -ErrorAction SilentlyContinue
        if ($pid) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $file -Force -ErrorAction SilentlyContinue
    }
}

Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "混合部署进程已停止" -ForegroundColor Green
