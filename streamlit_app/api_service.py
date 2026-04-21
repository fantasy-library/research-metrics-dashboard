"""SciVal / Supabase proxy client — ported from src/services/api.ts."""

from __future__ import annotations

import json
import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from streamlit_app.config import (
    DIRECT_API_BASE,
    ELSEVIER_INSTTOKEN,
    SCIVAL_API_KEY,
    SUPABASE_ANON_KEY,
    USE_DIRECT_API,
    supabase_proxy_url,
)

RATE_LIMIT_CONFIG = {
    "max_requests_per_second": 2,
    "max_concurrent_requests": 3,
    "retry_attempts": 3,
    "retry_delay": 2.0,
    "backoff_multiplier": 2,
}


def format_percentage(value: float) -> float:
    rounded = round(float(value), 2)
    return float(int(rounded)) if rounded % 1 == 0 else rounded


class APIError(Exception):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        is_entitlement_error: bool = False,
        is_rate_limit_error: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.is_entitlement_error = is_entitlement_error
        self.is_rate_limit_error = is_rate_limit_error


class _RateLimiter:
    def __init__(self) -> None:
        self._times: deque[float] = deque()
        self._active = 0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        max_per_sec = RATE_LIMIT_CONFIG["max_requests_per_second"]
        max_conc = RATE_LIMIT_CONFIG["max_concurrent_requests"]
        while True:
            wait_time = 0.05
            with self._lock:
                now = time.time()
                while self._times and now - self._times[0] > 1.0:
                    self._times.popleft()
                at_conc = self._active >= max_conc
                at_rate = len(self._times) >= max_per_sec
                if not at_conc and not at_rate:
                    self._active += 1
                    self._times.append(time.time())
                    return
                if at_conc:
                    wait_time = 0.1
                elif at_rate:
                    oldest = self._times[0]
                    wait_time = max(0.05, 1.0 - (now - oldest) + 0.1)
            time.sleep(wait_time)

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


_rate_limiter = _RateLimiter()


def _retry_with_backoff(operation):
    """Retry rate-limited SciVal calls. Do not retry read/connect timeouts (avoids long silent spinners)."""
    last_err: Optional[Exception] = None
    max_attempts = RATE_LIMIT_CONFIG["retry_attempts"]
    base_delay = RATE_LIMIT_CONFIG["retry_delay"]
    mult = RATE_LIMIT_CONFIG["backoff_multiplier"]
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except APIError as e:
            last_err = e
            if not e.is_rate_limit_error and attempt > 1:
                raise
        except httpx.TimeoutException as e:
            last_err = e
            break
        except httpx.ConnectError as e:
            last_err = e
            break
        except httpx.NetworkError as e:
            last_err = e
            break
        except Exception as e:
            last_err = e
        if attempt >= max_attempts:
            break
        delay = base_delay * (mult ** (attempt - 1)) + random.random()
        time.sleep(delay)
    if last_err is None:
        raise RuntimeError("retry failed")
    if isinstance(last_err, httpx.TimeoutException):
        raise APIError(
            "SciVal did not respond in time. The Elsevier API may be slow or unavailable; "
            "wait a moment and try again."
        ) from last_err
    if isinstance(last_err, (httpx.ConnectError, httpx.NetworkError)):
        raise APIError(
            "Could not reach SciVal (network error). Check your connection and try again."
        ) from last_err
    if isinstance(last_err, APIError):
        raise last_err
    raise APIError(str(last_err)) from last_err


def is_missing_scival_api_key_error(message: str) -> bool:
    """True when failure is due to no API key (avoid duplicate UI + redundant per-author retries)."""
    low = message.lower()
    if "no scival api key" in low and "configured" in low:
        return True
    if "scival api key" in low and ("not configured" in low or "required" in low):
        return True
    return False


def is_scival_authentication_error(message: str) -> bool:
    """HTTP 401 / invalid key — same message for every author; show once, skip per-author retries."""
    low = message.lower()
    if "api error (401)" in low:
        return True
    if "authentication failed" in low and (
        "scival" in low
        or "settings" in low
        or "environment" in low
        or "railway" in low
        or "api key" in low
    ):
        return True
    return False


def _extract_scival_error_detail(body: str) -> str:
    """Best-effort parse of Elsevier SciVal JSON/XML error bodies for UI (avoids generic 'HTTP 500' only)."""
    s = (body or "").strip()
    if not s:
        return ""
    if len(s) > 12000:
        s = s[:12000]
    low = s.lower()
    if low.startswith("<!doctype") or low.startswith("<html"):
        return "HTML error page (often gateway or proxy), not JSON from SciVal."

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        one = " ".join(s.split())
        return one[:420] + ("…" if len(one) > 420 else "")

    def walk(o: Any, depth: int = 0) -> Optional[str]:
        if depth > 12:
            return None
        if isinstance(o, dict):
            for key in (
                "statusText",
                "developerMessage",
                "message",
                "detail",
                "errorText",
                "title",
            ):
                v = o.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()[:500]
            st = o.get("status")
            if isinstance(st, dict):
                code = st.get("statusCode") or st.get("code")
                txt = st.get("statusText") or st.get("message")
                parts = [str(x) for x in (code, txt) if x]
                if parts:
                    return ": ".join(parts)[:500]
            for key in ("service-error", "serviceError", "error", "errors"):
                if key in o:
                    inner = walk(o[key], depth + 1)
                    if inner:
                        return inner
            if "errors" in o and isinstance(o["errors"], list) and o["errors"]:
                inner = walk(o["errors"][0], depth + 1)
                if inner:
                    return inner
        elif isinstance(o, list) and o:
            return walk(o[0], depth + 1)
        return None

    out = walk(data)
    if out:
        return out
    try:
        flat = json.dumps(data, ensure_ascii=False)[:450]
    except (TypeError, ValueError):
        flat = str(data)[:450]
    return flat + ("…" if len(flat) >= 450 else "")


