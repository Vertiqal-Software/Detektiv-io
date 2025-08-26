\# Detecktiv.io — Developer Guide



> Python/FastAPI + Postgres stack with Alembic migrations, Dockerized dev, and CI/CD.



\## Quickstart



\### Prereqs

\- Docker Desktop

\- Python 3.13 + pip

\- PowerShell (Windows) or a shell (for Docker commands)



\### 1) Configure env

Copy `.env.example` to `.env` and set strong credentials. For local Docker:

```sh

\# minimal example; adjust as needed

POSTGRES\_USER=postgres

POSTGRES\_PASSWORD=changeme

POSTGRES\_DB=detecktiv

POSTGRES\_HOST=localhost

POSTGRES\_PORT=5432



PGADMIN\_DEFAULT\_EMAIL=you@example.com

PGADMIN\_DEFAULT\_PASSWORD=another-strong-password



