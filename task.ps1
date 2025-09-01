# task.ps1 - Simplified Task Runner for detecktiv.io
param(
    [Parameter(Position=0)]
    [string]$Task = "help",
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

# Helper functions
function Write-TaskHeader($TaskName) {
    Write-Host ""
    Write-Host ("=== " + $TaskName) -ForegroundColor Cyan
    Write-Host ("=" * 50) -ForegroundColor DarkGray
}
function Write-Success($Message) { Write-Host ("OK: " + $Message) -ForegroundColor Green }
function Write-Err($Message)     { Write-Host ("ERROR: " + $Message) -ForegroundColor Red }
function Write-Info($Message)    { Write-Host ("INFO: " + $Message) -ForegroundColor Blue }

function Load-EnvFile {
    $envFile = ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^([^#][^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim().Trim('"')
                [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
        Write-Info "Loaded environment from $envFile"
    }
}

# Task functions
function help {
@"
detecktiv.io Task Runner

DOCKER & SERVICES:
  up                   Start the full stack (postgres + pgadmin + api)
  down                 Stop all services
  status               Show running containers
  logs                 View service logs
  restart              Restart all services

DATABASE:
  psql                 Connect to database with psql (search_path=app,public)
  migrate              Run database migrations (validates graph first)
  db-current           Show current Alembic revision (per DB)
  db-heads             Show Alembic head revisions (from files)
  migrations-validate  Validate migration graph (no DB access)
  reset-db             Clean reset database (DESTRUCTIVE)
  backup               Create database backup (docker exec pg_dump)
  restore-latest       Restore from latest backup (DESTRUCTIVE)

DEVELOPMENT:
  api                  Start API server locally (with reload)
  test                 Run pytest tests
  lint                 Run code formatting and linting
  install              Install Python dependencies

EXAMPLES:
  .\task up
  .\task migrate
  .\task db-current
  .\task psql
"@
}

function up {
    Write-TaskHeader "Starting Services"
    Load-EnvFile

    if (-not (Test-Path ".env")) {
        Write-Err ".env file not found"
        Write-Info "Copy .env.example to .env and configure it first"
        return
    }

    docker compose up -d
    Write-Success "Services started"
    Write-Info "API:     http://localhost:8000"
    Write-Info "pgAdmin: http://localhost:5050"
}

function down {
    Write-TaskHeader "Stopping Services"
    docker compose down
    Write-Success "Services stopped"
}

function status {
    Write-TaskHeader "Service Status"
    docker compose ps
}

function logs {
    Write-TaskHeader "Service Logs"
    docker compose logs -f
}

function restart {
    Write-TaskHeader "Restarting Services"
    docker compose down
    docker compose up -d
    Write-Success "Services restarted"
}

function psql {
    Write-TaskHeader "Connecting to Database"
    Load-EnvFile

    $user   = $env:POSTGRES_USER
    if (-not $user) { $user = "postgres" }

    $db     = $env:POSTGRES_DB
    if (-not $db) { $db = "detecktiv" }

    if ($env:POSTGRES_SCHEMA -and $env:POSTGRES_SCHEMA.Trim()) {
        $schema = $env:POSTGRES_SCHEMA
    } else {
        $schema = "app"
    }

    Write-Info ("Connecting as user '{0}' to database '{1}' (schema: {2})" -f $user, $db, $schema)

    # Open an interactive psql session inside the postgres container with search_path preset.
    docker compose exec `
        -e PGOPTIONS="-c search_path=$schema,public" `
        postgres psql -U $user -d $db
}

function migrate {
    Write-TaskHeader "Running Database Migrations"
    Load-EnvFile

    # Validate migration graph before applying (prevents broken down_revision errors)
    if (Test-Path "tools\validate_migrations.py") {
        Write-Info "Validating migration graph..."
        python tools/validate_migrations.py
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Migration graph validation failed"
            exit 1
        }
    }

    python -m alembic upgrade head
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Migrations completed"
    } else {
        Write-Err "Migration failed"
        exit 1
    }
}

function db-current {
    Write-TaskHeader "Current Alembic Revision (DB)"
    Load-EnvFile
    python -m alembic current -v
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Unable to fetch current revision"
        exit 1
    }
}

function db-heads {
    Write-TaskHeader "Alembic Heads (from files)"
    python -m alembic heads -v
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Unable to enumerate heads"
        exit 1
    }
}

