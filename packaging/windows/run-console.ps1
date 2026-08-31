param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-VersionAtLeast([string]$Version, [int]$Major, [int]$Minor, [int]$Patch) {
    $clean = $Version.Trim().TrimStart('v','V')
    $match = [regex]::Match($clean, '^(\d+)\.(\d+)(?:\.(\d+))?')
    if (-not $match.Success) { return $false }
    $actualPatch = 0
    if ($match.Groups[3].Success) { $actualPatch = [int]$match.Groups[3].Value }
    $actual = [Version]::new([int]$match.Groups[1].Value, [int]$match.Groups[2].Value, $actualPatch)
    $required = [Version]::new($Major, $Minor, $Patch)
    return $actual -ge $required
}

function Resolve-BundledNode {
    $candidate = Join-Path $PSScriptRoot '..\host-runtime\node\node.exe'
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Bundled Node.js runtime is missing from the immutable Plasma release: $candidate"
    }
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    $versionOutput = & $resolved --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Bundled Node.js runtime failed version probe: $resolved"
    }
    $version = ([string]$versionOutput).Trim()
    if (-not (Test-VersionAtLeast $version 22 13 0)) {
        throw "Bundled Node.js runtime is below the supported minimum 22.13: $version"
    }
    return $resolved
}

$node = Resolve-BundledNode
Write-Output "Plasma Console bundled Node.js runtime: $node"
if ($PreflightOnly) { exit 0 }

$programDataRoot = Join-Path $env:ProgramData 'Plasma'
$aliasPath = Join-Path $programDataRoot 'config\selected-ppu-alias'
$alias = ''
if (Test-Path -LiteralPath $aliasPath -PathType Leaf) {
    $aliasContent = Get-Content -Raw -LiteralPath $aliasPath
    if ($null -ne $aliasContent) { $alias = ([string]$aliasContent).Trim() }
}
$env:HOST = '127.0.0.1'
$env:PORT = '18000'
$env:PLASMA_MANAGER_API_URL = 'http://127.0.0.1:18180'
$env:PLASMA_MANAGER_PPU_ALIAS = $alias
$server = Join-Path $PSScriptRoot '..\runtime\console\server.js'
& $node $server
exit $LASTEXITCODE
