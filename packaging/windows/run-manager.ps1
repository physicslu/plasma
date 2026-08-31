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

function Resolve-BundledPython {
    $candidate = Join-Path $PSScriptRoot '..\host-runtime\python\python.exe'
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Bundled Python runtime is missing from the immutable Plasma release: $candidate"
    }
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    $versionOutput = & $resolved --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Bundled Python runtime failed version probe: $resolved"
    }
    $version = ([string]$versionOutput).Trim() -replace '^Python\s+', ''
    if (-not (Test-VersionAtLeast $version 3 11 0)) {
        throw "Bundled Python runtime is below the supported minimum 3.11: $version"
    }
    return $resolved
}

$python = Resolve-BundledPython
Write-Output "Plasma Manager bundled Python runtime: $python"
if ($PreflightOnly) { exit 0 }

$programDataRoot = Join-Path $env:ProgramData 'Plasma'
$configPath = Join-Path $programDataRoot 'config\manager.yaml'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Manager config is missing: $configPath"
}
$runtime = Join-Path $PSScriptRoot '..\runtime\manager\manager.pyz'
& $python $runtime --config $configPath
exit $LASTEXITCODE