function migrations-validate {
    Write-TaskHeader "Validating Migration Graph"
    if (-not (Test-Path "tools\validate_migrations.py")) {
        Write-Err "tools\validate_migrations.py not found"
        Write-Info "Run: python tools/validate_migrations.py (after adding the validator)"
        exit 1
    }
    python tools/validate_migrations.py
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Migrations look good"
    } else {
        Write-Err "Problems found in migration graph"
        exit 1
    }
}

function reset-db {
    Write-TaskHeader "Database Reset"
    Write-Host "WARNING: This will destroy all data!" -ForegroundColor Yellow
    $confirm = Read-Host "Type 'yes' to continue"

    if ($confirm -eq "yes") {
        if (Test-Path "cleanup_db.py") {
            python cleanup_db.py
        } else {
            Load-EnvFile
            $db = $env:POSTGRES_DB
            if (-not $db) { $db = "detecktiv" }
            Write-Info "Dropping and recreating database '$db'..."
            docker compose exec postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${db}' AND pid <> pg_backend_pid();"
            docker compose exec postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ${db};"
            docker compose exec postgres psql -U postgres -d postgres -c "CREATE DATABASE ${db};"
            Write-Success "Database recreated"
        }
    } else {
        Write-Info "Aborted"
    }
}

function backup {
    Write-TaskHeader "Creating Database Backup"
    Load-EnvFile

    $timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $backupDir = "backups\$(Get-Date -Format 'yyyy\MM\dd')"
    if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Force -Path $backupDir | Out-Null }

    $backupFile = "$backupDir\detecktiv_$timestamp.sql"

    $user = $env:POSTGRES_USER
    if (-not $user) { $user = "postgres" }

    $db = $env:POSTGRES_DB
    if (-not $db) { $db = "detecktiv" }

    docker compose exec -T postgres pg_dump -U $user -d $db > $backupFile
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Backup created: $backupFile"
    } else {
        Write-Err "Backup failed"
        exit 1
    }
}

function restore-latest {
    Write-TaskHeader "Restoring Latest Backup"
    Write-Host "WARNING: This will destroy current data!" -ForegroundColor Yellow
    $confirm = Read-Host "Type 'yes' to continue"
    if ($confirm -ne "yes") { Write-Info "Aborted"; return }

    $latest = Get-ChildItem "backups" -Recurse -Filter "*.sql" |
              Sort-Object LastWriteTime -Descending |
              Select-Object -First 1

    if (-not $latest) { Write-Err "No backup files found"; return }

    Load-EnvFile
    $user = $env:POSTGRES_USER
    if (-not $user) { $user = "postgres" }

    $db = $env:POSTGRES_DB
    if (-not $db) { $db = "detecktiv" }

    Write-Info "Restoring to database '$db' from: $($latest.FullName)"

    docker compose exec postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${db}' AND pid <> pg_backend_pid();"
    docker compose exec postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ${db};"
    docker compose exec postgres psql -U postgres -d postgres -c "CREATE DATABASE ${db};"

    Get-Content $latest.FullName | docker compose exec -T postgres psql -U $user -d $db
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Restore completed"
    } else {
        Write-Err "Restore failed"
        exit 1
    }
}

function api {
    Write-TaskHeader "Starting API Server"
    Load-EnvFile
    Write-Info "Starting with auto-reload..."
    Write-Info "API will be available at: http://localhost:8000"
    Write-Info "Press Ctrl+C to stop"
    python start.py
}

function test {
    Write-TaskHeader "Running Tests"
    Load-EnvFile
    $env:RUN_DB_TESTS = "1"
    Write-Info "Running pytest..."
    python -m pytest -v
    if ($LASTEXITCODE -eq 0) {
        Write-Success "All tests passed"
    } else {
        Write-Err "Some tests failed"
        exit 1
    }
}

function lint {
    Write-TaskHeader "Code Formatting and Linting"
    Write-Info "Running Black (formatting)..."
    python -m black . --check
    Write-Info "Running Flake8 (linting)..."
    python -m flake8 .
    Write-Success "Code quality checks completed"
}

function install {
    Write-TaskHeader "Installing Dependencies"
    Write-Info "Installing production dependencies..."
    python -m pip install -r requirements.txt
    Write-Info "Installing development dependencies..."
    python -m pip install -r requirements-dev.txt
    Write-Success "Dependencies installed"
    Write-Info "You may want to run: .\task migrate"
}

# Execute the requested task
if (Get-Command $Task -ErrorAction SilentlyContinue) {
    try { & $Task @Args } catch {
        Write-Err "Task '$Task' failed: $($_.Exception.Message)"
        exit 1
    }
} else {
    Write-Err "Unknown task: $Task"
    help
    exit 1
}