def _classify_api_error_plain(message: str, low: str) -> str | None:
    """Map common API / network / Elsevier-style messages to user-friendly text."""
    # Configuration (do not match on "vite_supabase_url" alone — that substring appears in our own hints.)
    if "supabase url not configured" in low:
        return (
            "The app is not configured to use the proxy API. "
            "Set VITE_SUPABASE_URL (and keys) in your environment, or switch to direct SciVal API mode."
        )
    if "scival api key" in low and ("not configured" in low or "required" in low):
        return (
            "No SciVal API key is configured. Add SCIVAL_API_KEY, VITE_SCIVAL_API_KEY, "
            "ELSEVIER_API_KEY, or ELS_API_KEY (or enter a key in Settings) to fetch metrics."
        )

    # Access & subscription
    if (
        "entitlement" in low
        or "not entitled" in low
        or "entitlements_error" in low
    ):
        return (
            "Your API key does not include access to this SciVal data. "
            "Confirm your Elsevier entitlement or ask your library administrator."
        )

    # Rate limiting & throttling
    if (
        "rate limit" in low
        or "rate_limit" in low
        or "too many requests" in low
        or re.search(r"\b429\b", message)
        or "quota" in low and "exceed" in low
    ):
        return (
            "The service is temporarily limiting requests (rate limit). "
            "Wait one to two minutes, then try again — or analyze fewer authors at once."
        )

    # Authentication
    if (
        "401" in message
        or "unauthorized" in low
        or "authentication failed" in low
        or "invalid api key" in low
        or "api key" in low and "invalid" in low
    ):
        return (
            "Authentication failed (HTTP 401). Verify your Elsevier API key: use Settings, "
            "or set SCIVAL_API_KEY in Railway (or .env). If your institution requires it, "
            "check ELSEVIER_INSTTOKEN too — wrong or missing tokens also return 401."
        )

    # Forbidden (non-entitlement)
    if "403" in message and "entitlement" not in low and "not entitled" not in low:
        return (
            "Access was denied (HTTP 403). The request may be blocked by policy or network rules. "
            "Try again later or from another network."
        )

    # Author / resource not found (common SciVal / Elsevier cases)
    if re.search(r"\b404\b", message) or "not found" in low:
        if "author" in low or "scopus" in low or "researcher" in low:
            return (
                "No data was returned for this Scopus Author ID. "
                "Check that the ID is correct (digits only, no typos) and that the profile exists in Scopus."
            )
        return (
            "The requested resource was not found (HTTP 404). "
            "Verify the author ID or try again later."
        )

    if (
        "no researcher found" in low
        or "researcher id not found" in low
        or "author not found" in low
        or "unknown author" in low
        or "invalid author" in low
    ):
        return (
            "No researcher matched this identifier. "
            "Please verify the Scopus Author ID or ORCID and try again."
        )

    # Server / overload
    if re.search(r"\b503\b|\b502\b|\b504\b", message) or "unavailable" in low:
        return (
            "The SciVal service is temporarily unavailable. "
            "Please try again in a few minutes."
        )
    if "500" in message or "internal server" in low:
        # Direct SciVal path may already attach Elsevier detail — do not replace with generic text.
        if "scival returned http" in low or "api detail:" in low:
            return None
        return (
            "The API returned a server error. This is usually temporary — try again shortly. "
            "If it persists, contact support with the time of the request."
        )

    # Timeouts & connectivity
    if (
        "timeout" in low
        or "timed out" in low
        or "readtimeout" in low
        or "connecttimeout" in low
    ):
        return (
            "The request timed out before the API responded. "
            "Check your connection, then retry. If you are analyzing many authors, try fewer at a time."
        )
    if (
        "connection refused" in low
        or "connection reset" in low
        or "network" in low
        or "unreachable" in low
        or "getaddrinfo" in low
        or "name or service not known" in low
        or "ssl" in low and "error" in low
    ):
        return (
            "Could not reach the API. Check your internet connection, firewall, or VPN, then try again."
        )

    return None


