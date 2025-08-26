# scripts/restore-latest-portable.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$latest = Get-ChildItem .\backups -Recurse -Filter *.sql | Sort-Object LastWriteTime -Desc | Select-Object -First 1
if (-not $latest) { Write-Host "No backups found." -ForegroundColor Yellow; exit 1 }

Write-Host "Restoring '$($latest.FullName)' to database 'detecktiv' (⚠ drops existing) ..." -ForegroundColor Yellow

# Terminate sessions and recreate database
docker compose exec -T postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='detecktiv' AND pid <> pg_backend_pid();"
docker compose exec -T postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS detecktiv;"
docker compose exec -T postgres psql -U postgres -d postgres -c "CREATE DATABASE detecktiv;"

# Restore
Get-Content $latest.FullName | docker compose exec -T postgres psql -U postgres -d detecktiv
Write-Host "Restore complete." -ForegroundColor Green
