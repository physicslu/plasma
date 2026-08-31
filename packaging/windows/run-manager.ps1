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

function Resolve-Python {
    $candidates = @(
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $versionOutput = & $candidate --version 2>&1
        if ($LASTEXITCODE -ne 0) { continue }
        $version = ([string]$versionOutput).Trim() -replace '^Python\s+', ''
        if (Test-VersionAtLeast $version 3 11 0) { return $candidate }
    }
    throw 'Python >= 3.11 was not found in supported system-wide locations or PATH.'
}

$programDataRoot = Join-Path $env:ProgramData 'Plasma'
$configPath = Join-Path $programDataRoot 'config\manager.yaml'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Manager config is missing: $configPath"
}
$python = Resolve-Python
$runtime = Join-Path $PSScriptRoot '..\runtime\manager\manager.pyz'
& $python $runtime --config $configPath
exit $LASTEXITCODE
