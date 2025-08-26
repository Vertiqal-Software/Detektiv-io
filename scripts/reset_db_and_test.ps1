# Save this file as scripts\reset_db_and_test.ps1, then run it in PowerShell.
# It clears the "companies" table (so tests start from a clean slate) and runs pytest.

param(
  [string]$PgUser = "postgres",
  [string]$PgDb   = "detecktiv",
  [string]$Service = "postgres"
)

Write-Host "Truncating public.companies inside docker service '$Service'..."
docker compose exec $Service psql -U $PgUser -d $PgDb -c "TRUNCATE TABLE public.companies RESTART IDENTITY;"

Write-Host "Setting test env vars and running pytest..."
$env:RUN_DB_TESTS      = '1'
$env:POSTGRES_USER     = 'postgres'
if (-not $env:POSTGRES_PASSWORD) { throw "Set POSTGRES_PASSWORD in your environment." }  # pragma: allowlist secret
$env:POSTGRES_DB       = 'detecktiv'
$env:POSTGRES_HOST     = '127.0.0.1'
$env:POSTGRES_PORT     = '5432'

py -3.13 -m pytest -q

