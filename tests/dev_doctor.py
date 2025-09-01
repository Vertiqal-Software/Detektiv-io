# scripts/dev_doctor.py
import os, sys, traceback
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command
from sqlalchemy import create_engine, text

def _db_url_from_env():
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "detecktiv")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD", "")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}?sslmode=disable"

def check_db():
    url = _db_url_from_env()
    print(f"[info] DB URL: {url.split('://')[0]}://***")
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as c:
        v = c.execute(text("select 1")).scalar()
        print("[ok] DB connect test:", v == 1)

def check_heads(cfg):
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_revisions("heads"))
    ids = [h.revision for h in heads]
    if len(ids) == 1:
        print("[ok] single head:", ids[0])
    else:
        print("[warn] multiple heads:", ", ".join(ids))
    return ids

def try_upgrade(cfg, target="head"):
    try:
        command.upgrade(cfg, target)
        print(f"[ok] alembic upgrade {target}")
        return True
    except Exception as e:
        print(f"[err] alembic upgrade {target} failed: {e.__class__.__name__}: {e}")
        traceback.print_exc()
        return False

def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    cfg = Config("alembic.ini")

    print("[step] DB check")
    check_db()

    print("[step] heads check")
    heads = check_heads(cfg)

    if len(heads) > 1:
        print("[hint] run:  python -m alembic merge -m \"merge heads\" " + " ".join(heads))
        return 2

    print("[step] upgrade head")
    ok = try_upgrade(cfg, "head")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
