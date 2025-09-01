# scripts/verify_schema.py
import os
from sqlalchemy import create_engine, text, inspect

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def db_url() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "detecktiv")
    ssl = os.getenv("POSTGRES_SSLMODE", "disable")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}?sslmode={ssl}"


def show_schema(conn, schema: str):
    print(f"\n[Tables in {schema}]")
    insp = inspect(conn)
    try:
        tables = sorted(insp.get_table_names(schema=schema))
        print(tables)
    except Exception as e:
        print(f"  (error listing tables: {e})")
        return

    for t in tables:
        print(f"\n[{schema}.{t} columns]")
        try:
            for c in insp.get_columns(t, schema=schema):
                print(f" - {c['name']}: nullable={c['nullable']}")
        except Exception as e:
            print(f"  (error reading columns: {e})")


def main():
    url = db_url()
    pw = os.getenv("POSTGRES_PASSWORD") or ""
    masked = url.replace(pw, "***") if pw else url
    print("[info] URL:", masked)

    schema = (
        os.getenv("ALEMBIC_SCHEMA")
        or os.getenv("POSTGRES_SCHEMA")
        or os.getenv("DB_SCHEMA")
        or "app"
    )

    eng = create_engine(url, pool_pre_ping=True, future=True)
    with eng.connect() as conn:
        # Match Alembic behavior
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.execute(text(f'SET search_path TO "{schema}", public'))

        db, cur_schema, host, port = conn.execute(
            text(
                "select current_database(), current_schema(), inet_server_addr(), inet_server_port()"
            )
        ).one()
        spath = conn.execute(text("SHOW search_path")).scalar()
        print(
            f"[info] Connected -> db={db}, current_schema={cur_schema}, host={host}, port={port}"
        )
        print(f"[info] search_path: {spath}")

        # Show both target schema and public
        show_schema(conn, schema)
        show_schema(conn, "public")

        # Default tenant check in target schema
        print(f"\n[Default tenant in {schema}] ", end="")
        exists = conn.execute(
            text("select to_regclass(:qname)"), {"qname": f"{schema}.tenants"}
        ).scalar()
        if exists:
            tid = conn.execute(
                text(f"SELECT id FROM {schema}.tenants WHERE tenant_key='default'")
            ).scalar()
            print("id:", tid)
        else:
            print("table missing")

    print("\n[OK] verification done")


if __name__ == "__main__":
    main()
