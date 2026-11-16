param([string]$Directory=$PSScriptRoot)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $Directory).Path
$count=0
foreach ($line in Get-Content -LiteralPath (Join-Path $root 'SHA256SUMS.txt')) {
  if (!$line.Trim()) { continue }
  if ($line -notmatch '^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$') { throw 'Invalid SHA256SUMS entry.' }
  $expectedHash=$Matches[1]; $name=$Matches[2]
  $actual=(Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant()
  if($actual -ne $expectedHash){throw "Hash mismatch: $name"}
  Write-Host "OK $name"
  $count++
}
if(!$count){throw 'No files to verify.'}
