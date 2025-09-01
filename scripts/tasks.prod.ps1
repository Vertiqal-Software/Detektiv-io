# scripts/tasks.prod.ps1
# Helpers for the minimal prod-like stack (docker-compose.prod.full.yml)

$ErrorActionPreference = "Stop"

$ProdEnvFile    = ".env.docker"
$ProdComposeYml = "docker-compose.prod.full.yml"

function up:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  if (-not (Test-Path $ProdEnvFile))    { throw "Missing $ProdEnvFile in repo root." }
  docker compose --env-file $ProdEnvFile -f $ProdComposeYml up -d
}

function down:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  docker compose -f $ProdComposeYml down --remove-orphans
}

function restart:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  docker compose --env-file $ProdEnvFile -f $ProdComposeYml up -d --force-recreate
}

function ps:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  docker compose -f $ProdComposeYml ps
}

function logs:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  param([string]$Service = "api")
  docker compose -f $ProdComposeYml logs -f --tail 200 $Service
}

function migrate:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  docker compose -f $ProdComposeYml exec -T api python -m alembic upgrade head
}

function current:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  docker compose -f $ProdComposeYml exec -T api alembic current
}

function psql:prod {
  if (-not (Test-Path $ProdComposeYml)) { throw "Missing $ProdComposeYml in repo root." }
  docker compose -f $ProdComposeYml exec -T postgres psql -U postgres -d detecktiv
}

function health:prod {
  param(
    [int]$TimeoutSeconds = 45,
    [int]$DelayMs = 800
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $r = Invoke-RestMethod http://localhost:8000/health -TimeoutSec 5
      if ($r.status -eq "ok") {
        Write-Host "ok"
        return
      }
    } catch {
      Start-Sleep -Milliseconds $DelayMs
    }
  } while ((Get-Date) -lt $deadline)

  Write-Host "Health check failed." -ForegroundColor Yellow
  throw "API did not become healthy within ${TimeoutSeconds}s"
}
