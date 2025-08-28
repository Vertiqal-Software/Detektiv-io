"""ensure tenants/source_events exist (idempotent), and enforce companies.tenant_id"""

from alembic import op
import sqlalchemy as sa

# Use the current head from your repo as down_revision (merge rev).
# If `python -m alembic heads` prints a different id, put that here.
revision = "20250828_ensure_core_tables"
down_revision = "8782f557b2eb"
branch_labels = None
depends_on = None


def _insp(conn):
    return sa.inspect(conn)


def _has_table(conn, name: str) -> bool:
    try:
        return name in _insp(conn).get_table_names()
    except Exception:
        return False


def _has_column(conn, table: str, col: str) -> bool:
    try:
        return col in [c["name"] for c in _insp(conn).get_columns(table)]
    except Exception:
        return False


def _index_names(conn, table: str) -> set[str]:
    try:
        return {ix["name"] for ix in _insp(conn).get_indexes(table)}
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


def _fk_exists(conn, table: str, columns: tuple[str, ...], ref_table: str) -> bool:
    try:
        for fk in _insp(conn).get_foreign_keys(table):
            if tuple(fk.get("constrained_columns") or ()) == columns and fk.get("referred_table") == ref_table:
                return True
        return False
    except Exception:
        return False


def upgrade():
    conn = op.get_bind()

    # 1) tenants (create if missing)
    if not _has_table(conn, "tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_key", sa.String(length=64), nullable=False, unique=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    default_tenant_id = None
    if _has_table(conn, "tenants"):
        # upsert default tenant
        op.execute(
            sa.text(
                "INSERT INTO tenants (tenant_key, name) "
                "VALUES ('default', 'Default Tenant') "
                "ON CONFLICT (tenant_key) DO NOTHING"
            )
        )
        default_tenant_id = conn.execute(sa.text("SELECT id FROM tenants WHERE tenant_key='default'")).scalar()

    # 2) companies.tenant_id (add/backfill/enforce) if companies table exists
    if _has_table(conn, "companies"):
        if not _has_column(conn, "companies", "tenant_id"):
            op.add_column("companies", sa.Column("tenant_id", sa.Integer(), nullable=True))

            if default_tenant_id is not None:
                conn.execute(
                    sa.text("UPDATE companies SET tenant_id = :tid WHERE tenant_id IS NULL"),
                    {"tid": default_tenant_id},
                )

            if _has_table(conn, "tenants") and not _fk_exists(conn, "companies", ("tenant_id",), "tenants"):
                op.create_foreign_key(None, "companies", "tenants", ["tenant_id"], ["id"])

            # Only enforce NOT NULL if we have a default tenant to backfill
            if default_tenant_id is not None:
                op.alter_column("companies", "tenant_id", nullable=False)

        # Ensure indexes/UQ
        comp_idx = _index_names(conn, "companies")
        comp_uqs = _unique_constraints_by_cols(conn, "companies")

        if "ix_companies_tenant_id" not in comp_idx and _has_column(conn, "companies", "tenant_id"):
            try:
                op.create_index("ix_companies_tenant_id", "companies", ["tenant_id"])
            except Exception:
                pass

        if "ix_companies_company_number" not in comp_idx and _has_column(conn, "companies", "company_number"):
            try:
                op.create_index("ix_companies_company_number", "companies", ["company_number"])
            except Exception:
                pass

        need_uq = ("tenant_id", "company_number") not in comp_uqs and ("company_number", "tenant_id") not in comp_uqs
        if need_uq and _has_column(conn, "companies", "tenant_id") and _has_column(conn, "companies", "company_number"):
            try:
                op.create_unique_constraint(
                    "uq_companies_tenant_company_number",
                    "companies",
                    ["tenant_id", "company_number"],
                )
            except Exception:
                pass

    # 3) source_events (create if missing, only if deps exist)
    if _has_table(conn, "tenants") and _has_table(conn, "companies") and not _has_table(conn, "source_events"):
        op.create_table(
            "source_events",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.JSON()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

        se_idx = _index_names(conn, "source_events")
        if "ix_source_events_tenant_id" not in se_idx:
            try:
                op.create_index("ix_source_events_tenant_id", "source_events", ["tenant_id"])
            except Exception:
                pass
        if "ix_source_events_company_id" not in se_idx:
            try:
                op.create_index("ix_source_events_company_id", "source_events", ["company_id"])
            except Exception:
                pass


def downgrade():
    # Safe, minimal rollback: do nothing destructive.
    # (We’re only ensuring existence / constraints; no schema removal.)
    pass
