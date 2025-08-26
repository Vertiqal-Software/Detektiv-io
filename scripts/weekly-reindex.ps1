# Weekly REINDEX to keep indexes fresh (small DBs benefit; safe to skip if huge)
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

function Invoke-Psql($Sql, $Db="detecktiv") {
  $cmd = 'docker compose exec -T postgres psql -U postgres -d {0} -v "ON_ERROR_STOP=1" -c "{1}"' -f $Db, ($Sql -replace '"','\"')
  powershell -NoProfile -Command $cmd
}

# REINDEX DATABASE (CONCURRENTLY) if you prefer fewer locks and you're on PG ≥ 12; CONCURRENTLY can be slower.
Invoke-Psql "REINDEX DATABASE detecktiv;"
