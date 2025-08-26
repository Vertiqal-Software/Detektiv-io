import os
import sys
import time
from pathlib import Path
import subprocess

import psycopg2
import pytest


def _wait_for_db(timeout=30):
    """Wait for the local Postgres specified by env vars to accept connections."""
    u = os.getenv("POSTGRES_USER", "postgres")
    p = os.getenv("POSTGRES_PASSWORD", "")
    h = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "detecktiv")

    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            with psycopg2.connect(
                user=u, password=p, host=h, port=port, dbname=db, sslmode="disable"
            ):
                return
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    raise RuntimeError(f"DB not ready after {timeout}s: {last_err}")


@pytest.fixture(scope="session", autouse=True)
def apply_migrations_before_tests():
    """
    Automatically apply Alembic migrations to HEAD before the test session starts.
    Uses the same env vars that the tests (and app) already rely on.
    """
    # 1) Ensure DB is reachable
    _wait_for_db(timeout=60)

    # 2) Run Alembic upgrade to head from the repo root
    repo_root = Path(__file__).resolve().parents[1]
    ini = repo_root / "alembic.ini"
    if not ini.exists():
        raise FileNotFoundError(f"alembic.ini not found at {ini}")

    env = os.environ.copy()
    cmd = [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"]
    result = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to run migrations before tests.\n"
            f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )
