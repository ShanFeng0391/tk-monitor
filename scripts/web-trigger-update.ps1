# Web 后台触发的更新包装（由 API 以 detached 方式启动，勿手动双击）
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$SkipGitPull,
    [switch]$Quick
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StatusFile = Join-Path $ProjectRoot 'data\deploy-update-status.json'
$LogFile = Join-Path $ProjectRoot 'data\logs\deploy-update.log'

function Set-DeployStatus {
    param([string]$State, [string]$Message)
    $payload = @{
        state = $State
        message = $Message
        finished_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.ffffff')
    }
    $existing = @{}
    if (Test-Path $StatusFile) {
        try { $existing = Get-Content $StatusFile -Raw | ConvertFrom-Json -AsHashtable } catch {}
    }
    if ($existing['started_at']) { $payload['started_at'] = $existing['started_at'] }
    $payload | ConvertTo-Json | Set-Content $StatusFile -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
"--- web update $(Get-Date -Format o) ---" | Add-Content $LogFile -Encoding UTF8

try {
    $updateArgs = @()
    if ($BackendOnly) { $updateArgs += '-BackendOnly' }
    if ($FrontendOnly) { $updateArgs += '-FrontendOnly' }
    if ($SkipGitPull) { $updateArgs += '-SkipGitPull' }
    if ($Quick) { $updateArgs += '-Quick' }

    & powershell -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\update.ps1" @updateArgs 2>&1 |
        Tee-Object -FilePath $LogFile -Append | Out-Null

    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Set-DeployStatus -State 'failed' -Message "update.ps1 退出码 $LASTEXITCODE"
        exit $LASTEXITCODE
    }
    Set-DeployStatus -State 'success' -Message '更新完成，服务已重启'
} catch {
    Set-DeployStatus -State 'failed' -Message $_.Exception.Message
    $_ | Add-Content $LogFile -Encoding UTF8
    exit 1
}
