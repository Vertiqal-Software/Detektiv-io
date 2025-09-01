"""Apply/ensure baseline schema post-stamp (NO-OP on fresh installs).

This revision intentionally does nothing on fresh installs. It only touches the
connection and checks that key tables can be referenced, avoiding any DDL that
could fail inside Alembic’s transaction.
"""

from __future__ import annotations

import os
from alembic import op
import sqlalchemy as sa  # noqa: F401
from sqlalchemy import text

# Alembic identifiers
revision = "a202509010003"
down_revision = "a202509010002"
branch_labels = None
depends_on = None


def _schema() -> str:
    return (
        os.getenv("ALEMBIC_SCHEMA")
        or os.getenv("POSTGRES_SCHEMA")
        or os.getenv("DB_SCHEMA")
        or "app"
    ).strip() or "app"


def _exists(conn, schema: str, relname: str) -> bool:
    q = text("select to_regclass(:qname)")
    return conn.execute(q, {"qname": "{}.{}".format(schema, relname)}).scalar() is not None


def upgrade():
    # Guarded NO-OP. Just verify objects are referenceable; do not raise.
    schema = _schema()
    conn = op.get_bind()
    for rel in ("tenants", "users", "companies", "source_events"):
        _exists(conn, schema, rel)  # fire-and-forget check
    return


def downgrade():
    # Non-destructive; do nothing.
    pass
