"""Utility functions for fetching OpenAlex works and running Aurora SDG classification."""

from __future__ import annotations

# Use the OS trust store (e.g. Windows) so HTTPS works behind corporate roots / AV TLS
# inspection; default certifi/OpenSSL alone often fails with CERTIFICATE_VERIFY_FAILED.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote
import unicodedata
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import requests

try:
    from scholarly import ProxyGenerator, scholarly  # type: ignore
except Exception:  # pragma: no cover - optional dependency at runtime
    ProxyGenerator = None
    scholarly = None

from cache_db import (
    get_cached_sdg_result,
    get_cached_work,
    upsert_sdg_result,
    upsert_work,
)

# ------------------ CONFIG ------------------
BASE_WORKS = "https://api.openalex.org/works"
BASE_INSTITUTIONS = "https://api.openalex.org/institutions"
BASE_AUTHORS = "https://api.openalex.org/authors"
AURORA_BASE = "https://aurora-sdg.labs.vu.nl/classifier/classify"
ELSEVIER_ABSTRACT_BY_DOI = "https://api.elsevier.com/content/abstract/doi/{doi}"
ELSEVIER_AUTHOR_BY_ID = "https://api.elsevier.com/content/author/author_id/{author_id}"
ELSEVIER_SCOPUS_SEARCH = "https://api.elsevier.com/content/search/scopus"
SERPAPI_GS_API = "https://serpapi.com/search" # New constant for SerpApi Google Scholar API

# OpenAlex ``type`` values → Scopus search ``DOCTYPE`` codes (subset; unknown types omit the filter).
OPENALEX_TYPE_TO_SCOPUS_DOCTYPE: Dict[str, str] = {
    "article": "ar",
    "book": "bk",
    "book-chapter": "ch",
    "proceedings-article": "cp",
    "proceedings": "cp",
    "review": "re",
    "editorial": "ed",
    "letter": "le",
    "dataset": "dp",
    "dissertation": "dp",
    "report": "rp",
    "standard": "st",
    "other": "ar",
}

_SCOPUS_AUTHOR_ID_IN_URL = re.compile(r"(?:authorId|authorID)=(\d{9,12})\b", re.I)


PER_PAGE = 200  # OpenAlex max
DEFAULT_FROM_DATE = "2023-01-01"
DEFAULT_USER_AGENT = "OpenAlex+Aurora SDG fetcher (mailto:you@example.com)"

AURORA_MODELS = [
    ("aurora-sdg", "Aurora SDG mBERT (single-label, slower)"),
    ("aurora-sdg-multi", "Aurora SDG multi-label mBERT (fast)"),
    ("elsevier-sdg-multi", "Elsevier SDG multi-label mBERT (fast)"),
    ("osdg", "OSDG model (multi-label, 15 languages)"),
    ("skip", "Skip SDG classification (no Aurora API calls)"),
]

MIN_WORDS_BY_MODEL = {"osdg": 50}
HTML_TAG_RE = re.compile(r"<[^>]+>")
# --------------------------------------------

ProgressHook = Optional[Callable[[int, Optional[int], str], None]]


class FetchCancelled(Exception):
    """Raised when the fetch loop is cancelled by the user."""

    pass


@dataclass
class FetchStats:
    total_expected: Optional[int]
    total_processed: int
    openalex_abstract_missing: int
    scopus_abstract_retrieved: int
    gs_abstract_retrieved: int
    total_abstracts_available: int = 0  # New field
    # Scopus AU-ID → DOI → OpenAlex bridge (optional; default 0)
    scopus_skipped_no_doi: int = 0
    scopus_skipped_duplicate_doi: int = 0
    scopus_doi_not_in_openalex: int = 0
    scopus_skipped_type_mismatch: int = 0
    scopus_skipped_date_mismatch: int = 0


def too_short_for_model(model: str, text: str) -> bool:
    """Return True if the supplied text lacks the minimum word count for a model."""
    need = MIN_WORDS_BY_MODEL.get(model, 0)
    return need > 0 and len((text or "").split()) < need


def is_ror_url(value: str) -> bool:
    """Lightweight validation for ROR URLs (https://ror.org/XXXXXXXXX)."""
    return bool(re.match(r"^https?://ror\.org/[0-9a-z]{9}$", value.strip(), flags=re.I))

def is_openalex_institution_id(value: str) -> bool:
    """Return True if the value looks like an OpenAlex institution ID/URL."""
    return bool(
        re.match(r"^(https?://openalex\.org/)?I[A-Z0-9]+$", value.strip(), flags=re.I)
    )


def is_openalex_author_id(value: str) -> bool:
    """Return True if the value looks like an OpenAlex author ID/URL."""
    return bool(re.match(r"^(https?://openalex\.org/)?A[A-Z0-9]+$", value.strip(), flags=re.I))


_ORCID_RE = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])\b")


def extract_orcid(text: str) -> Optional[str]:
    """Pull a canonical ORCID (16 digits + check) from free text or URL."""
    if not text:
        return None
    match = _ORCID_RE.search(text.strip())
    if not match:
        return None
    return match.group(1).upper()


def normalize_openalex_author_token(value: str) -> str:
    """Return short OpenAlex author id token (A…) if present."""
    if not value:
        return ""
    tail = value.strip().split("/")[-1].strip()
    return tail if re.match(r"^A[A-Z0-9]+$", tail, flags=re.I) else ""


def looks_like_scopus_author_id(value: str) -> bool:
    """Heuristic: numeric Scopus author identifiers are typically 10–11 digits."""
    s = value.strip()
    return s.isdigit() and 9 <= len(s) <= 12


