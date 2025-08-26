$dir = Join-Path $PSScriptRoot "..\backups"
$latest = Get-ChildItem $dir -Recurse -Filter *.sql | Sort-Object LastWriteTime -Desc | Select-Object -First 1
if (-not $latest) { Write-Host "No backups found." -ForegroundColor Yellow; exit 1 }
Write-Host "Restoring $($latest.FullName) to database 'detecktiv' (⚠ this drops existing) ..."
docker exec -i detecktiv-io-postgres-1 psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='detecktiv' AND pid <> pg_backend_pid();"
docker exec -i detecktiv-io-postgres-1 psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS detecktiv;"
docker exec -i detecktiv-io-postgres-1 psql -U postgres -d postgres -c "CREATE DATABASE detecktiv;"
Get-Content $latest.FullName | docker exec -i detecktiv-io-postgres-1 psql -U postgres -d detecktiv
Write-Host "Restore complete."
