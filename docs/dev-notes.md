\# Dev Notes



\## Required tools

\- Docker Desktop

\- Python 3.13 + pip

\- Git, GitHub CLI (optional)



\## Common tasks

\- Start/stop: `.\\task up`, `.\\task down`

\- Logs: `.\\task logs`

\- DB shell: `.\\task psql`

\- Backups: `.\\task backup` / restore `.\\task restore-latest`

\- Migrations: `.\\task make-migration "message"`, edit the file, `.\\task migrate`



\## Migrations

\- Alembic config loads `.env` and URL-encodes creds (handles `@` etc.).

\- CI workflow `tests.yml` boots a Postgres service, applies migrations, runs tests.



\## Conventions

\- Keep `.env` out of Git; provide `.env.example`.

\- Add new scripts under `scripts/` and new tasks in `scripts/tasks.ps1`.

\- Prefer PRs; main is protected with required checks.



\## Troubleshooting

\- If pgAdmin injects `PG\*` env vars, open a fresh PowerShell before running tasks.

\- If `docker compose` vs `docker-compose` mismatch, the task runner auto-detects.



