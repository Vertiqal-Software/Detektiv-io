# Nightly logical backup of "detecktiv" into ./backups
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$ts = Get-Date -Format "yyyyMMdd-HHmm"
$outFile = Join-Path (Join-Path (Get-Location) "backups") ("dump-detecktiv-{0}.sql" -f $ts)

# pg_dump is text SQL; OK to save UTF8
# Note: use -Fc for custom format if you want pg_restore later. Here we keep plain SQL.
$dumpCmd = 'docker compose exec -T postgres pg_dump -U postgres -d detecktiv'
$dump = & powershell -NoProfile -Command $dumpCmd
$dump | Set-Content -Path $outFile -Encoding UTF8

# Optional: prune old backups (keep 14 days)
Get-ChildItem .\backups\dump-detecktiv-*.sql | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Force -ErrorAction SilentlyContinue
