# scripts/tasks.ps1
# Task runner helpers for detecktiv-io

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Compute repository root (parent of /scripts)
$REPO_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# --------------------------
# Helpers
# --------------------------

function Resolve-Compose {
  # Prefer "docker compose", fall back to legacy "docker-compose"
  try {
    & docker compose version 1>$null 2>$null
    return @("docker","compose")
  } catch {
    try {
      & docker-compose version 1>$null 2>$null
      return @("docker-compose")
    } catch {
      throw "Docker Compose not found. Install Docker Desktop or ensure 'docker compose'/'docker-compose' is in PATH."
    }
  }
}

$COMPOSE = Resolve-Compose

function Run {
  param(
    [Parameter(Mandatory)][string]$Exe,
    [string[]]$ArgList = @(),
    [string]$WorkingDirectory = $null
  )
  Write-Host "→ $Exe $($ArgList -join ' ')" -ForegroundColor DarkGray
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Exe
  $psi.Arguments = [string]::Join(' ', $ArgList)
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError  = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  if ($WorkingDirectory) {
    $psi.WorkingDirectory = $WorkingDirectory
  } else {
    $psi.WorkingDirectory = (Get-Location).Path
  }

  $p = New-Object System.Diagnostics.Process
  $p.StartInfo = $psi

  if (-not $p.Start()) { throw "Failed to start: $Exe" }
  $out = $p.StandardOutput.ReadToEnd()
  $err = $p.StandardError.ReadToEnd()
  $p.WaitForExit()

  if ($p.ExitCode -ne 0) {
    if ($err) { Write-Host $err -ForegroundColor Red }
    throw "$Exe exited with code $($p.ExitCode)"
  }

  if ($out) { $out.TrimEnd() }
}

# Non-throwing helper for external commands
function Invoke-External {
  param(
    [Parameter(Mandatory)][string]$Exe,
    [string[]]$ArgList = @(),
    [string]$WorkingDirectory = $null
  )
  try {
    Run -Exe $Exe -ArgList $ArgList -WorkingDirectory $WorkingDirectory | Write-Host
    return $true
  } catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    return $false
  }
}

# Convenience wrapper that always runs in repo root
function RunRepo {
  param(
    [Parameter(Mandatory)][string]$Exe,
    [string[]]$ArgList = @()
  )
  Run -Exe $Exe -ArgList $ArgList -WorkingDirectory $REPO_ROOT
}

function Invoke-Compose {
  param([string[]]$ArgList)
  if ($COMPOSE.Count -gt 1) {
    # e.g. "docker" + ("compose" + args...)
    Run -Exe $COMPOSE[0] -ArgList (@($COMPOSE[1]) + $ArgList) -WorkingDirectory $REPO_ROOT
  } else {
    # e.g. "docker-compose" + args...
    Run -Exe $COMPOSE[0] -ArgList $ArgList -WorkingDirectory $REPO_ROOT
  }
}

