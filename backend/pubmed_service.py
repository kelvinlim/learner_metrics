"""PubMed E-utilities service.

Provides:
- PubMed query search (esearch)
- Record fetch + XML parse (efetch)
- Publication sync per user using their stored pubmed_query

Uses NCBI E-utilities. Set NCBI_API_KEY env var for higher rate limits (10/s vs 3/s).
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import Publication, User

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _ncbi_params(extra: dict) -> dict:
    p = {"db": "pubmed", "retmode": "json", **extra}
    api_key = getattr(settings, "NCBI_API_KEY", None)
    if api_key:
        p["api_key"] = api_key
    return p


async def search_pubmed(query: str, retmax: int = 500) -> List[str]:
    """Run an esearch query and return a list of PMIDs."""
    params = _ncbi_params({"term": query, "retmax": retmax, "usehistory": "n"})
    # Switch to json for esearch
    params["retmode"] = "json"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
            r.raise_for_status()
        data = r.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.error(f"PubMed esearch failed: {e}")
        return []


def _parse_article(article_elem: ET.Element) -> Optional[dict]:
    """Parse a PubmedArticle XML element into a publication dict."""
    try:
        medline = article_elem.find("MedlineCitation")
        if medline is None:
            return None
        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text.strip() if pmid_elem is not None else None

        art = medline.find("Article")
        if art is None:
            return None

        title_elem = art.find("ArticleTitle")
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
        if not title:
            return None

        # Journal
        journal = ""
        journal_elem = art.find("Journal")
        if journal_elem is not None:
            jt = journal_elem.find("Title")
            if jt is not None:
                journal = jt.text or ""

        # Publication date
        pub_year = None
        pub_date = None
        pub_date_elem = (
            art.find("Journal/JournalIssue/PubDate")
            or medline.find("Article/Journal/JournalIssue/PubDate")
        )
        if pub_date_elem is not None:
            year_e = pub_date_elem.find("Year")
            month_e = pub_date_elem.find("Month")
            day_e = pub_date_elem.find("Day")
            if year_e is not None and year_e.text:
                try:
                    pub_year = int(year_e.text)
                    month = month_e.text if month_e is not None else "Jan"
                    day = int(day_e.text) if day_e is not None and day_e.text else 1
                    # Convert month name to number
                    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,
                              "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10,
                              "Nov": 11, "Dec": 12}
                    month_num = months.get(month[:3].title(), 1) if not month.isdigit() else int(month)
                    pub_date = date(pub_year, month_num, day)
                except Exception:
                    pass

        # Authors
        author_list = art.find("AuthorList")
        author_names = []
        if author_list is not None:
            for author in author_list.findall("Author"):
                ln = author.find("LastName")
                fn = author.find("ForeName") or author.find("Initials")
                collective = author.find("CollectiveName")
                if collective is not None and collective.text:
                    author_names.append(collective.text)
                elif ln is not None and ln.text:
                    name = ln.text
                    if fn is not None and fn.text:
                        name += f" {fn.text}"
                    author_names.append(name)
        authors = "; ".join(author_names)

        # DOI from ArticleIdList
        doi = None
        article_id_list = article_elem.find("PubmedData/ArticleIdList")
        if article_id_list is not None:
            for aid in article_id_list.findall("ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text.strip().lower()
                    break

        return {
            "pmid": pmid,
            "doi": doi[:200] if doi else None,
            "title": title[:500],
            "journal": journal[:200],
            "pub_year": pub_year,
            "pub_date": pub_date,
            "authors": authors[:2000],
        }
    except Exception as e:
        logger.warning(f"Failed to parse PubMed article: {e}")
        return None


async def fetch_pubmed_records(pmids: List[str]) -> List[dict]:
    """Fetch full records for a list of PMIDs via efetch XML."""
    if not pmids:
        return []
    params: dict = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml",
    }
    api_key = getattr(settings, "NCBI_API_KEY", None)
    if api_key:
        params["api_key"] = api_key
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params)
            r.raise_for_status()
        root = ET.fromstring(r.content)
        records = []
        for article_elem in root.findall("PubmedArticle"):
            parsed = _parse_article(article_elem)
            if parsed:
                records.append(parsed)
        return records
    except Exception as e:
        logger.error(f"PubMed efetch failed: {e}")
        return []


async def sync_user_pubmed_publications(
    db: AsyncSession,
    tenant_id: UUID,
    user: User,
) -> dict:
    """Sync publications from PubMed for a single user.

    Uses user.pubmed_query. Merges with existing ORCID records by PMID/DOI.
    Returns {new, updated, status}.
    """
    if not user.pubmed_query:
        return {"new": 0, "updated": 0, "status": "skipped — no pubmed_query"}

    pmids = await search_pubmed(user.pubmed_query)
    if not pmids:
        return {"new": 0, "updated": 0, "status": "success — no results"}

    records = await fetch_pubmed_records(pmids)
    count_new = 0
    count_updated = 0

    for rec in records:
        pmid = rec.get("pmid")
        doi = rec.get("doi")

        # Try to find existing by PMID first, then DOI
        existing = None
        if pmid:
            result = await db.execute(
                select(Publication).where(
                    Publication.tenant_id == tenant_id,
                    Publication.user_id == user.id,
                    Publication.pmid == pmid,
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

        if existing:
            existing.pmid = pmid or existing.pmid
            existing.doi = doi or existing.doi
            existing.title = rec["title"] or existing.title
            existing.journal = rec.get("journal") or existing.journal
            existing.pub_year = rec.get("pub_year") or existing.pub_year
            existing.pub_date = rec.get("pub_date") or existing.pub_date
            existing.authors = rec.get("authors") or existing.authors
            # Upgrade source if previously ORCID-only
            if existing.source == "orcid":
                existing.source = "both"
            elif existing.source != "both":
                existing.source = "pubmed"
            count_updated += 1
        else:
            pub = Publication(
                tenant_id=tenant_id,
                user_id=user.id,
                pmid=pmid,
                doi=doi,
                title=rec["title"],
                journal=rec.get("journal") or "",
                pub_year=rec.get("pub_year"),
                pub_date=rec.get("pub_date"),
                authors=rec.get("authors") or "",
                source="pubmed",
                raw_data={},
            )
            db.add(pub)
            count_new += 1

    return {"new": count_new, "updated": count_updated, "status": "success"}
