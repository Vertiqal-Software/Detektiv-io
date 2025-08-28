# task.ps1 (repo root)
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

$PSNativeCommandUseErrorActionPreference = $true
$ErrorActionPreference = "Stop"

$script = Join-Path $PSScriptRoot "scripts\tasks.ps1"
if (-not (Test-Path $script)) { throw "Missing $script" }

& $script @Args
exit $LASTEXITCODE
