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

function Get-MachineRegisteredPythonCandidates {
    $roots = @(
        'HKLM:\SOFTWARE\Python\PythonCore',
        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        $versionKeys = @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | Sort-Object PSChildName -Descending)
        foreach ($versionKey in $versionKeys) {
            $installPathKey = Join-Path $versionKey.PSPath 'InstallPath'
            if (-not (Test-Path -LiteralPath $installPathKey -PathType Container)) { continue }
            $installPath = Get-Item -LiteralPath $installPathKey
            $executablePath = $installPath.GetValue('ExecutablePath', $null)
            if ($null -ne $executablePath -and -not [string]::IsNullOrWhiteSpace([string]$executablePath)) {
                [string]$executablePath
            }
            $installRoot = $installPath.GetValue('', $null)
            if ($null -ne $installRoot -and -not [string]::IsNullOrWhiteSpace([string]$installRoot)) {
                Join-Path ([string]$installRoot) 'python.exe'
            }
        }
    }
}

function Resolve-Python {
    $candidates = @(
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    $candidates += @(Get-MachineRegisteredPythonCandidates)
    $candidates += @(Get-MachinePathCandidates 'python.exe')
    foreach ($rawCandidate in $candidates | Select-Object -Unique) {
        if ($null -eq $rawCandidate) { continue }
        $candidate = ([string]$rawCandidate).Trim().Trim('"')
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $versionOutput = & $candidate --version 2>&1
        if ($LASTEXITCODE -ne 0) { continue }
        $version = ([string]$versionOutput).Trim() -replace '^Python\s+', ''
        if (Test-VersionAtLeast $version 3 11 0) { return $candidate }
    }
    throw 'Python >= 3.11 was not found in Program Files, HKLM PEP 514 registration, or the machine PATH. Per-user-only Python installations are not supported by the LocalSystem service.'
}

$python = Resolve-Python
Write-Output "Plasma Manager Python runtime: $python"
if ($PreflightOnly) { exit 0 }

$programDataRoot = Join-Path $env:ProgramData 'Plasma'
$configPath = Join-Path $programDataRoot 'config\manager.yaml'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Manager config is missing: $configPath"
}
$runtime = Join-Path $PSScriptRoot '..\runtime\manager\manager.pyz'
& $python $runtime --config $configPath
exit $LASTEXITCODE
