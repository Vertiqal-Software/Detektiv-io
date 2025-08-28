# scripts/verify_schema.py
import os
from sqlalchemy import create_engine, text, inspect

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def db_url():
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "detecktiv")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd  = os.getenv("POSTGRES_PASSWORD")
    ssl  = os.getenv("POSTGRES_SSLMODE", "disable")
    if not pwd:
        raise RuntimeError("POSTGRES_PASSWORD not set (put it in .env or export it in your shell).")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}?sslmode={ssl}"

def main():
    url = db_url()
    print("[info] DB URL:", url.split("://")[0] + "://***")

    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as conn:
        insp = inspect(conn)

        tables = sorted(insp.get_table_names())
        print("\n[Tables]")
        print(tables)

        # Default tenant (only if table exists)
        if "tenants" in tables:
            tid = conn.execute(text("SELECT id FROM tenants WHERE tenant_key='default'")).scalar()
            print("\n[Default tenant]")
            print("default tenant id:", tid)
        else:
            print("\n[Default tenant]")
            print("tenants table is missing")

        if "companies" in tables:
            cols = insp.get_columns("companies")
            col_map = {c["name"]: c for c in cols}
            print("\n[companies columns]")
            for c in ("id","tenant_id","company_number","name","status","incorporated_on","jurisdiction","last_accounts","created_at","updated_at"):
                if c in col_map:
                    print(f" - {c}: nullable={col_map[c]['nullable']}")
                else:
                    print(f" - {c}: MISSING")

            print("\n[companies FKs]")
            for fk in insp.get_foreign_keys("companies"):
                print(" -", fk.get("name"), "->", fk.get("referred_table"), fk.get("constrained_columns"))

            print("\n[companies indexes]")
            for ix in insp.get_indexes("companies"):
                print(" -", ix["name"], ix["column_names"])

            print("\n[companies unique constraints]")
            for uc in insp.get_unique_constraints("companies"):
                print(" -", uc.get("name"), uc.get("column_names"))

        if "source_events" in tables:
            print("\n[source_events indexes]")
            for ix in insp.get_indexes("source_events"):
                print(" -", ix["name"], ix["column_names"])

    print("\n[OK] verification done")

if __name__ == "__main__":
    main()
