$ErrorActionPreference = 'Stop'
if (!(Test-Path C:\Session\settings.json) -or !(Test-Path C:\Exchange)) { throw 'Run only through the generated Agent.wsb.' }
$python = 'C:\Kit\runtime\python\python.exe'
$env:PATH = 'C:\Kit\runtime\node;C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0'
# Dedicated state stays inside the disposable Sandbox. Real host credentials are not mapped.
$env:PI_CODING_AGENT_DIR = 'C:\State\pi'
$env:DSH_HOME = 'C:\State\dsh'
$env:CODEX_HOME = 'C:\State\codex'
$env:XDG_CONFIG_HOME = 'C:\State\config'
$env:XDG_DATA_HOME = 'C:\State\data'
$env:XDG_CACHE_HOME = 'C:\State\cache'
$env:CORP_SANDBOX_DUMMY_KEY = 'sandbox-placeholder'
$env:PI_OFFLINE = '1'
$env:PI_TELEMETRY = '0'
$env:DSH_TELEMETRY_DISABLED = '1'
$env:OPENCODE_DISABLE_AUTOUPDATE = '1'
$env:OPENCODE_DISABLE_MODELS_FETCH = '1'
$env:OPENCODE_DISABLE_PROJECT_CONFIG = '1'
$env:OPENCODE_PURE = '1'
$env:OPENCODE_CONFIG = 'C:\State\opencode\opencode.json'
$env:OTEL_SDK_DISABLED = 'true'
foreach ($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NODE_OPTIONS','NODE_EXTRA_CA_CERTS','OPENAI_API_KEY','ANTHROPIC_API_KEY','DEEPSEEK_API_KEY')) { Remove-Item "Env:\$name" -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force C:\Work,C:\State | Out-Null
Copy-Item -Path C:\Input\* -Destination C:\Work -Recurse -Force
& $python -I C:\Kit\src\configure.py --settings C:\Session\settings.json --root C:\State
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed.' }
Start-Process -FilePath $python -ArgumentList '-I C:\Kit\src\guard.py bridge --config C:\Session\settings.json --exchange C:\Exchange' -WindowStyle Hidden
Set-Location C:\Work
Write-Host 'Network-disabled company agent sandbox. Input is read-only; work is a disposable copy.'
Write-Host 'Save reviewed results to C:\Output before closing the Sandbox. Treat output files as untrusted.'
Write-Host 'Shell execution, external plugins and web tools are intentionally restricted in the supplied profiles.'
$settings = Get-Content C:\Session\settings.json -Raw | ConvertFrom-Json
& C:\Kit\windows\Run-Agent.ps1 -Agent $settings.agent
Write-Host 'Agent exited. To run again: & C:\Kit\windows\Run-Agent.ps1 -Agent pi'
Write-Host 'To export selected files: Copy-Item .\your-file C:\Output\'
