param([Parameter(Mandatory=$true)][string]$Session)
$ErrorActionPreference = 'Stop'
$kit = Split-Path $PSScriptRoot -Parent
$sessionPath = (Resolve-Path -LiteralPath $Session).Path
$localRoot = [IO.Path]::GetFullPath((Join-Path $kit 'local')) + '\'
if (!$sessionPath.StartsWith($localRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Session must be inside this kit local directory.' }
& "$kit\payload\runtime\python\python.exe" -I "$kit\payload\src\guard.py" host --config "$sessionPath\host-config.json" --exchange "$sessionPath\exchange"
exit $LASTEXITCODE
