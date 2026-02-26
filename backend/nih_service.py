"""NIH RePORTER API service.

Provides:
- Profile ID lookup by name/state
- Project sync (10-year lookback) per investigator profile ID
"""

import logging
from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import NIHReporterProject, User

logger = logging.getLogger(__name__)

NIH_API_URL = "https://api.reporter.nih.gov/v2/projects/search"
NIH_SYNC_YEARS = 10  # Years of lookback for project sync

# Fields to retrieve during project sync — same set as dept_dashboard
NIH_PROJECT_FIELDS = [
    "ApplId", "SubprojectId", "FiscalYear", "ProjectNum", "ProjectSerialNum",
    "Organization", "OrganizationType", "AwardType", "ActivityCode", "AwardAmount",
    "ProjectNumSplit", "PrincipalInvestigators", "ProgramOfficers", "AgencyIcAdmin",
    "AgencyIcFundings", "CongDist", "ProjectStartDate", "ProjectEndDate",
    "OpportunityNumber", "FullStudySection", "AwardNoticeDate", "CoreProjectNum",
    "PrefTerms", "ProjectTitle", "PhrText", "AbstractText", "SpendingCategoriesDesc",
    "ArraFunded", "BudgetStart", "BudgetEnd", "CfdaCode", "FundingMechanism",
    "DirectCostAmt", "IndirectCostAmt",
]


async def lookup_nih_profile(
    first_name: str,
    last_name: str,
    state: Optional[str] = None,
) -> List[dict]:
    """Search NIH RePORTER for investigators matching name/state.

    Returns deduplicated list of {full_name, profile_id, org}.
    """
    criteria: dict = {
        "pi_names": [{"first_name": first_name, "last_name": last_name}]
    }
    if state:
        criteria["org_states"] = [state.upper()]

    payload = {
        "criteria": criteria,
        "include_fields": ["PrincipalInvestigators", "Organization"],
        "limit": 25,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(NIH_API_URL, json=payload)
            response.raise_for_status()

        results = response.json().get("results", [])
        matches: list[dict] = []
        seen_ids: set[int] = set()

        for project in results:
            pi_list = project.get("principal_investigators", [])
            for pi in pi_list:
                if pi.get("last_name", "").lower() != last_name.lower():
                    continue
                pid = pi.get("profile_id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    matches.append({
                        "full_name": f"{pi.get('first_name', '')} {pi.get('last_name', '')}".strip(),
                        "profile_id": pid,
                        "org": project.get("organization", {}).get("org_name", ""),
                    })

        return matches

    except httpx.HTTPStatusError as e:
        logger.error(f"NIH API HTTP error: {e.response.status_code} — {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"NIH profile lookup failed: {e}")
        return []


def _parse_nih_date(date_str: Optional[str]) -> Optional[date]:
    """Parse NIH ISO date strings like '2024-05-31T00:00:00Z'."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except Exception:
        return None


async def sync_user_nih_projects(
    db: AsyncSession,
    tenant_id: UUID,
    user: User,
) -> dict:
    """Sync NIH RePORTER projects for a single investigator.

    Returns {new, updated, status}.
    """
    if not user.nih_profile_id:
        return {"new": 0, "updated": 0, "status": "skipped — no nih_profile_id"}

    current_year = datetime.now().year
    fiscal_years = list(range(current_year - NIH_SYNC_YEARS, current_year + 1))

    payload = {
        "criteria": {
            "pi_profile_ids": [user.nih_profile_id],
            "fiscal_years": fiscal_years,
        },
        "include_fields": NIH_PROJECT_FIELDS,
        "offset": 0,
        "limit": 500,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(NIH_API_URL, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"NIH sync HTTP error for user {user.id}: {e}")
        return {"new": 0, "updated": 0, "status": f"error: {e}"}

    results = response.json().get("results", [])
    count_new = 0
    count_updated = 0

    for project_data in results:
        appl_id = project_data.get("appl_id")
        if not appl_id:
            continue

        direct = project_data.get("direct_cost_amt") or 0
        indirect = project_data.get("indirect_cost_amt") or 0
        total_costs = direct + indirect

        # Fetch existing by (tenant_id, appl_id)
        result = await db.execute(
            select(NIHReporterProject).where(
                NIHReporterProject.tenant_id == tenant_id,
                NIHReporterProject.appl_id == appl_id,
            )
        )
        existing = result.scalar_one_or_none()

        project_title = (project_data.get("project_title") or "")[:300]
        project_num = (project_data.get("project_num") or "")[:30]
        core_project_num = (project_data.get("core_project_num") or "")[:30]
        fiscal_year = project_data.get("fiscal_year") or 0
        start_date = _parse_nih_date(project_data.get("project_start_date"))
        end_date = _parse_nih_date(project_data.get("project_end_date"))

        if existing:
            existing.project_title = project_title
            existing.project_num = project_num
            existing.core_project_num = core_project_num
            existing.fiscal_year = fiscal_year
            existing.total_costs = total_costs
            existing.direct_costs = direct
            existing.indirect_costs = indirect
            existing.project_start_date = start_date
            existing.project_end_date = end_date
            existing.project_details = project_data
            count_updated += 1
        else:
            new_project = NIHReporterProject(
                tenant_id=tenant_id,
                user_id=user.id,
                appl_id=appl_id,
                project_title=project_title,
                project_num=project_num,
                core_project_num=core_project_num,
                fiscal_year=fiscal_year,
                total_costs=total_costs,
                direct_costs=direct,
                indirect_costs=indirect,
                project_start_date=start_date,
                project_end_date=end_date,
                project_details=project_data,
            )
            db.add(new_project)
            count_new += 1

    user.nih_reporter_last_updated = datetime.now()

    return {"new": count_new, "updated": count_updated, "status": "success"}
