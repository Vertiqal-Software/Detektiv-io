\# Detecktiv-io – Overview



\## What this is

\- Postgres + pgAdmin stack managed by Docker Compose

\- Git hygiene + pre-commit + secret scanning

\- CI (format/lint/secrets), security scans (CodeQL, Trivy), Dependabot

\- Database managed with Alembic migrations

\- Task runner (`.\\task …`) for daily commands



\## How it runs (local)

\- `.\\task up` brings up Postgres (port 5432) and pgAdmin (port 5050).

\- Credentials come from `.env` (see `.env.example`).

\- Migrations: `.\\task migrate` (Alembic -> HEAD).

\- Backups: scheduled daily (Task Scheduler) and on-demand `.\\task backup`.



\## Data flow (high level)

\- Application (future) will connect to Postgres using env vars.

\- Migrations define schema evolution.

\- Backups go to `backups/YYYY/MM/DD/\*.sql`.



\## Security \& compliance

\- Pre-commit hooks ensure format/lint/secrets scan before commits.

\- CI enforces checks on PRs.

\- CodeQL + Trivy scan code and dependencies.



