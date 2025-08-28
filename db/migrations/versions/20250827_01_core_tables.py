"""core tables (add-only, idempotent-ish)

Revision ID: 20250827_01_core_tables
Revises: a2f9e70c0e4a
Create Date: 2025-08-27
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20250827_01_core_tables"
down_revision = "a2f9e70c0e4a"
branch_labels = None
depends_on = None


# ---------- helpers ----------
def _insp(conn):
    return sa.inspect(conn)


def _has_table(conn, name: str) -> bool:
    try:
        return name in _insp(conn).get_table_names()
    except Exception:
        return False


def _has_column(conn, table: str, col: str) -> bool:
    try:
        cols = [c["name"] for c in _insp(conn).get_columns(table)]
        return col in cols
    except Exception:
        return False


def _index_names(conn, table: str) -> set[str]:
    try:
        return {idx["name"] for idx in _insp(conn).get_indexes(table)}
    except Exception:
        return set()


def _unique_constraints_by_cols(conn, table: str) -> set[tuple[str, ...]]:
    try:
        uqs = set()
        for uc in _insp(conn).get_unique_constraints(table):
            cols = tuple(uc.get("column_names") or ())
            if cols:
                uqs.add(cols)
        return uqs
    except Exception:
        return set()


def _fk_exists(
    conn, table: str, constrained_cols: tuple[str, ...], referred_table: str
) -> bool:
    try:
        for fk in _insp(conn).get_foreign_keys(table):
            if (
                tuple(fk.get("constrained_columns") or ()) == constrained_cols
                and fk.get("referred_table") == referred_table
            ):
                return True
        return False
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()

    # ---------- tenants ----------
    if not _has_table(conn, "tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_key", sa.String(length=64), nullable=False, unique=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # Ensure a default tenant row is present (idempotent upsert)
    op.execute(
        sa.text(
            """
        INSERT INTO tenants (tenant_key, name)
        VALUES ('default', 'Default Tenant')
        ON CONFLICT (tenant_key) DO NOTHING
    """
        )
    )

    # We will need this for backfilling companies.tenant_id
    default_tenant_id = conn.execute(
        sa.text("SELECT id FROM tenants WHERE tenant_key = 'default'")
    ).scalar_one()

    # ---------- companies ----------
    if not _has_table(conn, "companies"):
        # Fresh create (includes tenant_id as NOT NULL with FK)
        op.create_table(
            "companies",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column(
                "tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False
            ),
            sa.Column("company_number", sa.String(length=16), nullable=False),
            sa.Column("name", sa.String(length=300), nullable=False),
            sa.Column("status", sa.String(length=50)),
            sa.Column("incorporated_on", sa.Date()),
            sa.Column("jurisdiction", sa.String(length=50)),
            sa.Column("last_accounts", sa.JSON()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "company_number",
                name="uq_companies_tenant_company_number",
            ),
        )
    else:
        # Table exists already. Ensure tenant_id is present and enforced safely.
        if not _has_column(conn, "companies", "tenant_id"):
            # 1) add nullable
            op.add_column(
                "companies", sa.Column("tenant_id", sa.Integer(), nullable=True)
            )
            # 2) backfill to default tenant  ✅ FIXED PARAM BINDING
            conn.execute(
                sa.text(
                    "UPDATE companies SET tenant_id = :tid WHERE tenant_id IS NULL"
                ),
                {"tid": default_tenant_id},
            )
            # 3) add FK if missing
            if not _fk_exists(conn, "companies", ("tenant_id",), "tenants"):
                op.create_foreign_key(
                    None, "companies", "tenants", ["tenant_id"], ["id"]
                )
            # 4) enforce NOT NULL
            op.alter_column("companies", "tenant_id", nullable=False)

    # Ensure expected company indexes / unique constraint exist regardless of table origin.
    if _has_table(conn, "companies"):
        comp_idx = _index_names(conn, "companies")
        comp_uqs = _unique_constraints_by_cols(conn, "companies")

        # Indexes
        if "ix_companies_tenant_id" not in comp_idx and _has_column(
            conn, "companies", "tenant_id"
        ):
            try:
                op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])
            except Exception:  # nosec B110
                pass

        if "ix_companies_company_number" not in comp_idx and _has_column(
            conn, "companies", "company_number"
        ):
            try:
                op.create_index(
                    "ix_companies_company_number", "companies", ["company_number"]
                )
            except Exception:  # nosec B110
                pass

        # Unique constraint on (tenant_id, company_number)
        # Check both column orderings as Alembic/DB may report in different order.
        need_uq = True
        if ("tenant_id", "company_number") in comp_uqs or (
            "company_number",
            "tenant_id",
        ) in comp_uqs:
            need_uq = False
        if (
            need_uq
            and _has_column(conn, "companies", "tenant_id")
            and _has_column(conn, "companies", "company_number")
        ):
            try:
                op.create_unique_constraint(
                    "uq_companies_tenant_company_number",
                    "companies",
                    ["tenant_id", "company_number"],
                )
            except Exception:  # nosec B110
                # If a similar constraint exists under a different name, ignore.
                pass

    # ---------- source_events ----------
    # Create only when dependencies exist to avoid FK creation failures.
    if _has_table(conn, "tenants") and _has_table(conn, "companies"):
        if not _has_table(conn, "source_events"):
            op.create_table(
                "source_events",
                sa.Column("id", sa.Integer, primary_key=True),
                sa.Column(
                    "tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False
                ),
                sa.Column(
                    "company_id",
                    sa.Integer,
                    sa.ForeignKey("companies.id"),
                    nullable=False,
                ),
                sa.Column("source", sa.String(length=64), nullable=False),
                sa.Column("kind", sa.String(length=64), nullable=False),
                sa.Column("payload", sa.JSON()),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("now()"),
                    nullable=False,
                ),
            )

        if _has_table(conn, "source_events"):
            se_idx = _index_names(conn, "source_events")
            if "ix_source_events_tenant_id" not in se_idx and _has_column(
                conn, "source_events", "tenant_id"
            ):
                try:
                    op.create_index(
                        "ix_source_events_tenant_id", "source_events", ["tenant_id"]
                    )
                except Exception:  # nosec B110
                    pass
            if "ix_source_events_company_id" not in se_idx and _has_column(
                conn, "source_events", "company_id"
            ):
                try:
                    op.create_index(
                        "ix_source_events_company_id", "source_events", ["company_id"]
                    )
                except Exception:  # nosec B110
                    pass


def downgrade():
    # Drop only what this migration introduces, and be defensive.
    # Indexes/constraints are dropped implicitly with tables in Postgres.
    for name in ("source_events", "tenants"):
        try:
            op.drop_table(name)
        except Exception:  # nosec B110
            pass
