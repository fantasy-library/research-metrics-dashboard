"""Environment configuration (mirrors Vite env names for shared .env)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


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
# Prefer explicit SciVal key; do not hardcode keys in source.
SCIVAL_API_KEY: str = (
    os.getenv("VITE_SCIVAL_API_KEY") or os.getenv("SCIVAL_API_KEY") or ""
)
# Optional institutional token (some Elsevier SciVal calls require it in the query string)
ELSEVIER_INSTTOKEN: str = (
    os.getenv("VITE_ELSEVIER_INSTTOKEN") or os.getenv("ELSEVIER_INSTTOKEN") or ""
)

DIRECT_API_BASE: str = (
    "https://api.elsevier.com/analytics/scival/author/metrics"
)


def supabase_proxy_url() -> str:
    if not SUPABASE_URL:
        return ""
    return f"{SUPABASE_URL}/functions/v1/scival-proxy"
