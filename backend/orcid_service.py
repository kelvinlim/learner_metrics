"""ORCID Public API service.

Provides:
- Researcher iD search by name/institution
- Works retrieval for a given ORCID iD
- Publication sync per user

Uses ORCID Public API v3.0 — no OAuth required for public records.
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Publication, User

logger = logging.getLogger(__name__)

ORCID_API = "https://pub.orcid.org/v3.0"
ORCID_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "LearnerMetrics/1.0 (mailto:admin@example.com)",
}


async def search_orcid_by_name(
    first_name: str,
    last_name: str,
    institution: Optional[str] = None,
) -> List[dict]:
    """Search ORCID for researchers matching name + optional institution.

    Returns list of {orcid_id, name, affiliation}.
    """
    parts = [f'given-names:"{first_name}"', f'family-name:"{last_name}"']
    if institution:
        parts.append(f'affiliation-org-name:"{institution}"')
    q = " AND ".join(parts)

    try:
        async with httpx.AsyncClient(timeout=15, headers=ORCID_HEADERS) as client:
            r = await client.get(f"{ORCID_API}/search", params={"q": q, "rows": 20})
            r.raise_for_status()

        data = r.json()
        results = data.get("result", [])
        matches = []
        for item in results:
            orcid_id = item.get("orcid-identifier", {}).get("path")
            if not orcid_id:
                continue
            # Fetch summary for name/affiliation
            try:
                async with httpx.AsyncClient(timeout=10, headers=ORCID_HEADERS) as client:
                    sr = await client.get(f"{ORCID_API}/{orcid_id}/person")
                    sr.raise_for_status()
                person = sr.json()
                name_obj = person.get("name") or {}
                given = (name_obj.get("given-names") or {}).get("value", "")
                family = (name_obj.get("family-name") or {}).get("value", "")
                full_name = f"{given} {family}".strip()

                affiliations = person.get("employments", {}).get("employment-summary", [])
                affil_name = ""
                if affiliations:
                    affil_name = (
                        affiliations[0]
                        .get("organization", {})
                        .get("name", "")
                    )
            except Exception:
                full_name = orcid_id
                affil_name = ""

            matches.append({
                "orcid_id": orcid_id,
                "name": full_name,
                "affiliation": affil_name,
            })

        return matches

    except httpx.HTTPStatusError as e:
        logger.error(f"ORCID search HTTP error: {e.response.status_code}")
        return []
    except Exception as e:
        logger.error(f"ORCID search failed: {e}")
        return []


def _extract_doi(work: dict) -> Optional[str]:
    """Pull DOI from an ORCID work's external-ids."""
    eids = work.get("external-ids", {}).get("external-id", [])
    for eid in eids:
        if eid.get("external-id-type") == "doi":
            return (eid.get("external-id-value") or "").strip().lower() or None
    return None


def _extract_pmid(work: dict) -> Optional[str]:
    """Pull PMID from an ORCID work's external-ids."""
    eids = work.get("external-ids", {}).get("external-id", [])
    for eid in eids:
        if eid.get("external-id-type") == "pmid":
            return (eid.get("external-id-value") or "").strip() or None
    return None


def _parse_orcid_date(pub_date: Optional[dict]) -> tuple[Optional[int], Optional[str]]:
    """Return (year, iso_date_str) from an ORCID publication-date dict."""
    if not pub_date:
        return None, None
    year_obj = pub_date.get("year") or {}
    month_obj = pub_date.get("month") or {}
    day_obj = pub_date.get("day") or {}
    year = int(year_obj.get("value", 0)) if year_obj.get("value") else None
    month = month_obj.get("value")
    day = day_obj.get("value")
    if year and month and day:
        try:
            iso = f"{year}-{int(month):02d}-{int(day):02d}"
            return year, iso
        except Exception:
            pass
    return year, None


