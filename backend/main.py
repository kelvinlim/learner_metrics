"""
Learner Metrics — FastAPI Application

Phases 1-4: Multi-tenant auth, RBAC, unit hierarchy, user management, schema service,
            NIH grants, ORCID integration, PubMed integration.
"""
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import sqlalchemy as sa
import uuid6
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend import auth_service, nih_service, orcid_service, pubmed_service
from backend.config import settings
from backend.context import get_current_tenant, set_current_tenant
from backend.database import AsyncSessionLocal, get_db, get_db_no_rls
from backend.models import (
    AuditLog,
    Identity,
    NIHReporterProject,
    Publication,
    ResourceSchema,
    Tenant,
    TenantMembership,
    Unit,
    User,
    UserUnitAssignment,
)
from backend.schema_service import (
    get_inherited_field_keys,
    get_local_schema,
    get_merged_schema,
    save_unit_schema,
    validate_schema_modification,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Schemas
# =============================================================================

# --- Auth ---

class GoogleIdentifyRequest(BaseModel):
    token: str


class TenantOption(BaseModel):
    tenant_id: UUID
    tenant_name: str


class GoogleIdentifyResponse(BaseModel):
    identity_id: UUID
    email: str
    tenants: List[TenantOption]


class GoogleAuthenticateRequest(BaseModel):
    identity_id: UUID
    tenant_id: UUID


class AuthenticateResponse(BaseModel):
    access_token: str
    token_type: str
    tenant_id: UUID
    tenant_name: str


class SwitchTenantRequest(BaseModel):
    tenant_id: UUID


# --- Tenants ---

class TenantCreate(BaseModel):
    name: str
    domain: Optional[str] = None
    slug: Optional[str] = None
    status: str = "active"
    ui_config: Dict[str, Any] = Field(default_factory=dict)
    feature_config: Dict[str, Any] = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    slug: Optional[str] = None
    status: Optional[str] = None
    ui_config: Optional[Dict[str, Any]] = None
    feature_config: Optional[Dict[str, Any]] = None


class TenantRead(BaseModel):
    id: UUID
    name: str
    domain: Optional[str]
    slug: Optional[str]
    status: str
    is_system_tenant: bool
    ui_config: Dict[str, Any]
    feature_config: Dict[str, Any]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProvisionAdminRequest(BaseModel):
    email: EmailStr
    first_name: str = ""
    last_name: str = ""
    root_unit_name: str = ""


# --- Units ---

class UnitCreate(BaseModel):
    name: str
    unit_level: int
    unit_type: Optional[str] = None
    parent_id: Optional[UUID] = None


class UnitUpdate(BaseModel):
    name: Optional[str] = None
    unit_type: Optional[str] = None
    active: Optional[bool] = None


class UnitRead(BaseModel):
    id: UUID
    tenant_id: UUID
    parent_id: Optional[UUID]
    name: str
    unit_level: int
    unit_type: Optional[str]
    tree_path: str
    active: bool
    model_config = ConfigDict(from_attributes=True)


# --- User Unit Assignments ---

class AssignmentCreate(BaseModel):
    unit_id: UUID
    privilege: str = "VIEW"  # ADMIN, FULL, PARTIAL, VIEW
    depth: int = -1
    is_cascading: bool = True


class AssignmentRead(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    unit_id: UUID
    privilege: str
    depth: int
    is_cascading: bool
    model_config = ConfigDict(from_attributes=True)


# --- Users ---

class UserCreate(BaseModel):
    email: EmailStr
    first_name: str = ""
    last_name: str = ""
    unit_id: Optional[UUID] = None
    is_active: bool = True
    is_covered_investigator: bool = False
    attributes: Dict[str, Any] = Field(default_factory=dict)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    unit_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    is_covered_investigator: Optional[bool] = None
    attributes: Optional[Dict[str, Any]] = None
    nih_profile_id: Optional[int] = None
    orcid_id: Optional[str] = None
    pubmed_query: Optional[str] = None


class UserRead(BaseModel):
    id: UUID
    tenant_id: UUID
    identity_id: Optional[UUID]
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    unit_id: Optional[UUID]
    is_active: bool
    is_covered_investigator: bool
    attributes: Dict[str, Any]
    nih_profile_id: Optional[int]
    orcid_id: Optional[str]
    pubmed_query: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Schemas ---

class ResourceSchemaCreate(BaseModel):
    schema_definition: Dict[str, Any]


class ResourceSchemaRead(BaseModel):
    id: UUID
    tenant_id: UUID
    unit_id: UUID
    resource_type: str
    schema_definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# App Setup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Learner Metrics API — environment: {settings.ENVIRONMENT}")
    yield
    logger.info("Shutting down Learner Metrics API")


app = FastAPI(
    title="Learner Metrics API",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = (
    ["*"] if settings.ENVIRONMENT == "production"
    else [
        "http://localhost:5201",
        "http://127.0.0.1:5201",
        "http://localhost:5010",   # staging
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Middleware
# =============================================================================

@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """Extract X-Tenant-ID header and set RLS context."""
    tenant_id_str = request.headers.get("X-Tenant-ID")
    if tenant_id_str:
        try:
            set_current_tenant(UUID(tenant_id_str))
        except ValueError:
            pass
    return await call_next(request)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Log request processing time."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(f"{request.method} {request.url.path} — {response.status_code} ({elapsed_ms:.1f}ms)")
    return response


# =============================================================================
# Auth Dependencies
# =============================================================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)

PRIV_MAP = {"ADMIN": 4, "FULL": 3, "PARTIAL": 2, "VIEW": 1}
INV_PRIV_MAP = {4: "ADMIN", 3: "FULL", 2: "PARTIAL", 1: "VIEW"}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    payload = auth_service.decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    return result.scalar_one_or_none()


def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_unit_privilege(user_id: UUID, unit_id: UUID, db: AsyncSession) -> Optional[str]:
    """Resolve the highest cascading privilege for a user on a given unit."""
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    target_unit = result.scalar_one_or_none()
    if not target_unit:
        return None

    ancestor_ids = [UUID(uid) for uid in target_unit.tree_path.split(".")]

    stmt = (
        select(UserUnitAssignment, Unit.unit_level)
        .join(Unit, UserUnitAssignment.unit_id == Unit.id)
        .where(
            UserUnitAssignment.user_id == user_id,
            UserUnitAssignment.unit_id.in_(ancestor_ids),
        )
    )
    result = await db.execute(stmt)

    max_priv_level = 0
    for row in result.all():
        assign = row[0]
        assign_level = row[1]
        level_diff = target_unit.unit_level - assign_level

        is_applicable = assign.depth == -1 or level_diff < assign.depth
        if is_applicable:
            max_priv_level = max(max_priv_level, PRIV_MAP.get(assign.privilege, 0))

    return INV_PRIV_MAP.get(max_priv_level)


def has_permission(required_privilege: str, unit_id_param: Optional[str] = None):
    """FastAPI Depends factory for RBAC privilege checking."""
    async def _check(
        request: Request,
        user: User = Depends(require_auth),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        target_unit_id = None
        if unit_id_param:
            target_unit_id = request.path_params.get(unit_id_param) or request.query_params.get(unit_id_param)

        if target_unit_id:
            try:
                priv = await get_unit_privilege(user.id, UUID(target_unit_id), db)
                if PRIV_MAP.get(priv, 0) >= PRIV_MAP.get(required_privilege, 0):
                    return user
            except ValueError:
                pass
        else:
            result = await db.execute(
                select(UserUnitAssignment.privilege)
                .where(UserUnitAssignment.user_id == user.id)
            )
            privs = result.scalars().all()
            max_p = max((PRIV_MAP.get(p, 0) for p in privs), default=0)
            if max_p >= PRIV_MAP.get(required_privilege, 0):
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: requires {required_privilege} privilege",
        )

    return _check


async def is_platform_admin(user: User, db: AsyncSession) -> bool:
    """True if user is in the system tenant with ADMIN on a level-1 unit."""
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_system_tenant:
        return False
    result = await db.execute(
        select(UserUnitAssignment)
        .join(Unit, UserUnitAssignment.unit_id == Unit.id)
        .where(
            UserUnitAssignment.user_id == user.id,
            UserUnitAssignment.privilege == "ADMIN",
            Unit.unit_level == 1,
        )
    )
    return result.scalar_one_or_none() is not None


async def require_platform_admin(
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not await is_platform_admin(user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin access required")
    return user


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health():
    """Health check — returns DB connectivity and version."""
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        logger.error(f"DB health check failed: {exc}")

    return {
        "status": "ok" if db_ok else "degraded",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
        "database": "connected" if db_ok else "unreachable",
    }


# =============================================================================
# Auth Endpoints — Google OAuth 2-Step Multi-Tenant Flow
# =============================================================================

@app.post("/auth/google/identify", response_model=GoogleIdentifyResponse)
async def google_identify(
    credentials: GoogleIdentifyRequest,
    db: AsyncSession = Depends(get_db_no_rls),
):
    """Step 1: Verify Google token and return list of available tenants."""
    token_payload = await auth_service.verify_google_token(credentials.token)
    if not token_payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    email = token_payload.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email not found in Google token")

    google_sub = token_payload.get("sub", "")
    first_name = token_payload.get("given_name", "")
    last_name = token_payload.get("family_name", "")

    # Auto-create or find identity
    identity = await auth_service.get_or_create_identity(db, email, google_sub, first_name, last_name)

    tenants = await auth_service.get_tenants_for_identity(db, identity.id)
    if not tenants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active tenant memberships for this account. Contact your administrator.",
        )

    return GoogleIdentifyResponse(
        identity_id=identity.id,
        email=identity.email,
        tenants=[TenantOption(tenant_id=UUID(t["tenant_id"]), tenant_name=t["tenant_name"]) for t in tenants],
    )


@app.post("/auth/google/authenticate", response_model=AuthenticateResponse)
async def google_authenticate(
    google_auth_in: GoogleAuthenticateRequest,
    db: AsyncSession = Depends(get_db_no_rls),
):
    """Step 2: Verify identity + tenant selection, issue JWT."""
    # Look up the identity by ID (already verified in step 1)
    result = await db.execute(select(Identity).where(Identity.id == google_auth_in.identity_id))
    identity = result.scalar_one_or_none()
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity not found")

    # Verify the tenant membership
    result = await db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, TenantMembership.tenant_id == Tenant.id)
        .where(
            TenantMembership.identity_id == identity.id,
            TenantMembership.tenant_id == google_auth_in.tenant_id,
            TenantMembership.status == "active",
            Tenant.status == "active",
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this tenant")

    membership, tenant = row

    access_token = auth_service.create_access_token(
        user_id=membership.user_id,
        tenant_id=tenant.id,
        identity_id=identity.id,
    )

    return AuthenticateResponse(
        access_token=access_token,
        token_type="bearer",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )


class DevLoginRequest(BaseModel):
    email: str


@app.post("/auth/dev-login", response_model=GoogleIdentifyResponse)
async def dev_login(
    payload: DevLoginRequest,
    db: AsyncSession = Depends(get_db_no_rls),
):
    """Dev-only bypass: skip Google token, return identity + tenant list by email."""
    if settings.ENVIRONMENT != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    email = payload.email.strip().lower()
    result = await db.execute(select(Identity).where(Identity.email == email))
    identity = result.scalar_one_or_none()
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No identity found for this email. Run the seed SQL first.")

    tenants = await auth_service.get_tenants_for_identity(db, identity.id)
    if not tenants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active tenant memberships for this account.")

    return GoogleIdentifyResponse(
        identity_id=identity.id,
        email=identity.email,
        tenants=[TenantOption(tenant_id=UUID(t["tenant_id"]), tenant_name=t["tenant_name"]) for t in tenants],
    )


@app.post("/auth/switch-tenant", response_model=AuthenticateResponse)
async def switch_tenant(
    payload: SwitchTenantRequest,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db_no_rls),
):
    """Re-issue a JWT for a different tenant the user belongs to."""
    # Verify the user has a membership for the requested tenant
    result = await db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, TenantMembership.tenant_id == Tenant.id)
        .where(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == payload.tenant_id,
            TenantMembership.status == "active",
            Tenant.status == "active",
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this tenant")

    membership, tenant = row

    access_token = auth_service.create_access_token(
        user_id=membership.user_id,
        tenant_id=tenant.id,
        identity_id=user.identity_id,
    )

    return AuthenticateResponse(
        access_token=access_token,
        token_type="bearer",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )


@app.get("/auth/tenants")
async def list_my_tenants(
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db_no_rls),
):
    """List all tenants available to the current user's identity."""
    if not user.identity_id:
        return []
    return await auth_service.get_tenants_for_identity(db, user.identity_id)


# =============================================================================
# Platform Admin Endpoints (system tenant ADMIN only)
# =============================================================================

@app.get("/platform/check-admin")
async def check_platform_admin(
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    return {"is_platform_admin": await is_platform_admin(user, db)}


@app.get("/platform/tenants", response_model=List[TenantRead])
async def list_tenants(
    db: AsyncSession = Depends(get_db_no_rls),
    current_user: User = Depends(require_platform_admin),
):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return result.scalars().all()


@app.post("/platform/tenants", response_model=TenantRead, status_code=201)
async def create_tenant(
    tenant_in: TenantCreate,
    db: AsyncSession = Depends(get_db_no_rls),
    current_user: User = Depends(require_platform_admin),
):
    if tenant_in.domain:
        existing = await db.execute(select(Tenant).where(Tenant.domain == tenant_in.domain))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Domain already in use")

    tenant = Tenant(
        name=tenant_in.name,
        domain=tenant_in.domain,
        slug=tenant_in.slug,
        status=tenant_in.status,
        ui_config=tenant_in.ui_config,
        feature_config=tenant_in.feature_config,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@app.put("/platform/tenants/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    tenant_id: UUID,
    tenant_in: TenantUpdate,
    db: AsyncSession = Depends(get_db_no_rls),
    current_user: User = Depends(require_platform_admin),
):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant_in.name is not None:
        tenant.name = tenant_in.name
    if tenant_in.domain is not None:
        tenant.domain = tenant_in.domain
    if tenant_in.slug is not None:
        tenant.slug = tenant_in.slug
    if tenant_in.status is not None:
        tenant.status = tenant_in.status
    if tenant_in.ui_config is not None:
        tenant.ui_config = tenant_in.ui_config
    if tenant_in.feature_config is not None:
        tenant.feature_config = tenant_in.feature_config

    await db.commit()
    await db.refresh(tenant)
    return tenant


@app.post("/platform/tenants/{tenant_id}/provision-admin")
async def provision_tenant_admin(
    tenant_id: UUID,
    payload: ProvisionAdminRequest,
    db: AsyncSession = Depends(get_db_no_rls),
    current_user: User = Depends(require_platform_admin),
):
    """Bootstrap a tenant with a root unit and admin user. Idempotent."""
    created: List[str] = []
    skipped: List[str] = []

    # 1. Tenant
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # 2. Root unit (level 1)
    result = await db.execute(
        select(Unit).where(Unit.tenant_id == tenant_id, Unit.unit_level == 1)
    )
    root_unit = result.scalar_one_or_none()

    if not root_unit:
        unit_name = payload.root_unit_name.strip() or tenant.name
        root_unit = Unit(
            tenant_id=tenant_id,
            name=unit_name,
            unit_level=1,
            unit_type="Organization",
            tree_path="placeholder",
        )
        db.add(root_unit)
        await db.flush()
        root_unit.tree_path = str(root_unit.id)
        created.append(f"Root unit '{unit_name}'")
    else:
        skipped.append(f"Root unit '{root_unit.name}' already exists")

    # 3. Identity
    email = payload.email.strip().lower()
    result = await db.execute(select(Identity).where(Identity.email == email))
    identity = result.scalar_one_or_none()

    if not identity:
        identity = Identity(
            email=email,
            first_name=payload.first_name or None,
            last_name=payload.last_name or None,
        )
        db.add(identity)
        await db.flush()
        created.append(f"Identity for '{email}'")
    else:
        skipped.append(f"Identity for '{email}' already exists")

    # 4. User
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            tenant_id=tenant_id,
            email=email,
            first_name=payload.first_name or identity.first_name,
            last_name=payload.last_name or identity.last_name,
            is_active=True,
            unit_id=root_unit.id,
            identity_id=identity.id,
        )
        db.add(user)
        await db.flush()
        created.append(f"User '{email}' in tenant")
    else:
        skipped.append(f"User '{email}' already exists in tenant")

    # 5. TenantMembership
    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.identity_id == identity.id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        membership = TenantMembership(
            identity_id=identity.id,
            tenant_id=tenant_id,
            user_id=user.id,
            status="active",
        )
        db.add(membership)
        created.append("TenantMembership")
    else:
        skipped.append("TenantMembership already exists")

    # 6. ADMIN assignment on root unit
    result = await db.execute(
        select(UserUnitAssignment).where(
            UserUnitAssignment.user_id == user.id,
            UserUnitAssignment.unit_id == root_unit.id,
            UserUnitAssignment.privilege == "ADMIN",
        )
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        assignment = UserUnitAssignment(
            tenant_id=tenant_id,
            user_id=user.id,
            unit_id=root_unit.id,
            privilege="ADMIN",
            depth=-1,
            is_cascading=True,
        )
        db.add(assignment)
        created.append("ADMIN privilege on root unit")
    else:
        skipped.append("ADMIN privilege already assigned")

    await db.commit()

    return {
        "success": True,
        "tenant_id": str(tenant_id),
        "tenant_name": tenant.name,
        "user_id": str(user.id),
        "email": email,
        "root_unit_id": str(root_unit.id),
        "created": created,
        "skipped": skipped,
    }


# =============================================================================
# Tenant Config
# =============================================================================

@app.get("/config")
async def get_tenant_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
):
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    result = await db.execute(select(Tenant).where(Tenant.id == t_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"name": tenant.name, "ui_config": tenant.ui_config, "features": tenant.feature_config}


# =============================================================================
# Units
# =============================================================================

@app.post("/units", response_model=UnitRead, status_code=201)
async def create_unit(
    unit_in: UnitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("ADMIN")),
):
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    if unit_in.parent_id:
        result = await db.execute(select(Unit).where(Unit.id == unit_in.parent_id))
        parent = result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent unit not found")
        tree_path = f"{parent.tree_path}.placeholder"
    else:
        tree_path = "placeholder"

    unit = Unit(
        tenant_id=t_id,
        parent_id=unit_in.parent_id,
        name=unit_in.name,
        unit_level=unit_in.unit_level,
        unit_type=unit_in.unit_type,
        tree_path=tree_path,
    )
    db.add(unit)
    await db.flush()

    # Set tree_path with actual ID
    if unit_in.parent_id:
        unit.tree_path = f"{parent.tree_path}.{unit.id}"
    else:
        unit.tree_path = str(unit.id)

    await db.commit()
    await db.refresh(unit)
    return unit


@app.get("/units", response_model=List[UnitRead])
async def list_units(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    manageable_only: bool = False,
):
    stmt = (
        select(UserUnitAssignment, Unit.tree_path, Unit.unit_level)
        .join(Unit, UserUnitAssignment.unit_id == Unit.id)
        .where(UserUnitAssignment.user_id == current_user.id)
    )
    if manageable_only:
        stmt = stmt.where(UserUnitAssignment.privilege.in_(["PARTIAL", "FULL", "ADMIN"]))

    result = await db.execute(stmt)
    assignments = result.all()

    if not assignments:
        return []

    or_conditions = []
    for row in assignments:
        assign = row[0]
        tree_path = row[1]
        level = row[2]
        cond = Unit.tree_path.like(f"{tree_path}%")
        if assign.depth != -1:
            cond = sa.and_(cond, (Unit.unit_level - level) < assign.depth)
        or_conditions.append(cond)

    result = await db.execute(
        select(Unit).where(Unit.active == True, sa.or_(*or_conditions))
    )
    return result.scalars().all()


@app.get("/units/{unit_id}", response_model=UnitRead)
async def get_unit(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    return unit


@app.put("/units/{unit_id}", response_model=UnitRead)
async def update_unit(
    unit_id: UUID,
    unit_in: UnitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("ADMIN")),
):
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    if unit_in.name is not None:
        unit.name = unit_in.name
    if unit_in.unit_type is not None:
        unit.unit_type = unit_in.unit_type
    if unit_in.active is not None:
        unit.active = unit_in.active

    await db.commit()
    await db.refresh(unit)
    return unit


@app.delete("/units/{unit_id}", status_code=204)
async def delete_unit(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("ADMIN")),
):
    t_id = get_current_tenant()

    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    child_count = await db.scalar(select(func.count(Unit.id)).where(Unit.parent_id == unit_id))
    if child_count:
        raise HTTPException(status_code=400, detail=f"Cannot delete unit: {child_count} child units exist")

    user_count = await db.scalar(select(func.count(User.id)).where(User.unit_id == unit_id))
    if user_count:
        raise HTTPException(status_code=400, detail=f"Cannot delete unit: {user_count} users assigned to it")

    assign_count = await db.scalar(
        select(func.count(UserUnitAssignment.id)).where(UserUnitAssignment.unit_id == unit_id)
    )
    if assign_count:
        raise HTTPException(status_code=400, detail=f"Cannot delete unit: {assign_count} privilege assignments exist")

    await db.delete(unit)
    await db.commit()


# =============================================================================
# Users
# =============================================================================

@app.post("/users", response_model=UserRead, status_code=201)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("FULL")),
):
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    # Check or create Identity (uses no-RLS session implicitly via joined session)
    identity_result = await db.execute(select(Identity).where(Identity.email == user_in.email))
    identity = identity_result.scalar_one_or_none()

    if not identity:
        identity = Identity(
            email=user_in.email,
            first_name=user_in.first_name or None,
            last_name=user_in.last_name or None,
        )
        db.add(identity)
        await db.flush()

    user = User(
        tenant_id=t_id,
        email=user_in.email,
        first_name=user_in.first_name or None,
        last_name=user_in.last_name or None,
        unit_id=user_in.unit_id,
        attributes=user_in.attributes,
        identity_id=identity.id,
        is_active=user_in.is_active,
        is_covered_investigator=user_in.is_covered_investigator,
    )
    db.add(user)
    await db.flush()

    # Create TenantMembership to enable login
    membership = TenantMembership(
        identity_id=identity.id,
        tenant_id=t_id,
        user_id=user.id,
        status="active",
    )
    db.add(membership)

    await db.commit()
    await db.refresh(user)
    return user


@app.get("/users", response_model=List[UserRead])
async def list_users(
    unit_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    # Resolve visible units via RBAC
    stmt = (
        select(UserUnitAssignment, Unit.tree_path, Unit.unit_level)
        .join(Unit, UserUnitAssignment.unit_id == Unit.id)
        .where(UserUnitAssignment.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    assignments = result.all()

    if not assignments:
        return []

    or_conditions = []
    for row in assignments:
        assign = row[0]
        tree_path = row[1]
        level = row[2]
        cond = Unit.tree_path.like(f"{tree_path}%")
        if assign.depth != -1:
            cond = sa.and_(cond, (Unit.unit_level - level) < assign.depth)
        or_conditions.append(cond)

    allowed_units_query = select(Unit.id).where(sa.or_(*or_conditions))

    if unit_id:
        filter_unit_result = await db.execute(select(Unit).where(Unit.id == unit_id))
        filter_unit = filter_unit_result.scalar_one_or_none()
        if filter_unit:
            allowed_units_query = allowed_units_query.where(
                Unit.tree_path.like(f"{filter_unit.tree_path}%")
            )

    result = await db.execute(
        select(User).where(
            sa.or_(
                User.unit_id.is_(None),
                User.unit_id.in_(allowed_units_query),
            )
        )
    )
    return result.scalars().all()


@app.get("/users/me", response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(require_auth)):
    return current_user


@app.get("/users/me/privilege/{unit_id}")
async def get_my_unit_privilege(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    priv = await get_unit_privilege(current_user.id, unit_id, db)
    return {"privilege": priv or "NONE", "unit_id": str(unit_id)}


@app.get("/users/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.put("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("FULL")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sync_identity = False
    if user_in.email is not None:
        user.email = user_in.email
        sync_identity = True
    if user_in.first_name is not None:
        user.first_name = user_in.first_name
        sync_identity = True
    if user_in.last_name is not None:
        user.last_name = user_in.last_name
        sync_identity = True
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.is_covered_investigator is not None:
        user.is_covered_investigator = user_in.is_covered_investigator
    if user_in.unit_id is not None:
        user.unit_id = user_in.unit_id
    if user_in.attributes is not None:
        user.attributes = user_in.attributes
    if user_in.nih_profile_id is not None:
        user.nih_profile_id = user_in.nih_profile_id
    if user_in.orcid_id is not None:
        user.orcid_id = user_in.orcid_id
    if user_in.pubmed_query is not None:
        user.pubmed_query = user_in.pubmed_query

    # Sync name/email back to Identity
    if sync_identity and user.identity_id:
        identity_result = await db.execute(select(Identity).where(Identity.id == user.identity_id))
        identity = identity_result.scalar_one_or_none()
        if identity:
            if user_in.email is not None:
                identity.email = user_in.email
            if user_in.first_name is not None:
                identity.first_name = user_in.first_name
            if user_in.last_name is not None:
                identity.last_name = user_in.last_name

    await db.commit()
    await db.refresh(user)
    return user


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("FULL")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    await db.delete(user)
    await db.commit()


# =============================================================================
# User Unit Assignments (RBAC management)
# =============================================================================

@app.get("/users/{user_id}/assignments", response_model=List[AssignmentRead])
async def list_user_assignments(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    result = await db.execute(
        select(UserUnitAssignment).where(UserUnitAssignment.user_id == user_id)
    )
    return result.scalars().all()


@app.post("/users/{user_id}/assignments", response_model=AssignmentRead, status_code=201)
async def create_user_assignment(
    user_id: UUID,
    assignment_in: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("ADMIN")),
):
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    # Ensure target user exists
    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    # Ensure target unit exists
    result = await db.execute(select(Unit).where(Unit.id == assignment_in.unit_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Unit not found")

    assignment = UserUnitAssignment(
        tenant_id=t_id,
        user_id=user_id,
        unit_id=assignment_in.unit_id,
        privilege=assignment_in.privilege,
        depth=assignment_in.depth,
        is_cascading=assignment_in.is_cascading,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


@app.delete("/users/{user_id}/assignments/{assignment_id}", status_code=204)
async def delete_user_assignment(
    user_id: UUID,
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("ADMIN")),
):
    result = await db.execute(
        select(UserUnitAssignment).where(
            UserUnitAssignment.id == assignment_id,
            UserUnitAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await db.delete(assignment)
    await db.commit()


# =============================================================================
# Schema Service Endpoints
# =============================================================================

@app.get("/schemas/{resource_type}/units/{unit_id}")
async def get_unit_schema(
    resource_type: str,
    unit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Get the merged (inherited + local) schema for a unit."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    merged_schema, field_metadata = await get_merged_schema(db, t_id, unit_id, resource_type)
    return {"schema": merged_schema, "field_metadata": field_metadata}


@app.get("/schemas/{resource_type}/units/{unit_id}/local")
async def get_unit_local_schema(
    resource_type: str,
    unit_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Get only the locally-defined schema for a unit (no inheritance)."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    schema = await get_local_schema(db, t_id, unit_id, resource_type)
    return {"schema": schema or {}, "unit_id": str(unit_id), "resource_type": resource_type}


@app.post("/schemas/{resource_type}/units/{unit_id}", response_model=ResourceSchemaRead)
async def create_or_update_unit_schema(
    resource_type: str,
    unit_id: UUID,
    schema_in: ResourceSchemaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(has_permission("ADMIN")),
):
    """Create or update the local schema for a unit."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    is_valid, error = await validate_schema_modification(
        db, t_id, unit_id, resource_type, schema_in.schema_definition
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    schema = await save_unit_schema(db, t_id, unit_id, resource_type, schema_in.schema_definition)
    return schema


@app.get("/schemas/{resource_type}/units")
async def list_unit_schemas(
    resource_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """List all schemas for a resource_type in the current tenant."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    result = await db.execute(
        select(ResourceSchema).where(
            ResourceSchema.tenant_id == t_id,
            ResourceSchema.resource_type == resource_type,
        )
    )
    schemas = result.scalars().all()
    return [{"unit_id": str(s.unit_id), "resource_type": s.resource_type, "schema": s.schema_definition} for s in schemas]


# ============================================================
# NIH RePORTER — Profile Lookup & Project Sync (Phase 2)
# ============================================================

class NIHProfileResult(BaseModel):
    full_name: str
    profile_id: int
    org: str


class NIHProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    appl_id: int
    project_title: str
    project_num: str
    core_project_num: str
    fiscal_year: int
    total_costs: int
    direct_costs: int
    indirect_costs: int
    project_start_date: Optional[Any] = None
    project_end_date: Optional[Any] = None
    user_id: UUID


@app.get("/nih/lookup", response_model=List[NIHProfileResult])
async def nih_profile_lookup(
    first_name: str,
    last_name: str,
    state: Optional[str] = None,
    current_user: User = Depends(require_auth),
    _priv=Depends(has_permission("FULL", None)),
):
    """Search NIH RePORTER for investigators by name + optional state."""
    matches = await nih_service.lookup_nih_profile(first_name, last_name, state)
    return matches


@app.post("/users/{user_id}/assign-nih-profile")
async def assign_nih_profile(
    user_id: UUID,
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Assign a NIH profile ID to a user."""
    t_id = get_current_tenant()
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == t_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.nih_profile_id = profile_id
    await db.commit()
    return {"status": "ok", "nih_profile_id": profile_id}


@app.post("/users/{user_id}/sync-nih-projects")
async def sync_user_nih_projects(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Sync NIH RePORTER projects for a single user."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == t_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sync_result = await nih_service.sync_user_nih_projects(db, t_id, user)
    await db.commit()
    return sync_result


@app.post("/users/sync-all-nih-projects")
async def sync_all_nih_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _priv=Depends(has_permission("ADMIN", None)),
):
    """Sync NIH RePORTER projects for all users with a nih_profile_id."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    result = await db.execute(
        select(User).where(
            User.tenant_id == t_id,
            User.nih_profile_id.isnot(None),
            User.is_active == True,
        )
    )
    users = result.scalars().all()

    totals = {"new": 0, "updated": 0, "skipped": 0, "errors": 0, "users_synced": 0}
    for user in users:
        sync_result = await nih_service.sync_user_nih_projects(db, t_id, user)
        if sync_result["status"] == "success":
            totals["new"] += sync_result["new"]
            totals["updated"] += sync_result["updated"]
            totals["users_synced"] += 1
        elif "skipped" in sync_result["status"]:
            totals["skipped"] += 1
        else:
            totals["errors"] += 1

    await db.commit()
    return totals


@app.get("/nih/projects")
async def list_nih_projects(
    user_id: Optional[UUID] = None,
    search: Optional[str] = None,
    fiscal_year: Optional[int] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """List NIH projects for the current tenant with optional filters."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    stmt = select(NIHReporterProject).where(NIHReporterProject.tenant_id == t_id)

    if user_id:
        stmt = stmt.where(NIHReporterProject.user_id == user_id)
    if search:
        stmt = stmt.where(
            NIHReporterProject.project_title.ilike(f"%{search}%")
            | NIHReporterProject.project_num.ilike(f"%{search}%")
            | NIHReporterProject.core_project_num.ilike(f"%{search}%")
        )
    if fiscal_year:
        stmt = stmt.where(NIHReporterProject.fiscal_year == fiscal_year)
    if active_only:
        today = datetime.now().date()
        stmt = stmt.where(NIHReporterProject.project_end_date >= today)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    stmt = stmt.order_by(
        NIHReporterProject.core_project_num,
        NIHReporterProject.fiscal_year.desc(),
    ).offset(offset).limit(limit)

    result = await db.execute(stmt)
    projects = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": str(p.id),
                "appl_id": p.appl_id,
                "project_title": p.project_title,
                "project_num": p.project_num,
                "core_project_num": p.core_project_num,
                "fiscal_year": p.fiscal_year,
                "total_costs": p.total_costs,
                "direct_costs": p.direct_costs,
                "indirect_costs": p.indirect_costs,
                "project_start_date": p.project_start_date.isoformat() if p.project_start_date else None,
                "project_end_date": p.project_end_date.isoformat() if p.project_end_date else None,
                "user_id": str(p.user_id),
            }
            for p in projects
        ],
    }


# ============================================================
# ORCID Integration (Phase 3)
# ============================================================

@app.get("/orcid/search")
async def orcid_search(
    first_name: str,
    last_name: str,
    institution: Optional[str] = None,
    current_user: User = Depends(require_auth),
    _priv=Depends(has_permission("FULL", None)),
):
    """Search ORCID public API for researchers by name + optional institution."""
    return await orcid_service.search_orcid_by_name(first_name, last_name, institution)


@app.put("/users/{user_id}/orcid")
async def assign_orcid_id(
    user_id: UUID,
    orcid_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Assign an ORCID iD to a user."""
    t_id = get_current_tenant()
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == t_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.orcid_id = orcid_id
    await db.commit()
    return {"status": "ok", "orcid_id": orcid_id}


@app.post("/users/{user_id}/sync-orcid")
async def sync_user_orcid(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Sync publications from ORCID for a single user."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == t_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sync_result = await orcid_service.sync_user_orcid_publications(db, t_id, user)
    await db.commit()
    return sync_result


@app.post("/users/sync-all-orcid")
async def sync_all_orcid(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _priv=Depends(has_permission("ADMIN", None)),
):
    """Sync ORCID publications for all users with an orcid_id."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    result = await db.execute(
        select(User).where(
            User.tenant_id == t_id,
            User.orcid_id.isnot(None),
            User.is_active == True,
        )
    )
    users = result.scalars().all()
    totals = {"new": 0, "updated": 0, "skipped": 0, "errors": 0, "users_synced": 0}
    for user in users:
        r = await orcid_service.sync_user_orcid_publications(db, t_id, user)
        if r["status"] == "success":
            totals["new"] += r["new"]
            totals["updated"] += r["updated"]
            totals["users_synced"] += 1
        elif "skipped" in r["status"]:
            totals["skipped"] += 1
        else:
            totals["errors"] += 1
    await db.commit()
    return totals


# ============================================================
# PubMed Integration (Phase 4)
# ============================================================

class PubMedTestQueryRequest(BaseModel):
    query: str


@app.post("/pubmed/test-query")
async def pubmed_test_query(
    body: PubMedTestQueryRequest,
    current_user: User = Depends(require_auth),
):
    """Run a PubMed query and return count + sample results (no DB write)."""
    pmids = await pubmed_service.search_pubmed(body.query, retmax=10)
    if not pmids:
        return {"count": 0, "sample": []}
    records = await pubmed_service.fetch_pubmed_records(pmids)
    return {"count": len(pmids), "sample": records[:10]}


@app.put("/users/{user_id}/pubmed-query")
async def set_pubmed_query(
    user_id: UUID,
    query: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Set the stored PubMed query for a user."""
    t_id = get_current_tenant()
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == t_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.pubmed_query = query
    await db.commit()
    return {"status": "ok"}


@app.post("/users/{user_id}/sync-pubmed")
async def sync_user_pubmed(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Sync publications from PubMed for a single user using their stored query."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == t_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sync_result = await pubmed_service.sync_user_pubmed_publications(db, t_id, user)
    await db.commit()
    return sync_result


@app.post("/users/sync-all-pubmed")
async def sync_all_pubmed(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _priv=Depends(has_permission("ADMIN", None)),
):
    """Sync PubMed publications for all users with a pubmed_query."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    result = await db.execute(
        select(User).where(
            User.tenant_id == t_id,
            User.pubmed_query.isnot(None),
            User.is_active == True,
        )
    )
    users = result.scalars().all()
    totals = {"new": 0, "updated": 0, "skipped": 0, "errors": 0, "users_synced": 0}
    for user in users:
        r = await pubmed_service.sync_user_pubmed_publications(db, t_id, user)
        if r["status"] == "success":
            totals["new"] += r["new"]
            totals["updated"] += r["updated"]
            totals["users_synced"] += 1
        elif "skipped" in r["status"]:
            totals["skipped"] += 1
        else:
            totals["errors"] += 1
    await db.commit()
    return totals


# ============================================================
# Publications — unified list (Phases 3 & 4)
# ============================================================

@app.get("/publications")
async def list_publications(
    user_id: Optional[UUID] = None,
    source: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """List publications for the current tenant with optional filters."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    stmt = select(Publication).where(Publication.tenant_id == t_id)
    if user_id:
        stmt = stmt.where(Publication.user_id == user_id)
    if source:
        stmt = stmt.where(Publication.source == source)
    if year_from:
        stmt = stmt.where(Publication.pub_year >= year_from)
    if year_to:
        stmt = stmt.where(Publication.pub_year <= year_to)
    if search:
        stmt = stmt.where(Publication.title.ilike(f"%{search}%"))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.order_by(Publication.pub_year.desc().nullslast(), Publication.title).offset(offset).limit(limit)
    pubs = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": str(p.id),
                "user_id": str(p.user_id),
                "title": p.title,
                "journal": p.journal,
                "pub_year": p.pub_year,
                "pub_date": p.pub_date.isoformat() if p.pub_date else None,
                "authors": p.authors,
                "doi": p.doi,
                "pmid": p.pmid,
                "source": p.source,
                "orcid_put_code": p.orcid_put_code,
            }
            for p in pubs
        ],
    }


# ============================================================
# Metrics (Phase 5)
# ============================================================

@app.get("/metrics/summary")
async def metrics_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """High-level summary counts for the current tenant."""
    t_id = get_current_tenant()
    if not t_id:
        raise HTTPException(status_code=400, detail="No tenant context")

    users_count = (await db.execute(
        select(func.count()).select_from(User).where(
            User.tenant_id == t_id, User.is_active == True
        )
    )).scalar()

    investigators_count = (await db.execute(
        select(func.count()).select_from(User).where(
            User.tenant_id == t_id,
            User.is_active == True,
            User.is_covered_investigator == True,
        )
    )).scalar()

    grants_count = (await db.execute(
        select(func.count()).select_from(NIHReporterProject).where(
            NIHReporterProject.tenant_id == t_id
        )
    )).scalar()

    publications_count = (await db.execute(
        select(func.count()).select_from(Publication).where(
            Publication.tenant_id == t_id
        )
    )).scalar()

    nih_linked = (await db.execute(
        select(func.count()).select_from(User).where(
            User.tenant_id == t_id,
            User.nih_profile_id.isnot(None),
        )
    )).scalar()

    orcid_linked = (await db.execute(
        select(func.count()).select_from(User).where(
            User.tenant_id == t_id,
            User.orcid_id.isnot(None),
        )
    )).scalar()

    return {
        "users": users_count,
        "investigators": investigators_count,
        "grants": grants_count,
        "publications": publications_count,
        "nih_linked": nih_linked,
        "orcid_linked": orcid_linked,
    }
