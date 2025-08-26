"""bootstrap companies table if missing, and ensure unique index

Revision ID: a2f9e70c0e4a
Revises: 9c3b1a2f4d0a
Create Date: 2025-08-26

This migration is intentionally defensive:
- If the table doesn't exist (e.g., earlier migrations were skipped
  by a flaky CI run), it creates the table with the expected shape.
- It only creates the unique index when the table exists.
- It can optionally seed a couple of rows when the table is empty.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a2f9e70c0e4a"  # pragma: allowlist secret
down_revision = "9c3b1a2f4d0a"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Create table if it somehow doesn't exist yet.
    conn.execute(
        sa.text(
            """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'companies'
          ) THEN
            CREATE TABLE public.companies (
              id BIGSERIAL PRIMARY KEY,
              name TEXT NOT NULL,
              website TEXT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            -- helpful for filtering
            CREATE INDEX IF NOT EXISTS ix_companies_name ON public.companies (name);
          END IF;
        END $$;
        """
        )
    )

    # 2) Ensure the unique index on name exists, but ONLY if the table exists.
    conn.execute(
        sa.text(
            """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'companies'
          ) THEN
            -- Safe: IF NOT EXISTS avoids duplicate-index errors across re-runs.
            CREATE UNIQUE INDEX IF NOT EXISTS ux_companies_name
            ON public.companies (name);
          ELSE
            RAISE NOTICE 'companies table missing; skipping unique index creation';
          END IF;
        END $$;
        """
        )
    )

    # 3) (Optional) Seed a couple of rows if the table is empty.
    #    This keeps behavior aligned with "bootstrap" intent but is still idempotent.
    conn.execute(
        sa.text(
            """
        INSERT INTO public.companies (name, website)
        SELECT v.name, v.website
        FROM (VALUES
            ('Acme Ltd', 'https://acme.example'),
            ('Globex Corp', 'https://globex.example')
        ) AS v(name, website)
        WHERE NOT EXISTS (SELECT 1 FROM public.companies)
        ON CONFLICT DO NOTHING;
        """
        )
    )


def downgrade() -> None:
    # We don't drop data or indexes here to avoid surprising data loss on downgrade.
    # If you truly need to revert, you can drop the seed rows and/or index manually.
    pass