def parse_orcid_from_elsevier_author_xml(content: bytes) -> Optional[str]:
    """Return ORCID from Elsevier Author Retrieval API (XML) ``coredata``, if present."""
    if not content:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None

    def _local(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    if _local(root.tag).lower() == "service-error":
        return None
    st = (root.attrib.get("status") or "").lower()
    if st in {"invalid", "not_found"}:
        return None

    for el in root.iter():
        if _local(el.tag).lower() != "orcid":
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        norm = extract_orcid(text)
        if norm:
            return norm
    return None


def fetch_orcid_from_elsevier_author(
    author_id: str,
    api_key: str,
    insttoken: str,
    session: Optional[requests.Session] = None,
    timeout: float = 30,
) -> Optional[str]:
    """
    GET Elsevier Scopus Author Retrieval by author id; return ORCID when present.
    Same ``apiKey`` + ``insttoken`` as Elsevier Abstract Retrieval.
    """
    sid = author_id.strip()
    if not sid.isdigit() or not api_key or not (insttoken or "").strip():
        return None
    url = ELSEVIER_AUTHOR_BY_ID.format(author_id=sid)
    params = {
        "apiKey": api_key,
        "httpAccept": "text/xml",
        "insttoken": insttoken.strip(),
    }
    headers = {"Accept": "text/xml, application/xml;q=0.9,*/*;q=0.8"}
    requester = session or requests
    try:
        resp = requester.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            return None
        return parse_orcid_from_elsevier_author_xml(resp.content)
    except requests.RequestException:
        return None


def _openalex_resolve_by_orcid(
    sess: requests.Session,
    headers: Dict[str, str],
    orcid: str,
) -> Tuple[Optional[str], Optional[str], str]:
    """Resolve ORCID via OpenAlex Authors API. Returns (author_token, display_name, error_message)."""
    try:
        resp = sess.get(
            BASE_AUTHORS,
            params={"filter": f"orcid:{orcid}", "per-page": 1},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return None, None, f"No OpenAlex author matched ORCID {orcid}."
        rec = results[0]
        aid = normalize_openalex_author_token(rec.get("id") or "")
        if not aid:
            return None, None, "OpenAlex returned an author without an id."
        name = (rec.get("display_name") or "").strip() or None
        return aid, name, ""
    except requests.RequestException as exc:
        return None, None, f"Author lookup failed: {exc}"


def fetch_author_record(
    author_token: str,
    user_agent: str = DEFAULT_USER_AGENT,
    session: Optional[requests.Session] = None,
    timeout: float = 30,
) -> Optional[dict]:
    """GET a single OpenAlex author entity by short id (e.g. A5107910394)."""
    token = normalize_openalex_author_token(author_token)
    if not token:
        return None
    headers = {"User-Agent": user_agent}
    url = f"{BASE_AUTHORS}/{token}"
    requester = session or requests
    try:
        resp = requester.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except requests.RequestException:
        return None


def resolve_author_openalex_id(
    raw_input: str,
    user_agent: str = DEFAULT_USER_AGENT,
    session: Optional[requests.Session] = None,
    scopus_api_key: Optional[str] = None,
    scopus_insttoken: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str, Optional[str]]:
    """
    Map ORCID, OpenAlex author URL/id, or Scopus author id to an OpenAlex author id.

    **Numeric Scopus ID + Elsevier credentials** (``scopus_api_key`` / ``scopus_insttoken``):
    ``Scopus → Elsevier Author Retrieval (ORCID) → OpenAlex authors (filter=orcid) →``
    downstream Works use ``author.id:A…``. If Elsevier returns no ORCID, falls back to
    OpenAlex ``filter=scopus:…`` (same as the no-credentials path).

    **Numeric Scopus ID without Elsevier**: OpenAlex ``filter=scopus:…`` only (often empty).

    Returns ``(author_token, display_name, error_message, resolution_note_md)``.
    ``resolution_note_md`` is for UI captions; Markdown; ``None`` if not applicable.
    On success ``error_message`` is ``""``.
    """
    raw = (raw_input or "").strip()
    if not raw:
        return None, None, "Enter an ORCID, OpenAlex author URL, or Scopus author ID.", None

    sess = session or requests.Session()
    headers = {"User-Agent": user_agent}

    token = normalize_openalex_author_token(raw)
    if token:
        record = fetch_author_record(token, user_agent=user_agent, session=sess)
        if record:
            name = (record.get("display_name") or "").strip() or None
            return (
                token,
                name,
                "",
                f"Works load via OpenAlex Works API `filter=author.id:{token}`.",
            )
        return None, None, f"No OpenAlex author found for id {token}.", None

    orcid_direct = extract_orcid(raw)
    if orcid_direct:
        aid, name, err = _openalex_resolve_by_orcid(sess, headers, orcid_direct)
        if err:
            return None, None, err, None
        return (
            aid,
            name,
            "",
            f"ORCID `{orcid_direct}` → OpenAlex `{aid}`; works use "
            f"`filter=author.id:{aid}`.",
        )

    if looks_like_scopus_author_id(raw):
        sid = raw.strip()
        inst = (scopus_insttoken or "").strip()
        have_elsevier = bool(scopus_api_key and inst)

        if have_elsevier:
            orcid_sv = fetch_orcid_from_elsevier_author(
                sid, scopus_api_key, inst, session=sess, timeout=30
            )
            if orcid_sv:
                aid, name, err = _openalex_resolve_by_orcid(sess, headers, orcid_sv)
                if err:
                    return None, None, err, None
                if not aid:
                    return (
                        None,
                        None,
                        f"ORCID {orcid_sv} from Scopus {sid} is not mapped to an OpenAlex author.",
                        None,
                    )
                note = (
                    f"1. Scopus ID `{sid}` → **Elsevier** Author API → ORCID `{orcid_sv}`  \n"
                    f"2. ORCID → **OpenAlex** author `{aid}` (`filter=orcid`)  \n"
                    f"3. Publication fetch → Works API `filter=author.id:{aid}`"
                )
                return aid, name, "", note

        try:
            resp = sess.get(
                BASE_AUTHORS,
                params={"filter": f"scopus:{sid}", "per-page": 5},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if not results:
                if have_elsevier:
                    return (
                        None,
                        None,
                        "Elsevier Author API returned no ORCID for this Scopus author profile, "
                        "and OpenAlex has no author indexed with `filter=scopus:"
                        f"{sid}`. Check api key / insttoken and HTTPS access; add ORCID to the "
                        "Scopus profile if missing; or paste an OpenAlex author URL / ORCID.",
                        None,
                    )
                return (
                    None,
                    None,
                    "OpenAlex has no author indexed with this Scopus ID, and Elsevier "
                    "credentials are not set—so ORCID cannot be read from Scopus. "
                    "Add **scopus_api_key** and **scopus_insttoken** to "
                    "`.streamlit/secrets.toml` or `.env` (`SCOPUS_API_KEY` / "
                    "`SCOPUS_INSTTOKEN`), install `python-dotenv`, then restart the app. "
                    "Or paste ORCID / `https://openalex.org/A…` instead.",
                    None,
                )
            if len(results) > 1:
                names = ", ".join(
                    (r.get("display_name") or r.get("id") or "?") for r in results[:5]
                )
                return (
                    None,
                    None,
                    f"Multiple OpenAlex authors matched Scopus ID {sid}: {names}. "
                    "Paste the OpenAlex author URL for the correct person.",
                    None,
                )
            rec = results[0]
            aid = normalize_openalex_author_token(rec.get("id") or "")
            if not aid:
                return None, None, "OpenAlex returned an author without an id.", None
            name = (rec.get("display_name") or "").strip() or None
            if have_elsevier:
                note = (
                    f"Elsevier had no ORCID for Scopus `{sid}`; matched via OpenAlex "
                    f"`filter=scopus:{sid}`. Works use `filter=author.id:{aid}`."
                )
            else:
                note = (
                    f"Matched via OpenAlex `filter=scopus:{sid}` (Elsevier/ORCID step skipped—no credentials). "
                    f"Works use `filter=author.id:{aid}`."
                )
            return aid, name, "", note
        except requests.RequestException as exc:
            return None, None, f"Scopus author lookup failed: {exc}", None

    return (
        None,
        None,
        "Unrecognized input. Paste an ORCID (URL or 0000-0001-2345-6789), "
        "https://openalex.org/A…, or a numeric Scopus author ID.",
        None,
    )


def _normalize_institution_id(value: str) -> str:
    """Return the short OpenAlex institution ID token if present."""
    if is_openalex_institution_id(value):
        return value.strip().split("/")[-1]
    return value.strip()

def search_institutions_by_name(
    name: str, user_agent: str = DEFAULT_USER_AGENT, limit: int = 10
) -> List[dict]:
    """Query the OpenAlex institutions endpoint using the user's keyword."""
    params = {"search": name, "per-page": limit}
    headers = {"User-Agent": user_agent}
    response = requests.get(BASE_INSTITUTIONS, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json().get("results", [])

def fetch_institution_lineage(
    institution_id: str,
    user_agent: str = DEFAULT_USER_AGENT,
    retries: int = 2,
    pause: float = 0.4,
) -> List[str]:
    """Fetch the institution record to read its lineage IDs."""
    inst_token = _normalize_institution_id(institution_id)
    url = f"{BASE_INSTITUTIONS}/{inst_token}"
    headers = {"User-Agent": user_agent}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 429:
                time.sleep(pause * attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            lineage = data.get("lineage") or []
            if isinstance(lineage, list):
                return [str(_normalize_institution_id(item)) for item in lineage if item]
            return []
        except requests.RequestException:
            if attempt == retries:
                return []
            time.sleep(pause * attempt)
    return []

def reconstruct_abstract(inv: Optional[dict]) -> str:
    """Rebuild abstract text from OpenAlex 'abstract_inverted_index' or '_v3'."""
    if not inv or not isinstance(inv, dict):
        return ""
    max_pos = -1
    for positions in inv.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    if max_pos < 0:
        return ""
    tokens_by_pos = [""] * (max_pos + 1)
    for token, positions in inv.items():
        for p in positions:
            if p < 0:
                continue
            if p >= len(tokens_by_pos):
                tokens_by_pos.extend([""] * (p - len(tokens_by_pos) + 1))
            tokens_by_pos[p] = (
                (tokens_by_pos[p] + " " + token).strip() if tokens_by_pos[p] else token
            )
    return " ".join(tokens_by_pos).strip()

def flatten_authors_and_institutions(authorships: Sequence[dict]) -> Tuple[str, str, List[dict]]:
    """
    Convert OpenAlex authorship structures into 'A; B' strings and collect structured affiliations.
    Each affiliation is a dict with id, name, and country.
    """
    if not authorships:
        return "", "", []
    author_names: List[str] = []
    all_insts: List[str] = []
    affiliations: List[dict] = []
    for author_entry in authorships:
        author = (author_entry.get("author") or {}).get("display_name") or ""
        if author:
            author_names.append(author)
        for inst in author_entry.get("institutions") or []:
            name = inst.get("display_name") or ""
            if name:
                all_insts.append(name)
            affiliations.append(
                {
                    "id": inst.get("id") or "",
                    "name": name,
                    "country": (inst.get("country_code") or "").upper(),
                }
            )
    seen = set()
    inst_names: List[str] = []
    for name in all_insts:
        if name not in seen:
            seen.add(name)
            inst_names.append(name)
    return "; ".join(author_names), "; ".join(inst_names), affiliations

def clean_html_fragment(text: str) -> str:
    """Strip HTML tags/entities and normalize whitespace."""
    if not text:
        return ""
    decoded = unescape(text)
    without_tags = HTML_TAG_RE.sub(" ", decoded)
    normalized = re.sub(r"\s+", " ", without_tags)
    return normalized.strip()

def _normalize_text_for_match(text: str) -> str:
    """Normalize and lowercase text for equality checks ignoring punctuation."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text).lower()
    return re.sub(r"\s+", "", text).strip()

def _normalize_author_token(name: str) -> str:
    """Produce a stable author token (surname or first token if comma style)."""
    if not name:
        return ""
    clean = unicodedata.normalize("NFKD", name)
    clean = "".join(ch for ch in clean if not unicodedata.combining(ch))
    has_comma = "," in clean
    clean = re.sub(r"[^\w\s]", " ", clean).lower()
    parts = clean.split()
    if not parts:
        return ""
    return parts[0] if has_comma else parts[-1]

def get_abstract_from_serpapi_google_scholar(
    title: str,
    authors: str,
    api_key: Optional[str],
    session: requests.Session,
    retries: int = 3,
    pause: float = 0.5,
) -> Optional[str]:
    """Fetches abstract from Google Scholar via SerpApi."""
    if not api_key or not title:
        return None

    query = f"{title} {authors}" if authors else title
    if not query:
        return None # Should not happen if title is present but just in case

    params = {
        "engine": "google_scholar",
        "q": query,
        "api_key": api_key,
        "hl": "en", # Host language for results
        "num": 5, # Number of results, usually enough to find the paper
    }

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(SERPAPI_GS_API, params=params, timeout=20)
            if resp.status_code == 429: # Rate limit
                time.sleep(pause * attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            norm_title = _normalize_text_for_match(title)

            for result in data.get("organic_results", []):
                result_title = result.get("title")
                # Basic title match to ensure we're looking at the right paper
                if not result_title:
                    continue
                norm_result_title = _normalize_text_for_match(result_title)
                # Relaxed matching: check if one is a prefix of the other.
                if norm_result_title.startswith(norm_title) or norm_title.startswith(norm_result_title):
                    abstract = result.get("snippet") # SerpApi often provides abstract in 'snippet'
                    if abstract:
                        logging.info("SerpApi Google Scholar abstract retrieved for '%s'", title)
                        return clean_html_fragment(abstract)

            logging.info("Serpapi Google Scholar abstract not found for '%s' (no matching results with snippets)", title)
            return None

        except requests.RequestException as exc:
            logging.warning(f"Serpapi call failed for '{title}' (attempt {attempt}): {exc}")
            if attempt == retries:
                return None
            time.sleep(pause * attempt)
    return None

def get_abstract_from_scholarly(
    title: str,
    authors: str,
    retries: int = 2,
    pause: float = 1.0,
) -> Optional[str]:
    """Fetch an abstract via scholarly using FreeProxies when SerpApi is unavailable."""
    if not title or scholarly is None or ProxyGenerator is None:
        return None

    query = f"{title} {authors}" if authors else title
    if not query:
        return None

    try:
        pg = ProxyGenerator()
        proxy_ok = pg.FreeProxies()
        if proxy_ok:
            scholarly.use_proxy(pg)
    except Exception as exc:  # pragma: no cover - network/proxy dependent
        logging.warning("scholarly FreeProxies setup failed: %s", exc)

    target_title = _normalize_text_for_match(title)
    for attempt in range(1, retries + 1):
        try:
            results = scholarly.search_pubs(query)  # type: ignore[arg-type]
            for _ in range(5):  # look at a few candidates
                try:
                    candidate = next(results)
                except StopIteration:
                    break
                cand_title = candidate.get("bib", {}).get("title") or candidate.get("name")
                if not cand_title:
                    continue
                norm_candidate = _normalize_text_for_match(cand_title)
                if not (norm_candidate.startswith(target_title) or target_title.startswith(norm_candidate)):
                    continue
                try:
                    filled = scholarly.fill(candidate)  # type: ignore[arg-type]
                except Exception as fill_exc:  # pragma: no cover - external call
                    logging.debug("scholarly.fill failed: %s", fill_exc)
                    continue
                abstract = (
                    filled.get("abstract")
                    or (filled.get("bib") or {}).get("abstract")
                )
                if abstract:
                    logging.info("scholarly abstract retrieved for '%s'", title)
                    return clean_html_fragment(abstract)
            return None
        except Exception as exc:  # pragma: no cover - external call
            logging.warning("scholarly search failed (attempt %s): %s", attempt, exc)
            if attempt == retries:
                return None
            time.sleep(pause * attempt)
    return None

def abbreviate_authors(value: str) -> str:
    """Return compact 'First Author et al.' preview for UI progress messages."""
    if not value:
        return ""
    authors = [part.strip() for part in value.split(";") if part.strip()]
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    return f"{authors[0]} et al."

def make_filter(
    institution_id: str,
    from_date: Optional[str],
    work_type: Optional[str],
    to_date: Optional[str] = None,
    extra_institution_ids: Optional[Sequence[str]] = None,
) -> str:
    inst_ids = [_normalize_institution_id(institution_id)]
    for item in extra_institution_ids or []:
        norm = _normalize_institution_id(str(item))
        if norm and norm not in inst_ids:
            inst_ids.append(norm)
    ids: List[str] = []
    rors: List[str] = []
    for inst in inst_ids:
        if is_openalex_institution_id(inst):
            ids.append(inst.split("/")[-1])
        else:
            rors.append(inst)
    if ids:
        inst_filter = f"institutions.id:{'|'.join(ids)}"
    elif rors:
        inst_filter = f"institutions.ror:{'|'.join(rors)}"
    else:
        inst_filter = ""
    parts = [
        inst_filter,
        "is_paratext:false",
    ]
    if from_date:
        parts.append(f"from_publication_date:{from_date}")
    if to_date:
        parts.append(f"to_publication_date:{to_date}")
    if work_type:
        parts.append(f"type:{work_type}")
    return ",".join(parts)


def make_author_filter(
    author_openalex_id: str,
    from_date: Optional[str],
    work_type: Optional[str],
    to_date: Optional[str] = None,
) -> str:
    """Build OpenAlex Works API filter string for a single author."""
    token = normalize_openalex_author_token(author_openalex_id)
    if not token:
        raise ValueError("Invalid OpenAlex author id")
    parts = [
        f"author.id:{token}",
        "is_paratext:false",
    ]
    if from_date:
        parts.append(f"from_publication_date:{from_date}")
    if to_date:
        parts.append(f"to_publication_date:{to_date}")
    if work_type:
        parts.append(f"type:{work_type}")
    return ",".join(parts)


def classify_text_aurora(
    model: str,
    text: str,
    session: requests.Session,
    user_agent: str = DEFAULT_USER_AGENT,
    retries: int = 3,
    pause: float = 0.4,
) -> Tuple[Optional[dict], str]:
    """
    Calls Aurora SDG classifier via POST, returns (json or None, note string).
    note is "" on success, or an explanation like "http_error:429" / "empty json".
    """
    if not text:
        return None, "no text"
    url = f"{AURORA_BASE}/{model}"
    headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"text": text}
    for attempt in range(1, retries + 1):
        try:
            resp = session.post(
                url, headers=headers, data=json.dumps(payload), timeout=60
            )
            if resp.status_code == 429:
                time.sleep(pause * attempt + 0.5)
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None, "empty json"
            return data, ""
        except requests.RequestException as exc:
            if attempt == retries:
                code = getattr(getattr(exc, "response", None), "status_code", None)
                return None, f"http_error:{code}"
            time.sleep(pause * attempt)
    return None, "unknown"

def _els_tag_local(tag: str) -> str:
    if not tag:
        return ""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_abstract_from_elsevier_xml(content: bytes) -> Optional[str]:
    """Extract plain text from Elsevier Abstract Retrieval API (XML) response."""
    if not content:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    if _els_tag_local(root.tag).lower() == "service-error":
        return None
    blocks: List[str] = []
    for el in root.iter():
        if _els_tag_local(el.tag).lower() != "abstract":
            continue
        parts: List[str] = []
        for sub in el.iter():
            if _els_tag_local(sub.tag).lower() == "para":
                t = "".join(sub.itertext()).strip()
                if t:
                    parts.append(t)
        if parts:
            blocks.append(" ".join(parts))
    if not blocks:
        return None
    return max(blocks, key=len).strip() or None


def get_abstract_from_scopus(
    doi: str,
    session: Optional[requests.Session] = None,
    api_key: Optional[str] = None,
    insttoken: Optional[str] = None,
    retries: int = 3,
    pause: float = 0.5,
) -> Optional[str]:
    """
    Fetch abstract via Elsevier Scopus / Abstract Retrieval API (by DOI).
    Requires both apiKey and insttoken (query params).
    """
    if not doi or not api_key or not (insttoken or "").strip():
        return None
    cleaned = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
    if not cleaned:
        return None
    path_doi = quote(cleaned, safe="")
    url = ELSEVIER_ABSTRACT_BY_DOI.format(doi=path_doi)
    params = {
        "apiKey": api_key,
        "httpAccept": "text/xml",
        "insttoken": insttoken.strip(),
    }
    headers = {"Accept": "text/xml, application/xml;q=0.9,*/*;q=0.8"}
    requester = session or requests
    for attempt in range(1, retries + 1):
        try:
            resp = requester.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                time.sleep(pause * attempt)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code >= 400:
                return None
            abstract = parse_abstract_from_elsevier_xml(resp.content)
            if abstract:
                return abstract
            return None
        except requests.RequestException:
            if attempt == retries:
                return None
            time.sleep(pause * attempt)
    return None


def extract_scopus_author_id_from_raw(raw: str) -> Optional[str]:
    """Return numeric Scopus Author ID from plain digits or a Scopus author URL."""
    s = (raw or "").strip()
    if not s:
        return None
    if looks_like_scopus_author_id(s):
        return s
    m = _SCOPUS_AUTHOR_ID_IN_URL.search(s)
    if m:
        return m.group(1)
    return None


def extract_scopus_author_id_from_openalex_author(author_record: Optional[dict]) -> Optional[str]:
    """Read Scopus author id from an OpenAlex author ``ids`` block when Elsevier links it."""
    if not author_record or not isinstance(author_record, dict):
        return None
    ids = author_record.get("ids") or {}
    if not isinstance(ids, dict):
        return None
    sc = ids.get("scopus")
    if isinstance(sc, int):
        s = str(sc).strip()
        return s if looks_like_scopus_author_id(s) else None
    if isinstance(sc, str):
        s = sc.strip()
        if looks_like_scopus_author_id(s):
            return s
        m = _SCOPUS_AUTHOR_ID_IN_URL.search(s)
        if m:
            return m.group(1)
    return None


def resolve_scopus_au_id_for_search(
    author_raw_identifier: str,
    author_openalex_id: str,
    session: requests.Session,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[str]:
    """
    Scopus Search uses ``AU-ID(…)``. Prefer digits / URL from the user paste; otherwise
    the Scopus id linked on the resolved OpenAlex author record.
    """
    sid = extract_scopus_author_id_from_raw(author_raw_identifier)
    if sid:
        return sid
    rec = fetch_author_record(author_openalex_id, user_agent=user_agent, session=session)
    return extract_scopus_author_id_from_openalex_author(rec)


def build_scopus_author_publications_query(
    au_id: str,
    from_date: Optional[str],
    to_date: Optional[str],
    work_type: Optional[str],
) -> str:
    """Build Elsevier Scopus search query string (``AU-ID`` + optional PUBYEAR / DOCTYPE)."""
    parts = [f"AU-ID({au_id.strip()})"]
    y_from: Optional[int] = None
    y_to: Optional[int] = None
    if from_date and len(from_date) >= 4 and from_date[:4].isdigit():
        y_from = int(from_date[:4])
    if to_date and len(to_date) >= 4 and to_date[:4].isdigit():
        y_to = int(to_date[:4])
    if y_from is not None and y_to is not None:
        if y_from == y_to:
            parts.append(f"PUBYEAR IS {y_from}")
        else:
            parts.append(f"PUBYEAR AFT {y_from - 1}")
            parts.append(f"PUBYEAR BEF {y_to + 1}")
    elif y_from is not None:
        parts.append(f"PUBYEAR AFT {y_from - 1}")
    elif y_to is not None:
        parts.append(f"PUBYEAR BEF {y_to + 1}")
    if work_type:
        code = OPENALEX_TYPE_TO_SCOPUS_DOCTYPE.get(work_type.strip().lower())
        if code:
            parts.append(f"DOCTYPE({code})")
    return " AND ".join(parts)


def _scopus_entry_child_texts(parent: ET.Element, local_name: str) -> List[str]:
    out: List[str] = []
    want = local_name.lower()
    for ch in list(parent):
        if _els_tag_local(ch.tag).lower() == want and (ch.text or "").strip():
            out.append(ch.text.strip())
    return out


def _scopus_entry_first_text(parent: ET.Element, local_name: str) -> str:
    vals = _scopus_entry_child_texts(parent, local_name)
    return vals[0] if vals else ""


def _scopus_entry_citedby_count(entry_el: ET.Element) -> Optional[int]:
    """Parse ``<citedby-count>`` from a Scopus search ``entry`` (non-negative integer)."""
    raw = _scopus_entry_first_text(entry_el, "citedby-count")
    if not raw or not raw.strip().isdigit():
        return None
    n = int(raw.strip())
    return n if n >= 0 else None


def _scopus_entry_affiliations_json(entry_el: ET.Element) -> Tuple[str, List[dict]]:
    """
    Affiliations from Scopus search ``entry`` XML (often a subset of all co-authors).

    Each affiliation gets a stable synthetic ``id`` so downstream tools (e.g. co-affiliation graphs)
    can link institutions; Scopus search does not supply ROR/OpenAlex institution ids here.
    """
    names: List[str] = []
    affs: List[dict] = []
    for ch in list(entry_el):
        if _els_tag_local(ch.tag).lower() != "affiliation":
            continue
        nm = ""
        country = ""
        city = ""
        for sub in list(ch):
            ln = _els_tag_local(sub.tag).lower()
            if ln == "affilname" and sub.text:
                nm = sub.text.strip()
            elif ln == "affiliation-country" and sub.text:
                country = sub.text.strip()
            elif ln == "affiliation-city" and sub.text:
                city = sub.text.strip()
        if nm:
            names.append(nm)
            key = f"{nm}|{country}|{city}".lower().encode("utf-8", errors="ignore")
            aff_id = "scopus:" + hashlib.sha256(key).hexdigest()[:22]
            affs.append({"id": aff_id, "name": nm, "country": country, "city": city})
    return "; ".join(names), affs


def _scopus_entry_link_href(entry_el: ET.Element, ref: str) -> str:
    want = ref.lower()
    for ch in list(entry_el):
        if _els_tag_local(ch.tag).lower() != "link":
            continue
        if (ch.get("ref") or "").lower() == want:
            href = (ch.get("href") or "").strip()
            if href:
                return href
    return ""


def _scopus_collect_nested_values(entry_el: ET.Element, parent_tag_local: str) -> List[str]:
    """Collect text of each ``<value>`` child under ``<freetoreadLabel>``-style parents (local tag match)."""
    want = parent_tag_local.lower()
    out: List[str] = []
    for ch in list(entry_el):
        if _els_tag_local(ch.tag).lower() != want:
            continue
        for sub in list(ch):
            if _els_tag_local(sub.tag).lower() == "value" and (sub.text or "").strip():
                out.append(sub.text.strip())
    return out


def _scopus_entry_open_access(entry_el: ET.Element) -> Tuple[Optional[bool], str]:
    """
    Map Scopus search open-access fields to ``is_oa`` and ``oa_status``.

    ``oa_status`` follows the Scopus **freetoreadLabel** block: human-readable ``<value>`` strings
    joined with `` | `` (e.g. ``All Open Access | Hybrid Gold``). If labels are absent, machine
    ``freetoread`` values are used; only then do we fall back to ``openaccess`` / ``openaccessFlag``.
    """
    flag_txt = _scopus_entry_first_text(entry_el, "openaccessFlag").lower()
    oa_code = _scopus_entry_first_text(entry_el, "openaccess")
    freetoread_label_vals = _scopus_collect_nested_values(entry_el, "freetoreadlabel")
    freetoread_code_vals = _scopus_collect_nested_values(entry_el, "freetoread")

    is_oa: Optional[bool] = None
    if flag_txt == "true":
        is_oa = True
    elif flag_txt == "false":
        is_oa = False
    if is_oa is None and oa_code in {"1", "2"}:
        is_oa = True
    if is_oa is None and oa_code == "0":
        is_oa = False
    if is_oa is None and (freetoread_label_vals or freetoread_code_vals):
        is_oa = True

    if freetoread_label_vals:
        oa_status = " | ".join(freetoread_label_vals)
    elif freetoread_code_vals:
        oa_status = " | ".join(freetoread_code_vals)
    else:
        parts: List[str] = []
        if oa_code:
            parts.append(f"openaccess={oa_code}")
        if flag_txt:
            parts.append(f"openaccessFlag={flag_txt}")
        oa_status = " · ".join(parts) if parts else ""

    return is_oa, oa_status


def parse_scopus_search_xml_page(content: bytes) -> Tuple[Optional[int], List[ET.Element]]:
    """
    Parse one Scopus Search API (Atom) XML page. Returns ``(total_results, entry_elements)``.
    ``total_results`` is ``None`` if the feed does not report it.
    """
    if not content:
        return None, []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None, []
    if _els_tag_local(root.tag).lower() == "service-error":
        return None, []
    total: Optional[int] = None
    for ch in root.iter():
        ln = _els_tag_local(ch.tag).lower()
        if ln == "totalresults" and (ch.text or "").strip().isdigit():
            total = int(ch.text.strip())
            break
    entries: List[ET.Element] = []
    for ch in list(root):
        if _els_tag_local(ch.tag).lower() == "entry":
            entries.append(ch)
    return total, entries


def normalize_doi_for_openalex(doi: str) -> str:
    """Return bare DOI ``10…/…`` for building an OpenAlex work URL ``https://doi.org/…``."""
    if not doi:
        return ""
    cleaned = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned.strip()


def fetch_openalex_work_by_doi(
    doi: str,
    session: requests.Session,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 35,
) -> Optional[dict]:
    """GET a single OpenAlex work entity using its DOI (returns ``None`` if not found)."""
    cleaned = normalize_doi_for_openalex(doi)
    if not cleaned or "/" not in cleaned:
        return None
    work_url = "https://doi.org/" + cleaned
    url = f"{BASE_WORKS}/{quote(work_url, safe='')}"
    headers = {"User-Agent": user_agent}
    try:
        resp = session.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("id"):
            return data
        return None
    except requests.RequestException:
        return None


def _openalex_work_in_publication_date_range(
    work: dict, from_date: Optional[str], to_date: Optional[str]
) -> bool:
    """``True`` if ``publication_date`` is within ``[from_date, to_date]`` (YYYY-MM-DD strings)."""
    pub = (work.get("publication_date") or "").strip()[:10]
    if not pub:
        return True
    if from_date and pub and pub < (from_date or "")[:10]:
        return False
    if to_date and pub and pub > (to_date or "")[:10]:
        return False
    return True


def _openalex_work_matches_type(work: dict, work_type: Optional[str]) -> bool:
    if not work_type:
        return True
    return (work.get("type") or "").strip().lower() == work_type.strip().lower()


def enrich_append_openalex_work(
    work: dict,
    *,
    session: requests.Session,
    stats: FetchStats,
    rows: List[Dict[str, Any]],
    model: str,
    user_agent: str,
    scopus_api_key: Optional[str],
    scopus_insttoken: Optional[str],
    enable_google_scholar: bool,
    serpapi_api_key: Optional[str],
    progress_callback: ProgressHook,
    cancel_check: Optional[Callable[[], bool]],
    citedby_count: Any = "",
    raw_record_overlay: Optional[Dict[str, Any]] = None,
    row_overlay: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Turn one OpenAlex ``work`` JSON object into a result row (abstract, SDG, cache) and append to ``rows``.

    Shared by the OpenAlex Works cursor pipeline and the Scopus AU-ID → DOI → OpenAlex bridge.
    """
    if cancel_check and cancel_check():
        raise FetchCancelled()

    def emit_progress(message: str = "") -> None:
        if cancel_check and cancel_check():
            raise FetchCancelled()
        if progress_callback:
            progress_callback(stats.total_processed, stats.total_expected, message)

    openalex_id = work.get("id", "")
    title = work.get("display_name") or work.get("title") or ""
    publication_date = work.get("publication_date") or ""
    doi = work.get("doi") or ""
    work_type_val = work.get("type") or ""
    language = work.get("language") or ""
    open_access = work.get("open_access") or {}
    is_oa = open_access.get("is_oa")
    oa_status = open_access.get("oa_status") or ""
    authorships = work.get("authorships") or []
    authors_str, insts_str, inst_affiliations = flatten_authors_and_institutions(authorships)

    cached_work = get_cached_work(openalex_id) if openalex_id else None
    cached_abstract = (cached_work or {}).get("abstract") or ""

    abstract_text = reconstruct_abstract(work.get("abstract_inverted_index"))
    authors_preview = abbreviate_authors(authors_str)
    title_display = title if len(title) <= 120 else f"{title[:117]}..."
    detail_label = title_display or openalex_id or "Untitled work"
    if authors_preview:
        detail_label = f"{authors_preview}, {detail_label}"
    emit_progress(detail_label)

    if not abstract_text:
        stats.openalex_abstract_missing += 1
        if cached_abstract:
            abstract_text = cached_abstract
        elif doi:
            sc_abs = get_abstract_from_scopus(
                doi,
                session=session,
                api_key=scopus_api_key,
                insttoken=scopus_insttoken,
            )
            if sc_abs:
                abstract_text = sc_abs
                stats.scopus_abstract_retrieved += 1
    if enable_google_scholar and not abstract_text:
        if serpapi_api_key:
            serpapi_abstract = get_abstract_from_serpapi_google_scholar(
                title, authors_str, api_key=serpapi_api_key, session=session
            )
            if serpapi_abstract:
                abstract_text = serpapi_abstract
                stats.gs_abstract_retrieved += 1
        else:
            scholarly_abs = get_abstract_from_scholarly(title, authors_str)
            if scholarly_abs:
                abstract_text = scholarly_abs
                stats.gs_abstract_retrieved += 1
    clean_cached_abs = clean_html_fragment(cached_abstract)
    abstract_text = clean_html_fragment(abstract_text)
    abstract_updated = bool(abstract_text and abstract_text != clean_cached_abs)

    if abstract_text:
        stats.total_abstracts_available += 1

    text_for_sdg = abstract_text if abstract_text else title
    sdg_json: Optional[dict] = None
    sdg_note = ""
    sdg_formatted = ""
    cached_sdg_entry: Optional[Dict[str, Any]] = None
    reused_sdg = False

    if model == "skip":
        sdg_note = "skipped: user selected 'skip'"
    else:
        if model == "osdg" and too_short_for_model(model, text_for_sdg):
            sdg_note = "skipped: osdg requires >=50 words"
        else:
            cached_sdg_entry = (
                get_cached_sdg_result(openalex_id, model) if openalex_id else None
            )
            should_reuse_sdg = bool(cached_sdg_entry) and not abstract_updated
            if should_reuse_sdg:
                reused_sdg = True
                raw_json = cached_sdg_entry.get("sdg_response") or ""
                if raw_json:
                    try:
                        sdg_json = json.loads(raw_json)
                    except json.JSONDecodeError:
                        sdg_json = None
                sdg_formatted = cached_sdg_entry.get("sdg_formatted") or ""
                sdg_note = cached_sdg_entry.get("sdg_note") or ""
                if not sdg_formatted and sdg_json:
                    sdg_formatted = format_sdg_predictions(sdg_json)
            else:
                sdg_json, sdg_note = classify_text_aurora(
                    model, text_for_sdg, session=session, user_agent=user_agent
                )
                sdg_formatted = (
                    format_sdg_predictions(sdg_json) if sdg_json is not None else ""
                )
                upsert_sdg_result(
                    openalex_id=openalex_id,
                    model=model,
                    sdg_response=sdg_json,
                    sdg_formatted=sdg_formatted,
                    sdg_note=sdg_note,
                )
                time.sleep(0.12)

    sdg_raw_str = json.dumps(sdg_json, ensure_ascii=False) if sdg_json is not None else ""
    if reused_sdg and not sdg_raw_str and cached_sdg_entry:
        sdg_raw_str = cached_sdg_entry.get("sdg_response") or ""

    row_data: Dict[str, Any] = {
        "openalex_id": openalex_id,
        "title": title,
        "publication_date": publication_date,
        "doi": doi,
        "type": work_type_val,
        "language": language,
        "is_oa": is_oa,
        "oa_status": oa_status,
        "citedby_count": citedby_count if citedby_count is not None and citedby_count != "" else "",
        "authors": authors_str,
        "institutions": insts_str,
        "institution_ids": "; ".join([aff.get("id", "") for aff in inst_affiliations if aff.get("id")]),
        "institution_countries": "; ".join([aff.get("country", "") for aff in inst_affiliations]),
        "institution_names_raw": "; ".join([aff.get("name", "") for aff in inst_affiliations]),
        "institution_affiliations_json": json.dumps(inst_affiliations, ensure_ascii=False),
        "abstract": abstract_text,
        "sdg_model": model,
        "sdg_response": sdg_raw_str,
        "sdg_formatted": sdg_formatted,
        "sdg_note": sdg_note,
    }
    if row_overlay:
        row_data.update(row_overlay)

    rows.append(row_data)
    stats.total_processed += 1
    raw_out: Dict[str, Any] = dict(work)
    if raw_record_overlay:
        raw_out.update(raw_record_overlay)
    upsert_work(row_data, raw_record=raw_out)
    emit_progress("")


def fetch_author_publications_scopus_with_sdg(
    from_date: str,
    work_type: Optional[str],
    model: str,
    author_openalex_id: str,
    author_raw_identifier: str,
    to_date: Optional[str] = None,
    limit_rows: Optional[int] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    scopus_api_key: Optional[str] = None,
    scopus_insttoken: Optional[str] = None,
    enable_google_scholar: bool = True,
    serpapi_api_key: Optional[str] = None,
    progress_callback: ProgressHook = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[List[Dict[str, object]], FetchStats]:
    """
    Discover DOIs via Elsevier Scopus Search (``AU-ID``), then load each work from **OpenAlex by DOI**.

    Rows match a normal OpenAlex fetch (authors, ``oa_status``, ``type``, authorship affiliations for
    charts and the co-affiliation network). ``citedby_count`` is taken from Scopus ``<citedby-count>``
    when present. Entries with no DOI, duplicate DOIs, no OpenAlex match, or type/date outside your
    filters increment counters on ``FetchStats``.
    """
    if not scopus_api_key or not (scopus_insttoken or "").strip():
        raise ValueError(
            "Scopus publication source requires non-empty scopus_api_key and scopus_insttoken "
            "(secrets.toml or SCOPUS_API_KEY / SCOPUS_INSTTOKEN)."
        )

    stats = FetchStats(
        total_expected=None,
        total_processed=0,
        openalex_abstract_missing=0,
        scopus_abstract_retrieved=0,
        gs_abstract_retrieved=0,
    )
    rows: List[Dict[str, Any]] = []

    def _ensure_not_cancelled() -> None:
        if cancel_check and cancel_check():
            raise FetchCancelled()

    def emit_progress(message: str = "") -> None:
        _ensure_not_cancelled()
        if progress_callback:
            progress_callback(stats.total_processed, stats.total_expected, message)

    emit_progress("Resolving Scopus Author ID (AU-ID)")

    with requests.Session() as session:
        session.headers["User-Agent"] = user_agent
        au_id = resolve_scopus_au_id_for_search(
            author_raw_identifier,
            author_openalex_id,
            session,
            user_agent=user_agent,
        )
        if not au_id:
            raise ValueError(
                "Could not determine a Scopus Author ID for this profile. Paste a **numeric Scopus "
                "author ID** (or a Scopus author URL containing authorId=…), or resolve an OpenAlex "
                "author that has a **Scopus** id in its OpenAlex record."
            )

        query_str = build_scopus_author_publications_query(au_id, from_date, to_date, work_type)
        headers = {"Accept": "text/xml, application/xml;q=0.9,*/*;q=0.8"}
        base_params = {
            "apiKey": scopus_api_key,
            "insttoken": (scopus_insttoken or "").strip(),
            "query": query_str,
            "httpAccept": "text/xml",
        }

        start = 0
        page_size = 200
        total_reported: Optional[int] = None
        seen_dois: Set[str] = set()

        while True:
            _ensure_not_cancelled()
            if limit_rows is not None and stats.total_processed >= limit_rows:
                break
            params = dict(base_params)
            params["start"] = start
            params["count"] = page_size
            resp = session.get(ELSEVIER_SCOPUS_SEARCH, params=params, headers=headers, timeout=90)
            if resp.status_code == 400 and page_size > 25:
                page_size = 25
                params["count"] = page_size
                resp = session.get(ELSEVIER_SCOPUS_SEARCH, params=params, headers=headers, timeout=90)
            resp.raise_for_status()
            total_page, entry_els = parse_scopus_search_xml_page(resp.content)
            if total_reported is None and total_page is not None:
                total_reported = total_page
                stats.total_expected = total_page
            if not entry_els:
                break

            for entry_el in entry_els:
                _ensure_not_cancelled()
                if limit_rows is not None and stats.total_processed >= limit_rows:
                    break

                doi_raw = _scopus_entry_first_text(entry_el, "doi")
                doi_norm = normalize_doi_for_openalex(doi_raw)
                if not doi_norm:
                    stats.scopus_skipped_no_doi += 1
                    continue
                doi_key = doi_norm.lower()
                if doi_key in seen_dois:
                    stats.scopus_skipped_duplicate_doi += 1
                    continue
                seen_dois.add(doi_key)

                work = fetch_openalex_work_by_doi(doi_norm, session, user_agent=user_agent)
                if not work:
                    stats.scopus_doi_not_in_openalex += 1
                    continue
                if not _openalex_work_matches_type(work, work_type):
                    stats.scopus_skipped_type_mismatch += 1
                    continue
                if not _openalex_work_in_publication_date_range(work, from_date, to_date):
                    stats.scopus_skipped_date_mismatch += 1
                    continue

                cited_n = _scopus_entry_citedby_count(entry_el)
                eid = _scopus_entry_first_text(entry_el, "eid")
                overlay = {
                    "_via_scopus_auid": True,
                    "_scopus_au_id": au_id,
                    "_scopus_eid": eid,
                    "_scopus_search_doi": doi_raw.strip(),
                }
                enrich_append_openalex_work(
                    work,
                    session=session,
                    stats=stats,
                    rows=rows,
                    model=model,
                    user_agent=user_agent,
                    scopus_api_key=scopus_api_key,
                    scopus_insttoken=scopus_insttoken,
                    enable_google_scholar=enable_google_scholar,
                    serpapi_api_key=serpapi_api_key,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                    citedby_count=cited_n if cited_n is not None else "",
                    raw_record_overlay=overlay,
                    row_overlay={"data_source": "scopus_auid_then_openalex"},
                )
                time.sleep(0.06)

            if limit_rows is not None and stats.total_processed >= limit_rows:
                break
            if len(entry_els) < page_size:
                break
            if total_reported is not None and start + len(entry_els) >= total_reported:
                break
            start += page_size
            time.sleep(0.2)

    emit_progress("Completed")
    return rows, stats


def format_sdg_predictions(sdg_json: Optional[dict]) -> str:
    """
    Returns '\n'-joined strings like "84% SDG 10 (Reduced inequalities)".
    Handles multiple API variants.
    """

    def fmt_line(score, code, name):
        code_str = str(code).strip()
        name_str = (name or f"SDG {code_str}").strip()
        if name_str.lower().startswith("sdg "):
            return "{pct:.0f}% {label}".format(pct=score * 100, label=name_str)
        return "{pct:.0f}% SDG {code} ({name})".format(
            pct=score * 100, code=code_str, name=name_str
        )

    if not sdg_json:
        return ""

    items: List[Tuple[float, str, str]] = []

    preds = sdg_json.get("predictions")
    if isinstance(preds, list) and preds:
        for entry in preds:
            sdg = entry.get("sdg") or {}
            code = sdg.get("code")
            name = sdg.get("name")
            score = entry.get("prediction")
            if code is None or score is None:
                continue
            try:
                items.append((float(score), code, name))
            except (TypeError, ValueError):
                continue

    if not items and isinstance(sdg_json, list):
        for entry in sdg_json:
            label = entry.get("label")
            score = entry.get("score")
            if label is None or score is None:
                continue
            match = re.search(r"\bSDG\s*(\d+)", str(label), flags=re.I)
            code = match.group(1) if match else ""
            items.append((float(score), code, str(label)))

    if (
        not items
        and isinstance(sdg_json, dict)
        and "labels" in sdg_json
        and "scores" in sdg_json
    ):
        labels = sdg_json.get("labels") or []
        scores = sdg_json.get("scores") or []
        for label, score in zip(labels, scores):
            match = re.search(r"\bSDG\s*(\d+)", str(label), flags=re.I)
            code = match.group(1) if match else ""
            items.append((float(score), code, str(label)))

    if not items and isinstance(sdg_json, dict):
        numeric_keys = [key for key in sdg_json.keys() if str(key).isdigit()]
        if numeric_keys:
            for key in numeric_keys:
                try:
                    items.append((float(sdg_json[key]), key, None))
                except (TypeError, ValueError):
                    continue

    if (
        not items
        and isinstance(sdg_json, dict)
        and isinstance(sdg_json.get("results"), list)
    ):
        for entry in sdg_json["results"]:
            code = entry.get("sdg") or entry.get("code")
            score = entry.get("score") or entry.get("prediction")
            name = entry.get("name") or entry.get("label")
            if code is None or score is None:
                continue
            items.append((float(score), code, name))

    if not items:
        return ""

    items.sort(key=lambda item: item[0], reverse=True)
    return "\n".join(fmt_line(score, code, name) for score, code, name in items)

def sanitize_filename(value: str) -> str:
    """Strip unsafe characters so the filename can be used on most OSes."""
    value = unicodedata.normalize("NFKD", value)
    value = re.sub(r"[^\w\-\.]+", "_", value, flags=re.UNICODE)
    return value.strip("_")

def fetch_works_with_sdg(
    from_date: str,
    work_type: Optional[str],
    model: str,
    institution_id: Optional[str] = None,
    to_date: Optional[str] = None,
    limit_rows: Optional[int] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    scopus_api_key: Optional[str] = None,
    scopus_insttoken: Optional[str] = None,
    enable_google_scholar: bool = True,
    serpapi_api_key: Optional[str] = None, # New parameter
    extra_institution_ids: Optional[Sequence[str]] = None,
    author_openalex_id: Optional[str] = None,
    progress_callback: ProgressHook = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[List[Dict[str, object]], FetchStats]:
    """Main pipeline: fetch works page-by-page and enrich/cache SDG info."""
    if author_openalex_id:
        filter_str = make_author_filter(
            author_openalex_id, from_date, work_type, to_date=to_date
        )
    elif institution_id:
        filter_str = make_filter(
            institution_id,
            from_date,
            work_type,
            to_date,
            extra_institution_ids=extra_institution_ids,
        )
    else:
        raise ValueError("Provide institution_id or author_openalex_id")

    params = {
        "filter": filter_str,
        "select": "id,display_name,title,publication_date,doi,abstract_inverted_index,type,language,open_access,authorships",
        "per-page": PER_PAGE,
        "cursor": "*",
    }
    headers = {"User-Agent": user_agent}

    stats = FetchStats(
        total_expected=None,
        total_processed=0,
        openalex_abstract_missing=0,
        scopus_abstract_retrieved=0,
        gs_abstract_retrieved=0,
    )
    rows: List[Dict[str, Any]] = []

    def _ensure_not_cancelled() -> None:
        """Raise if the caller requested cancellation."""
        if cancel_check and cancel_check():
            raise FetchCancelled()

    def emit_progress(message: str = "") -> None:
        """Convenience wrapper for reporting progress up to the UI."""
        _ensure_not_cancelled()
        if progress_callback:
            progress_callback(stats.total_processed, stats.total_expected, message)

    emit_progress("Starting fetch")

    with requests.Session() as session:
        # First page to establish total size
        response = session.get(BASE_WORKS, params=params, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        stats.total_expected = (
            (data.get("meta") or {}).get("count")
            if isinstance(data.get("meta"), dict)
            else None
        )
        results = data.get("results", []) or []
        next_cursor = (data.get("meta") or {}).get("next_cursor")

        def process_record(work: dict) -> None:
            """Normalize/calculate every column for a single OpenAlex work."""
            enrich_append_openalex_work(
                work,
                session=session,
                stats=stats,
                rows=rows,
                model=model,
                user_agent=user_agent,
                scopus_api_key=scopus_api_key,
                scopus_insttoken=scopus_insttoken,
                enable_google_scholar=enable_google_scholar,
                serpapi_api_key=serpapi_api_key,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

        for work in results:
            _ensure_not_cancelled()
            if limit_rows is not None and stats.total_processed >= limit_rows:
                next_cursor = None
                break
            process_record(work)

        params["cursor"] = next_cursor

        while next_cursor:
            _ensure_not_cancelled()
            if limit_rows is not None and stats.total_processed >= limit_rows:
                break
            response = session.get(BASE_WORKS, params=params, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", []) or []
            next_cursor = (data.get("meta") or {}).get("next_cursor")
            for work in results:
                if limit_rows is not None and stats.total_processed >= limit_rows:
                    next_cursor = None
                    break
                process_record(work)
            params["cursor"] = next_cursor
            time.sleep(0.2)

    emit_progress("Completed")
    return rows, stats


__all__ = [
    "AURORA_MODELS",
    "BASE_AUTHORS",
    "DEFAULT_FROM_DATE",
    "DEFAULT_USER_AGENT",
    "FetchCancelled",
    "FetchStats",
    "ELSEVIER_SCOPUS_SEARCH",
    "OPENALEX_TYPE_TO_SCOPUS_DOCTYPE",
    "extract_orcid",
    "extract_scopus_author_id_from_openalex_author",
    "extract_scopus_author_id_from_raw",
    "fetch_author_publications_scopus_with_sdg",
    "fetch_author_record",
    "fetch_openalex_work_by_doi",
    "enrich_append_openalex_work",
    "normalize_doi_for_openalex",
    "fetch_institution_lineage",
    "ELSEVIER_ABSTRACT_BY_DOI",
    "ELSEVIER_AUTHOR_BY_ID",
    "fetch_orcid_from_elsevier_author",
    "parse_orcid_from_elsevier_author_xml",
    "SERPAPI_GS_API",
    "build_scopus_author_publications_query",
    "resolve_scopus_au_id_for_search",
    "fetch_works_with_sdg",
    "format_sdg_predictions",
    "is_openalex_author_id",
    "is_openalex_institution_id",
    "is_ror_url",
    "looks_like_scopus_author_id",
    "make_author_filter",
    "normalize_openalex_author_token",
    "resolve_author_openalex_id",
    "sanitize_filename",
    "search_institutions_by_name",
]
