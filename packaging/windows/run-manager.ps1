$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-VersionAtLeast([string]$Version, [int]$Major, [int]$Minor, [int]$Patch) {
    $clean = $Version.Trim().TrimStart('v','V')
    $parts = $clean.Split('.')
    if ($parts.Count -lt 2) { return $false }
    $values = @(0,0,0)
    for ($i = 0; $i -lt [Math]::Min(3, $parts.Count); $i++) {
        $token = ($parts[$i] -replace '[^0-9].*$', '')
        if (-not [int]::TryParse($token, [ref]$values[$i])) { return $false }
    }
    if ($values[0] -ne $Major) { return $values[0] -gt $Major }
    if ($values[1] -ne $Minor) { return $values[1] -gt $Minor }
    return $values[2] -ge $Patch
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
