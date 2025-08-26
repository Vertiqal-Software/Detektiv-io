$ts = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$dest = Join-Path $PSScriptRoot "..\backups\$((Get-Date).ToString('yyyy\\MM\\dd'))"
New-Item -ItemType Directory -Force $dest | Out-Null
$out = Join-Path $dest "detecktiv_$ts.sql"
docker exec detecktiv-io-postgres-1 pg_dump -U postgres -d detecktiv > $out
Write-Host "Backup written to $out"
