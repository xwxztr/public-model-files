param(
  [Parameter(Mandatory=$true)][string]$InputFolder,
  [Parameter(Mandatory=$true)][string]$ConfigFile,
  [ValidateSet('pi','opencode','deepseek','codex')][string]$Agent = 'pi'
)
$ErrorActionPreference = 'Stop'
$kit = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'Verify-Payload.ps1')
$inputPath = (Resolve-Path -LiteralPath $InputFolder).Path
$configPath = (Resolve-Path -LiteralPath $ConfigFile).Path
$payload = Join-Path $kit 'payload'
if (!(Test-Path -LiteralPath "$payload\runtime\python\python.exe")) { throw 'Use the full offline runtime ZIP, not just the source ZIP.' }
if (!(Test-Path -LiteralPath "$payload\vendor\node_modules")) { throw 'Offline dependencies are missing.' }
if ($inputPath -eq [IO.Path]::GetPathRoot($inputPath)) { throw 'Stage a small approved project, never a drive root.' }
if (!$inputPath -or !(Get-Item -LiteralPath $inputPath).PSIsContainer) { throw 'InputFolder must be a directory.' }
if ($configPath.StartsWith(($inputPath.TrimEnd('\')+'\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Host configuration must not be inside the mapped input directory.' }
foreach ($target in @($inputPath, $configPath, $kit)) {
  $item = Get-Item -LiteralPath $target -Force
  while ($null -ne $item) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked/reparse paths are not accepted.' }
    $item = $item.Parent
  }
}
if (Get-ChildItem -LiteralPath $inputPath -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1) { throw 'Remove links/junctions from staged input first.' }
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if ($settings.model -notmatch '^[A-Za-z0-9_.:/-]{1,160}$' -or $settings.model -match 'REPLACE') { throw 'Configure a real internal model ID.' }
if ($Agent -eq 'codex' -and $settings.allow_responses -ne $true) { throw 'Codex requires a verified Responses API. Use Pi for Chat Completions.' }
$session = Join-Path $kit ('local\' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $session -Force | Out-Null
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $session '/inheritance:r' '/grant:r' "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict session directory permissions.' }
foreach ($name in @('exchange','output','launch')) { New-Item -ItemType Directory -Path (Join-Path $session $name) | Out-Null }
Copy-Item -LiteralPath $configPath -Destination (Join-Path $session 'host-config.json')
@{model=$settings.model; allow_responses=($settings.allow_responses -eq $true); agent=$Agent; relay_wait_seconds=([int]$settings.timeout_seconds+20)} | ConvertTo-Json | Set-Content -LiteralPath "$session\launch\settings.json" -Encoding UTF8
function EscapeXml([string]$value) { [Security.SecurityElement]::Escape($value) }
$mappings = @(
  @{Host=$payload; Guest='C:\Kit'; ReadOnly='true'},
  @{Host=$inputPath; Guest='C:\Input'; ReadOnly='true'},
  @{Host="$session\output"; Guest='C:\Output'; ReadOnly='false'},
  @{Host="$session\exchange"; Guest='C:\Exchange'; ReadOnly='false'},
  @{Host="$session\launch"; Guest='C:\Session'; ReadOnly='true'}
)
$folders = ($mappings | ForEach-Object { "<MappedFolder><HostFolder>$(EscapeXml $_.Host)</HostFolder><SandboxFolder>$($_.Guest)</SandboxFolder><ReadOnly>$($_.ReadOnly)</ReadOnly></MappedFolder>" }) -join "`r`n"
$xml = @"
<Configuration>
  <Networking>Disable</Networking>
  <vGPU>Disable</vGPU>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <PrinterRedirection>Disable</PrinterRedirection>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MemoryInMB>8192</MemoryInMB>
  <MappedFolders>$folders</MappedFolders>
  <LogonCommand><Command>powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File C:\Kit\windows\Bootstrap.ps1</Command></LogonCommand>
</Configuration>
"@
$xml | Set-Content -LiteralPath "$session\Agent.wsb" -Encoding UTF8
Write-Host "Prepared session: $session"
Write-Host "1. In another PowerShell window: & '$PSScriptRoot\Start-Host.ps1' -Session '$session'"
Write-Host "2. Double-click '$session\Agent.wsb'. Keep the relay open."
Write-Host 'No Sandbox has been launched and no API connection has been made yet.'
