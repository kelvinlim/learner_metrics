"""Initial schema — all tables + RLS policies

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-02-26

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that need RLS policies
RLS_TABLES = [
    "units",
    "users",
    "user_unit_assignments",
    "resource_schemas",
    "audit_logs",
    "nih_reporter_projects",
    "publications",
]


def upgrade() -> None:
    # ----------------------------------------------------------------
    # Global tables (no RLS)
    # ----------------------------------------------------------------

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), unique=True),
        sa.Column("slug", sa.String(100), unique=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("is_system_tenant", sa.Boolean, server_default="false"),
        sa.Column("ui_config", JSONB, server_default="{}"),
        sa.Column("feature_config", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    op.create_table(
        "identities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("google_sub", sa.String(255), unique=True),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_identities_email", "identities", ["email"])
    op.create_index("ix_identities_google_sub", "identities", ["google_sub"])

    # ----------------------------------------------------------------
    # Tenant-scoped tables (with RLS)
    # ----------------------------------------------------------------

    op.create_table(
        "units",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("units.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit_level", sa.Integer, nullable=False),
        sa.Column("unit_type", sa.String(100)),
        sa.Column("tree_path", sa.String, nullable=False),
        sa.Column("active", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_units_tenant_id", "units", ["tenant_id"])
    op.create_index("ix_units_tree_path", "units", ["tree_path"])

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("identity_id", UUID(as_uuid=True), sa.ForeignKey("identities.id"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("unit_id", UUID(as_uuid=True), sa.ForeignKey("units.id"), nullable=True),
        sa.Column("attributes", JSONB, server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_covered_investigator", sa.Boolean, server_default="false"),
        # NIH integration
        sa.Column("nih_profile_id", sa.Integer, nullable=True),
        sa.Column("nih_reporter_last_updated", sa.DateTime(timezone=True), nullable=True),
        # ORCID integration
        sa.Column("orcid_id", sa.String(20), nullable=True),
        sa.Column("orcid_last_updated", sa.DateTime(timezone=True), nullable=True),
        # PubMed integration
        sa.Column("pubmed_query", sa.Text, nullable=True),
        sa.Column("pubmed_last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_identity_id", "users", ["identity_id"])
    op.create_index("ix_users_nih_profile_id", "users", ["nih_profile_id"])
    op.create_index("ix_users_orcid_id", "users", ["orcid_id"])

    # Now that users exists, create tenant_memberships (references users)
    op.create_table(
        "tenant_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("identity_id", UUID(as_uuid=True), sa.ForeignKey("identities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("identity_id", "tenant_id", name="uq_identity_tenant"),
        sa.UniqueConstraint("user_id", name="uq_membership_user"),
    )
    op.create_index("ix_tenant_memberships_identity_id", "tenant_memberships", ["identity_id"])
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])

    op.create_table(
        "user_unit_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("unit_id", UUID(as_uuid=True), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("privilege", sa.String(20), server_default="VIEW"),
        sa.Column("depth", sa.Integer, server_default="-1"),
        sa.Column("is_cascading", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_user_unit_assignments_tenant_id", "user_unit_assignments", ["tenant_id"])

    op.create_table(
        "resource_schemas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("unit_id", UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("schema_definition", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "unit_id", "resource_type", name="uq_resource_schema_tenant_unit_type"),
    )
    op.create_index("ix_resource_schemas_tenant_id", "resource_schemas", ["tenant_id"])
    op.create_index("ix_resource_schemas_unit_id", "resource_schemas", ["unit_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("changes", JSONB, server_default="{}"),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])

    op.create_table(
        "nih_reporter_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("appl_id", sa.Integer, nullable=False),
        sa.Column("project_title", sa.String(300), nullable=False),
        sa.Column("project_num", sa.String(30), nullable=False),
        sa.Column("core_project_num", sa.String(30), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("total_costs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("direct_costs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("indirect_costs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("project_start_date", sa.Date, nullable=True),
        sa.Column("project_end_date", sa.Date, nullable=True),
        sa.Column("project_details", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "appl_id", name="uq_nih_project_tenant_appl"),
    )
    op.create_index("ix_nih_reporter_projects_tenant_id", "nih_reporter_projects", ["tenant_id"])
    op.create_index("ix_nih_reporter_projects_user_id", "nih_reporter_projects", ["user_id"])
    op.create_index("ix_nih_reporter_projects_appl_id", "nih_reporter_projects", ["appl_id"])
    op.create_index("ix_nih_reporter_projects_core_project_num", "nih_reporter_projects", ["core_project_num"])
    op.create_index("ix_nih_reporter_projects_fiscal_year", "nih_reporter_projects", ["fiscal_year"])

    op.create_table(
        "publications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pmid", sa.String(20), nullable=True),
        sa.Column("doi", sa.String(200), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("journal", sa.String(200), nullable=True),
        sa.Column("pub_year", sa.Integer, nullable=True),
        sa.Column("pub_date", sa.Date, nullable=True),
        sa.Column("authors", sa.Text, nullable=True),
        sa.Column("source", sa.String(10), nullable=False, server_default="manual"),
        sa.Column("orcid_put_code", sa.String(50), nullable=True),
        sa.Column("raw_data", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "user_id", "pmid", name="uq_pub_tenant_user_pmid"),
        sa.UniqueConstraint("tenant_id", "user_id", "doi", name="uq_pub_tenant_user_doi"),
    )
    op.create_index("ix_publications_tenant_id", "publications", ["tenant_id"])
    op.create_index("ix_publications_user_id", "publications", ["user_id"])
    op.create_index("ix_publications_pmid", "publications", ["pmid"])
    op.create_index("ix_publications_doi", "publications", ["doi"])
    op.create_index("ix_publications_pub_year", "publications", ["pub_year"])

    # ----------------------------------------------------------------
    # Row-Level Security
    # ----------------------------------------------------------------

    conn = op.get_bind()

    # Create the DB role used by the app (if not exists)
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'learner_service') THEN
                CREATE ROLE learner_service LOGIN;
            END IF;
        END$$;
    """))

    # Grant usage on schema
    conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO learner_service"))
    conn.execute(sa.text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO learner_service"))
    conn.execute(sa.text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO learner_service"))
    conn.execute(sa.text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO learner_service"))
    conn.execute(sa.text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO learner_service"))

    for table in RLS_TABLES:
        # Enable RLS
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        # Allow the app role to bypass RLS for its own rows (using current_setting)
        conn.execute(sa.text(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
        """))
        # Allow superuser to bypass RLS (for migrations)
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))

    # audit_logs: allow NULL tenant_id rows (system-level events) to be readable by all
    conn.execute(sa.text("""
        CREATE POLICY audit_logs_null_tenant ON audit_logs
        USING (tenant_id IS NULL)
    """))


def downgrade() -> None:
    conn = op.get_bind()

    for table in RLS_TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    conn.execute(sa.text("DROP POLICY IF EXISTS audit_logs_null_tenant ON audit_logs"))

    op.drop_table("publications")
    op.drop_table("nih_reporter_projects")
    op.drop_table("audit_logs")
    op.drop_table("resource_schemas")
    op.drop_table("user_unit_assignments")
    op.drop_table("tenant_memberships")
    op.drop_table("users")
    op.drop_table("units")
    op.drop_table("identities")
    op.drop_table("tenants")
