"""Schema service layer for hierarchical schema inheritance.

Parent unit schemas cascade down to child units as read-only fields.
"""

import copy
from typing import Dict, Any, List, Tuple, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ResourceSchema, Unit


async def get_merged_schema(
    db: AsyncSession,
    tenant_id: UUID,
    unit_id: UUID,
    resource_type: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Fetch and merge schemas from the unit hierarchy.

    Schemas are merged from parent to child (root to leaf), with parent schemas
    taking precedence. Returns (merged_schema, field_metadata).
    """
    result = await db.execute(select(Unit).where(Unit.id == unit_id))
    target_unit = result.scalar_one_or_none()
    if not target_unit:
        return {}, []

    ancestor_ids = [UUID(uid) for uid in target_unit.tree_path.split(".")]

    stmt = (
        select(ResourceSchema, Unit.id, Unit.name, Unit.unit_level)
        .join(Unit, ResourceSchema.unit_id == Unit.id)
        .where(
            ResourceSchema.tenant_id == tenant_id,
            ResourceSchema.unit_id.in_(ancestor_ids),
            ResourceSchema.resource_type == resource_type,
        )
        .order_by(Unit.unit_level.asc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    merged_properties: Dict[str, Any] = {}
    merged_required: set = set()
    merged_categories: Dict[str, Any] = {}
    field_metadata: List[Dict[str, Any]] = []

    for row in rows:
        schema_obj, unit_id_row, unit_name, unit_level = row
        schema_def = schema_obj.schema_definition

        properties = schema_def.get("properties", {})
        required = schema_def.get("required", [])

        categories = schema_def.get("x-categories", {})
        for cat_key, cat_def in categories.items():
            if cat_key not in merged_categories:
                merged_categories[cat_key] = copy.deepcopy(cat_def)

        is_inherited = unit_id_row != unit_id

        for field_key, field_def in properties.items():
            if field_key not in merged_properties:
                merged_properties[field_key] = copy.deepcopy(field_def)
                field_metadata.append({
                    "key": field_key,
                    "defined_by_unit_id": str(unit_id_row),
                    "unit_name": unit_name,
                    "unit_level": unit_level,
                    "inherited": is_inherited,
                })
                if field_key in required:
                    merged_required.add(field_key)

    merged_schema: Dict[str, Any] = {
        "type": "object",
        "properties": merged_properties,
        "required": list(merged_required),
        "additionalProperties": False,
    }
    if merged_categories:
        merged_schema["x-categories"] = merged_categories

    return merged_schema, field_metadata


async def get_local_schema(
    db: AsyncSession,
    tenant_id: UUID,
    unit_id: UUID,
    resource_type: str,
) -> Optional[Dict[str, Any]]:
    """Fetch only the local (non-inherited) schema for this unit."""
    result = await db.execute(
        select(ResourceSchema).where(
            ResourceSchema.tenant_id == tenant_id,
            ResourceSchema.unit_id == unit_id,
            ResourceSchema.resource_type == resource_type,
        )
    )
    schema = result.scalar_one_or_none()
    return schema.schema_definition if schema else None


async def save_unit_schema(
    db: AsyncSession,
    tenant_id: UUID,
    unit_id: UUID,
    resource_type: str,
    schema_definition: Dict[str, Any],
) -> ResourceSchema:
    """Create or update a unit's local schema."""
    result = await db.execute(
        select(ResourceSchema).where(
            ResourceSchema.tenant_id == tenant_id,
            ResourceSchema.unit_id == unit_id,
            ResourceSchema.resource_type == resource_type,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.schema_definition = schema_definition
        await db.commit()
        await db.refresh(existing)
        return existing

    new_schema = ResourceSchema(
        tenant_id=tenant_id,
        unit_id=unit_id,
        resource_type=resource_type,
        schema_definition=schema_definition,
    )
    db.add(new_schema)
    await db.commit()
    await db.refresh(new_schema)
    return new_schema


async def validate_schema_modification(
    db: AsyncSession,
    tenant_id: UUID,
    unit_id: UUID,
    resource_type: str,
    new_local_fields: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Validate that the modification does not override inherited fields."""
    _, field_metadata = await get_merged_schema(db, tenant_id, unit_id, resource_type)
    inherited_keys = {fm["key"] for fm in field_metadata if fm["inherited"]}
    new_field_keys = set(new_local_fields.get("properties", {}).keys())
    conflicting = inherited_keys & new_field_keys

    if conflicting:
        conflict_details = []
        for key in conflicting:
            meta = next((fm for fm in field_metadata if fm["key"] == key), None)
            if meta:
                conflict_details.append(f"{key} (from {meta['unit_name']})")
        return False, f"Cannot override inherited fields: {', '.join(conflict_details)}"

    return True, None


async def get_inherited_field_keys(
    db: AsyncSession,
    tenant_id: UUID,
    unit_id: UUID,
    resource_type: str,
) -> set:
    """Return the set of field keys inherited from parent units."""
    _, field_metadata = await get_merged_schema(db, tenant_id, unit_id, resource_type)
    return {fm["key"] for fm in field_metadata if fm["inherited"]}