function Load-DotEnv {
  param(
    [string]$Path = (Join-Path $PSScriptRoot "..\.env")
  )
  if (-not (Test-Path $Path)) { return }
  Get-Content -LiteralPath $Path | ForEach-Object {
    if ($_ -match '^\s*#') { return }   # comments
    if ($_ -match '^\s*$') { return }   # blanks
    $kv = $_ -split '=', 2
    if ($kv.Length -eq 2) {
      $k = $kv[0].Trim()
      $v = $kv[1].Trim('"').Trim()
      [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
  }
}

# Generic env-file loader (for .env.docker, etc.)
function Load-EnvFile {
  param([Parameter(Mandatory)][string]$Path)
  if (-not (Test-Path $Path)) { return }
  Get-Content -LiteralPath $Path | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    $kv = $_ -split '=', 2
    if ($kv.Length -eq 2) {
      $k = $kv[0].Trim()
      $v = $kv[1].Trim('"').Trim()
      [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
  }
}

# Wait until API /health reports {"status":"ok"}
function Wait-Api-Healthy {
  param(
    [string]$Url = "http://localhost:8000/health",
    [int]$TimeoutSeconds = 60,
    [int]$IntervalSeconds = 2
  )
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  do {
    try {
      $res = Invoke-RestMethod -Uri $Url -TimeoutSec 5
      if ($res -and $res.status -eq "ok") {
        Write-Host "API healthy ($Url)" -ForegroundColor Green
        return $true
      }
    } catch {
      # swallow and retry
    }
    Start-Sleep -Seconds $IntervalSeconds
  } while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds)
  throw "API did not become healthy within ${TimeoutSeconds}s"
}

# Default container names from your compose up
$PG_CONTAINER      = "detecktiv-io-postgres-1"
$PGADMIN_CONTAINER = "detecktiv-io-pgadmin-1"

# --------------------------
# Dev Tasks
# --------------------------

function help {
@"
Available tasks:
  .\task help               Show this help

  # Dev stack (postgres + pgadmin)
  .\task up                 Start postgres + pgadmin (detached)
  .\task down               Stop and remove containers
  .\task status             Show docker containers
  .\task logs               Tail logs for both services
  .\task psql               Open psql shell in postgres container
  .\task backup             Run on-demand DB backup (scripts\backup-db.ps1)
  .\task restore-latest     Restore most recent backup into DB  (⚠ destructive)
  .\task build              Build docker images (if any)
  .\task restart            Down then up
  .\task lint               Run Black + Flake8 locally via pre-commit
  .\task scan-secrets       Run detect-secrets and update .secrets.baseline
  .\task migrate            Apply latest Alembic migrations (upgrade head)
  .\task db-current         Show current Alembic revision
  .\task make-migration     Create a new Alembic revision from a message
  .\task autogen-migration  Create a new Alembic revision with --autogenerate
  .\task downgrade          Downgrade one revision (⚠ use carefully)
  .\task db-stamp <rev>     Stamp DB at a revision without running migrations
  .\task seed               Insert sample dev data (safe/no-op if already present)
  .\task test               Run pytest locally
  .\task api                Test API Health (local dev server)

  # Prod-like minimal stack (docker-compose.prod.full.yml)
  .\task up:prod
  .\task down:prod
  .\task restart:prod
  .\task ps:prod
  .\task logs:prod [service]
  .\task migrate:prod
  .\task current:prod
  .\task psql:prod
  .\task health:prod [-TimeoutSeconds 60] [-IntervalSeconds 2]
"@
}

function up {
  Load-DotEnv
  Invoke-Compose @("up","-d") | Out-Null
  Write-Host "Stack is up." -ForegroundColor Green
}

function down {
  Invoke-Compose @("down") | Out-Null
  Write-Host "Stack is down." -ForegroundColor Yellow
}

function status {
  Run "docker" @("ps") | Write-Host
}

function logs {
  Invoke-Compose @("logs","-f")
}

function psql {
  Load-DotEnv
  $user = if ($Env:POSTGRES_USER) { $Env:POSTGRES_USER } else { "postgres" }
  $db   = if ($Env:POSTGRES_DB)   { $Env:POSTGRES_DB }   else { "detecktiv" }
  Write-Host "Opening psql in container '$PG_CONTAINER' as user '$user' to DB '$db'..." -ForegroundColor Cyan
  & docker exec -it $PG_CONTAINER psql -U $user -d $db
}

function backup {
  $script = Join-Path $PSScriptRoot "backup-db.ps1"
  if (-not (Test-Path $script)) { throw "Missing: $script" }
  & $script
}

function restore-latest {
  $script = Join-Path $PSScriptRoot "restore-latest.ps1"
  if (-not (Test-Path $script)) { throw "Missing: $script" }
  & $script
}

function build {
  Invoke-Compose @("build")
}

function restart {
  down
  up
}

function lint {
  # pre-commit runs Black + Flake8 as configured
  RunRepo "python" @("-m","pre_commit","run","--all-files") | Write-Host
}

function scan-secrets {
  # refresh baseline
  RunRepo "python" @("-m","detect_secrets","scan") | Set-Content -Encoding UTF8 (Join-Path $REPO_ROOT ".secrets.baseline")
  Write-Host "Updated .secrets.baseline" -ForegroundColor Green
}

function migrate {
  # Apply latest Alembic migrations (run from repo root so alembic.ini is found)
  Load-DotEnv
  Write-Host "→ python -m alembic upgrade head" -ForegroundColor DarkGray
  RunRepo "python" @("-m","alembic","upgrade","head") | Write-Host
  Write-Host "Migrations applied to HEAD." -ForegroundColor Green
  db-current
}

function db-current {
  Load-DotEnv
  Write-Host "→ python -m alembic current" -ForegroundColor DarkGray
  RunRepo "python" @("-m","alembic","current") | Write-Host
}

function make-migration {
    <#
      .SYNOPSIS
        Create a new Alembic revision (empty template).
      .EXAMPLE
        .\task make-migration "add orders table"
    #>
    param(
      [Parameter(Mandatory=$true, Position=0)]
      [string]$Message
    )
    Write-Host "→ python -m alembic revision -m `"$Message`""
    $ok = Invoke-External -Exe "python" -ArgList @("-m","alembic","revision","-m",$Message) -WorkingDirectory $REPO_ROOT
    if ($ok) { Write-Host "Revision created under db\migrations\versions\" -ForegroundColor Green }
}

function autogen-migration {
    <#
      .SYNOPSIS
        Create a new Alembic revision with autogenerate (requires SQLAlchemy models + target_metadata).
      .EXAMPLE
        .\task autogen-migration "sync models"
    #>
    param(
      [Parameter(Mandatory=$true, Position=0)]
      [string]$Message
    )
    Write-Host "→ python -m alembic revision --autogenerate -m `"$Message`""
    $ok = Invoke-External -Exe "python" -ArgList @("-m","alembic","revision","--autogenerate","-m",$Message) -WorkingDirectory $REPO_ROOT
    if ($ok) { Write-Host "Autogenerated revision created." -ForegroundColor Green }
}

function downgrade {
    <#
      .SYNOPSIS
        Downgrade one migration (use carefully).
      .EXAMPLE
        .\task downgrade
    #>
    Write-Host "→ python -m alembic downgrade -1"
    Invoke-External -Exe "python" -ArgList @("-m","alembic","downgrade","-1") -WorkingDirectory $REPO_ROOT | Out-Null
}

function db-stamp {
    <#
      .SYNOPSIS
        Mark the database as being at head (no migrations run).
      .EXAMPLE
        .\task db-stamp head
    #>
    param(
      [Parameter(Mandatory=$true, Position=0)]
      [string]$Revision
    )
    Write-Host "→ python -m alembic stamp $Revision"
    Invoke-External -Exe "python" -ArgList @("-m","alembic","stamp",$Revision) -WorkingDirectory $REPO_ROOT | Out-Null
}

# Simple seed task for local dev data (safe to re-run)
function seed {
    <#
      .SYNOPSIS
        Insert sample development data (idempotent).
      .EXAMPLE
        .\task seed
    #>
    Load-DotEnv
    $user = if ($Env:POSTGRES_USER) { $Env:POSTGRES_USER } else { "postgres" }
    $db   = if ($Env:POSTGRES_DB)   { $Env:POSTGRES_DB }   else { "detecktiv" }

    $sql = @"
create table if not exists users (
  id serial primary key,
  email text unique not null,
  full_name text
);
insert into users (email, full_name)
values
  ('alice@example.com','Alice Example'),
  ('bob@example.com','Bob Example')
on conflict (email) do nothing;
"@

    try {
      $tmp = [System.IO.Path]::GetTempFileName()
      Set-Content -LiteralPath $tmp -Value $sql -Encoding UTF8

      # copy to container and run
      Run "docker" @("cp", $tmp, "$PG_CONTAINER`:/tmp/seed.sql") | Out-Null
      Run "docker" @("exec", $PG_CONTAINER, "psql", "-U", $user, "-d", $db, "-f", "/tmp/seed.sql") | Write-Host
      Run "docker" @("exec", $PG_CONTAINER, "rm", "-f", "/tmp/seed.sql") | Out-Null
      Remove-Item $tmp -Force -ErrorAction SilentlyContinue
      Write-Host "Seed complete." -ForegroundColor Green
    } catch {
      Write-Host "Seed failed: $($_.Exception.Message)" -ForegroundColor Red
      throw
    }
}

function test {
  # Run pytest locally with current env
  Load-DotEnv
  Write-Host "→ pytest -q" -ForegroundColor DarkGray
  RunRepo "python" @("-m","pytest","-q") | Write-Host
  Write-Host "Tests passed." -ForegroundColor Green
}

function api {
  # Run FastAPI locally
  Write-Host "→ uvicorn app.main:app --reload --port 8000"
  RunRepo "uvicorn" @("app.main:app","--reload","--port","8000") | Write-Host
}

# ---------- Prod (full) helpers ----------
# Minimal prod-like stack defined in docker-compose.prod.full.yml
# - No pgAdmin, no host 5432 port publishing (internal only)
# - Uses .env.docker for DB credentials

$ProdEnvFile    = ".env.docker"
$ProdComposeYml = "docker-compose.prod.full.yml"

function up:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdEnvFile)))    { throw "Missing $ProdEnvFile in repo root." }
  Invoke-Compose @("--env-file", $ProdEnvFile, "-f", $ProdComposeYml, "up", "-d")
}

