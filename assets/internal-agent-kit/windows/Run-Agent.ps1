param([ValidateSet('pi','opencode','deepseek','codex')][string]$Agent='pi')
$ErrorActionPreference='Stop'
if (!(Test-Path C:\Session\settings.json)) { throw 'Agent launch is restricted to the Sandbox layout.' }
$settings = Get-Content C:\Session\settings.json -Raw | ConvertFrom-Json
switch ($Agent) {
  'pi' { & C:\Kit\runtime\node\node.exe C:\Kit\vendor\node_modules\@earendil-works\pi-coding-agent\dist\bundle\cli.js --offline --no-session --no-extensions --no-mcp --no-skills --no-prompt-templates --no-themes --tools read,edit,write --provider corp --model $settings.model }
  'opencode' { & C:\Kit\runtime\opencode\opencode.exe -m "corp/$($settings.model)" }
  'deepseek' {
    Write-Host 'Open the displayed localhost Web UI URL inside the Sandbox browser. No host browser is used.'
    & C:\Kit\runtime\node\node.exe C:\Kit\vendor\node_modules\@deepseek-ai\dsh\lib\bin.js web --host 127.0.0.1 --no-open
  }
  'codex' {
    if ($settings.allow_responses -ne $true) { throw 'Responses API compatibility has not been enabled.' }
    & C:\Kit\runtime\codex\codex.exe
  }
}
