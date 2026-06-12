# Install sing-box into project data/bin (Windows amd64)
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$binDir = Join-Path $projectRoot 'data\bin'
$target = Join-Path $binDir 'sing-box.exe'
$version = '1.12.0'
$zipName = "sing-box-$version-windows-amd64.zip"
$url = "https://github.com/SagerNet/sing-box/releases/download/v$version/$zipName"
$tempZip = Join-Path $env:TEMP $zipName
$tempExtract = Join-Path $env:TEMP "sing-box-$version"

Write-Host "Target: $target"

if (Test-Path $target) {
    Write-Host "sing-box already installed."
    & $target version
    exit 0
}

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Write-Host "Downloading $url ..."
Invoke-WebRequest -Uri $url -OutFile $tempZip -UseBasicParsing
if (Test-Path $tempExtract) { Remove-Item $tempExtract -Recurse -Force }
Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force
$exe = Get-ChildItem -Recurse $tempExtract -Filter 'sing-box.exe' | Select-Object -First 1
if (-not $exe) { throw 'sing-box.exe not found after extract' }
Copy-Item $exe.FullName $target -Force
Write-Host 'Installed:'
& $target version
