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

function Resolve-Node {
    $candidates = @("$env:ProgramFiles\nodejs\node.exe")
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $version = & $candidate --version 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-VersionAtLeast $version 22 13 0)) { return $candidate }
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
