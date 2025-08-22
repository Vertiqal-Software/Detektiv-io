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
