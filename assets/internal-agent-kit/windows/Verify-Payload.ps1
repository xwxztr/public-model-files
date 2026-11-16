$ErrorActionPreference = 'Stop'
$kit = Split-Path $PSScriptRoot -Parent
$manifestPath = Join-Path $kit 'payload-manifest.json'
if (!(Test-Path -LiteralPath $manifestPath)) { throw 'Missing payload manifest. Use the complete reviewed runtime package.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$expected = @{}
foreach ($entry in $manifest.files) {
  $relative = [string]$entry.path
  if (!$relative.StartsWith('payload/') -or $relative -match '(^|/)\.\.(/|$)|[:\\]' -or $entry.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid payload manifest entry.' }
  if ($expected.ContainsKey($relative)) { throw 'Duplicate manifest entry.' }
  $expected[$relative] = $entry.sha256
}
$files = @(Get-ChildItem -LiteralPath (Join-Path $kit 'payload') -Recurse -Force)
if ($files | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1) { throw 'Payload links/reparse points are forbidden.' }
$actualCount = 0
foreach ($file in ($files | Where-Object { !$_.PSIsContainer })) {
  $relative = $file.FullName.Substring($kit.Length+1).Replace('\','/')
  if (!$expected.ContainsKey($relative)) { throw "Unlisted payload file: $relative" }
  $actual = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected[$relative]) { throw "Payload hash mismatch: $relative" }
  $actualCount++
}
if ($actualCount -ne $expected.Count) { throw 'Payload files missing.' }
Write-Host "Payload verified: $actualCount files. This checks consistency, not publisher authenticity."
