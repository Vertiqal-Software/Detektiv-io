#!/usr/bin/env python3
"""
Force-set the Alembic stored revision directly in the DB (no psql needed),
with safety features:

- Supports: explicit revision id, "head", or "base"
- Validates the revision against your Alembic scripts (alembic.ini)
- Auto-widens app.alembic_version.version_num to VARCHAR(255) if too short
- Normalizes the table to a single row with the target revision
- Removes legacy public.alembic_version

Usage:
  python db/migrations/_admin_set_revision.py <revision_id | head | base>
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

# Optional: verify revisions via Alembic config/scripts
try:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    _ALEMBIC_AVAILABLE = True
except Exception:
    _ALEMBIC_AVAILABLE = False

# --- Match env.py: make project root importable + load .env -------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass


def _schema() -> str:
    return (os.getenv("ALEMBIC_SCHEMA") or os.getenv("POSTGRES_SCHEMA") or os.getenv("DB_SCHEMA") or "app").strip() or "app"


def _alembic_ini_path() -> str:
    """
    Resolve alembic.ini path similarly to how tooling runs it.
    Prefers ALEMBIC_CONFIG if set, else repo-root alembic.ini.
    """
    return os.getenv("ALEMBIC_CONFIG") or str(PROJECT_ROOT / "alembic.ini")


def _mask_url(url: str) -> str:
    try:
        if "://" in url and "@" in url:
            head, tail = url.split("://", 1)
            creds, rest = tail.split("@", 1)
            user = creds.split(":", 1)[0]
            return f"{head}://{user}:***@{rest}"
        return url
    except Exception:
        return url


def _database_url() -> str:
    """
    Resolve DB URL in this order (mirrors env.py behavior):

    1) app.core.config.settings.get_database_url() if importable
    2) $DATABASE_URL if set
    3) Build from POSTGRES_* env vars
    """
    # 1) App settings
    try:
        from app.core.config import settings  # type: ignore
        url = settings.get_database_url()
        if url:
            return url
    except Exception:
        pass

    # 2) DATABASE_URL env
    dburl = os.getenv("DATABASE_URL")
    if dburl:
        return dburl

    # 3) Fallback to POSTGRES_* envs
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "detecktiv")
    sslmode = os.getenv("POSTGRES_SSLMODE", "disable")
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{database}?sslmode={sslmode}"
    )


def _versions_dir() -> Path:
    # db/migrations/versions relative to this file
    return Path(__file__).resolve().parent / "versions"


def _known_revisions_from_files() -> set[str]:
    """
    Fallback validator: parse revision IDs from migration files when Alembic isn't importable.
    Looks for: revision = "...."
    """
    revs: set[str] = set()
    pat = re.compile(r'^\s*revision\s*=\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE | re.MULTILINE)
    vdir = _versions_dir()
    if not vdir.exists():
        return revs
    for f in vdir.glob("*.py"):
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            m = pat.search(txt)
            if m:
                revs.add(m.group(1))
        except Exception:
            pass
    return revs


def _print_alembic_script_location(cfg: Config | None) -> None:
    try:
        if not cfg:
            return
        script = ScriptDirectory.from_config(cfg)
        print(f"Alembic script_location: {script.dir}")
    except Exception:
        pass


def _ensure_version_table_and_widen(engine, schema: str, needed_len: int) -> None:
    with engine.begin() as conn:
        # Ensure schema + version table
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS "{schema}"."alembic_version" '
                f"(version_num varchar(32) NOT NULL)"
            )
        )

        # Check current column definition
        row = conn.execute(
            text(
                """
                SELECT data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = 'alembic_version'
                  AND column_name = 'version_num'
                """
            ),
            {"schema": schema},
        ).first()

        # If VARCHAR and too short, widen to 255
        if row:
            data_type = (row[0] or "").lower()
            char_len = row[1]
            if "character varying" in data_type or "varchar" in data_type:
                if char_len is None or (needed_len and char_len < max(needed_len, 64)):
                    conn.execute(
                        text(
                            f'ALTER TABLE "{schema}"."alembic_version" '
                            f"ALTER COLUMN version_num TYPE varchar(255)"
                        )
                    )
            # If it's TEXT, we're fine; if something else, still try to widen:
            elif char_len is not None and (needed_len and char_len < max(needed_len, 64)):
                conn.execute(
                    text(
                        f'ALTER TABLE "{schema}"."alembic_version" '
                        f"ALTER COLUMN version_num TYPE varchar(255)"
                    )
                )

        # Drop legacy public version table if present
        has_public = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema='public' AND table_name='alembic_version'"
                ")"
            )
        ).scalar_one()
        if has_public:
            conn.execute(text("DROP TABLE public.alembic_version"))


def _resolve_target_revision(arg: str) -> str | None:
    """
    Resolve 'head'/'base'/explicit revision id against Alembic scripts.
    Returns:
      - concrete revision id string (for head or explicit)
      - None if 'base' (meaning empty table = base)
    Exits with code 2 if validation fails.
    """
    arg_in = (arg or "").strip()
    arg_lc = arg_in.lower()
    ini_path = _alembic_ini_path()

    # base means: zero rows in version table
    if arg_lc == "base":
        return None

    # Prefer alembic API if available
    if _ALEMBIC_AVAILABLE:
        try:
            cfg = Config(ini_path)
        except Exception as ex:
            print(f"[WARN] Could not load alembic.ini at {ini_path}: {ex}")
            cfg = None

        _print_alembic_script_location(cfg)

        if cfg:
            try:
                script = ScriptDirectory.from_config(cfg)
            except Exception as ex:
                print(f"[WARN] Could not load Alembic ScriptDirectory: {ex}")
                script = None
        else:
            script = None

        if script:
            if arg_lc in ("head", "heads"):
                heads = script.get_heads()
                if not heads:
                    print("[ERROR] No heads found in Alembic script directory.")
                    sys.exit(2)
                if len(heads) > 1:
                    print(f"[ERROR] Multiple heads found: {heads}. Please specify one explicitly.")
                    sys.exit(2)
                return heads[0]

            # explicit id (validate exists; allow short prefix)
            try:
                rev = script.get_revision(arg_in)
                if rev is None:
                    raise ValueError("not found")
                return rev.revision
            except Exception:
                try:
                    short = arg_in[:12] if len(arg_in) > 12 else arg_in
                    rev = script.get_revision(short)
                    if rev:
                        return rev.revision
                except Exception:
                    pass
                print(f"[ERROR] Revision '{arg_in}' not found in Alembic scripts at {ini_path}.")
                try:
                    print(f"[HINT] Current head: {script.get_current_head()}")
                except Exception:
                    pass
                sys.exit(2)

        # If we reach here, Alembic is available but config/scripts couldn't be loaded.
        # Fall back to scanning files.
        print("[WARN] Using file-scan fallback to validate revision.")
        known = _known_revisions_from_files()
        if arg_lc in ("head", "heads"):
            if not known:
                print("[ERROR] Cannot resolve 'head' without Alembic script directory.")
                sys.exit(2)
            # head heuristic: use max lexicographically (only for fallback; better to pass explicit)
            try:
                return sorted(known)[-1]
            except Exception:
                print("[ERROR] Failed to resolve head from files.")
                sys.exit(2)
        if arg_in not in known:
            print(f"[ERROR] Revision '{arg_in}' not found in versions/ (fallback).")
            print(f"[HINT] Known: {sorted(known)}")
            sys.exit(2)
        return arg_in

    # Alembic not importable: accept explicit ids or validate via files
    known = _known_revisions_from_files()
    if arg_lc in ("head", "heads"):
        if not known:
            print("[ERROR] Alembic not available and no revisions discovered in versions/. Pass an explicit revision id.")
            sys.exit(2)
        try:
            return sorted(known)[-1]
        except Exception:
            print("[ERROR] Failed to resolve head from files.")
            sys.exit(2)
    # explicit id
    if not arg_in or len(arg_in) > 255:
        print("[ERROR] Invalid revision id.")
        sys.exit(2)
    if known and arg_in not in known:
        print(f"[ERROR] Revision '{arg_in}' not found in versions/.")
        print(f"[HINT] Known: {sorted(known)}")
        sys.exit(2)
    return arg_in


def main():
    if len(sys.argv) != 2:
        print("Usage: python db/migrations/_admin_set_revision.py <revision_id | head | base>")
        sys.exit(2)

    requested = sys.argv[1]
    schema = _schema()
    url = _database_url()

    print(f"DB URL: { _mask_url(url) }")
    print(f"Target schema: {schema}")
    print(f"Alembic ini: {_alembic_ini_path()}")

    target_rev = _resolve_target_revision(requested)
    if target_rev is None:
        print("Target: base (no stored revision row)")
    else:
        if len(target_rev) > 255:
            print(f"[ERROR] Target revision exceeds 255 characters (got {len(target_rev)}).")
            sys.exit(2)
        print(f"Target revision: {target_rev}")

    # Create engine with robust error messaging
    try:
        engine = create_engine(url, future=True)
    except Exception as e:
        print(f"[ERROR] Could not create database engine: {e}")
        sys.exit(4)

    # Ensure table exists and version_num is wide enough for the target rev
    need_len = len(target_rev) if target_rev else 0
    try:
        _ensure_version_table_and_widen(engine, schema, needed_len=need_len)
    except Exception as e:
        print(f"[ERROR] Failed ensuring version table/widening: {e}")
        sys.exit(5)

    # Normalize the version table and set desired revision
    try:
        with engine.begin() as conn:
            before = conn.execute(text(f'SELECT version_num FROM "{schema}"."alembic_version"')).scalars().all()

            # clean to zero or single row
            conn.execute(text(f'DELETE FROM "{schema}"."alembic_version"'))

            if target_rev is not None:
                conn.execute(
                    text(
                        f'INSERT INTO "{schema}"."alembic_version"(version_num) '
                        f"VALUES (:rev)"
                    ),
                    {"rev": target_rev},
                )

            after = conn.execute(text(f'SELECT version_num FROM "{schema}"."alembic_version"')).scalars().all()

        # Verify
        if target_rev is None:
            if len(after) != 0:
                print(f"[ERROR] Expected empty version table for base, found: {after}")
                sys.exit(6)
            print(f"[OK] {schema}.alembic_version cleared (base).")
        else:
            if after != [target_rev]:
                print(f"[ERROR] Stored revision mismatch: {after} != {target_rev}")
                sys.exit(6)
            print(f"[OK] {schema}.alembic_version set to {target_rev}.")
        print(f"Before: {before or '[]'}")
        print(f"After : {after or '[]'}")

    except Exception as e:
        print(f"[ERROR] Failed to set revision: {e}")
        sys.exit(7)


if __name__ == "__main__":
    main()