async def get_orcid_works(orcid_id: str) -> List[dict]:
    """Retrieve all works for an ORCID iD, returning normalized publication dicts."""
    try:
        async with httpx.AsyncClient(timeout=30, headers=ORCID_HEADERS) as client:
            r = await client.get(f"{ORCID_API}/{orcid_id}/works")
            r.raise_for_status()
    except Exception as e:
        logger.error(f"ORCID works fetch failed for {orcid_id}: {e}")
        return []

    data = r.json()
    groups = data.get("group", [])
    publications = []

    for group in groups:
        summaries = group.get("work-summary", [])
        if not summaries:
            continue
        # Take the preferred (first) summary
        summary = summaries[0]
        put_code = str(summary.get("put-code", ""))
        title_obj = summary.get("title") or {}
        title = (title_obj.get("title") or {}).get("value") or ""
        journal = (summary.get("journal-title") or {}).get("value") or ""
        pub_date = summary.get("publication-date")
        year, iso_date = _parse_orcid_date(pub_date)
        doi = _extract_doi(summary)
        pmid = _extract_pmid(summary)

        # Attempt to get contributors from the full work record for author list
        authors = ""
        try:
            async with httpx.AsyncClient(timeout=10, headers=ORCID_HEADERS) as client:
                wr = await client.get(f"{ORCID_API}/{orcid_id}/work/{put_code}")
                wr.raise_for_status()
            full_work = wr.json()
            contributors = (
                (full_work.get("contributors") or {})
                .get("contributor", [])
            )
            author_names = [
                (c.get("credit-name") or {}).get("value", "")
                for c in contributors
                if c.get("contributor-attributes", {}).get("contributor-role") == "author"
            ]
            authors = "; ".join(filter(None, author_names))
            # Also try to get DOI/PMID from full record if not in summary
            if not doi:
                doi = _extract_doi(full_work)
            if not pmid:
                pmid = _extract_pmid(full_work)
        except Exception:
            pass

        if not title:
            continue

        publications.append({
            "put_code": put_code,
            "title": title[:500],
            "journal": journal[:200] if journal else "",
            "pub_year": year,
            "pub_date": iso_date,
            "doi": doi[:200] if doi else None,
            "pmid": pmid[:20] if pmid else None,
            "authors": authors[:2000] if authors else "",
            "raw": summary,
        })

    return publications


async def sync_user_orcid_publications(
    db: AsyncSession,
    tenant_id: UUID,
    user: User,
) -> dict:
    """Sync publications from ORCID for a single user.

    Returns {new, updated, status}.
    """
    if not user.orcid_id:
        return {"new": 0, "updated": 0, "status": "skipped — no orcid_id"}

    works = await get_orcid_works(user.orcid_id)
    count_new = 0
    count_updated = 0

    for work in works:
        put_code = work["put_code"]
        doi = work.get("doi")
        pmid = work.get("pmid")

        # Find existing by put_code first, then doi/pmid
        existing = None

        result = await db.execute(
            select(Publication).where(
                Publication.tenant_id == tenant_id,
                Publication.user_id == user.id,
                Publication.orcid_put_code == put_code,
            )
        )
        existing = result.scalar_one_or_none()

        if not existing and doi:
            result = await db.execute(
                select(Publication).where(
                    Publication.tenant_id == tenant_id,
                    Publication.user_id == user.id,
                    Publication.doi == doi,
                )
            )
            existing = result.scalar_one_or_none()

        if not existing and pmid:
            result = await db.execute(
                select(Publication).where(
                    Publication.tenant_id == tenant_id,
                    Publication.user_id == user.id,
                    Publication.pmid == pmid,
                )
            )
            existing = result.scalar_one_or_none()

        title = work["title"]
        journal = work.get("journal") or ""
        pub_year = work.get("pub_year")
        pub_date_str = work.get("pub_date")
        authors = work.get("authors") or ""

        from datetime import date as date_type
        pub_date = None
        if pub_date_str:
            try:
                pub_date = date_type.fromisoformat(pub_date_str)
            except Exception:
                pass

        if existing:
            existing.title = title
            existing.journal = journal or existing.journal
            existing.pub_year = pub_year or existing.pub_year
            existing.pub_date = pub_date or existing.pub_date
            existing.authors = authors or existing.authors
            existing.orcid_put_code = put_code
            existing.doi = doi or existing.doi
            existing.pmid = pmid or existing.pmid
            # If it was pubmed-only, mark as both
            if existing.source == "pubmed":
                existing.source = "both"
            elif existing.source != "both":
                existing.source = "orcid"
            existing.raw_data = work.get("raw", {})
            count_updated += 1
        else:
            pub = Publication(
                tenant_id=tenant_id,
                user_id=user.id,
                title=title,
                journal=journal,
                pub_year=pub_year,
                pub_date=pub_date,
                authors=authors,
                doi=doi,
                pmid=pmid,
                source="orcid",
                orcid_put_code=put_code,
                raw_data=work.get("raw", {}),
            )
            db.add(pub)
            count_new += 1

    user.orcid_last_updated = datetime.now()
    return {"new": count_new, "updated": count_updated, "status": "success"}
