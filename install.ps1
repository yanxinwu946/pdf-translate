# Install this skill into coding-agent skill folders on Windows.
$ErrorActionPreference = 'Stop'
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$HomeDir = $env:USERPROFILE

$Roots = @(
    Join-Path $HomeDir '.claude\skills'
    Join-Path $HomeDir '.grok\skills'
    Join-Path $HomeDir '.agents\skills'
    Join-Path $HomeDir '.codex\skills'
    Join-Path $HomeDir '.cursor\skills'
    Join-Path $HomeDir '.copilot\skills'
    Join-Path $HomeDir '.gemini\skills'
    Join-Path $HomeDir '.config\opencode\skills'
    Join-Path $HomeDir '.factory\skills'
    Join-Path $HomeDir '.codeium\windsurf\skills'
    Join-Path $HomeDir '.pi\agent\skills'
    Join-Path $HomeDir '.openclaw\skills'
    Join-Path $HomeDir '.agent\skills'
    Join-Path $HomeDir '.hermes\skills'
    Join-Path $HomeDir '.windsurf\skills'
    Join-Path $HomeDir '.continue\skills'
    Join-Path $HomeDir '.qwen\skills'
    Join-Path $HomeDir '.trae\skills'
    Join-Path $HomeDir '.lingma\skills'
    Join-Path $HomeDir '.opencode\skills'
)

function Same-Path([string]$A, [string]$B) {
    $na = [IO.Path]::GetFullPath($A).TrimEnd('\', '/')
    $nb = [IO.Path]::GetFullPath($B).TrimEnd('\', '/')
    return $na.Equals($nb, [StringComparison]::OrdinalIgnoreCase)
}

function Install-One([string]$Root) {
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    $Dest = Join-Path $Root 'pdf-translate'
    if (Test-Path $Dest) {
        $item = Get-Item $Dest
        $targets = @($item.Target)
        $already = $item.LinkType -in @('Junction', 'SymbolicLink') -and (
            $targets | Where-Object { $_ -and (Same-Path $_ $Src) }
        )
        if ($already) {
            Write-Host "[skip] already linked  $Dest"
            return
        }
        Write-Host "[replace] $Dest"
        Remove-Item -LiteralPath $Dest -Recurse -Force
    }
    try {
        New-Item -ItemType Junction -Path $Dest -Target $Src | Out-Null
        Write-Host "[link] $Dest -> $Src"
    } catch {
        Copy-Item -Recurse -Force $Src $Dest
        Write-Host "[copy] $Dest"
    }
}

Write-Host "Installing pdf-translate from $Src"
foreach ($root in $Roots) {
    $parent = Split-Path -Parent $root
    $always = $root -match '\\(\.agents|\.claude|\.grok)\\skills$'
    if ($always -or (Test-Path $parent)) {
        Install-One $root
    }
}
New-Item -ItemType Directory -Force -Path (Join-Path $HomeDir '.agents\skills') | Out-Null
Install-One (Join-Path $HomeDir '.agents\skills')

Write-Host ''
Write-Host 'Done. In your agent, say: 翻译这篇论文'
