"""Publication-level SDG helpers backed by the Aurora/OpenAlex pipeline."""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from streamlit_app.config import (
    ELSEVIER_INSTTOKEN,
    OPENALEX_USER_AGENT,
    SCOPUS_CONTENT_API_KEY,
    SERPAPI_API_KEY,
)

_ROOT = Path(__file__).resolve().parent.parent
_AURORA_DIR = Path(__file__).resolve().parent / "aurora_pipeline"
_CACHE_PATH = _ROOT / "data" / "aurora_sdg_cache.sqlite3"


class SDGServiceError(RuntimeError):
    """Raised when the SDG publication workflow cannot run."""


@dataclass(frozen=True)
class SDGFetchResult:
    rows: List[Dict[str, Any]]
    stats: Any
    from_date: str
    to_date: str
    work_types: Tuple[Optional[str], ...]


def _load_aurora_modules():
    """Import Aurora modules after pinning their SQLite cache to the main app data dir."""
    if not _AURORA_DIR.exists():
        raise SDGServiceError(f"Aurora folder not found: {_AURORA_DIR}")
    if str(_AURORA_DIR) not in sys.path:
        sys.path.insert(0, str(_AURORA_DIR))

    import cache_db  # type: ignore

    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if getattr(cache_db, "DB_PATH", None) != _CACHE_PATH:
        existing_conn = getattr(cache_db, "_CONN", None)
        if existing_conn is not None:
            try:
                existing_conn.close()
            except Exception:
                pass
        cache_db.DB_PATH = _CACHE_PATH
        cache_db._CONN = None

    import openalex_sdg  # type: ignore

    return openalex_sdg


def sdg_credentials_available() -> bool:
    return bool(SCOPUS_CONTENT_API_KEY and ELSEVIER_INSTTOKEN)


def year_key_to_date_range(year_key: str, today: Optional[date] = None) -> Tuple[str, str]:
    """Map SciVal year presets to explicit publication dates for OpenAlex/Scopus."""
    today = today or date.today()
    years_back = 5
    if str(year_key).startswith("3yrs"):
        years_back = 3
    elif str(year_key).startswith("10yrs"):
        years_back = 10
    start_year = max(1900, today.year - years_back + 1)
    return f"{start_year}-01-01", f"{today.year}-12-31"


def docs_key_to_openalex_work_types(docs_key: str) -> Tuple[Optional[str], ...]:
    """Translate dashboard document filters into Aurora/OpenAlex work types."""
    mapping: Dict[str, Tuple[Optional[str], ...]] = {
        "AllPublicationTypes": (None,),
        "ArticlesOnly": ("article",),
        "ArticlesReviews": ("article", "review"),
        "ArticlesReviewsConferencePapers": ("article", "review", "proceedings-article"),
        "ArticlesConferencePapers": ("article", "proceedings-article"),
        "BooksAndBookChapters": ("book", "book-chapter"),
    }
    return mapping.get(str(docs_key), (None,))


def dedupe_rows_by_work(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        key = str(row.get("openalex_id") or row.get("doi") or row.get("title") or "").strip().lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(row)
    return deduped


def rows_to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    preferred = [
        "openalex_id",
        "authors",
        "title",
        "publication_date",
        "doi",
        "type",
        "language",
        "is_oa",
        "oa_status",
        "citedby_count",
        "institutions",
        "institution_ids",
        "institution_countries",
        "abstract",
        "asjc_issn",
        "asjc_subject_codes",
        "asjc_subjects",
        "sdg_model",
        "sdg_formatted",
        "sdg_note",
        "data_source",
    ]
    extras = sorted({key for row in rows for key in row.keys()} - set(preferred))
    fieldnames = [key for key in preferred if any(key in row for row in rows)] + extras
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def fetch_author_sdg_publications(
    author_id: str,
    *,
    year_key: str,
    docs_key: str,
    model: str = "aurora-sdg-multi",
    limit_rows: Optional[int] = 50,
    progress_callback: Optional[Callable[[int, Optional[int], str], None]] = None,
) -> SDGFetchResult:
    """Fetch publications for one Scopus AU-ID and enrich them with SDG predictions."""
    if not author_id or not str(author_id).strip().isdigit():
        raise SDGServiceError("Select a numeric Scopus Author ID before fetching SDG publications.")
    if not sdg_credentials_available():
        raise SDGServiceError(
            "Scopus publication search requires an Elsevier API key and insttoken. "
            "Set SCOPUS_API_KEY (or an existing Elsevier/SciVal key) and ELSEVIER_INSTTOKEN."
        )

    openalex_sdg = _load_aurora_modules()
    from_date, to_date = year_key_to_date_range(year_key)
    work_types = docs_key_to_openalex_work_types(docs_key)
    all_rows: List[Dict[str, Any]] = []
    aggregate_stats = None

    for work_type in work_types:
        remaining = None if limit_rows is None else max(limit_rows - len(all_rows), 0)
        if remaining == 0:
            break
        rows, stats = openalex_sdg.fetch_author_publications_scopus_with_sdg(
            from_date,
            work_type,
            model,
            author_openalex_id="",
            author_raw_identifier=str(author_id).strip(),
            to_date=to_date,
            limit_rows=remaining,
            user_agent=OPENALEX_USER_AGENT,
            scopus_api_key=SCOPUS_CONTENT_API_KEY,
            scopus_insttoken=ELSEVIER_INSTTOKEN,
            enable_google_scholar=bool(SERPAPI_API_KEY),
            serpapi_api_key=SERPAPI_API_KEY or None,
            progress_callback=progress_callback,
        )
        if aggregate_stats is None:
            aggregate_stats = stats
        else:
            aggregate_stats.total_processed += getattr(stats, "total_processed", 0) or 0
            if aggregate_stats.total_expected is None or getattr(stats, "total_expected", None) is None:
                aggregate_stats.total_expected = None
            else:
                aggregate_stats.total_expected += stats.total_expected
            for attr in (
                "openalex_abstract_missing",
                "scopus_abstract_retrieved",
                "gs_abstract_retrieved",
                "total_abstracts_available",
                "cached_abstract_retrieved",
                "scopus_candidates_scanned",
                "scopus_skipped_no_doi",
                "scopus_skipped_duplicate_doi",
                "scopus_doi_not_in_openalex",
                "scopus_skipped_type_mismatch",
                "scopus_skipped_date_mismatch",
            ):
                setattr(
                    aggregate_stats,
                    attr,
                    (getattr(aggregate_stats, attr, 0) or 0) + (getattr(stats, attr, 0) or 0),
                )
        all_rows.extend(dict(row) for row in rows)

    return SDGFetchResult(
        rows=dedupe_rows_by_work(all_rows),
        stats=aggregate_stats,
        from_date=from_date,
        to_date=to_date,
        work_types=work_types,
    )
