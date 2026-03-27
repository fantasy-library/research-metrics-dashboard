"""Environment configuration (mirrors Vite env names for shared .env)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _truthy(val: str | None) -> bool:
    if not val:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


USE_DIRECT_API: bool = _truthy(os.getenv("VITE_USE_DIRECT_API"))
SUPABASE_URL: str = (os.getenv("VITE_SUPABASE_URL") or "").rstrip("/")
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
