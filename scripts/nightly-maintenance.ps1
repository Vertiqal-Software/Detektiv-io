# Nightly maintenance: VACUUM/ANALYZE + reset pg_stat_statements + health snapshot
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

# Helper for running SQL via docker compose
function Invoke-Psql($Sql, $Db="detecktiv") {
  $cmd = 'docker compose exec -T postgres psql -U postgres -d {0} -v "ON_ERROR_STOP=1" -c "{1}"' -f $Db, ($Sql -replace '"','\"')
  powershell -NoProfile -Command $cmd
}

# Start marker
Invoke-Psql "SELECT now() AS started_at, current_user AS run_as;"

# Autovacuum does a lot already; this nudges stats & small tables
Invoke-Psql "VACUUM (ANALYZE, VERBOSE);"

# Reset pg_stat_statements daily to keep windows clean
Invoke-Psql "SELECT pg_stat_statements_reset();" "postgres"

# Quick health snapshot into server log
Invoke-Psql "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database ORDER BY pg_database_size(datname) DESC;" "postgres"
