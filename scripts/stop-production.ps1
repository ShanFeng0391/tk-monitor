$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pidFile = "$ProjectRoot\data\server.pid"
if (Test-Path $pidFile) {
    $procId = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($procId) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped server PID $procId" -ForegroundColor Green
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped process on port 8000 (PID $($_.OwningProcess))" -ForegroundColor Green
    }
if (-not (Test-Path $pidFile)) {
    Write-Host "Server stopped" -ForegroundColor Green
}
