import os
import time
import psycopg2


def _dsn_from_env():
    user = os.getenv("POSTGRES_USER", "postgres")
    pw = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "detecktiv")
    return f"dbname={db} user={user} password={pw} host={host} port={port}"


def test_select_1():
    # a couple retries in CI just in case
    dsn = _dsn_from_env()
    last_err = None
    for _ in range(10):
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("select 1;")
                    assert cur.fetchone()[0] == 1
            return
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    raise last_err
