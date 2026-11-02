param([string]$Root = (Join-Path $env:USERPROFILE '.codex\skills'))
$ErrorActionPreference = 'Stop'
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
$Destination = Join-Path $Root 'pdf-translate'
if (Get-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue) {
    Write-Host "Existing installation preserved: $Destination"
    exit 0
}
New-Item -ItemType Directory -Force -Path $Root | Out-Null
New-Item -ItemType Junction -Path $Destination -Target $Source | Out-Null
Write-Host "Installed: $Destination"
