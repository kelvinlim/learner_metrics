"""
Database models for Learner Metrics.

Multi-tenant architecture with PostgreSQL Row-Level Security (RLS).

Tables WITHOUT RLS (global, pre-auth access):
  - identities, tenant_memberships

Tables WITH RLS (tenant_id = current_setting('app.current_tenant')::uuid):
  - units, users, user_unit_assignments, resource_schemas, audit_logs
  - nih_reporter_projects, publications
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
import uuid6
import sqlalchemy as sa
from sqlalchemy import String, ForeignKey, Boolean, Integer, DateTime, Float, Date, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB


class Base(DeclarativeBase):
    pass


# ============================================================
# MULTI-TENANT FOUNDATION (Phase 1)
# ============================================================

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    slug: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    is_system_tenant: Mapped[bool] = mapped_column(Boolean, default=False)

    ui_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    feature_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    units: Mapped[List["Unit"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    users: Mapped[List["User"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class Identity(Base):
    """Global auth identity — NOT tenant-scoped (no RLS).

    Stores Google identity info separately from tenant-scoped User records.
    One Identity can belong to multiple tenants (multi-tenant accounts).
    """
    __tablename__ = "identities"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)

    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    memberships: Mapped[List["TenantMembership"]] = relationship(back_populates="identity", cascade="all, delete-orphan")


class TenantMembership(Base):
    """Links an Identity to a tenant-scoped User record — NOT tenant-scoped (no RLS).

    Allows cross-tenant lookup during login: given an identity_id, find all
    tenants the user belongs to.
    """
    __tablename__ = "tenant_memberships"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    identity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("identities.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    identity: Mapped["Identity"] = relationship(back_populates="memberships")
    tenant: Mapped["Tenant"] = relationship()
    user: Mapped["User"] = relationship(back_populates="tenant_membership")

    __table_args__ = (
        sa.UniqueConstraint("identity_id", "tenant_id", name="uq_identity_tenant"),
        sa.UniqueConstraint("user_id", name="uq_membership_user"),
    )


class Unit(Base):
    """Hierarchical organizational unit (e.g. University → College → Department).

    tree_path uses dot-separated UUIDs for efficient ancestor/descendant queries.
    RLS-enabled.
    """
    __tablename__ = "units"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("units.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_level: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_type: Mapped[Optional[str]] = mapped_column(String(100))

    tree_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="units")
    parent: Mapped[Optional["Unit"]] = relationship("Unit", remote_side=[id], back_populates="children")
    children: Mapped[List["Unit"]] = relationship("Unit", back_populates="parent")


class User(Base):
    """Tenant-scoped investigator/user record. RLS-enabled.

    NIH, ORCID, and PubMed integration fields are explicit columns (not JSONB
    attributes) because they are first-class integration keys used for API sync.
    """
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    identity_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("identities.id"), nullable=True, index=True)

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))

    unit_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("units.id"), nullable=True)

    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_covered_investigator: Mapped[bool] = mapped_column(Boolean, default=False)

    # NIH RePORTER integration (Phase 2)
    nih_profile_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    nih_reporter_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ORCID integration (Phase 3)
    orcid_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    orcid_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # PubMed integration (Phase 4)
    pubmed_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pubmed_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    identity: Mapped[Optional["Identity"]] = relationship()
    unit: Mapped[Optional["Unit"]] = relationship()
    unit_assignments: Mapped[List["UserUnitAssignment"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tenant_membership: Mapped[Optional["TenantMembership"]] = relationship(back_populates="user")
    nih_reporter_projects: Mapped[List["NIHReporterProject"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    publications: Mapped[List["Publication"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserUnitAssignment(Base):
    """RBAC privilege assignment. Privilege cascades down the unit tree per depth.

    Privilege levels: ADMIN(4) > FULL(3) > PARTIAL(2) > VIEW(1)
    depth=-1 = cascade to all descendants; depth=1 = this unit only.
    RLS-enabled.
    """
    __tablename__ = "user_unit_assignments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("units.id"), nullable=False)

    privilege: Mapped[str] = mapped_column(String(20), default="VIEW")
    depth: Mapped[int] = mapped_column(Integer, default=-1)
    is_cascading: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="unit_assignments")


class ResourceSchema(Base):
    """Per-unit custom field definitions (JSONSchema). RLS-enabled.

    Schemas merge hierarchically: root → parent → child.
    Parent fields become inherited/read-only in child units.
    """
    __tablename__ = "resource_schemas"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    unit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True)

    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_definition: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

    unit: Mapped["Unit"] = relationship("Unit")

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "unit_id", "resource_type", name="uq_resource_schema_tenant_unit_type"),
    )


class AuditLog(Base):
    """Immutable audit trail. RLS-enabled (tenant-scoped visibility)."""
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    actor_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(30))

    changes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


# ============================================================
# NIH GRANTS MODULE (Phase 2)
# ============================================================

class NIHReporterProject(Base):
    """Cached NIH RePORTER project, synced per investigator's nih_profile_id.

    Unique per (tenant_id, appl_id) — same grant application is separate per tenant.
    Full API response in project_details JSONB preserves all NIH fields.
    RLS-enabled.
    """
    __tablename__ = "nih_reporter_projects"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    appl_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_title: Mapped[str] = mapped_column(String(300), nullable=False)
    project_num: Mapped[str] = mapped_column(String(30), nullable=False)
    core_project_num: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_costs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_costs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indirect_costs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    project_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    project_details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

    user: Mapped["User"] = relationship(back_populates="nih_reporter_projects")

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "appl_id", name="uq_nih_project_tenant_appl"),
    )


# ============================================================
# PUBLICATIONS MODULE (Phases 3 + 4)
# ============================================================

class Publication(Base):
    """Publication record sourced from ORCID and/or PubMed.

    source values:
      'orcid'  — found via ORCID API only
      'pubmed' — found via PubMed E-utilities only
      'both'   — confirmed in both (PMID or DOI match) — no duplicate stored
      'manual' — manually entered

    Dedup: unique on (tenant_id, user_id, pmid) and (tenant_id, user_id, doi).
    When same paper found in both sources, existing record updated with source='both'.
    RLS-enabled.
    """
    __tablename__ = "publications"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    pmid: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    doi: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    journal: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pub_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    pub_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    orcid_put_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    raw_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

    user: Mapped["User"] = relationship(back_populates="publications")

    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "user_id", "pmid", name="uq_pub_tenant_user_pmid"),
        sa.UniqueConstraint("tenant_id", "user_id", "doi", name="uq_pub_tenant_user_doi"),
    )
