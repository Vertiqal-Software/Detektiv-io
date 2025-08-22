# scripts/tasks.ps1
# Task runner helpers for detecktiv-io

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
    [string[]]$Args = @()
  )
  Write-Host "→ $Exe $($Args -join ' ')" -ForegroundColor DarkGray
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Exe
  $psi.Arguments = [string]::Join(' ', $Args)
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError  = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true

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

# ADD: small wrapper used by some tasks below (non-throwing, returns $true/$false)
function Invoke-External {
  param(
    [Parameter(Mandatory)][string]$Exe,
    [string[]]$Args = @()
  )
  try {
    Run $Exe $Args | Write-Host
    return $true
  } catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    return $false
  }
}

function Invoke-Compose {
  param([string[]]$Args)
  if ($COMPOSE.Count -gt 1) {
    Run $COMPOSE[0] @(@($COMPOSE[1]) + $Args)
  } else {
    Run $COMPOSE[0] $Args
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

# Default container names from your compose up
$PG_CONTAINER      = "detecktiv-io-postgres-1"
$PGADMIN_CONTAINER = "detecktiv-io-pgadmin-1"

# --------------------------
# Tasks
# --------------------------

function help {
@"
Available tasks:
  .\task help               Show this help
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
  .\task test              Run pytest locally


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
  # interactive to keep TTY attached
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
  Run "python" @("-m","pre_commit","run","--all-files") | Write-Host
}

function scan-secrets {
  # refresh baseline
  Run "python" @("-m","detect_secrets","scan") | Set-Content -Encoding UTF8 ".secrets.baseline"
  Write-Host "Updated .secrets.baseline" -ForegroundColor Green
}

function migrate {
  # Apply latest Alembic migrations (call python directly for clean output/exit code)
  Load-DotEnv
  Write-Host "→ python -m alembic upgrade head" -ForegroundColor DarkGray
  & python -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) {
    throw "Alembic upgrade failed with exit code $LASTEXITCODE"
  }
  Write-Host "Migrations applied to HEAD." -ForegroundColor Green

  db-current
}

function db-current {
  # Show current Alembic revision(s) (call python directly)
  Load-DotEnv
  Write-Host "→ python -m alembic current" -ForegroundColor DarkGray
  & python -m alembic current
  if ($LASTEXITCODE -ne 0) {
    throw "Alembic current failed with exit code $LASTEXITCODE"
  }
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
    $ok = Invoke-External -Exe "python" -Args @("-m","alembic","revision","-m",$Message)
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
    $ok = Invoke-External -Exe "python" -Args @("-m","alembic","revision","--autogenerate","-m",$Message)
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
    Invoke-External -Exe "python" -Args @("-m","alembic","downgrade","-1") | Out-Null
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
    Invoke-External -Exe "python" -Args @("-m","alembic","stamp",$Revision) | Out-Null
}

# ADD: simple seed task for local dev data (safe to re-run)
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
  & python -m pytest -q
  if ($LASTEXITCODE -ne 0) {
    throw "pytest failed with exit code $LASTEXITCODE"
  }
  Write-Host "Tests passed." -ForegroundColor Green
}
