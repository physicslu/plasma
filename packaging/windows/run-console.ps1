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

function Resolve-Node {
    $candidates = @("$env:ProgramFiles\nodejs\node.exe")
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $versionOutput = & $candidate --version 2>&1
        if ($LASTEXITCODE -ne 0) { continue }
        $version = ([string]$versionOutput).Trim()
        if (Test-VersionAtLeast $version 22 13 0) { return $candidate }
    }
    throw 'Node.js >= 22.13 was not found in the system-wide Program Files location or PATH.'
}

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
$node = Resolve-Node
$server = Join-Path $PSScriptRoot '..\runtime\console\server.js'
& $node $server
exit $LASTEXITCODE
