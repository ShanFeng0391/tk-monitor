param(
    [Parameter(Mandatory = $false)]
    [string]$Link
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $projectRoot 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$script = Join-Path $backend 'scripts\test_proxy_gateway.py'

if (-not $Link) {
    $Link = Get-Clipboard -Raw
}
$Link = ($Link -or '').Trim()
if (-not $Link) {
    Write-Host 'Usage: .\scripts\add-proxy-link.ps1 -Link "vmess://..."'
    Write-Host 'Or copy a link to clipboard and run without -Link.'
    exit 1
}

Copy-Item (Join-Path $projectRoot '.env.local') (Join-Path $projectRoot '.env') -Force
$env:LOCAL_MODE = 'true'
$env:DATA_DIR = Join-Path $projectRoot 'data'

powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot 'scripts\install-singbox.ps1') | Out-Null
& $python $script --add $Link --check
