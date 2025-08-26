# scripts/backup-db-portable.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$ts   = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$dest = Join-Path (Get-Location) ("backups\{0}" -f (Get-Date).ToString("yyyy\\MM\\dd"))
New-Item -ItemType Directory -Force $dest | Out-Null
$out  = Join-Path $dest ("detecktiv_{0}.sql" -f $ts)

Write-Host "Creating logical backup via 'docker compose exec -T postgres pg_dump'..."
$dumpCmd = 'docker compose exec -T postgres pg_dump -U postgres -d detecktiv'
$dump    = & powershell -NoProfile -Command $dumpCmd
$dump | Set-Content -Path $out -Encoding UTF8
Write-Host "Backup written to $out" -ForegroundColor Green
