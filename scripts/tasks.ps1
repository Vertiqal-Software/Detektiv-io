# scripts\tasks.ps1
$ErrorActionPreference = 'Stop'

# --- Detect compose command (plugin vs legacy) ---
$Global:ComposeMode = "plugin"
try {
  & docker compose version 1>$null 2>$null
} catch {
  if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $Global:ComposeMode = "legacy"
  } else {
    throw "Docker Compose not found. Start Docker Desktop or install docker-compose."
  }
}
function Compose {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
  if ($Global:ComposeMode -eq "plugin") {
    & docker compose @Args
  } else {
    & docker-compose @Args
  }
}

# --- Helpers ---
function _PostgresName { "detecktiv-io-postgres-1" }
function _PgAdminName  { "detecktiv-io-pgadmin-1"  }

# --- Tasks ---
function help {
  @"
Available tasks:
  .\task help              Show this help
  .\task up                Start postgres + pgadmin (detached)
  .\task down              Stop and remove containers
  .\task status            Show docker containers
  .\task logs              Tail logs for both services
  .\task psql              Open psql shell in postgres container
  .\task backup            Run on-demand DB backup (scripts\backup-db.ps1)
  .\task restore-latest    Restore most recent backup into DB  (⚠ destructive)
"@ | Write-Host
}

function up      { Compose up -d }
function down    { Compose down }
function status  { docker ps }
function logs    { Compose logs -f }

function psql {
  $c = _PostgresName
  & docker exec -it $c psql -U postgres -d detecktiv
}

function backup {
  $script = Join-Path $PSScriptRoot "backup-db.ps1"
  if (-not (Test-Path $script)) { throw "Missing $script" }
  & pwsh -NoProfile -ExecutionPolicy Bypass -File $script
}

function restore-latest {
  $script = Join-Path $PSScriptRoot "restore-latest.ps1"
  if (-not (Test-Path $script)) { throw "Missing $script" }
  & pwsh -NoProfile -ExecutionPolicy Bypass -File $script
}
