"""Environment configuration (mirrors Vite env names for shared .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load from repo root so Streamlit/Railway still see .env when cwd is not the project root.
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _truthy(val: str | None) -> bool:
    if not val:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


def _clean_supabase_url(raw: str | None) -> str:
    """Return empty if unset or if value is a common .env placeholder (treat as not configured)."""
    s = (raw or "").strip().rstrip("/")
    if not s:
        return ""
    low = s.lower()
    # Typical copy-paste from .env.example — must not enable proxy mode.
    if "your_supabase" in low:
        return ""
    return s


SUPABASE_URL: str = _clean_supabase_url(os.getenv("VITE_SUPABASE_URL"))
# Prefer direct Elsevier API when no Supabase proxy URL is set (common on Railway / one-key deploys).
# If VITE_SUPABASE_URL is configured, proxy mode is used unless VITE_USE_DIRECT_API=true.
_has_supabase_url: bool = bool(SUPABASE_URL)
USE_DIRECT_API: bool = _truthy(os.getenv("VITE_USE_DIRECT_API")) or not _has_supabase_url
SUPABASE_ANON_KEY: str = os.getenv("VITE_SUPABASE_ANON_KEY") or ""


def _clean_scival_api_key(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    low = s.lower()
    if "your_scival" in low:
        return ""
    return s


def _resolve_scival_api_key() -> str:
    """First non-empty env value (shared Elsevier API keys often use other names on hosts)."""
    for name in (
        "VITE_SCIVAL_API_KEY",
        "SCIVAL_API_KEY",
        "SCOPUS_API_KEY",
        "ELSEVIER_API_KEY",
        "ELS_API_KEY",
    ):
        v = _clean_scival_api_key(os.getenv(name))
        if v:
            return v
    return ""


# Prefer explicit SciVal key; do not hardcode keys in source.
SCIVAL_API_KEY: str = _resolve_scival_api_key()


def _resolve_scopus_content_api_key() -> str:
    """API key used for Elsevier Scopus Content APIs such as AU-ID publication search."""
    for name in (
        "SCOPUS_API_KEY",
        "ELSEVIER_API_KEY",
        "ELS_API_KEY",
        "VITE_SCIVAL_API_KEY",
        "SCIVAL_API_KEY",
    ):
        v = _clean_scival_api_key(os.getenv(name))
        if v:
            return v
    return ""


SCOPUS_CONTENT_API_KEY: str = _resolve_scopus_content_api_key()


def _resolve_insttoken() -> str:
    """Institutional token; accept common Railway typos (e.g. ELSVIER vs ELSEVIER)."""
    for name in (
        "VITE_ELSEVIER_INSTTOKEN",
        "ELSEVIER_INSTTOKEN",
        "ELSVIER_INSTTOKEN",  # typo: missing E (Elsevier)
    ):
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return ""


# Optional institutional token (Elsevier query param insttoken and/or header X-ELS-Insttoken)
ELSEVIER_INSTTOKEN: str = _resolve_insttoken()

# OpenAlex asks callers to identify themselves. Override in deployment with a contact email.
OPENALEX_USER_AGENT: str = (
    os.getenv("OPENALEX_USER_AGENT")
    or os.getenv("HTTP_USER_AGENT")
    or "HKUST Research Metrics Dashboard (mailto:library@ust.hk)"
).strip()

# Optional; currently reserved for future abstract backfill when Google Scholar is enabled.
SERPAPI_API_KEY: str = (os.getenv("SERPAPI_API_KEY") or "").strip()

# Optional HTTP(S) proxy for SciVal HTTP client only (Elsevier direct API + ORCID lookup).
# Use when Cloudflare blocks your server's datacenter IP: point this at a library/campus proxy
# so traffic exits from an allowlisted university address. Example: http://proxy.ust.hk:8080
SCIVAL_HTTP_PROXY: str = (os.getenv("SCIVAL_HTTP_PROXY") or "").strip()


def scival_httpx_verify() -> bool | str:
    """TLS ``verify`` argument for httpx clients talking to Elsevier/SciVal.

    - Default: Mozilla CA bundle via ``certifi`` when installed (often fixes Windows
      ``CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate``).
    - ``SCIVAL_SSL_VERIFY=false`` (or ``0`` / ``no``): disable verification — **insecure**;
      only as a last resort (e.g. unusual TLS inspection without a corporate CA file).
    - ``SCIVAL_SSL_CA_BUNDLE``: path to a PEM bundle (e.g. institutional root CA).
    """
    ssl_raw = (os.getenv("SCIVAL_SSL_VERIFY") or "").strip().lower()
    if ssl_raw in ("0", "false", "no", "off"):
        return False
    ca_path = (os.getenv("SCIVAL_SSL_CA_BUNDLE") or "").strip()
    if ca_path:
        return ca_path
    try:
        import certifi

        return certifi.where()
    except ImportError:
        return True


DIRECT_API_BASE: str = (
    "https://api.elsevier.com/analytics/scival/author/metrics"
)


def supabase_proxy_url() -> str:
    if not SUPABASE_URL:
        return ""
    return f"{SUPABASE_URL}/functions/v1/scival-proxy"
