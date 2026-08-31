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

function Get-MachinePathCandidates([string]$ExecutableName) {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    if ([string]::IsNullOrWhiteSpace($machinePath)) { return }
    foreach ($entry in $machinePath -split ';') {
        if ([string]::IsNullOrWhiteSpace($entry)) { continue }
        $directory = [Environment]::ExpandEnvironmentVariables($entry.Trim().Trim('"'))
        if ([string]::IsNullOrWhiteSpace($directory)) { continue }
        Join-Path $directory $ExecutableName
    }
}

function Resolve-Node {
    $candidates = @("$env:ProgramFiles\nodejs\node.exe")
    $candidates += @(Get-MachinePathCandidates 'node.exe')
    foreach ($rawCandidate in $candidates | Select-Object -Unique) {
        if ($null -eq $rawCandidate) { continue }
        $candidate = ([string]$rawCandidate).Trim().Trim('"')
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $versionOutput = & $candidate --version 2>&1
        if ($LASTEXITCODE -ne 0) { continue }
        $version = ([string]$versionOutput).Trim()
        if (Test-VersionAtLeast $version 22 13 0) { return $candidate }
    }
    throw 'Node.js >= 22.13 was not found in the system-wide Program Files location or machine PATH. Per-user-only Node.js installations are not supported by the LocalSystem service.'
}

$node = Resolve-Node
Write-Output "Plasma Console Node.js runtime: $node"
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
