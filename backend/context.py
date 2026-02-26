from contextvars import ContextVar
from uuid import UUID
from typing import Optional

# Context variable to store the current tenant ID for the request
tenant_id_context: ContextVar[Optional[UUID]] = ContextVar("tenant_id", default=None)


def set_current_tenant(t_id: UUID):
    tenant_id_context.set(t_id)


def get_current_tenant() -> Optional[UUID]:
    return tenant_id_context.get()
