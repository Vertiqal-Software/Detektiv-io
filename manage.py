#!/usr/bin/env python3
"""
Minimal manage.py wrapper for common ops used in README/CI.
No new deps: stdlib + subprocess only.
"""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

def _run(cmd: list[str]) -> int:
    print("→", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO_ROOT), env=os.environ.copy())

def _alembic(*args: str) -> int:
    # Delegates to "python -m alembic ..." so it works in venv/CI
    return _run([sys.executable, "-m", "alembic", *args])

def cmd_db_current() -> int:
    return _alembic("current")

def cmd_db_upgrade() -> int:
    return _alembic("upgrade", "head")

def cmd_db_downgrade_one() -> int:
    return _alembic("downgrade", "-1")

def cmd_check_db() -> int:
    # Non-fatal connectivity probe (mirrors test expectations)
    from sqlalchemy import create_engine, text  # type: ignore

    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "")
    h = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "detecktiv")
    url = f"postgresql+psycopg2://{u}:{p}@{h}:{port}/{db}?sslmode=disable"
    safe_url = url.replace(p, "***") if p else url
    print("SQLAlchemy URL:", safe_url)

    eng = create_engine(url, future=True)
    with eng.connect() as c:
        print("select 1 ->", c.execute(text("select 1")).scalar_one())
    return 0

def cmd_db_seed() -> int:
    # Delegate to PowerShell task if available; otherwise no-op
    ps_task = REPO_ROOT / "task.ps1"
    if ps_task.exists():
        return _run(["pwsh", "-NoProfile", "-File", str(ps_task), "seed"])
    print("Seed task not available; skipping.")
    return 0

def main() -> int:
    actions = {
        "db-current": cmd_db_current,
        "db-upgrade": cmd_db_upgrade,
        "db-downgrade-one": cmd_db_downgrade_one,
        "check-db": cmd_check_db,
        "db-seed": cmd_db_seed,
    }
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print("manage.py [db-current|db-upgrade|db-downgrade-one|check-db|db-seed]")
        return 0
    fn = actions.get(sys.argv[1])
    if not fn:
        print(f"Unknown command: {sys.argv[1]}")
        return 1
    return fn()

if __name__ == "__main__":
    raise SystemExit(main())
