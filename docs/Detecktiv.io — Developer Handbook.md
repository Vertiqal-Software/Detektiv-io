# Detecktiv.io — Developer Handbook (MVP → Multi‑tenant SaaS)

> A single, authoritative reference for local dev, CI/CD, database, security, compliance, and operations. Optimized for beginners with IT support background. Copy‑paste friendly, with checklists.

---

## Table of Contents
1. Project Overview
2. Architecture & Stack
3. Local Development Setup
4. Environments & Configuration
5. Docker & Compose (Dev vs Prod)
6. Database & Alembic Migrations
7. Task Runner (./task)
8. Testing Strategy
9. CI/CD Pipelines
10. Security & Secrets Management
11. Backups & Maintenance Jobs
12. Observability & Logging
13. Data Protection & GDPR (incl. Scraping)
14. API Guidelines (FastAPI/Flask)
15. Production Readiness Checklist
16. Troubleshooting Guide
17. Glossary
18. Roadmap Snapshot
19. Contribution Workflow

---

## 1) Project Overview
**Detecktiv.io** is a UK IT sales intelligence platform. We’re building a multi‑tenant SaaS with an initial MVP focused on:
- A Postgres database with structured migrations
- A Python API (FastAPI) to read/write data
- Companies House integration and basic web scraping (phase 2–3)
- CI/CD with quality and security gates from day one

**Guiding principles**
- Ship working software early; prefer simple, documented solutions
- Safety first: secrets hygiene, least privilege, respect robots.txt, and GDPR
- Add tests and logging with every feature

---

## 2) Architecture & Stack
**Tech**: Python (FastAPI/Flask), Postgres, Docker Compose, Alembic, Pytest, pre‑commit, Trivy/CodeQL.

**High‑level diagram**
```
[ Client ] → [ API container ] → [ Postgres container ]
                        ↓
                     [ Logs ]
```

**Key directories**
- `app/` — API application (routers, services, schemas)
- `db/` — Alembic config and migrations
- `scripts/` — backups, maintenance, task runner helpers
- `docs/` — documentation

---

## 3) Local Development Setup
### Prerequisites
- Docker Desktop (or Docker Engine + Compose)
- Python 3.13 + pip
- PowerShell (Windows) or Bash/Zsh (for Docker)

### First‑time setup
1. **Clone repo** and create env files
   ```sh
   cp .env.example .env
   cp .env.docker.example .env.docker  # if present; otherwise create
   ```
2. **Set strong credentials** in `.env` (never commit real secrets).
3. **Start stack**
   ```powershell
   .\task up
   # or: docker compose up -d
   ```
4. **Run migrations** (if not auto‑run by entrypoint)
   ```powershell
   .\task migrate
   ```
5. **Open DB admin (dev only)**: http://localhost:5050 (pgAdmin)
6. **Run API locally**
   ```powershell
   .\task api
   # then check: http://localhost:8000/health
   ```

### Common commands
```powershell
.\task status     # show containers
.\task logs       # tail service logs
.\task psql       # psql shell inside DB container
.\task test       # run pytest
.\task backup     # on-demand DB backup
.\task restore-latest  # destructive: restore latest backup
```

---

## 4) Environments & Configuration
### Environment variables
Minimal set (dev):
```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=strong-dev-password
POSTGRES_DB=detecktiv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

PGADMIN_DEFAULT_EMAIL=dev@example.com
PGADMIN_DEFAULT_PASSWORD=strong-pgadmin-pass
```

### Secrets hygiene
- **Never commit** real secrets. Use `.env.example` as template.
- For CI: store secrets in GitHub Actions **encrypted secrets**.
- For prod: use a secrets manager (AWS Secrets Manager, Doppler, Vault, etc.).

### Config loading (API)
- Prefer `pydantic-settings` (FastAPI) or `python-dotenv` fallback.
- Validate on startup; fail fast if required vars missing.

---

## 5) Docker & Compose (Dev vs Prod)
### Dev compose
- Services: `postgres`, `pgadmin`, `api`
- Published ports: `5432` (DB), `5050` (pgAdmin), `8000` (API)

### Prod compose overlay
- **Do not** publish Postgres to host; API connects over the internal network.
- **Omit** pgAdmin from prod.