def format_error_message_for_user(
    message: str,
    max_plain: int = 600,
    *,
    is_entitlement_error: bool = False,
    is_rate_limit_error: bool = False,
) -> str:
    """
    Short, readable UI text. Replaces HTML bodies (e.g. Cloudflare block pages)
    with a calm sentence so users never see raw markup. Classifies common API errors.
    """
    if not message:
        return "Something went wrong. Please try again."
    if is_entitlement_error:
        return (
            "Your API key does not include access to this SciVal data. "
            "Confirm your Elsevier entitlement or ask your library administrator."
        )
    if is_rate_limit_error:
        return (
            "The service is temporarily limiting requests (rate limit). "
            "Wait one to two minutes, then try again — or analyze fewer authors at once."
        )
    s = message.strip()
    low = s.lower()
    if (
        "you have been blocked" in low
        or "sorry, you have been blocked" in low
        or ("cloudflare" in low and "ray id" in low)
        or "unable to access elsevier" in low
    ):
        return (
            "Cloudflare blocked this traffic (Elsevier’s edge security). "
            "Common causes: hosting the app on a public cloud IP (Railway, AWS, etc.), using a consumer VPN, "
            "or sending many SciVal requests in a short time. "
            "Try: run from your university network or an institutional VPN that exits on campus, "
            "turn off other VPNs, wait 15–30 minutes, and avoid rapid repeated Analyze clicks. "
            "If it persists, contact your library or Elsevier support with the Ray ID shown on the block page "
            "and mention API access to api.elsevier.com (SciVal author metrics)."
        )
    looks_html = (
        "<html" in low
        or "<!doctype" in low
        or (len(s) > 400 and "cloudflare" in low and "cf-" in low)
    )
    if looks_html:
        if "403" in s[:200] or " (403)" in s[:200]:
            return (
                "The API blocked this request (HTTP 403). "
                "Try again later or use another network."
            )
        if "429" in s[:120] or " (429)" in s[:120]:
            return (
                "Too many requests were sent in a short time. "
                "Please wait a minute and try again."
            )
        if "cloudflare" in low or "you have been blocked" in low:
            return (
                "The response was an HTML block page (often Cloudflare) instead of JSON from SciVal. "
                "Retry from a campus or institutional network, avoid consumer VPNs and burst traffic, "
                "or contact Elsevier/your librarian with the Ray ID if you host on a public cloud IP."
            )
        return (
            "The API returned an HTML error page instead of data. "
            "Please try again later or check your network."
        )

    classified = _classify_api_error_plain(s, low)
    if classified:
        return classified

    if len(s) > max_plain:
        return s[: max_plain - 1].rstrip() + "…"
    return s


def _parse_supabase_error(
    response: httpx.Response, error_text: str
) -> tuple[str, bool, bool]:
    msg = f"HTTP {response.status_code}: {error_text}"
    is_ent = False
    is_rl = False
    try:
        err_data = json.loads(error_text)
        err_s = str(err_data.get("error", ""))
        if "ENTITLEMENTS_ERROR" in err_s or "Not entitled to the resource" in err_s:
            is_ent = True
            msg = (
                "API Access Error: Your SciVal API key does not have the required "
                "permissions to access this resource. Please contact your administrator."
            )
        elif response.status_code == 429 or "RATE_LIMIT_EXCEEDED" in err_s:
            is_rl = True
            msg = (
                "Rate limit exceeded. The system will automatically retry your request. "
                "Please wait..."
            )
        elif err_s:
            msg = err_s
    except json.JSONDecodeError:
        low = error_text.lower()
        if "entitlement" in low or "not entitled" in low:
            is_ent = True
            msg = (
                "API Access Error: Your SciVal API key does not have the required "
                "permissions to access this resource."
            )
        elif response.status_code == 429 or "rate limit" in low:
            is_rl = True
            msg = "Rate limit exceeded. Please wait..."
        else:
            msg = format_error_message_for_user(msg)
    return msg, is_ent, is_rl