function down:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Invoke-Compose @("-f", $ProdComposeYml, "down", "--remove-orphans")
}

function restart:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Invoke-Compose @("--env-file", $ProdEnvFile, "-f", $ProdComposeYml, "up", "-d", "--force-recreate")
}

function ps:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Invoke-Compose @("-f", $ProdComposeYml, "ps")
}

function logs:prod {
  param([string]$Service = "api")
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Invoke-Compose @("-f", $ProdComposeYml, "logs", "-f", "--tail", "200", $Service)
}

function migrate:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Invoke-Compose @("-f", $ProdComposeYml, "exec", "-T", "api", "python", "-m", "alembic", "upgrade", "head")
}

function current:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Invoke-Compose @("-f", $ProdComposeYml, "exec", "-T", "api", "alembic", "current")
}

function psql:prod {
  if (-not (Test-Path (Join-Path $REPO_ROOT $ProdComposeYml))) { throw "Missing $ProdComposeYml in repo root." }
  Load-EnvFile (Join-Path $REPO_ROOT $ProdEnvFile)
  $user = if ($Env:POSTGRES_USER) { $Env:POSTGRES_USER } else { "postgres" }
  $db   = if ($Env:POSTGRES_DB)   { $Env:POSTGRES_DB }   else { "detecktiv" }
  Invoke-Compose @("-f", $ProdComposeYml, "exec", "-T", "postgres", "psql", "-U", $user, "-d", $db)
}

function health:prod {
  param(
    [int]$TimeoutSeconds = 60,
    [int]$IntervalSeconds = 2
  )
  try {
    Wait-Api-Healthy -TimeoutSeconds $TimeoutSeconds -IntervalSeconds $IntervalSeconds | Out-Null
  } catch {
    Write-Host "Health check failed." -ForegroundColor Yellow
    throw
  }
}

# --------------------------
# Lightweight CLI dispatcher
# --------------------------
# Allows: .\task <name> [args], including colon-names like up:prod

if ($MyInvocation.MyCommand.Path -and $PSCommandPath -and ($MyInvocation.MyCommand.Path -eq $PSCommandPath)) {
  if ($args.Count -eq 0) {
    help
    exit 0
  }
  $task = $args[0]
  $rest = @()
  if ($args.Count -gt 1) { $rest = $args[1..($args.Count-1)] }

  $fn = Get-Command -Name $task -CommandType Function -ErrorAction SilentlyContinue
  if (-not $fn) {
    Write-Host "Unknown task: $task" -ForegroundColor Yellow
    help
    exit 1
  }

  & $task @rest
  exit $LASTEXITCODE
}