Run prod overlay:
```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Healthchecks**
- Postgres: `pg_isready`
- API: `GET /health` returns 200 JSON

---

## 6) Database & Alembic Migrations
### Connection
- Driver: `psycopg2` or `psycopg[binary]`
- DSN format: `postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME` (URL‑encode special chars)

### Alembic layout
- `alembic.ini` at repo root (or `ALEMBIC_CONFIG` env points to it)
- `db/migrations/versions/*.py` — ordered revisions

### Common flows
```powershell
.\task make-migration "create users table"
# edit migration file if needed
.\task migrate

.\task downgrade   # rolls back one revision (careful!)
.\task db-current  # show current DB revision
```

### Best practices
- Keep migrations **small and reversible**
- Idempotent data migrations (use UPSERT / `on conflict do nothing`)
- Gate **auto‑migrate on boot** via env (`RUN_MIGRATIONS_ON_BOOT=1` in dev only)

---

## 7) Task Runner (./task)
The PowerShell task runner wraps common Docker and DB actions with consistent logging and error handling.

Key tasks (highlights):
- `up`, `down`, `restart`, `status`, `logs`
- `psql`, `backup`, `restore-latest`
- `migrate`, `make-migration`, `autogen-migration`, `downgrade`, `db-stamp`, `db-current`
- `seed`, `test`, `api`, `lint`, `scan-secrets`

> Tip: Prefer **service names** with `docker compose exec -T postgres ...` instead of hard‑coded container names for portability.

---

## 8) Testing Strategy
### Levels
- **Unit tests** (pure Python; no DB)
- **Integration tests** (DB container; use transactions + rollback per test)
- **API tests** (FastAPI `TestClient`; hit `/health`, `/companies`, etc.)

### Pytest fixtures (pattern)
- `db_session` fixture opens a transaction for each test and rolls back
- `client` fixture provides a test client with dependency overrides

### Running tests
```powershell
.\task test
# or
python -m pytest -q
```

### Rules
- No external network calls in default test run
- Mark slow/integration tests (e.g., `@pytest.mark.db`) and run selectively

---

## 9) CI/CD Pipelines
### Typical stages
1. **Lint & format & secret scan** (pre‑commit, detect‑secrets)
2. **Unit/integration tests** with Postgres service
3. **Security scanning** (CodeQL, Trivy)
4. **Migrations check** (upgrade/downgrade round‑trip)
5. **Build & publish image** (future)
6. **Deploy & run migrations** (job or entrypoint flag)

### Tips
- Pin dependency versions (`requirements.txt`, `requirements-dev.txt`)
- Cache pip to speed up runs
- Upload JUnit XML for test reporting

---

## 10) Security & Secrets Management
### Baseline
- Pre‑commit hooks for Black, Flake8, detect‑secrets
- CI: CodeQL (code), Trivy (dependencies & filesystem)

### Additions to adopt
- **Bandit** Python security linter in pre‑commit & CI
- **Rate limiting** at API layer (e.g., `slowapi`) to defend against abuse
- **CORS**: default deny; allow known origins per env
- **Dependency review**: Dependabot PRs

### Handling secrets
- Local: `.env` (git‑ignored) + `.env.example`
- CI: GitHub Secrets
- Prod: a dedicated secrets manager + least privilege IAM

### Sensitive data in logs
- Never log PII or secrets; mask tokens; scrub query strings
- Structured JSON logging with log levels and trace IDs

---

## 11) Backups & Maintenance Jobs
### On‑demand backups
- Logical backup with `pg_dump` (plain SQL) into `./backups/YYYY/MM/DD/*.sql`

### Nightly maintenance
- `VACUUM (ANALYZE)`
- Reset `pg_stat_statements`
- Optional reindex weekly

### Restore flow
1. Terminate active sessions
2. Drop and recreate database
3. Restore from latest `.sql`

> Always test restore in a non‑prod environment and keep retention/pruning policies.

---

## 12) Observability & Logging
- **API logs**: JSON with request ID, user/tenant (when available), status code, duration
- **DB metrics**: enable `pg_stat_statements`; consider Prometheus + Grafana later
- **Health endpoints**: `/health` (shallow), `/readiness` (DB ping + pending migrations)

---

## 13) Data Protection & GDPR (incl. Scraping)
### Lawful basis & data minimisation
- Capture only data necessary for sales intelligence use‑case
- Document lawful basis (legitimate interests or consent, as applicable)

### Data subject rights
- Build support to **export**, **rectify**, and **delete** an account’s data
- Track data provenance (e.g., Companies House vs web scrape)

### Retention & encryption
- Define retention per data class; purge on schedule
- Encrypt at rest (disk); consider column‑level or application‑level encryption for sensitive PII

### Web scraping
- Respect **robots.txt** and site terms; throttle requests; handle rate limits
- Identify yourself with a UA; backoff on errors; avoid collecting sensitive categories

> Add a `PRIVACY.md` and, later, a DPA/Record of Processing Activities.

---

## 14) API Guidelines (FastAPI/Flask)
### Project layout (suggested)
```
app/
  main.py           # create_app(), include_routers, middleware, logging
  api/
    __init__.py
    health.py       # GET /health
    companies.py    # /companies endpoints
  core/
    config.py       # settings via pydantic
    db.py           # session management
    logging.py      # JSON logger, request IDs
  models/
  schemas/
  services/
```

### Health endpoint
```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}
```

### Error handling
- Use global exception handlers to return consistent JSON structures
- Validate request bodies with Pydantic models; never trust input

### Security headers
- Add `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, HSTS (when behind TLS)

---

## 15) Production Readiness Checklist
- [ ] Separate **dev** vs **prod** compose; Postgres not exposed in prod
- [ ] Auto‑migrate gated behind env flag (or separate migration job)
- [ ] Strong passwords/keys from a secrets manager
- [ ] Backups tested; restore drill documented
- [ ] Health/readiness probes wired into orchestrator
- [ ] Rate limits & CORS configured
- [ ] Logs are structured; error alerting in place
- [ ] GDPR basics: privacy doc, retention policy, data subject flows

---

## 16) Troubleshooting Guide
**pgAdmin leaking PG_* envs**
- Close the shell and open a fresh one; check `env | grep PG_`

**Containers won’t start**
- `docker compose logs -f` and look for port conflicts
- Ensure `.env` has required vars; no stray quotes

**Migrations fail**
- Check current revision: `.\task db-current`
- Recreate a clean dev DB if needed: backup → drop → migrate → restore sample

**Backups using wrong container name**
- Switch scripts to `docker compose exec -T postgres ...` service name pattern

---

## 17) Glossary
- **Alembic** — Database migration tool for SQLAlchemy
- **Baseline** — Initial Alembic revision stamped to DB
- **CI/CD** — Continuous Integration / Continuous Delivery
- **PG** — PostgreSQL database server

---

## 18) Roadmap Snapshot
- Phase 1: Single‑tenant API + DB + basic insights
- Phase 2: Companies House API integration
- Phase 3: Basic web scraping with legal guardrails
- Phase 4: Database design refinements; indexes and constraints
- Phase 5: User auth (JWT/cookies), per‑tenant isolation plan
- Phase 6: Multi‑tenancy conversion (schema or row‑level security)
- Phase 7: AI‑powered insights (safe prompt logging & evals)

---

## 19) Contribution Workflow
1. Branch from `main`: `feat/<topic>`
2. Commit with Conventional Commits
3. Run pre‑commit locally (`.\task lint`) and tests (`.\task test`)
4. Open PR; ensure CI is green
5. On merge, deployments/migrations run per environment

---

### Appendices
**A) Sample docker-compose.prod.yml**
```yaml
services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

  api:
    build: .
    restart: unless-stopped
    env_file:
      - .env
      - .env.docker
    environment:
      ALEMBIC_CONFIG: /app/alembic.ini
      RUN_MIGRATIONS_ON_BOOT: "0"
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8000:8000"
```

**B) Pytest DB transaction fixture (pattern)**
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def db_session():
    engine = create_engine("postgresql+psycopg2://postgres:password@localhost:5432/detecktiv")
    connection = engine.connect()
    transaction = connection.begin()

    Session = sessionmaker(bind=connection)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
```

**C) PRIVACY.md (starter)**
```
# Privacy & Data Protection (Draft)
- Purpose: IT sales intelligence for UK B2B
- Lawful basis: legitimate interests (document balancing test)
- Data categories: company metadata; business contact data (work emails), public registry data
- Retention: define per data class; automatic pruning jobs
- Data subject rights: contact privacy@detecktiv.io; export/delete within 30 days
- Processors/sub‑processors: list and DPAs on file
- Security: encryption at rest; least privilege access; logging & monitoring
```

**D) API Security Checklist**
- [ ] Input validate all request bodies & query params
- [ ] AuthN/AuthZ in middleware; deny by default
- [ ] Rate limit per IP/user/tenant
- [ ] CORS: allowlist origins
- [ ] Error responses do not leak internals
- [ ] Secrets come only from env/manager, not code
- [ ] Logs exclude PII and secrets
- [ ] Dependencies are scanned and pinned