class APIService:
    def __init__(self) -> None:
        # Tighter than 120s: long hangs made "Fetching metrics…" feel stuck; Elsevier usually responds in seconds.
        self._client = httpx.Client(timeout=httpx.Timeout(55.0, connect=12.0))

    def close(self) -> None:
        self._client.close()

    def _make_supabase_request(
        self,
        url: str,
        method: str,
        body: Dict[str, Any],
        custom_api_key: Optional[str],
        year_range: Optional[str],
        available_metrics: Optional[List[Dict[str, Any]]],
        included_docs: Optional[str],
    ) -> Any:
        if custom_api_key:
            body["customApiKey"] = custom_api_key
        if year_range:
            body["yearRange"] = year_range
        if available_metrics is not None:
            body["availableMetrics"] = available_metrics
        if included_docs:
            body["includedDocs"] = included_docs

        headers = {
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }

        def op():
            _rate_limiter.acquire()
            try:
                r = self._client.request(
                    method, url, headers=headers, content=json.dumps(body)
                )
                text = r.text
                if not r.is_success:
                    msg, is_ent, is_rl = _parse_supabase_error(r, text)
                    raise APIError(msg, r.status_code, is_ent, is_rl)
                return r.json()
            finally:
                _rate_limiter.release()

        return _retry_with_backoff(op)

    def _fetch_direct_metric(
        self,
        author_id: str,
        metric_type: str,
        by_year: bool,
        custom_api_key: Optional[str],
        year_range: str,
        include_self_citations: str,
        included_docs: str,
    ) -> Any:
        api_key = (custom_api_key or SCIVAL_API_KEY or "").strip()
        if not api_key:
            raise APIError(
                "SciVal API key is not configured. Set SCIVAL_API_KEY, VITE_SCIVAL_API_KEY, "
                "or ELSEVIER_API_KEY (or enter a key in Settings)."
            )
        # Elsevier allows apiKey / insttoken on the query string (same pattern as author XML URLs).
        # Institutional access often requires both; we also send X-ELS-* headers below.
        inst = (ELSEVIER_INSTTOKEN or "").strip()
        params: Dict[str, str] = {
            "apiKey": api_key,
            "authors": author_id,
            "metricTypes": metric_type,
            "includedDocs": included_docs,
            "yearRange": year_range,
            "includeSelfCitations": include_self_citations,
            "byYear": str(by_year).lower(),
            # Match Elsevier SciVal browser / Data Fetcher examples (see dev.elsevier.com SciVal payloads).
            # Requests without these sometimes differ in behaviour across metric types or tenants.
            "journalImpactType": "CiteScore",
            "showAsFieldWeighted": "false",
            "indexType": "hIndex",
        }
        if inst:
            params["insttoken"] = inst
        url = f"{DIRECT_API_BASE}?{urlencode(params)}"
        headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": api_key,
            "User-Agent": "SciVal-Research-Dashboard/1.0",
        }
        if inst:
            headers["X-ELS-Insttoken"] = inst

        def op():
            _rate_limiter.acquire()
            try:
                r = self._client.get(url, headers=headers)
                text = r.text
                if not r.is_success:
                    is_ent = False
                    is_rl = False
                    msg = f"API Error ({r.status_code}): {text}"
                    if r.status_code == 429 or "RATE_LIMIT_EXCEEDED" in text:
                        is_rl = True
                        msg = (
                            "Rate limit exceeded. The system will automatically retry. "
                            "Please wait..."
                        )
                    elif (
                        "ENTITLEMENTS_ERROR" in text
                        or "Not entitled to the resource" in text
                    ):
                        is_ent = True
                        msg = (
                            "API Access Error: Your SciVal API key does not have the "
                            "required permissions for SciVal author metrics."
                        )
                    elif r.status_code >= 500:
                        detail = _extract_scival_error_detail(text)
                        msg = (
                            f"SciVal returned HTTP {r.status_code} (server error from Elsevier). "
                        )
                        if detail:
                            msg += f"API detail: {detail} "
                        msg += (
                            "This is often temporary—try again in a few minutes. "
                            "If it keeps happening, confirm SCIVAL_API_KEY and, if your institution uses one, "
                            "ELSEVIER_INSTTOKEN with your library."
                        )
                    else:
                        detail = _extract_scival_error_detail(text)
                        msg = format_error_message_for_user(
                            f"API Error ({r.status_code}): {detail or text[:900]}"
                        )
                    raise APIError(msg, r.status_code, is_ent, is_rl)
                return r.json()
            finally:
                _rate_limiter.release()

        return _retry_with_backoff(op)

    @staticmethod
    def _process_h_index(data: Any) -> Dict[str, Any]:
        try:
            val = data["results"][0]["metrics"][0].get("value", "N/A")
        except (KeyError, IndexError, TypeError):
            val = "N/A"
        return {"value": val, "dataSource": data.get("dataSource")}

    def _normalize_year_data(self, year_data: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        if not isinstance(year_data, dict):
            return out
        for year_str, value in year_data.items():
            try:
                y = int(year_str)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict) and value is not None and "value" in value:
                out[year_str] = round(float(value["value"]), 2)
            elif isinstance(value, (int, float)):
                out[year_str] = round(float(value), 2)
            else:
                out[year_str] = 0.0
        return out

    def _normalize_year_data_with_formatting(self, year_data: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        if not isinstance(year_data, dict):
            return out
        for year_str, value in year_data.items():
            try:
                y = int(year_str)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict) and value is not None and "value" in value:
                out[year_str] = float(format_percentage(float(value["value"])))
            elif isinstance(value, (int, float)):
                out[year_str] = float(format_percentage(float(value)))
            else:
                out[year_str] = 0.0
        return out

    def _process_scholarly_output(self, year_data: Any, total_data: Any) -> Dict[str, Any]:
        try:
            by_year = year_data["results"][0]["metrics"][0].get("valueByYear") or {}
        except (KeyError, IndexError, TypeError):
            by_year = {}
        try:
            total = total_data["results"][0]["metrics"][0].get("value", "N/A")
        except (KeyError, IndexError, TypeError):
            total = "N/A"
        return {"byYear": self._normalize_year_data(by_year), "total": total}

    def _process_fwci(self, year_data: Any, total_data: Any) -> Dict[str, Any]:
        try:
            by_year = year_data["results"][0]["metrics"][0].get("valueByYear") or {}
        except (KeyError, IndexError, TypeError):
            by_year = {}
        try:
            total = total_data["results"][0]["metrics"][0].get("value", "N/A")
        except (KeyError, IndexError, TypeError):
            total = "N/A"
        return {"byYear": self._normalize_year_data(by_year), "total": total}

    def _process_top_journal(self, year_data: Any, total_data: Any) -> Dict[str, Any]:
        by_year: Dict[str, float] = {}
        total: Any = "N/A"
        try:
            vals = year_data["results"][0]["metrics"][0].get("values") or []
            for v in vals:
                if v.get("threshold") == 10:
                    by_year = v.get("percentageByYear") or {}
                    break
        except (KeyError, IndexError, TypeError):
            pass
        try:
            tvals = total_data["results"][0]["metrics"][0].get("values") or []
            for v in tvals:
                if v.get("threshold") == 10:
                    total = v.get("percentage", "N/A")
                    break
        except (KeyError, IndexError, TypeError):
            pass
        return {
            "byYear": self._normalize_year_data_with_formatting(by_year),
            "total": total,
        }

    def _process_citations(self, year_data: Any, total_data: Any) -> Dict[str, Any]:
        try:
            by_year = year_data["results"][0]["metrics"][0].get("valueByYear") or {}
        except (KeyError, IndexError, TypeError):
            by_year = {}
        try:
            total = total_data["results"][0]["metrics"][0].get("value", "N/A")
        except (KeyError, IndexError, TypeError):
            total = "N/A"
        return {"byYear": self._normalize_year_data(by_year), "total": total}

    def _process_collaboration(self, data: Any) -> Dict[str, Any]:
        default_types = {
            "institutional": {"byYear": {}, "total": "N/A"},
            "international": {"byYear": {}, "total": "N/A"},
            "national": {"byYear": {}, "total": "N/A"},
            "singleAuthorship": {"byYear": {}, "total": "N/A"},
        }
        try:
            metric = data["results"][0]["metrics"][0]
            values = metric.get("values")
        except (KeyError, IndexError, TypeError):
            return {"byYear": {}, "total": "N/A", "collaborationTypes": default_types}
        if not values:
            return {"byYear": {}, "total": "N/A", "collaborationTypes": default_types}

        collaboration_types: Dict[str, Any] = {
            k: {"byYear": {}, "total": "N/A"} for k in default_types
        }
        total_by_year: Dict[str, float] = {}

        for collab_data in values:
            ctype = (collab_data.get("collabType") or "").lower()
            pby = collab_data.get("percentageByYear")
            if not pby:
                continue
            norm = self._normalize_year_data_with_formatting(pby)
            vals_list = list(norm.values())
            avg = (
                format_percentage(sum(vals_list) / len(vals_list))
                if vals_list
                else "N/A"
            )
            if "institutional" in ctype:
                collaboration_types["institutional"] = {"byYear": norm, "total": avg}
            elif "international" in ctype:
                collaboration_types["international"] = {"byYear": norm, "total": avg}
                total_by_year = norm
            elif "national" in ctype:
                collaboration_types["national"] = {"byYear": norm, "total": avg}
            elif "single" in ctype:
                collaboration_types["singleAuthorship"] = {"byYear": norm, "total": avg}

        tv = list(total_by_year.values())
        grand = (
            format_percentage(sum(tv) / len(tv)) if tv else "N/A"
        )
        return {
            "byYear": total_by_year,
            "total": grand,
            "collaborationTypes": collaboration_types,
        }

    def _process_academic_corporate(self, data: Any) -> Dict[str, Any]:
        default_types = {
            "academicCorporate": {"byYear": {}, "total": "N/A"},
            "academicOnly": {"byYear": {}, "total": "N/A"},
            "corporateOnly": {"byYear": {}, "total": "N/A"},
        }
        try:
            metric = data["results"][0]["metrics"][0]
            values = metric.get("values")
        except (KeyError, IndexError, TypeError):
            return {"byYear": {}, "total": "N/A", "collaborationTypes": default_types}
        if not values:
            return {"byYear": {}, "total": "N/A", "collaborationTypes": default_types}

        collaboration_types: Dict[str, Any] = {
            k: {"byYear": {}, "total": "N/A"} for k in default_types
        }
        total_by_year: Dict[str, float] = {}

        for collab_data in values:
            ctype = (collab_data.get("collabType") or "").lower()
            pby = collab_data.get("percentageByYear")
            if not pby:
                continue
            norm = self._normalize_year_data_with_formatting(pby)
            vals_list = list(norm.values())
            avg = (
                format_percentage(sum(vals_list) / len(vals_list))
                if vals_list
                else "N/A"
            )
            if "academic-corporate" in ctype:
                collaboration_types["academicCorporate"] = {"byYear": norm, "total": avg}
                total_by_year = norm
            elif "academic only" in ctype:
                collaboration_types["academicOnly"] = {"byYear": norm, "total": avg}
            elif "corporate only" in ctype:
                collaboration_types["corporateOnly"] = {"byYear": norm, "total": avg}

        tv = list(total_by_year.values())
        grand = format_percentage(sum(tv) / len(tv)) if tv else "N/A"
        return {
            "byYear": total_by_year,
            "total": grand,
            "collaborationTypes": collaboration_types,
        }

    @staticmethod
    def _extract_author_name(data: Any) -> Optional[str]:
        try:
            return data["results"][0]["author"].get("name")
        except (KeyError, IndexError, TypeError):
            return None

    def get_direct_author_metrics(
        self,
        author_id: str,
        custom_api_key: Optional[str],
        year_range: str,
        available_metrics: Optional[List[Dict[str, Any]]],
        included_docs: str,
        include_self_citations: bool,
    ) -> Dict[str, Any]:
        enabled = [m for m in (available_metrics or []) if m.get("enabled")]
        enabled_ids = [m["id"] for m in enabled]

        h_index_data = self._fetch_direct_metric(
            author_id,
            "HIndices",
            False,
            custom_api_key,
            year_range,
            str(include_self_citations).lower(),
            included_docs,
        )

        so_year = so_total = None
        fwci_y = fwci_t = None
        top_j = top_j_t = None
        cc_y = cc_t = None
        cpp_y = cpp_t = None
        collab = None
        acc = None

        def pause() -> None:
            time.sleep(0.2)

        if "publication" in enabled_ids:
            pause()
            so_year = self._fetch_direct_metric(
                author_id,
                "ScholarlyOutput",
                True,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
            pause()
            so_total = self._fetch_direct_metric(
                author_id,
                "ScholarlyOutput",
                False,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
        if "fwci" in enabled_ids:
            pause()
            fwci_y = self._fetch_direct_metric(
                author_id,
                "FieldWeightedCitationImpact",
                True,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
            pause()
            fwci_t = self._fetch_direct_metric(
                author_id,
                "FieldWeightedCitationImpact",
                False,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
        if "topJournal" in enabled_ids:
            pause()
            top_j = self._fetch_direct_metric(
                author_id,
                "PublicationsInTopJournalPercentiles",
                True,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
            pause()
            top_j_t = self._fetch_direct_metric(
                author_id,
                "PublicationsInTopJournalPercentiles",
                False,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
        if "citationCount" in enabled_ids:
            pause()
            cc_y = self._fetch_direct_metric(
                author_id,
                "CitationCount",
                True,
                custom_api_key,
                year_range,
                str(include_self_citations).lower(),
                included_docs,
            )
            pause()
            cc_t = self._fetch_direct_metric(
                author_id,
                "CitationCount",
                False,
                custom_api_key,
                year_range,
                str(include_self_citations).lower(),
                included_docs,
            )
        if "citationsPerPublication" in enabled_ids:
            pause()
            cpp_y = self._fetch_direct_metric(
                author_id,
                "CitationsPerPublication",
                True,
                custom_api_key,
                year_range,
                str(include_self_citations).lower(),
                included_docs,
            )
            pause()
            cpp_t = self._fetch_direct_metric(
                author_id,
                "CitationsPerPublication",
                False,
                custom_api_key,
                year_range,
                str(include_self_citations).lower(),
                included_docs,
            )
        if "collaboration" in enabled_ids:
            pause()
            collab = self._fetch_direct_metric(
                author_id,
                "Collaboration",
                True,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )
        if "academicCorporateCollaboration" in enabled_ids:
            pause()
            acc = self._fetch_direct_metric(
                author_id,
                "AcademicCorporateCollaboration",
                True,
                custom_api_key,
                year_range,
                "false",
                included_docs,
            )

        author_name = (
            self._extract_author_name(h_index_data)
            or self._extract_author_name(so_year)
            or self._extract_author_name(so_total)
        )

        ds = h_index_data.get("dataSource") or {}
        metrics: Dict[str, Any] = {"hIndex": self._process_h_index(h_index_data)}

        if so_year and so_total:
            metrics["scholarlyOutput"] = self._process_scholarly_output(
                so_year, so_total
            )
        else:
            metrics["scholarlyOutput"] = {"byYear": {}, "total": "N/A"}

        if fwci_y and fwci_t:
            metrics["fwci"] = self._process_fwci(fwci_y, fwci_t)
        else:
            metrics["fwci"] = {"byYear": {}, "total": "N/A"}

        if top_j and top_j_t:
            metrics["topJournal"] = self._process_top_journal(top_j, top_j_t)
        else:
            metrics["topJournal"] = {"byYear": {}, "total": "N/A"}

        if cc_y and cc_t:
            metrics["citationCount"] = self._process_citations(cc_y, cc_t)
        else:
            metrics["citationCount"] = {"byYear": {}, "total": "N/A"}

        if cpp_y and cpp_t:
            metrics["citationsPerPublication"] = self._process_citations(cpp_y, cpp_t)
        else:
            metrics["citationsPerPublication"] = {"byYear": {}, "total": "N/A"}

        if collab:
            metrics["collaboration"] = self._process_collaboration(collab)
        else:
            metrics["collaboration"] = {"byYear": {}, "total": "N/A"}

        if acc:
            metrics["academicCorporateCollaboration"] = self._process_academic_corporate(
                acc
            )
        else:
            metrics["academicCorporateCollaboration"] = {
                "byYear": {},
                "total": "N/A",
            }

        return {
            "authorName": author_name,
            "dataSource": {
                **ds,
                "sourceName": ds.get("sourceName") or "SciVal",
                "lastUpdated": ds.get("lastUpdated")
                or datetime.utcnow().isoformat() + "Z",
                "metricStartYear": ds.get("metricStartYear") or 2020,
                "metricEndYear": ds.get("metricEndYear")
                or datetime.utcnow().year,
            },
            "metrics": metrics,
        }

    def get_author_metrics(
        self,
        author_id: str,
        custom_api_key: Optional[str] = None,
        year_range: str = "5yrs",
        available_metrics: Optional[List[Dict[str, Any]]] = None,
        included_docs: str = "AllPublicationTypes",
        include_self_citations: bool = True,
    ) -> Dict[str, Any]:
        aid = author_id.strip()
        try:
            url = supabase_proxy_url()
            # If proxy is not actually available, always use direct Elsevier (avoids deploy misconfig).
            if USE_DIRECT_API or not url:
                return self.get_direct_author_metrics(
                    aid,
                    custom_api_key,
                    year_range,
                    available_metrics,
                    included_docs,
                    include_self_citations,
                )
            data = self._make_supabase_request(
                url,
                "POST",
                {"action": "getAuthorMetrics", "authorId": aid},
                custom_api_key,
                year_range,
                available_metrics,
                included_docs,
            )
            if isinstance(data, dict) and data.get("error"):
                raise APIError(str(data["error"]))
            return data
        except APIError:
            raise
        except Exception as e:
            raise APIError(
                f"Error processing {aid}: {e}",
            ) from e

    def process_multiple_authors(
        self,
        author_ids: List[str],
        custom_api_key: Optional[str] = None,
        year_range: str = "5yrs",
        available_metrics: Optional[List[Dict[str, Any]]] = None,
        included_docs: str = "AllPublicationTypes",
        include_self_citations: bool = True,
    ) -> List[Dict[str, Any]]:
        ids = [i.strip() for i in author_ids if i.strip()]
        url = supabase_proxy_url()
        if USE_DIRECT_API or not url:
            out: List[Dict[str, Any]] = []
            for i, aid in enumerate(ids):
                try:
                    data = self.get_direct_author_metrics(
                        aid,
                        custom_api_key,
                        year_range,
                        available_metrics,
                        included_docs,
                        include_self_citations,
                    )
                    out.append({"id": aid, "data": data})
                except Exception as e:
                    out.append(
                        {
                            "id": aid,
                            "data": {
                                "error": str(e),
                                "metrics": _empty_metrics_payload(),
                            },
                        }
                    )
                if i < len(ids) - 1:
                    time.sleep(1.0)
            return out

        data = self._make_supabase_request(
            url,
            "POST",
            {"action": "processMultipleAuthors", "authorIds": ids},
            custom_api_key,
            year_range,
            available_metrics,
            included_docs,
        )
        return data


def _empty_metrics_payload() -> Dict[str, Any]:
    na = {"byYear": {}, "total": "N/A"}
    return {
        "hIndex": {"value": "N/A", "dataSource": {}},
        "scholarlyOutput": dict(na),
        "fwci": dict(na),
        "topJournal": dict(na),
        "citationCount": dict(na),
        "citationsPerPublication": dict(na),
        "collaboration": dict(na),
        "academicCorporateCollaboration": dict(na),
    }


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_scival_author_orcid_xml(body: str) -> tuple[str, str]:
    """Parse Elsevier SciVal author-by-ORCID XML (authorResponse / author / id, name).

    If multiple ``<author>`` nodes exist for one ORCID, the **first** in document
    order is used (same rule as the app: first Scopus Author ID wins).
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise APIError(f"Could not parse API response as XML: {e}") from e

    authors = root.findall(".//author")
    if not authors:
        raise APIError("Researcher ID not found in API response")

    author_el = authors[0]
    aid: Optional[str] = None
    name = "Unknown"
    for child in author_el:
        ln = _xml_local_name(child.tag)
        if ln == "id" and child.text:
            aid = child.text.strip()
        elif ln == "name" and child.text:
            name = child.text.strip()

    if not aid:
        raise APIError("Researcher ID not found in API response")
    return aid, name


def _parse_scival_author_orcid_json(data: Any) -> tuple[str, str]:
    """Use the first author entry when ``author`` is a list or ``authors`` is present."""
    if not isinstance(data, dict):
        raise APIError("Unexpected API response format.")
    raw = data.get("author")
    if raw is None:
        raw = data.get("authors")
    if isinstance(raw, list):
        if not raw:
            raise APIError("Researcher ID not found in API response")
        author = raw[0] if isinstance(raw[0], dict) else {}
    elif isinstance(raw, dict):
        author = raw
    else:
        author = {}
    aid = author.get("id")
    if aid is None:
        raise APIError("Researcher ID not found in API response")
    name = author.get("name") or "Unknown"
    return str(aid), str(name)


def _extract_orcid_from_input(raw: str) -> str:
    """Accept bare ORCID or pasted Elsevier/ORCID URLs; return normalized XXXX-XXXX-XXXX-XXXx."""
    s = raw.strip()
    if not s:
        return ""
    m = re.search(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", s, re.I)
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", s)
    if len(digits) == 16 and re.match(r"^\d{15}[\dX]$", digits, re.I):
        d = digits.upper()
        return f"{d[0:4]}-{d[4:8]}-{d[8:12]}-{d[12:16]}"
    return ""


def lookup_scopus_id_from_orcid(orcid: str, api_key: Optional[str] = None) -> tuple[str, str]:
    """Resolve Scopus Author ID and display name from ORCID via SciVal author-by-ORCID API.

    Requests XML (httpAccept=text/xml), parses author id and name from authorResponse.
    If the response is JSON, parses the author object instead.

    When the API returns multiple Scopus profiles for one ORCID, the **first**
    profile in the response is used.
    """
    key = (api_key or SCIVAL_API_KEY or "").strip()
    if not key:
        raise APIError(
            "SciVal API key required for ORCID lookup (set SCIVAL_API_KEY or ELSEVIER_API_KEY)."
        )

    extracted = _extract_orcid_from_input(orcid)
    cleaned = (extracted or orcid.strip()).replace(" ", "")
    digits = cleaned.replace("-", "")
    if len(digits) == 16 and re.match(r"^\d{15}[\dX]$", digits, re.I):
        formatted = (
            f"{digits[0:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:15]}{digits[15].upper()}"
        )
    elif re.match(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$", cleaned, re.I):
        formatted = cleaned
    else:
        raise APIError(
            "Please enter a valid ORCID (16-digit identifier), or paste an Elsevier/ORCID URL."
        )

    base = f"https://api.elsevier.com/analytics/scival/author/orcid/{formatted}"
    params: Dict[str, str] = {"httpAccept": "text/xml"}
    inst = (ELSEVIER_INSTTOKEN or "").strip()
    if inst:
        params["insttoken"] = inst

    headers = {
        "Accept": "application/xml, text/xml, application/json;q=0.9",
        "X-ELS-APIKey": key,
        "User-Agent": "SciVal-Research-Dashboard/1.0",
    }
    if inst:
        headers["X-ELS-Insttoken"] = inst

    client = httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0))
    try:
        r = client.get(base, params=params, headers=headers)
        if not r.is_success:
            if r.status_code == 404:
                raise APIError("No researcher found with this ORCID in SciVal database.")
            if r.status_code == 401:
                raise APIError("API authentication failed. Check API key.")
            if r.status_code == 403:
                raise APIError("API access denied. Check API key permissions.")
            raise APIError(f"API request failed with status {r.status_code}")

        text = (r.text or "").strip()
        ct = (r.headers.get("content-type") or "").lower()

        if "json" in ct or text.startswith("{"):
            try:
                data = r.json()
                return _parse_scival_author_orcid_json(data)
            except json.JSONDecodeError:
                pass

        return _parse_scival_author_orcid_xml(text)
    finally:
        client.close()


def resolve_author_ids_for_metrics(
    raw_ids: List[str],
    api_key: Optional[str] = None,
) -> List[str]:
    """Return Scopus Author IDs for the metrics API.

    Entries that look like ORCIDs (including pasted Elsevier URLs) are resolved
    via ``/analytics/scival/author/orcid/{orcid}``. Other values are returned
    unchanged (assumed to already be Scopus Author IDs).

    After resolution, **duplicate Scopus Author IDs are removed** (same person
    entered as both ORCID and numeric ID, or the same ID twice). Order is kept;
    the first occurrence wins.
    """
    out: List[str] = []
    for raw in raw_ids:
        s = raw.strip()
        if not s:
            continue
        if _extract_orcid_from_input(s):
            sid, _name = lookup_scopus_id_from_orcid(s, api_key)
            out.append(sid.strip())
        else:
            out.append(s.strip())

    seen: set[str] = set()
    deduped: List[str] = []
    for aid in out:
        if aid not in seen:
            seen.add(aid)
            deduped.append(aid)
    return deduped


def resolve_author_ids_for_metrics_safe(
    raw_ids: List[str],
    api_key: Optional[str] = None,
) -> tuple[List[str], List[str]]:
    """Resolve IDs without failing the whole batch.

    Returns ``(resolved_unique_ids, warnings)`` where warnings contains one
    line per skipped ORCID that could not be resolved.
    """
    out: List[str] = []
    warnings: List[str] = []
    for raw in raw_ids:
        s = raw.strip()
        if not s:
            continue
        if _extract_orcid_from_input(s):
            try:
                sid, _name = lookup_scopus_id_from_orcid(s, api_key)
                out.append(sid.strip())
            except APIError as e:
                warnings.append(f"{s}: {format_error_message_for_user(str(e))}")
        else:
            out.append(s)

    seen: set[str] = set()
    deduped: List[str] = []
    for aid in out:
        if aid not in seen:
            seen.add(aid)
            deduped.append(aid)
    return deduped, warnings


# Singleton-style service for Streamlit
_service: Optional[APIService] = None


def get_api_service() -> APIService:
    global _service
    if _service is None:
        _service = APIService()
    return _service
