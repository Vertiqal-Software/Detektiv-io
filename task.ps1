param(
  [Parameter(Position=0)]
  [string]$Task = "help",
  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]]$Args
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\scripts\tasks.ps1"

if (Get-Command $Task -ErrorAction SilentlyContinue) {
  & $Task @Args
} else {
  Write-Host "Unknown task: $Task" -ForegroundColor Red
  help
  exit 1
}
