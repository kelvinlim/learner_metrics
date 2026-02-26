"""
Authentication Service — Google OAuth + JWT

Only Google OAuth is supported for login (as per Description.md).
JWT tokens carry sub (user_id), tenant_id, and identity_id claims.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import jwt
from jwt.exceptions import PyJWTError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Identity, TenantMembership, User, Tenant
from backend.config import settings

logger = logging.getLogger(__name__)

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


# ============================================================
# Google OAuth2 Verification
# ============================================================

async def verify_google_token(token: str) -> Optional[dict]:
    """Verify a Google ID token. Returns payload or None on failure."""
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        logger.error("GOOGLE_CLIENT_ID not configured")
        return None
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            client_id,
        )
        if idinfo.get("aud") != client_id:
            logger.error("Google token audience mismatch")
            return None
        return idinfo
    except ValueError as e:
        logger.error(f"Google token verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying Google token: {e}")
        return None


# ============================================================
# JWT Token Management
# ============================================================

def create_access_token(user_id: UUID, tenant_id: UUID, identity_id: Optional[UUID] = None) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "exp": expire,
    }
    if identity_id:
        payload["identity_id"] = str(identity_id)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate an access token. Returns payload or None."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except PyJWTError:
        return None


# ============================================================
# Identity & Tenant Lookup
# ============================================================

async def get_or_create_identity(db: AsyncSession, email: str, google_sub: str,
                                  first_name: str = "", last_name: str = "") -> Identity:
    """Find existing identity by Google sub or email, or create a new one."""
    # Try by google_sub first (most stable identifier)
    result = await db.execute(select(Identity).where(Identity.google_sub == google_sub))
    identity = result.scalar_one_or_none()
    if identity:
        return identity

    # Try by email (handles first Google login after manual creation)
    result = await db.execute(select(Identity).where(Identity.email == email))
    identity = result.scalar_one_or_none()
    if identity:
        if not identity.google_sub:
            identity.google_sub = google_sub
            await db.commit()
            await db.refresh(identity)
        return identity

    # Create new identity
    identity = Identity(
        email=email,
        google_sub=google_sub,
        first_name=first_name,
        last_name=last_name,
    )
    db.add(identity)
    await db.commit()
    await db.refresh(identity)
    return identity


async def get_tenants_for_identity(db: AsyncSession, identity_id: UUID) -> list[dict]:
    """Return list of {tenant_id, tenant_name} for an identity's memberships."""
    result = await db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, TenantMembership.tenant_id == Tenant.id)
        .where(
            TenantMembership.identity_id == identity_id,
            TenantMembership.status == "active",
            Tenant.status == "active",
        )
    )
    rows = result.all()
    return [
        {"tenant_id": str(row.Tenant.id), "tenant_name": row.Tenant.name}
        for row in rows
    ]


async def get_or_create_user_for_tenant(
    db: AsyncSession, identity: Identity, tenant_id: UUID
) -> User:
    """Find user for this identity+tenant combo, or create if auto-provision is enabled."""
    result = await db.execute(
        select(TenantMembership)
        .where(
            TenantMembership.identity_id == identity.id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise ValueError(f"No membership found for identity {identity.id} in tenant {tenant_id}")

    result = await db.execute(select(User).where(User.id == membership.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"Membership references missing user {membership.user_id}")
    return user
