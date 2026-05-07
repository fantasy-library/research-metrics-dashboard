"""
Research Impact Dashboard — Streamlit port of the React/Vite app.
Run from repository root:  streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_echarts5 import st_echarts
try:
    from streamlit_sortables import sort_items
except ImportError:  # pragma: no cover - dependency is installed from requirements.txt
    sort_items = None
from streamlit_app.api_service import (
    ACADEMIC_CORPORATE_SUBMETRIC_IDS,
    APIError,
    COLLABORATION_SUBMETRIC_IDS,
    format_error_message_for_user,
    get_api_service,
    is_missing_scival_api_key_error,
    is_scival_authentication_error,
    lookup_scopus_id_from_orcid,
    resolve_author_ids_for_metrics_safe,
)
from streamlit_app.config import SCIVAL_API_KEY, SCIVAL_HTTP_PROXY, USE_DIRECT_API
from streamlit_app.export_utils import export_docx_bytes, export_excel_bytes, export_pdf_bytes

st.set_page_config(
    page_title="Research Metrics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

HKUST_LOGO = "https://library.hkust.edu.hk/wp-content/themes/hkustlib/hkust_alignment/profiles/ust/modules/custom/hkust_signature_affiliate/assets/images/HKUST-logo.png"
LIB_LOGO = "https://library.hkust.edu.hk/wp-content/themes/hkustlib/hkust_alignment/core/assets/library/library_logo.png_transparent_bkgd_h300.png"

# Defer #analyze-metrics-anchor scroll until the node exists (avoids “wrong view then jump”).
_DEEP_LINK_ANALYZE_HTML = """
<script>
(function () {
  var HASH = "#analyze-metrics-anchor";
  function topWin() {
    var w = window;
    try {
      while (w.parent && w.parent !== w) w = w.parent;
    } catch (e) {}
    return w;
  }
  function wantScroll() {
    try {
      return (topWin().location.hash || "") === HASH;
    } catch (e) {
      return false;
    }
  }
  if (!wantScroll()) return;

  function byId(doc) {
    if (!doc) return null;
    try {
      return doc.getElementById("analyze-metrics-anchor");
    } catch (e) {
      return null;
    }
  }

  function findEl(doc, depth) {
    if (depth > 14) return null;
    var el = byId(doc);
    if (el) return el;
    try {
      var ifr = doc.querySelectorAll("iframe");
      for (var i = 0; i < ifr.length; i++) {
        try {
          var idoc = ifr[i].contentDocument;
          el = findEl(idoc, depth + 1);
          if (el) return el;
        } catch (e) {}
      }
    } catch (e) {}
    return null;
  }

  function scrollNow() {
    var tw = topWin();
    var el = byId(tw.document) || findEl(tw.document, 0);
    if (!el) return false;
    try {
      el.scrollIntoView({ block: "start", behavior: "auto" });
    } catch (e) {}
    return true;
  }

  if (scrollNow()) return;

  var tw = topWin();
  var root = null;
  try {
    root = tw.document.body;
  } catch (e) {}
  if (!root) return;

  var obs = new MutationObserver(function () {
    if (scrollNow()) obs.disconnect();
  });
  obs.observe(root, { childList: true, subtree: true });
  setTimeout(function () {
    try {
      obs.disconnect();
    } catch (e) {}
  }, 15000);
})();
</script>
"""

# Filter / shell icons — unified stroke (1.75), viewBox 24×24; sized via CSS badges below.
_FILTER_ICON_CALENDAR = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>'
)
_FILTER_ICON_DOCUMENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/><path d="M8 13h8M8 17h8M8 9h2"/></svg>'
)
_FILTER_ICON_FUNNEL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/></svg>'
)
_FILTER_ICON_PERSON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true" focusable="false">'
    '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
)
_FILTER_ICON_USERS = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true" focusable="false">'
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
    '<circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
    '<path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
)
_FILTER_ICON_METRICS_MENU = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true" focusable="false">'
    '<path d="m6 9 6 6 6-6"/></svg>'
)
# Year filter tooltip trigger — same badge family, compact size
_FILTER_ICON_INFO_SMALL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'
)
# Export workspace strip — “outputs” glyph (separate from analysis / charts)
_EXPORT_WORKSPACE_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'
)
_EXPORT_OPTIONS_ICON_PATH = Path(__file__).resolve().parent / "assets" / "export-options-icon.png"


def _export_options_heading_html(*, subtitle: str | None = None) -> str:
    """Export card title with icon; ``subtitle`` defaults to the multi-author bundle hint."""
    _sub = (
        subtitle
        if subtitle is not None
        else "Choose authors and metrics, then download PDF, Word, or Excel below."
    )
    _sub_esc = html.escape(_sub, quote=True)
    img_inner: str
    try:
        if _EXPORT_OPTIONS_ICON_PATH.is_file():
            b64 = base64.standard_b64encode(_EXPORT_OPTIONS_ICON_PATH.read_bytes()).decode(
                "ascii"
            )
            img_inner = (
                f'<img class="prepare-export-heading-icon-img" '
                f'src="data:image/png;base64,{b64}" width="48" height="48" alt="" />'
            )
        else:
            img_inner = (
                f'<span class="prepare-export-heading-icon-fallback">{_EXPORT_WORKSPACE_ICON}</span>'
            )
    except OSError:
        img_inner = (
            f'<span class="prepare-export-heading-icon-fallback">{_EXPORT_WORKSPACE_ICON}</span>'
        )
    return (
        '<div class="export-module-title-block">'
        '<div class="prepare-export-heading-row">'
        '<div class="prepare-export-heading-icon" aria-hidden="true">'
        f"{img_inner}</div>"
        '<p class="prepare-export-heading">Export Options</p>'
        "</div>"
        f'<p class="prepare-export-module-sub">{_sub_esc}</p>'
        "</div>"
    )


def _inject_export_download_styles() -> None:
    """Styled PDF / Word / Excel export row (file + download icons, data-URI SVGs)."""
    from urllib.parse import quote

    svg_pdf = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 1.4L18.6 9H14V3.4zM8 12.5h8v1.25H8v-1.25zm0 3h6v1.25H8v-1.25z"/>'
        "</svg>"
    )
    svg_doc = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 1.4L18.6 9H14V3.4zM8 11h8v1.15H8V11zm0 2.65h8v1.15H8v-1.15zm0 2.65h6v1.15H8v-1.15z"/>'
        "</svg>"
    )
    svg_xls = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"/>'
        '<path d="M14 2v6h6"/><path d="M8 11h8M8 14.5h8M8 18h5"/>'
        '<path d="m16.5 16 2.5 2.5m0-2.5L16.5 19"/>'
        "</svg>"
    )
    svg_dl = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 3v12"/><path d="m8 11 4 4 4-4"/><path d="M5 21h14"/>'
        "</svg>"
    )
    u_pdf, u_doc, u_xls, u_dl = (
        quote(svg_pdf, safe=""),
        quote(svg_doc, safe=""),
        quote(svg_xls, safe=""),
        quote(svg_dl, safe=""),
    )
    st.markdown(
        f"""
<style>
/* Compact export row: PDF + Word + Excel (scoped — do not match Step 1/2 columns) */
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] {{
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: wrap !important;
  align-items: center !important;
  gap: 0.35rem !important;
  column-gap: 0.35rem !important;
  justify-content: flex-start !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
  flex: 0 0 auto !important;
  flex-grow: 0 !important;
  width: auto !important;
  min-width: 0 !important;
  max-width: fit-content !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  margin: 0 !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] > div {{
  gap: 0 !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] .block-container {{
  padding-left: 0 !important;
  padding-right: 0 !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] [data-testid="stDownloadButton"],
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] .stDownloadButton {{
  width: auto !important;
  min-width: 0 !important;
}}

[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button,
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(1) .stDownloadButton > button,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(1) .stDownloadButton > button {{
  width: auto !important;
  min-height: 2.25rem !important;
  height: auto !important;
  padding: 0.4rem 0.7rem !important;
  border-radius: 10px !important;
  border: none !important;
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.35rem !important;
  font-weight: 700 !important;
  font-size: 0.8125rem !important;
  line-height: 1.2 !important;
  color: #ffffff !important;
  box-shadow: 0 2px 12px rgba(239, 68, 68, 0.32) !important;
  background: linear-gradient(145deg, #fca5a5 0%, #f87171 40%, #ef4444 100%) !important;
  text-shadow: 0 1px 0 rgba(15, 23, 42, 0.12) !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button:hover,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button:hover {{
  filter: brightness(1.05) saturate(1.05);
  box-shadow: 0 3px 16px rgba(239, 68, 68, 0.4) !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button::before,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button::before {{
  content: "" !important;
  display: block !important;
  width: 1.05rem !important;
  height: 1.05rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_pdf}") center / contain no-repeat !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button::after,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button::after {{
  content: "" !important;
  display: block !important;
  width: 0.9rem !important;
  height: 0.9rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_dl}") center / contain no-repeat !important;
}}

[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button,
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(2) .stDownloadButton > button,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(2) .stDownloadButton > button {{
  width: auto !important;
  min-height: 2.25rem !important;
  height: auto !important;
  padding: 0.4rem 0.7rem !important;
  border-radius: 10px !important;
  border: none !important;
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.35rem !important;
  font-weight: 700 !important;
  font-size: 0.8125rem !important;
  line-height: 1.2 !important;
  color: #ffffff !important;
  box-shadow: 0 2px 12px rgba(59, 130, 246, 0.35) !important;
  background: linear-gradient(145deg, #dbeafe 0%, #93c5fd 42%, #3b82f6 100%) !important;
  text-shadow: 0 1px 0 rgba(15, 23, 42, 0.12) !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button:hover,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button:hover {{
  filter: brightness(1.05) saturate(1.05);
  box-shadow: 0 3px 16px rgba(37, 99, 235, 0.4) !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button::before,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button::before {{
  content: "" !important;
  display: block !important;
  width: 1.05rem !important;
  height: 1.05rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_doc}") center / contain no-repeat !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button::after,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button::after {{
  content: "" !important;
  display: block !important;
  width: 0.9rem !important;
  height: 0.9rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_dl}") center / contain no-repeat !important;
}}

[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stDownloadButton"] button,
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(3) .stDownloadButton > button,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(3) [data-testid="stDownloadButton"] button,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(3) .stDownloadButton > button {{
  width: auto !important;
  min-height: 2.25rem !important;
  height: auto !important;
  padding: 0.4rem 0.7rem !important;
  border-radius: 10px !important;
  border: none !important;
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.35rem !important;
  font-weight: 700 !important;
  font-size: 0.8125rem !important;
  line-height: 1.2 !important;
  color: #ffffff !important;
  box-shadow: 0 2px 12px rgba(34, 197, 94, 0.28) !important;
  background: linear-gradient(145deg, #d1fae5 0%, #86efac 45%, #22c55e 100%) !important;
  text-shadow: 0 1px 0 rgba(15, 23, 42, 0.1) !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stDownloadButton"] button:hover,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(3) [data-testid="stDownloadButton"] button:hover {{
  filter: brightness(1.05) saturate(1.05);
  box-shadow: 0 3px 16px rgba(22, 163, 74, 0.36) !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stDownloadButton"] button::before,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(3) [data-testid="stDownloadButton"] button::before {{
  content: "" !important;
  display: block !important;
  width: 1.05rem !important;
  height: 1.05rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_xls}") center / contain no-repeat !important;
}}
[class*="st-key-export_download_row"] [data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stDownloadButton"] button::after,
[class*="st-key-export_download_row"] div[data-testid="column"]:nth-of-type(3) [data-testid="stDownloadButton"] button::after {{
  content: "" !important;
  display: block !important;
  width: 0.9rem !important;
  height: 0.9rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_dl}") center / contain no-repeat !important;
}}
[class*="st-key-export_download_row"] {{
  display: block !important;
  width: 100% !important;
  clear: both !important;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def _inject_theme_css() -> None:
    """Approximate the original Tailwind look (gradients, glass cards, typography)."""
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600;700&family=Source+Serif+4:wght@400;600;700&display=swap');

/* Design tokens — primary actions & focus ring (Streamlit overrides use these hues) */
:root {
  --rm-primary: #673ab7;
  --rm-primary-hover: #5e35b1;
  --rm-focus-ring: rgba(103, 58, 183, 0.22);
  --rm-radius-card: 12px;
  --rm-radius-input: 12px;
  --rm-radius-pill: 999px;
}

html, body, .stApp, [class*="stMarkdown"] {
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* App canvas — light gray so white cards read as elevated surfaces */
.stApp {
  background-color: #f8fafc !important; /* slate-50 */
  background-image: none !important;
  color: #0f172a !important;
}

.block-container {
  padding-top: 0.85rem !important;
  padding-bottom: 5rem !important;
  max-width: 1200px !important;
}
/* Let the page grow so the custom HTML footer is reachable below long forms */
section[data-testid="stMain"] {
  overflow-y: auto !important;
  padding-bottom: 2rem !important;
}
[data-testid="stAppViewContainer"] > .main {
  overflow: visible !important;
}

/*
 * Global bordered containers: white cards (exclude tinted filter panels).
 * Streamlit re-runs can change column DOM; do not rely only on span.config-card
 * inside columns — use span.skin-filter-panel on st.container(border=True) instead.
 */
div[data-testid="stVerticalBlockBorderWrapper"]:not([class*="st-key-filter_panel_blue"]):not([class*="st-key-filter_panel_mint"]):not([class*="st-key-filter_panel_peach"]) {
  background: #ffffff !important;
  color: #0f172a !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  border-radius: 12px !important;
  border: 1px solid #e2e8f0 !important;
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
  padding: 1.5rem !important;
  margin-bottom: 1.25rem !important;
}

/* Primary actions (test id varies by Streamlit version) */
button[data-testid="baseButton-primary"],
button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #3b82f6, #4f46e5) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 12px !important;
  font-weight: 600 !important;
  padding: 0.55rem 1.15rem !important;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.35) !important;
  transition: filter 0.15s ease, box-shadow 0.15s ease !important;
}
button[data-testid="baseButton-primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {
  filter: brightness(1.06);
  box-shadow: 0 6px 22px rgba(59, 130, 246, 0.42) !important;
}

/* Secondary / download */
.stDownloadButton button,
button[data-testid="baseButton-secondary"],
button[data-testid="stBaseButton-secondary"] {
  border-radius: 10px !important;
  font-weight: 600 !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(248,250,252,0.99)) !important;
  border-right: 1px solid rgba(226, 232, 240, 0.9) !important;
}
section[data-testid="stSidebar"] .block-container {
  padding-top: 1.5rem !important;
}

/* Expanders */
details[data-testid="stExpander"] {
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(226, 232, 240, 0.95) !important;
  border-radius: 14px !important;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06), 0 2px 6px rgba(99, 102, 241, 0.06);
}
details[data-testid="stExpander"] summary {
  font-weight: 600 !important;
  color: #1e293b !important;
}

/* Dataframe */
div[data-testid="stDataFrame"] {
  border-radius: 14px !important;
  overflow: hidden;
  border: 1px solid #e2e8f0 !important;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.07), 0 2px 8px rgba(99, 102, 241, 0.06);
}

/* Alerts / warnings closer to original amber strip */
div[data-testid="stAlert"] {
  border-radius: 12px !important;
}

#MainMenu { visibility: hidden; }

/* Hide Streamlit top bar (Deploy, toolbar) — stops it from clipping the custom header */
header[data-testid="stHeader"] {
  display: none !important;
  height: 0 !important;
  overflow: hidden !important;
}
[data-testid="stDecoration"] {
  display: none !important;
}
[data-testid="stToolbar"] {
  display: none !important;
}
[data-testid="stDeployButton"],
[data-testid="stToolbarActions"],
.stDeployButton,
button[kind="header"] {
  display: none !important;
}
/* Main column: remove extra top gap after header is gone */
section[data-testid="stMain"] > div {
  padding-top: 0.5rem !important;
}
[data-testid="stAppViewContainer"] {
  padding-top: 0 !important;
}
/* Hide bottom toolbar/chrome if present (can overlap last widgets) */
[data-testid="stBottom"],
[data-testid="stStatusWidget"],
footer[data-testid="stFooter"] {
  display: none !important;
}

/* Filter deck: white card wrapping the 3-column tinted filter panels */
[class*="st-key-filter_deck_shell"] {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 16px !important;
  padding: 1.5rem 1.4rem 1.5rem !important;
  padding-top: 20px !important;
  margin-bottom: 1.25rem !important;
  box-shadow:
    0 4px 6px -1px rgba(15, 23, 42, 0.06),
    0 12px 24px -4px rgba(15, 23, 42, 0.08) !important;
}
/* No rules / lines under Analysis scope / Filters intro */
[class*="st-key-filter_deck_shell"] .filters-row-intro,
[class*="st-key-filter_deck_shell"] .filters-row-kicker,
[class*="st-key-filter_deck_shell"] .filters-row-title,
[class*="st-key-filter_deck_shell"] .filters-row-sub {
  border: none !important;
  border-bottom: none !important;
  box-shadow: none !important;
}
[class*="st-key-filter_deck_shell"] hr {
  display: none !important;
}

/* Inline “Analyze Metrics” in search shell — full-width pill CTA */
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] .stButton {
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
}
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] .stButton > button {
  width: 100% !important;
}
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="stBaseButton-primary"],
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="baseButton-primary"] {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
  min-height: 3.85rem !important;
  height: auto !important;
  font-size: 1.2rem !important;
  border-radius: 999px !important;
  padding-left: 2rem !important;
  padding-right: 2rem !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  background: #fff5d6 !important;
  background-image: none !important;
  background-color: #fff5d6 !important;
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
  border: 1px solid rgba(0, 0, 0, 0.07) !important;
  box-shadow:
    0 4px 16px rgba(15, 23, 42, 0.07),
    0 1px 3px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.65) !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em !important;
  text-shadow: none !important;
  font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
  cursor: pointer !important;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.15s ease,
    -webkit-text-fill-color 0.2s ease !important;
}
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="stBaseButton-primary"] p,
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="baseButton-primary"] p,
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="stBaseButton-primary"] span,
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="baseButton-primary"] span {
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
}
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="stBaseButton-primary"]:hover,
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="baseButton-primary"]:hover {
  background: #673ab7 !important;
  background-image: none !important;
  background-color: #673ab7 !important;
  border-color: rgba(255, 255, 255, 0.22) !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
  box-shadow:
    0 6px 24px rgba(103, 58, 183, 0.45),
    0 0 0 3px rgba(103, 58, 183, 0.22),
    0 2px 8px rgba(15, 23, 42, 0.12) !important;
  transform: none !important;
}
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="stBaseButton-primary"]:active,
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="baseButton-primary"]:active {
  transform: translateY(1px) !important;
  box-shadow:
    0 3px 12px rgba(103, 58, 183, 0.35),
    0 1px 4px rgba(15, 23, 42, 0.1) !important;
}
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="stBaseButton-primary"]:focus-visible,
[class*="st-key-search_shell"] [class*="st-key-analyze_metrics_inline"] button[data-testid="baseButton-primary"]:focus-visible {
  outline: 2px solid #673ab7 !important;
  outline-offset: 3px !important;
}

/* Analyze Metrics — prominent loading (spinner + multi-author progress bar) */
[data-testid="stSpinner"] {
  padding: 1.05rem 1.35rem !important;
  margin: 0.65rem 0 !important;
  background: linear-gradient(180deg, #faf5ff 0%, #f3e8ff 42%, #ffffff 100%) !important;
  border: 2px solid #a78bfa !important;
  border-radius: 14px !important;
  box-shadow:
    0 14px 44px rgba(91, 33, 182, 0.15),
    0 4px 14px rgba(15, 23, 42, 0.07) !important;
}
[data-testid="stSpinner"] p,
[data-testid="stSpinner"] span,
[data-testid="stSpinner"] label {
  font-size: 1.14rem !important;
  font-weight: 700 !important;
  color: #4c1d95 !important;
  line-height: 1.35 !important;
}
.metrics-fetch-subhint {
  margin: 0.5rem 0 0 0 !important;
  padding: 0 !important;
  font-size: 1rem !important;
  font-weight: 600 !important;
  color: #5b21b6 !important;
  line-height: 1.45 !important;
}
[data-testid="stProgress"] {
  padding: 0.95rem 1.2rem !important;
  margin: 0.55rem 0 0.75rem 0 !important;
  background: linear-gradient(180deg, #faf5ff 0%, #f5f3ff 52%, #ffffff 100%) !important;
  border: 2px solid #c4b5fd !important;
  border-radius: 14px !important;
  box-shadow: 0 12px 36px rgba(91, 33, 182, 0.13) !important;
}
[data-testid="stProgress"] p,
[data-testid="stProgress"] [data-testid="stMarkdownContainer"] p {
  font-size: 1.06rem !important;
  font-weight: 700 !important;
  color: #4c1d95 !important;
  margin-bottom: 0.55rem !important;
}

/* Analyze Metrics — fullscreen loading popup (backdrop + card) */
[class*="st-key-metrics_fetch_loading_overlay"] {
  position: fixed !important;
  inset: 0 !important;
  z-index: 999990 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  background: rgba(15, 23, 42, 0.48) !important;
  backdrop-filter: blur(4px) !important;
  -webkit-backdrop-filter: blur(4px) !important;
  padding: 1.25rem !important;
  margin: 0 !important;
}
[class*="st-key-metrics_fetch_loading_inner"] {
  width: min(28rem, calc(100vw - 2.5rem)) !important;
  margin: 0 auto !important;
  padding: 1.35rem 1.6rem 1.5rem !important;
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 16px !important;
  box-shadow:
    0 25px 50px -12px rgba(15, 23, 42, 0.28),
    0 0 0 1px rgba(255, 255, 255, 0.06) inset !important;
}
[class*="st-key-metrics_fetch_loading_inner"] .metrics-fetch-loading-title {
  margin: 0 0 0.35rem 0 !important;
  font-size: 1.28rem !important;
  font-weight: 700 !important;
  color: #1e1b4b !important;
  letter-spacing: -0.02em !important;
}
[class*="st-key-metrics_fetch_loading_inner"] .metrics-fetch-loading-hint {
  margin: 0 0 1rem 0 !important;
  font-size: 0.95rem !important;
  font-weight: 600 !important;
  color: #64748b !important;
  line-height: 1.45 !important;
}
[class*="st-key-metrics_fetch_loading_inner"] .metrics-fetch-loading-detail {
  margin: 0 !important;
  padding: 0.65rem 0.85rem !important;
  font-size: 1.02rem !important;
  font-weight: 600 !important;
  color: #4338ca !important;
  line-height: 1.4 !important;
  background: linear-gradient(180deg, #f5f3ff 0%, #faf5ff 100%) !important;
  border: 1px solid #ddd6fe !important;
  border-radius: 10px !important;
}
[class*="st-key-metrics_fetch_loading_inner"] [data-testid="stProgress"] {
  margin-top: 0.85rem !important;
  padding: 0.35rem 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* Metric toggle cards: stronger “on” vs “off” affordance */
[class*="st-key-metric_card_"]:has(input:checked),
[class*="st-key-metric_card_"]:has(input:checked),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-dense_metric_"]:has(input:checked),
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-metric_cell_"]:has([data-baseweb="switch"][aria-checked="true"]) {
  border-color: #a78bfa !important;
  background: linear-gradient(165deg, #faf5ff 0%, #ffffff 55%) !important;
  box-shadow:
    0 2px 8px rgba(124, 58, 237, 0.12),
    0 8px 20px rgba(15, 23, 42, 0.06) !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)),
[class*="st-key-metric_card_"]:has(input:not(:checked)),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]),
[class*="st-key-dense_metric_"]:has(input:not(:checked)),
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="false"]),
[class*="st-key-metric_cell_"]:has([data-baseweb="switch"][aria-checked="false"]) {
  border-color: #e5e7eb !important;
  background: #fafafa !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)) label,
[class*="st-key-metric_card_"]:has(input:not(:checked)) label,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-metric_cell_"]:has([data-baseweb="switch"][aria-checked="false"]) label {
  color: #64748b !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)) p.metric-subtext,
[class*="st-key-metric_card_"]:has(input:not(:checked)) p.metric-subtext,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-metric_cell_"]:has([data-baseweb="switch"][aria-checked="false"]) p.metric-subtext {
  color: #94a3b8 !important;
}

/* --- Unified shell: single elevated white card on gray app background --- */
div[data-testid="stVerticalBlockBorderWrapper"]:has(span.skin-unified-form-shell),
div[data-testid="stVerticalBlock"]:has(span.skin-unified-form-shell) {
  background: #ffffff !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
  margin-bottom: 1.5rem !important;
}
.unified-section-divider {
  border: none;
  height: 1px;
  margin: 1.2rem 0 1.05rem;
  background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.5), transparent);
}
/*
 * Config cards: .config-card + .blue-header | .mint-header | .peach-header
 */
/* Filter cards: rounded, theme-tinted panels */
.filters-row-intro {
  margin: 0 0 0.75rem 0;
  padding: 0 0.15rem;
}
.filters-row-kicker {
  font-size: 0.68rem !important;
  font-weight: 800 !important;
  letter-spacing: 0.14em !important;
  text-transform: uppercase !important;
  color: #64748b !important;
  margin: 0 0 0.35rem 0 !important;
}
.filters-row-title {
  font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;
  font-size: 1.35rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.03em !important;
  color: #0f172a !important;
  margin: 0 0 0.35rem 0 !important;
  text-decoration: none !important;
  border-bottom: none !important;
  box-shadow: none !important;
}
.filters-row-sub {
  font-size: 0.9rem !important;
  color: #64748b !important;
  margin: 0 !important;
  line-height: 1.45 !important;
  max-width: 52rem;
}
.filter-panel-head {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin: 0 0 1.1rem 0;
  padding-bottom: 0;
  border-bottom: none !important;
}
.filter-panel-icon-wrap {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0;
  line-height: 0;
  background: #ffffff !important;
  border: 1px solid rgba(15, 23, 42, 0.1) !important;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06) !important;
}
.filter-panel-icon-wrap svg {
  display: block;
}
.filter-panel-head--blue .filter-panel-icon-wrap {
  color: #1d4ed8 !important;
}
.filter-panel-head--mint .filter-panel-icon-wrap {
  color: #0d9488 !important;
}
.filter-panel-head--peach .filter-panel-icon-wrap {
  color: #c2410c !important;
}
.filter-panel-kicker {
  font-size: 0.65rem !important;
  font-weight: 800 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  margin: 0 0 0.2rem 0 !important;
}
.filter-panel-head--blue .filter-panel-kicker { color: #2563eb !important; }
.filter-panel-head--mint .filter-panel-kicker { color: #0d9488 !important; }
.filter-panel-head--peach .filter-panel-kicker { color: #c2410c !important; }
.filter-panel-title {
  font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;
  font-size: 1.05rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em !important;
  color: #0f172a !important;
  margin: 0 0 0.25rem 0 !important;
  line-height: 1.25 !important;
}
.filter-panel-sub {
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  color: #475569 !important;
  margin: 0 !important;
  line-height: 1.4 !important;
}

/*
 * Tinted filter columns: marker lives on st.container(border=True) so the styled
 * node is always stVerticalBlockBorderWrapper — avoids column DOM / :has() races.
 */
[class*="st-key-filter_panel_blue"] {
  border-radius: 18px !important;
  margin: 0 6px 1rem 6px !important;
  padding: 1.25rem 1rem 1.35rem !important;
  box-shadow:
    0 4px 6px -1px rgba(15, 23, 42, 0.06),
    0 12px 24px -4px rgba(15, 23, 42, 0.08) !important;
  border: 1px solid #c9ddef !important;
  background: #f0f7ff !important;
}
[class*="st-key-filter_panel_mint"] {
  border-radius: 18px !important;
  margin: 0 6px 1rem 6px !important;
  padding: 1.25rem 1rem 1.35rem !important;
  box-shadow:
    0 4px 6px -1px rgba(15, 23, 42, 0.06),
    0 12px 24px -4px rgba(15, 23, 42, 0.08) !important;
  border: 1px solid #cde7d6 !important;
  background: #f2faf5 !important;
}
[class*="st-key-filter_panel_peach"] {
  border-radius: 18px !important;
  margin: 0 6px 1rem 6px !important;
  padding: 1.25rem 1rem 1.35rem !important;
  box-shadow:
    0 4px 6px -1px rgba(15, 23, 42, 0.06),
    0 12px 24px -4px rgba(15, 23, 42, 0.08) !important;
  border: 1px solid #e8dac1 !important;
  background: #fff9f0 !important;
}
[class*="st-key-filter_panel_blue"] [data-testid="stSelectbox"],
[class*="st-key-filter_panel_blue"] [data-testid="stMarkdownContainer"],
[class*="st-key-filter_panel_blue"] [data-testid="stVerticalBlock"],
[class*="st-key-filter_panel_mint"] [data-testid="stSelectbox"],
[class*="st-key-filter_panel_mint"] [data-testid="stMarkdownContainer"],
[class*="st-key-filter_panel_mint"] [data-testid="stVerticalBlock"],
[class*="st-key-filter_panel_peach"] [data-testid="stRadio"],
[class*="st-key-filter_panel_peach"] [data-testid="stMarkdownContainer"],
[class*="st-key-filter_panel_peach"] [data-testid="stVerticalBlock"] {
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
[class*="st-key-filter_panel_blue"] h3,
[class*="st-key-filter_panel_mint"] h3,
[class*="st-key-filter_panel_peach"] h3 {
  display: none !important;
}
/* Partition: extra air between Search / IDs and filter cards */
.search-to-filters-gap {
  margin-bottom: 30px !important;
  height: 0 !important;
  overflow: hidden !important;
}
.filter-row-wrap {
  margin: 0;
  padding-top: 0;
  padding-bottom: 0.2rem;
  font-size: 0;
  line-height: 0;
}
.analyze-hint {
  display: flex;
  justify-content: center;
  align-items: center;
  margin: 1rem 0 0.25rem 0;
  padding: 1.5rem;
  font-size: 0.9rem;
  font-weight: 500;
  color: #334155;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.08),
    0 2px 4px -1px rgba(0, 0, 0, 0.04);
}
.analyze-hint-inner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 24px;
  max-width: 100%;
  box-sizing: border-box;
}
.analyze-hint-text {
  flex: 0 1 auto;
  line-height: 1.45;
  margin: 0;
  text-align: center;
}
@media (min-width: 640px) {
  .analyze-hint-text {
    text-align: left;
  }
}
.analyze-hint a.analyze-hint-cta,
.analyze-hint .analyze-hint-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  align-self: center;
  gap: 0.55rem;
  padding: 10px 24px !important;
  background: #5c7cfa !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  font-size: 0.9rem !important;
  border-radius: 8px !important;
  border: 1px solid #5c7cfa !important;
  text-decoration: none !important;
  box-shadow: 0 6px 18px rgba(92, 124, 250, 0.22) !important;
}
.analyze-hint a.analyze-hint-cta:hover,
.analyze-hint .analyze-hint-cta:hover {
  text-decoration: none !important;
  background: #4263eb !important;
  border-color: #4263eb !important;
  box-shadow: 0 10px 24px rgba(66, 99, 235, 0.24) !important;
}
.metrics-subhead {
  font-size: 0.85rem;
  font-weight: 800;
  color: #1e1b4b;
  margin: 1.6rem 0 1.05rem 0;
  padding: 0.5rem 0.75rem;
  background: #ffffff;
  border-radius: 10px;
  border-left: 4px solid #7c3aed;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06);
}
.metrics-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin: 0.5rem 0 1rem 0;
  font-size: 0.88rem;
  color: #6b21a8;
  font-weight: 600;
}
.metrics-count-bar {
  display: inline-flex;
  align-items: center;
  padding: 0.32rem 0.72rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  font-weight: 500;
  font-size: 0.78rem;
  color: #64748b;
  letter-spacing: 0.01em;
  box-shadow: none;
}

/* —— Search configuration (shell + widgets: final shell tokens live in “Stable key-based” block) —— */
.search-config-title {
  margin: 0 0 0.65rem 0 !important;
  font-family: 'Inter', 'Segoe UI', sans-serif !important;
  font-size: 1.1rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.015em !important;
  color: #111827 !important;
  line-height: 1.35 !important;
}
[class*="st-key-find_scopus_help_panel"] {
  margin: 0 0 1rem 0 !important;
  padding: 1rem 1.05rem !important;
  border-radius: 14px !important;
  border: 1px solid #bbf7d0 !important;
  background: linear-gradient(180deg, #f0fdf4 0%, #ecfdf5 55%, #f8fafc 100%) !important;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06) !important;
}
[class*="st-key-find_scopus_help_panel"] .find-scopus-banner {
  display: flex !important;
  align-items: center !important;
  gap: 0.45rem !important;
  margin: 0 0 0.85rem 0 !important;
  font-size: 1.05rem !important;
  font-weight: 800 !important;
  color: #14532d !important;
  letter-spacing: -0.02em !important;
}
[class*="st-key-find_scopus_help_panel"] .find-scopus-banner-badge {
  flex-shrink: 0 !important;
}
.minimal-filter-label {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin: 0 0 0.48rem 0 !important;
  font-size: 0.95rem !important;
  font-weight: 700 !important;
  color: #374151 !important;
  letter-spacing: 0.01em;
}
[class*="st-key-search_shell"] .minimal-filter-label {
  overflow: visible !important;
  position: relative;
  z-index: 2;
}
.year-filter-label-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.year-filter-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  outline: none;
}
.year-filter-tip-marker.minimal-filter-icon-badge {
  cursor: help !important;
}
.year-filter-tip-marker svg {
  display: block;
  width: 100%;
  height: 100%;
  flex-shrink: 0;
}
.year-filter-tip:hover .year-filter-tip-marker,
.year-filter-tip:focus .year-filter-tip-marker,
.year-filter-tip:focus-within .year-filter-tip-marker {
  border-color: #93c5fd !important;
  box-shadow:
    0 4px 14px rgba(37, 99, 235, 0.14),
    0 1px 3px rgba(15, 23, 42, 0.06) !important;
}
.year-filter-tip-popup {
  position: absolute;
  left: 0;
  top: calc(100% + 6px);
  z-index: 100;
  width: min(18.5rem, 78vw);
  padding: 0.55rem 0.65rem;
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1.5;
  color: #1f2937;
  text-align: left;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 0.15s ease, visibility 0.15s ease;
}
.year-filter-tip:hover .year-filter-tip-popup,
.year-filter-tip:focus .year-filter-tip-popup,
.year-filter-tip:focus-within .year-filter-tip-popup {
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}
/* Circular badge: white disc, soft shadow — shared by filters, Find Scopus, metrics heading */
.minimal-filter-icon-badge {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 2.5rem !important;
  height: 2.5rem !important;
  border-radius: 50% !important;
  background: #ffffff !important;
  border: 1px solid #e8ecf1 !important;
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.09),
    0 1px 3px rgba(15, 23, 42, 0.06) !important;
  flex-shrink: 0 !important;
  line-height: 0 !important;
  box-sizing: border-box !important;
}
.minimal-filter-icon-badge--compact {
  width: 1.75rem !important;
  height: 1.75rem !important;
  border-radius: 50% !important;
  box-shadow:
    0 3px 10px rgba(15, 23, 42, 0.08),
    0 1px 2px rgba(15, 23, 42, 0.05) !important;
}
.minimal-filter-icon-badge svg {
  width: 1.2rem !important;
  height: 1.2rem !important;
  flex-shrink: 0 !important;
}
.minimal-filter-icon-badge--compact svg {
  width: 0.88rem !important;
  height: 0.88rem !important;
}
.minimal-filter-icon-badge--calendar svg {
  color: #2563eb !important;
}
.minimal-filter-icon-badge--document svg {
  color: #0f766e !important;
}
.minimal-filter-icon-badge--funnel svg {
  color: #9c4221 !important;
}
.minimal-filter-icon-badge--person svg {
  color: #15803d !important;
}
.minimal-filter-icon-badge--users svg {
  color: #2563eb !important;
}
.minimal-filter-icon-badge--metrics svg {
  color: #6d28d9 !important;
}
.minimal-filter-icon-badge--info svg {
  color: #2563eb !important;
}
[class*="st-key-search_shell"] [data-testid="stSelectbox"] {
  margin-top: 0.05rem !important;
  margin-bottom: 0.22rem !important;
}
[class*="st-key-search_shell"] [data-baseweb="select"] > div {
  border: 1px solid #e2e8f0 !important;
  border-radius: 12px !important;
  background: #ffffff !important;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06) !important;
  min-height: 42px !important;
}
[class*="st-key-search_shell"] [data-testid="stTextArea"] {
  margin-top: 0.25rem !important;
}
[class*="st-key-search_shell"] [data-testid="stTextArea"] label p {
  margin-bottom: 0.3rem !important;
  font-size: 0.875rem !important;
  font-weight: 500 !important;
  color: #4B5563 !important;
}
[class*="st-key-search_shell"] textarea::placeholder {
  color: #9CA3AF !important;
  opacity: 1 !important;
  -webkit-text-fill-color: #9CA3AF !important;
}
[class*="st-key-search_shell"] .author-limit-hint {
  display: flex;
  align-items: center;
  gap: 0.52rem;
  margin: 0.35rem 0 0.1rem 0;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  font-size: 0.84rem;
  line-height: 1.35;
  overflow: visible;
}
[class*="st-key-search_shell"] .author-limit-hint--ok {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1e3a8a;
}
[class*="st-key-search_shell"] .author-limit-hint--warn {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  color: #9a3412;
}
[class*="st-key-search_shell"] .author-limit-icon.minimal-filter-icon-badge {
  align-self: center !important;
  margin-top: 0 !important;
  flex-shrink: 0 !important;
}
[class*="st-key-search_shell"] .author-limit-count {
  font-weight: 700;
  margin-left: 0.25rem;
}
[class*="st-key-search_shell"] .author-input-header-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.45rem 0.85rem;
  margin: 0 0 0.25rem 0;
}
[class*="st-key-search_shell"] .author-input-header-title {
  font-size: 0.875rem;
  font-weight: 500;
  color: #4b5563;
  flex: 0 0 auto;
}
[class*="st-key-search_shell"] .author-limit-hint-inline {
  margin: 0 !important;
  flex: 1 1 220px;
  min-width: min(100%, 14rem);
  align-items: center !important;
  padding: 0.52rem 0.65rem !important;
  font-size: 0.8rem !important;
  line-height: 1.4 !important;
  overflow: visible !important;
}
[class*="st-key-search_shell"]
  [data-testid="stMarkdownContainer"]:has(.author-limit-hint-inline) {
  overflow: visible !important;
}
/* Find Scopus toggle: light-green pill; icon + label centered (avoid svg clip) */
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="stBaseButton-secondary"],
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="baseButton-secondary"] {
  gap: 0.55rem !important;
  column-gap: 0.55rem !important;
  background: #ecfdf5 !important;
  background-image: none !important;
  border: 1px solid #a7f3d0 !important;
  color: #14532d !important;
  min-height: 2.65rem !important;
  padding-top: 0.42rem !important;
  padding-bottom: 0.42rem !important;
  padding-left: 0.65rem !important;
  padding-right: 0.65rem !important;
  overflow: visible !important;
  align-items: center !important;
  justify-content: center !important;
  box-shadow: 0 1px 2px rgba(20, 83, 45, 0.06) !important;
}
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="stBaseButton-secondary"]:hover,
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="baseButton-secondary"]:hover {
  background: #d1fae5 !important;
  border-color: #6ee7b7 !important;
  color: #052e16 !important;
}
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="stBaseButton-secondary"]:focus-visible,
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="baseButton-secondary"]:focus-visible {
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.32) !important;
}
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="stBaseButton-secondary"] > div,
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="baseButton-secondary"] > div {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.55rem !important;
  line-height: 1 !important;
  overflow: visible !important;
}
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="stBaseButton-secondary"] p,
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="baseButton-secondary"] p {
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
  line-height: 1.28 !important;
  margin: 0 !important;
  padding-top: 0.06rem !important;
  white-space: nowrap !important;
}
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="stBaseButton-secondary"] svg,
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] button[data-testid="baseButton-secondary"] svg {
  flex-shrink: 0 !important;
  width: 1.38rem !important;
  height: 1.38rem !important;
  min-width: 1.38rem !important;
  min-height: 1.38rem !important;
  color: #15803d !important;
  -webkit-text-fill-color: #15803d !important;
  overflow: visible !important;
  display: block !important;
  vertical-align: middle !important;
}
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] [data-testid="element-container"],
[class*="st-key-search_shell"] [class*="st-key-toggle_find_scopus_panel"] .stButton {
  overflow: visible !important;
}
.minimal-section-divider {
  border-top: 1px solid #E5E7EB;
  margin: 0.28rem 0 0.5rem 0;
}
/* Self-citation: hug content (avoid stretching across the whole column) */
[class*="st-key-search_shell"] [data-testid="stRadio"] {
  width: fit-content !important;
  max-width: 100% !important;
}
[class*="st-key-search_shell"] [data-testid="stRadio"] [role="radiogroup"] {
  display: inline-flex !important;
  align-items: center !important;
  width: fit-content !important;
  border: 1px solid #e5e7eb !important;
  border-radius: 8px !important;
  background: #f3f4f6 !important;
  padding: 3px !important;
  gap: 3px !important;
  margin-top: 0.05rem !important;
}
[class*="st-key-search_shell"] [data-testid="stRadio"] label {
  margin: 0 !important;
  flex: 0 0 auto !important;
  border-radius: 6px !important;
  border: 1px solid transparent !important;
  padding: 0.22rem 0.55rem !important;
  color: #374151 !important;
  background: transparent !important;
  font-weight: 600 !important;
  gap: 0.35rem !important;
}
[class*="st-key-search_shell"] [data-testid="stRadio"] label p {
  font-size: 0.9rem !important;
  font-weight: 600 !important;
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
  margin: 0 !important;
  line-height: 1.25 !important;
}
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked),
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] {
  background: transparent !important;
  border-color: transparent !important;
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
  box-shadow: none !important;
}
/* Nested Streamlit text — neutral (no purple chip) */
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked) p,
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked) span,
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] p,
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] span {
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
}
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked) div,
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] div {
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
}
[class*="st-key-search_shell"] .stRadio input[type="radio"] {
  width: 1.05rem !important;
  height: 1.05rem !important;
  flex-shrink: 0;
}
[class*="st-key-search_shell"] .stRadio input {
  accent-color: #673ab7 !important;
}
.minimal-go-analyze-wrap {
  display: flex;
  justify-content: center;
  margin-top: 0.55rem;
}
a.minimal-go-analyze-btn,
.minimal-go-analyze-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: min(250px, 100%);
  max-width: 28rem;
  padding: 0.56rem 1.35rem !important;
  border-radius: 999px !important;
  border: 1px solid rgba(0, 0, 0, 0.07) !important;
  background: #fff5d6 !important;
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
  text-decoration: none !important;
  font-size: 0.98rem !important;
  font-weight: 600 !important;
  font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
  box-shadow:
    0 4px 16px rgba(15, 23, 42, 0.07),
    0 1px 3px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.65) !important;
  cursor: pointer !important;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    -webkit-text-fill-color 0.2s ease !important;
}
a.minimal-go-analyze-btn:hover,
.minimal-go-analyze-btn:hover {
  background: #673ab7 !important;
  border-color: rgba(255, 255, 255, 0.22) !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
  text-decoration: none !important;
  box-shadow:
    0 6px 20px rgba(103, 58, 183, 0.35),
    0 2px 6px rgba(15, 23, 42, 0.1) !important;
}
a.minimal-go-analyze-btn:focus-visible,
.minimal-go-analyze-btn:focus-visible {
  outline: 2px solid #673ab7 !important;
  outline-offset: 3px !important;
}

/* Compare — trends & bubble: narrow control column, chart uses remaining width */
:is([class*="st-key-compare_trends_row"], [class*="st-key-compare_bubble_row"]) [data-testid="stHorizontalBlock"] {
  align-items: flex-start !important;
  gap: 0.5rem !important;
}
:is([class*="st-key-compare_trends_row"], [class*="st-key-compare_bubble_row"]) [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child {
  flex: 0 0 clamp(168px, 22vw, 240px) !important;
  max-width: 260px !important;
}
:is([class*="st-key-compare_trends_row"], [class*="st-key-compare_bubble_row"]) .compare-filter-mini {
  margin: 0 0 0.2rem 0 !important;
  font-size: 0.78rem !important;
  font-weight: 600 !important;
  color: #64748b !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
:is([class*="st-key-compare_trends_row"], [class*="st-key-compare_bubble_row"]) [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-baseweb="select"] > div {
  min-height: 40px !important;
}
:is([class*="st-key-compare_trends_row"], [class*="st-key-compare_bubble_row"]) [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stRadio"] {
  margin-top: 0.15rem !important;
}
:is([class*="st-key-compare_trends_row"], [class*="st-key-compare_bubble_row"]) [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stRadio"] label p {
  font-size: 0.85rem !important;
}

/* Export bundle: one checkbox per scholar, full names wrap on one logical line each */
[class*="st-key-export_scholar_shell"] [data-testid="stCheckbox"] {
  margin-bottom: 0.35rem !important;
}
[class*="st-key-export_scholar_shell"] [data-testid="stCheckbox"] label {
  white-space: normal !important;
  word-break: break-word !important;
  max-width: 100% !important;
}
[class*="st-key-export_scholar_shell"] [data-testid="stCheckbox"] label p {
  font-size: 0.92rem !important;
  line-height: 1.35 !important;
}

/* Metrics container: white card + purple accent rail (calmer than full tint) */
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) {
  background: #ffffff !important;
  border: 1px solid rgba(226, 232, 240, 0.95) !important;
  border-left: 4px solid #7c3aed !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
  margin: 0.5rem 0 0.55rem 0 !important;
  box-shadow:
    0 4px 8px rgba(15, 23, 42, 0.05),
    0 12px 28px rgba(15, 23, 42, 0.06) !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) .metrics-grid-hint {
  display: block;
  padding: 0.7rem 1rem !important;
  margin-bottom: 1rem !important;
  background: rgba(255, 255, 255, 0.85) !important;
  border-radius: 12px !important;
  border-left: 4px solid #7c3aed !important;
  font-weight: 600 !important;
  color: #4c1d95 !important;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06) !important;
}
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) p.section-kicker {
  color: #7c3aed !important;
  letter-spacing: 0.11em !important;
  font-weight: 800 !important;
}
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) p.section-title {
  font-size: 1.15rem !important;
  font-weight: 800 !important;
  color: #4c1d95 !important;
  letter-spacing: -0.02em !important;
}
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) h3 {
  color: #1e1b4b !important;
  font-weight: 800 !important;
  font-size: 0.95rem !important;
  margin: 0.15rem 0 0.35rem 0 !important;
  letter-spacing: -0.02em !important;
}
/* Outline toolbar actions (do not compete with Analyze) */
 [class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell))
  button[data-testid="baseButton-secondary"],
 [class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell))
  button[data-testid="stBaseButton-secondary"] {
  background: transparent !important;
  background-image: none !important;
  color: #6d28d9 !important;
  border: 2px solid #9333ea !important;
  box-shadow: none !important;
  font-weight: 600 !important;
}
 [class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell))
  button[data-testid="baseButton-secondary"]:hover,
 [class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell))
  button[data-testid="stBaseButton-secondary"]:hover {
  background: rgba(147, 51, 234, 0.08) !important;
  border-color: #7c3aed !important;
}
/* Collaboration metrics group shell (legacy; grid no longer uses it) */
[class*="st-key-collab_metrics_shell"] {
  background: transparent !important;
}
/* Legacy metric_card / dense_metric (unused by current grid; keep for :has() joint rules above) */
[class*="st-key-metric_card_"] label {
  display: flex !important;
  align-items: flex-start !important;
  gap: 0.5rem !important;
  padding: 0.15rem 0 0.25rem 0 !important;
  margin-bottom: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  font-weight: 600 !important;
  color: #0f172a !important;
}
[class*="st-key-metric_card_"] label p {
  line-height: 1.35 !important;
  min-height: 2.7em !important;
  margin-top: 0.05rem !important;
}
/* Minimal metrics grid: 3 columns per row (Select Metrics) */
[class*="st-key-metrics_toolbar_shell"] {
  /* Space below heading row so button chrome/icons clear any divider / tight baseline */
  margin-top: 0.45rem !important;
  padding-top: 0.2rem !important;
  margin-bottom: 0.5rem !important;
  padding-bottom: 0 !important;
}
/* Select All / Clear All: breathing room between Material icon and label */
[class*="st-key-metrics_toolbar_shell"] button[data-testid="stBaseButton-secondary"],
[class*="st-key-metrics_toolbar_shell"] button[data-testid="baseButton-secondary"] {
  gap: 0.65rem !important;
  column-gap: 0.65rem !important;
}
[class*="st-key-metrics_toolbar_shell"] button[data-testid="stBaseButton-secondary"] > div,
[class*="st-key-metrics_toolbar_shell"] button[data-testid="baseButton-secondary"] > div {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.65rem !important;
}
[class*="st-key-metrics_toolbar_shell"] button[data-testid="stBaseButton-secondary"] svg,
[class*="st-key-metrics_toolbar_shell"] button[data-testid="baseButton-secondary"] svg {
  flex-shrink: 0 !important;
  margin-inline-end: 0.25rem !important;
}
[class*="st-key-metrics_grid_shell"] {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
/* Metric category accordions: bold headers; allow (i) tooltips to escape expander clip */
[class*="st-key-metrics_grid_shell"] details[data-testid="stExpander"] {
  margin-bottom: 0.65rem !important;
  overflow: visible !important;
}
[class*="st-key-metrics_grid_shell"] details[data-testid="stExpander"]:last-child {
  margin-bottom: 0 !important;
}
[class*="st-key-metrics_grid_shell"] details[data-testid="stExpander"] summary {
  font-weight: 700 !important;
  font-size: 1.02rem !important;
  color: #1e1b4b !important;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%) !important;
  border-radius: 8px !important;
  display: flex !important;
  align-items: center !important;
  gap: 0.45rem !important;
}
/* Unified glyph box for :material/analytics: and :material/hub: */
[class*="st-key-metrics_grid_shell"] details[data-testid="stExpander"] summary svg {
  width: 1.125rem !important;
  height: 1.125rem !important;
  min-width: 1.125rem !important;
  min-height: 1.125rem !important;
  flex-shrink: 0 !important;
  display: block !important;
}
[class*="st-key-metrics_grid_shell"] details[data-testid="stExpander"] summary img {
  width: 1.125rem !important;
  height: 1.125rem !important;
  min-width: 1.125rem !important;
  min-height: 1.125rem !important;
  flex-shrink: 0 !important;
  object-fit: contain !important;
}
/* Metrics (Default) panel — slightly larger analytics glyph */
[class*="st-key-metrics_grid_shell"]
  details[data-testid="stExpander"]:first-of-type
  summary
  svg,
[class*="st-key-metrics_grid_shell"]
  details[data-testid="stExpander"]:first-of-type
  summary
  img {
  width: 1.38rem !important;
  height: 1.38rem !important;
  min-width: 1.38rem !important;
  min-height: 1.38rem !important;
}
/* Hub glyph reads slightly larger than analytics — nudge Collaboration only */
[class*="st-key-metrics_grid_shell"]
  details[data-testid="stExpander"]:last-of-type
  summary
  svg,
[class*="st-key-metrics_grid_shell"]
  details[data-testid="stExpander"]:last-of-type
  summary
  img {
  width: 1rem !important;
  height: 1rem !important;
  min-width: 1rem !important;
  min-height: 1rem !important;
}
[class*="st-key-metrics_grid_row"] {
  margin-bottom: 0.75rem !important;
}
[class*="st-key-metrics_grid_shell"] [class*="st-key-metrics_grid_row"]:last-child {
  margin-bottom: 0 !important;
}
[class*="st-key-metrics_grid_shell"] [data-testid="stHorizontalBlock"] {
  gap: 0.75rem !important;
  align-items: stretch !important;
}
[class*="st-key-metrics_grid_shell"] [data-testid="column"] {
  display: flex !important;
  flex-direction: column !important;
}
[class*="st-key-metrics_grid_shell"] [data-testid="column"] > div {
  flex: 1 1 auto !important;
  height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: visible !important;
}
[class*="st-key-metric_cell_"] {
  border: 1px solid #e5e7eb !important;
  border-radius: 0.5rem !important;
  padding: 0.32rem 0.5rem !important;
  margin: 0 !important;
  min-height: 4.6rem !important;
  height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  box-sizing: border-box !important;
  background: #ffffff !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05) !important;
  overflow: visible !important;
  container-type: inline-size !important;
  container-name: metric-cell !important;
}
[class*="st-key-metric_cell_"] > div[data-testid="stVerticalBlock"] {
  gap: 0 !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] {
  gap: 0.35rem !important;
  align-items: stretch !important;
  flex: 1 1 auto !important;
  margin-bottom: 0 !important;
  min-height: 2.85rem !important;
  overflow: visible !important;
}
/* Toggle column first (left), title + (i) second — matches reference metric cards */
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child {
  flex: 0 0 auto !important;
  width: auto !important;
  display: flex !important;
  align-items: flex-start !important;
  justify-content: flex-start !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child [data-testid="stVerticalBlock"] {
  align-items: flex-start !important;
  display: flex !important;
  justify-content: flex-start !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child {
  flex: 1 1 auto !important;
  min-width: 0 !important;
  display: flex !important;
  align-items: flex-start !important;
  overflow: visible !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child [data-testid="stVerticalBlock"] {
  align-items: flex-start !important;
  display: flex !important;
  justify-content: flex-start !important;
}
[class*="st-key-metric_cell_"] h3 {
  display: none !important;
}
[class*="st-key-metric_cell_"] label {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 0 !important;
}
[class*="st-key-metric_cell_"] [data-baseweb="switch"] {
  margin: 0 !important;
  transform: scale(0.86);
  transform-origin: top left !important;
}
p.metric-compact-title {
  margin: 0 !important;
  padding: 0 !important;
  font-size: 0.875rem !important;
  font-weight: 600 !important;
  color: #1f2937 !important;
  line-height: 1.25 !important;
  min-height: 2.5em !important;
  display: block !important;
}
[class*="st-key-metric_cell_"] p.metric-compact-title--with-info {
  max-width: 100% !important;
  overflow: visible !important;
}
[class*="st-key-metric_cell_"] p.metric-compact-title--with-info .metric-title-text {
  word-break: break-word !important;
}
[class*="st-key-metric_cell_"] p.metric-compact-title--with-info .metric-info-wrap {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  vertical-align: 0.12em !important;
  margin-left: 0.35rem !important;
  position: relative !important;
  outline: none !important;
}
[class*="st-key-metric_cell_"] .metric-info-icon {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 1.05rem !important;
  height: 1.05rem !important;
  border-radius: 50% !important;
  border: 1.5px solid #64748b !important;
  color: #475569 !important;
  font-size: 0.58rem !important;
  font-weight: 800 !important;
  font-family: Georgia, "Times New Roman", serif !important;
  font-style: italic !important;
  line-height: 1 !important;
  cursor: help !important;
  user-select: none !important;
  background: #f8fafc !important;
}
[class*="st-key-metric_cell_"] .metric-info-wrap:hover .metric-info-icon,
[class*="st-key-metric_cell_"] .metric-info-wrap:focus-within .metric-info-icon {
  border-color: #4338ca !important;
  color: #3730a3 !important;
  background: #eef2ff !important;
}
/* Global: tooltip text must stay hidden even if markup sits outside the keyed cell. */
.metric-info-panel {
  display: none !important;
  position: absolute !important;
  z-index: 9999 !important;
  /* Default: anchor to left of (i), grow right (works for columns 1–2). */
  left: 0 !important;
  right: auto !important;
  top: calc(100% + 6px) !important;
  width: min(22rem, calc(100vw - 1.25rem)) !important;
  max-width: min(22rem, calc(100vw - 1.25rem), 100cqw) !important;
  box-sizing: border-box !important;
  max-height: min(88vh, 28rem) !important;
  overflow-y: auto !important;
  overscroll-behavior: contain !important;
  padding: 0.65rem 0.75rem !important;
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 10px !important;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.18) !important;
  text-align: left !important;
}
/* Columns 2–3: (i) toward outer edge — anchor panel to right of (i) (avoids horizontal clip). */
[class*="st-key-metrics_grid_shell"] [class*="st-key-metrics_grid_row"] [data-testid="column"]:nth-child(2) .metric-info-panel,
[class*="st-key-metrics_grid_shell"] [class*="st-key-metrics_grid_row"] [data-testid="column"]:nth-child(3) .metric-info-panel {
  left: auto !important;
  right: 0 !important;
}
.metric-info-wrap:hover .metric-info-panel,
.metric-info-wrap:focus-within .metric-info-panel {
  display: block !important;
}
.metric-info-panel-inner {
  font-size: 0.78rem !important;
  font-weight: 400 !important;
  line-height: 1.45 !important;
  color: #334155 !important;
  white-space: pre-wrap !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
  scrollbar-width: thin !important;
  scrollbar-color: #cbd5e1 #f8fafc !important;
}
[class*="st-key-metric_cell_"]:has([role="switch"][aria-checked="true"]) {
  box-shadow: 0 1px 4px rgba(124, 58, 237, 0.12) !important;
}
p.metric-subtext {
  color: #4b5563 !important;
  font-size: 0.85rem !important;
  margin-top: 4px !important;
  margin-bottom: 16px !important;
  padding: 0 !important;
  line-height: 1.5 !important;
}
/* Anchor for “Go to Analyze” link — zero layout height, keeps scroll target */
#analyze-metrics-anchor.analyze-anchor-tight {
  scroll-margin-top: 1rem;
  display: block;
  height: 0;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden;
  pointer-events: none;
}
[data-testid="element-container"]:has(#analyze-metrics-anchor) {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
[data-testid="element-container"]:has(#analyze-metrics-anchor) [data-testid="stMarkdownContainer"] {
  margin-bottom: 0 !important;
}
[data-testid="element-container"]:has(#analyze-metrics-anchor) [data-testid="stMarkdownContainer"] p {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 0 !important;
}
/* Anchor for “Download all” jump (PDF / Excel at end of results) */
#export-downloads-anchor {
  scroll-margin-top: 1rem;
}
/* Toggle / switch accent (metrics panel only) */
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) [data-baseweb="switch"] {
  color: #7c3aed !important;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12) !important;
}
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) [data-baseweb="switch"] input {
  accent-color: #7c3aed !important;
}

/* Fallback: broader scope so accent can't miss due to DOM structure */
[class*="st-key-metrics_panel_shell"] [data-baseweb="switch"] {
  color: #7c3aed !important;
}
[class*="st-key-metrics_panel_shell"] [data-baseweb="switch"] input {
  accent-color: #7c3aed !important;
}
.stRadio input {
  accent-color: #2563eb !important;
}

/* Custom header block (HTML below) */
.dash-top-header {
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(226, 232, 240, 0.85);
  border-radius: 20px;
  padding: 1.2rem 1.45rem 1.25rem;
  margin-top: 0.25rem;
  margin-bottom: 1.5rem;
  box-shadow:
    0 4px 8px rgba(15, 23, 42, 0.04),
    0 14px 32px rgba(99, 102, 241, 0.1),
    0 24px 48px rgba(15, 23, 42, 0.07);
}
.dash-top-inner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem 1.25rem;
}
.dash-logos {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}
.dash-logos a img { height: 48px; width: auto; display: block; }
.dash-logo-rule { width: 1px; height: 44px; background: #cbd5e1; }
.dash-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem 0.5rem;
  flex: 1;
  min-width: 220px;
}
.dash-icon-badge {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b82f6, #4f46e5);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 1.2rem;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
}
.dash-title-text {
  font-size: 1.55rem;
  font-weight: 700;
  line-height: 1.2;
  margin: 0;
  background: linear-gradient(90deg, #0f172a, #475569);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.dash-badge-beta {
  display: inline-block;
  background: linear-gradient(90deg, #f97316, #ef4444);
  color: #fff;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(249, 115, 22, 0.35);
  vertical-align: middle;
}
.dash-subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.88rem;
  color: #64748b;
  font-weight: 500;
}
.disclaimer-card-wrap {
  display: flex;
  justify-content: center;
  padding: 1.25rem 0 1rem;
}
.disclaimer-card {
  width: 100%;
  max-width: 940px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 1.5rem 1.65rem;
  margin-bottom: 1rem;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
}
.disclaimer-card p {
  margin: 0 0 0.8rem;
  color: #1f2937;
  font-size: 1rem;
  line-height: 1.6;
  font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
}
.disclaimer-heading {
  margin: 0 0 0.65rem 0;
  color: #0f172a;
  font-size: 1.1rem;
  font-weight: 700;
  font-family: "Plus Jakarta Sans", Inter, sans-serif;
}
.disclaimer-links {
  font-size: 0.92rem;
  margin-top: 0.35rem;
  font-family: Inter, Roboto, "Segoe UI", sans-serif;
}
.disclaimer-links a {
  color: #2c5282;
  font-weight: 600;
  text-decoration: none;
}
.disclaimer-links a:hover { text-decoration: underline; }
[class*="st-key-disclaimer_ack"] button[data-testid="baseButton-primary"],
[class*="st-key-disclaimer_ack"] button[data-testid="stBaseButton-primary"] {
  background: #2c5282 !important;
  border: 1px solid #2c5282 !important;
  color: #ffffff !important;
  border-radius: 8px !important;
  box-shadow: 0 8px 18px rgba(44, 82, 130, 0.22) !important;
  font-family: Inter, Roboto, "Segoe UI", sans-serif !important;
  font-weight: 700 !important;
}
[class*="st-key-disclaimer_ack"] button[data-testid="baseButton-primary"]:hover,
[class*="st-key-disclaimer_ack"] button[data-testid="stBaseButton-primary"]:hover {
  background: #24466f !important;
  border-color: #24466f !important;
  color: #ffffff !important;
}
.section-kicker {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #334155;
  margin: 0 0 0.35rem 0;
}
.section-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.85rem 0;
}
/* Between multi-author charts and Export Option */
hr.charts-export-divider {
  border: none;
  border-top: 3px solid #8b5cf6;
  margin: 1.65rem 0 1.35rem 0;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.9) inset, 0 4px 14px rgba(124, 58, 237, 0.18);
  border-radius: 2px;
  height: 0;
  opacity: 1;
}
.prepare-export-heading-row {
  display: flex !important;
  align-items: center !important;
  gap: 0.65rem !important;
  margin: 0.35rem 0 0.45rem 0 !important;
}
.prepare-export-heading-icon {
  flex-shrink: 0 !important;
  line-height: 0 !important;
}
.prepare-export-heading-icon-img {
  width: 3rem !important;
  height: 3rem !important;
  display: block !important;
  border-radius: 14px !important;
  object-fit: cover !important;
}
.prepare-export-heading-icon-fallback {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 3.1rem !important;
  height: 3.1rem !important;
  border-radius: 14px !important;
  background: linear-gradient(145deg, #ecfdf5 0%, #d1fae5 100%) !important;
  border: 1px solid rgba(52, 211, 153, 0.65) !important;
  color: #047857 !important;
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.22) !important;
}
.prepare-export-heading-icon-fallback svg {
  display: block !important;
}
.prepare-export-heading-row p.prepare-export-heading {
  margin: 0 !important;
}
p.prepare-export-heading {
  font-size: 1.38rem !important;
  font-weight: 700 !important;
  color: #5b21b6 !important;
  letter-spacing: -0.02em;
  margin: 0.35rem 0 0.45rem 0 !important;
  line-height: 1.25 !important;
}
/* Export bundle: three steps — same label size + numbered badges */
p.export-step-label {
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  color: #334155 !important;
  margin: 0 0 0.4rem 0 !important;
  line-height: 1.4 !important;
  display: flex !important;
  align-items: center !important;
  flex-wrap: wrap !important;
  gap: 0.35rem 0.5rem !important;
}
p.export-step-label .export-step-label-text {
  font-size: inherit !important;
  font-weight: inherit !important;
  color: inherit !important;
}
span.export-step-badge {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 2.1rem !important;
  padding: 0.2rem 0.45rem !important;
  border-radius: 8px !important;
  background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%) !important;
  border: 1px solid #c4b5fd !important;
  color: #5b21b6 !important;
  font-size: 0.78rem !important;
  font-weight: 700 !important;
  font-variant-numeric: tabular-nums !important;
  line-height: 1.2 !important;
  flex-shrink: 0 !important;
}

/* Export workspace — one outer card (stack = single-author; bundle = configure + downloads) */
:is([class*="st-key-export_workspace_stack"], [class*="st-key-export_workspace_bundle"]) {
  margin-top: 0.85rem !important;
  margin-bottom: 0.35rem !important;
  padding: 1.05rem 1.2rem 1.2rem 1.25rem !important;
  border-radius: 16px !important;
  background: linear-gradient(
    165deg,
    #f8fafc 0%,
    #f0fdf4 28%,
    #ecfdf5 55%,
    #f8fafc 100%
  ) !important;
  border: 1px solid rgba(16, 185, 129, 0.42) !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.95) inset,
    0 10px 36px rgba(16, 185, 129, 0.12),
    0 4px 14px rgba(15, 23, 42, 0.06) !important;
  position: relative !important;
}
.export-module-title-block {
  margin: 0 0 0.5rem 0 !important;
}
.export-module-title-block .prepare-export-heading-row {
  margin-bottom: 0.25rem !important;
}
.prepare-export-module-sub {
  margin: 0 0 0.35rem 0 !important;
  padding: 0 0.05rem 0 0 !important;
  font-size: 0.9rem !important;
  font-weight: 500 !important;
  color: #64748b !important;
  line-height: 1.45 !important;
  max-width: 44rem !important;
}
hr.export-bundle-divider {
  border: none !important;
  height: 0 !important;
  margin: 0.65rem 0 0.75rem 0 !important;
  border-top: 1px solid rgba(148, 163, 184, 0.45) !important;
  opacity: 1 !important;
}
.export-downloads-section {
  margin: 0 0 0.35rem 0 !important;
  padding: 0 !important;
}
/* Same typography as export step labels (e.g. Pick metrics / Metrics to export) */
.export-downloads-kicker {
  margin: 0 0 0.35rem 0 !important;
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  color: #334155 !important;
  line-height: 1.4 !important;
  letter-spacing: normal !important;
  text-transform: none !important;
}
.export-downloads-hint {
  margin: 0 0 0.55rem 0 !important;
  font-size: 0.88rem !important;
  font-weight: 500 !important;
  color: #64748b !important;
  line-height: 1.45 !important;
  max-width: 46rem !important;
}
.export-metric-order-kicker {
  margin: 0.65rem 0 0.45rem 0 !important;
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  color: #334155 !important;
  line-height: 1.4 !important;
}
:is([class*="st-key-export_workspace_stack"], [class*="st-key-export_workspace_bundle"])::before {
  content: "";
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 5px;
  border-radius: 0 6px 6px 0;
  background: linear-gradient(180deg, #34d399 0%, #10b981 48%, #059669 100%);
  box-shadow: 2px 0 10px rgba(16, 185, 129, 0.35);
  pointer-events: none;
}
header.export-workspace-module-head {
  margin: 0 0 1.15rem 0 !important;
  padding: 0 0 0 0.35rem !important;
}
.export-workspace-module-head-row {
  display: flex !important;
  align-items: flex-start !important;
  gap: 1rem !important;
}
.export-workspace-module-copy {
  flex: 1 !important;
  min-width: 0 !important;
}
.export-workspace-module-icon {
  flex-shrink: 0 !important;
  width: 3.1rem !important;
  height: 3.1rem !important;
  border-radius: 14px !important;
  background: linear-gradient(145deg, #ecfdf5 0%, #d1fae5 100%) !important;
  border: 1px solid rgba(52, 211, 153, 0.65) !important;
  color: #047857 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.22) !important;
}
.export-workspace-module-icon svg {
  display: block !important;
}
.export-workspace-module-title {
  margin: 0 0 0.35rem 0 !important;
  font-size: 1.2rem !important;
  font-weight: 800 !important;
  color: #0f172a !important;
  letter-spacing: -0.025em !important;
  line-height: 1.2 !important;
}
.export-workspace-module-desc {
  margin: 0 !important;
  font-size: 0.88rem !important;
  font-weight: 500 !important;
  color: #475569 !important;
  line-height: 1.45 !important;
  max-width: 40rem !important;
}
.export-workspace-module-kicker {
  display: inline-block !important;
  font-size: 0.68rem !important;
  font-weight: 800 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  color: #059669 !important;
  margin-bottom: 0.4rem !important;
}
/* Merged bundle: downloads sit in same card as steps — no second padded frame */
[class*="st-key-export_workspace_bundle"] [class*="st-key-export_results_shell"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
/* Single-author export: keep inner white panel for filename + buttons */
[class*="st-key-export_workspace_stack"] [class*="st-key-export_results_shell"] {
  background: rgba(255, 255, 255, 0.97) !important;
  border-color: rgba(16, 185, 129, 0.28) !important;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.05) !important;
}
.metrics-grid-hint {
  font-size: 0.85rem;
  color: #4b5563;
  margin-bottom: 0.65rem;
}

/* Site footer — light band: logo + contact / library columns */
.site-footer {
  margin-top: 2.5rem;
  margin-bottom: 1rem;
  padding: 1.1rem 0 0.95rem;
  background: linear-gradient(180deg, #ffffff 0%, #f4f8fc 100%);
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.38) !important;
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.95);
  scroll-margin-bottom: 3rem;
}
.site-footer-inner {
  max-width: 1120px;
  margin: 0 auto;
  padding: 0 1.25rem;
}
.site-footer-main {
  display: flex;
  align-items: flex-start;
  gap: 1.35rem 2rem;
}
.site-footer-brand {
  flex-shrink: 0;
  padding-top: 0.15rem;
}
.site-footer-logo {
  height: 48px;
  width: auto;
  max-width: min(200px, 38vw);
  object-fit: contain;
  opacity: 0.96;
  display: block;
}
.site-footer-info {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem 1.75rem;
  padding: 0.15rem 0 0 0.25rem;
  border-left: 3px solid rgba(31, 55, 108, 0.12);
}
/* Use <p>, not <h2>: Streamlit markdown applies large default styles to headings */
footer.site-footer p.site-footer-block-title {
  margin: 0 0 0.4rem 0 !important;
  padding: 0 !important;
  font-size: calc(0.8125rem * 2) !important;
  font-weight: 700 !important;
  letter-spacing: 0.012em;
  color: #1e3a5f !important;
  line-height: 1.25 !important;
  border: none !important;
}
.site-footer-lines {
  margin: 0;
  padding: 0;
  list-style: none;
}
.site-footer-lines li {
  margin: 0;
  padding: 0;
  font-size: 0.84rem;
  line-height: 1.5;
  color: #334155;
}
.site-footer-lines a {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: #1f376c;
  font-weight: 500;
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.site-footer-lines a .site-footer-line-icon {
  flex-shrink: 0;
  width: 1.05em;
  height: 1.05em;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0.88;
}
.site-footer-lines a:hover,
.site-footer-lines a:focus-visible {
  color: #0f172a;
  border-bottom-color: rgba(31, 55, 108, 0.35);
  outline: none;
}
.site-footer-lines a:hover .site-footer-line-icon,
.site-footer-lines a:focus-visible .site-footer-line-icon {
  opacity: 1;
}
.site-footer-address {
  margin: 0;
  font-size: 0.84rem;
  line-height: 1.5;
  color: #475569;
}
footer.site-footer .site-footer-copy {
  margin: 0.75rem 0 0;
  padding-top: 0.65rem;
  border-top: 1px solid rgba(148, 163, 184, 0.32);
  text-align: center !important;
  color: #64748b;
  font-size: 0.78rem;
  line-height: 1.45;
}
@media (max-width: 720px) {
  .site-footer-main {
    flex-direction: column;
    gap: 0.85rem;
  }
  .site-footer-info {
    border-left: none;
    padding-left: 0;
    padding-top: 0.65rem;
    border-top: 1px solid rgba(148, 163, 184, 0.28);
    grid-template-columns: 1fr;
    gap: 0.85rem;
  }
}
@media (max-width: 480px) {
  .site-footer {
    padding: 0.95rem 0 0.85rem;
    border-radius: 10px;
  }
  .site-footer-inner {
    padding: 0 0.85rem;
  }
  .site-footer-logo {
    height: 40px;
  }
  footer.site-footer p.site-footer-block-title {
    font-size: calc(0.78rem * 2) !important;
  }
  .site-footer-lines li,
  .site-footer-address {
    font-size: 0.8rem;
  }
  footer.site-footer .site-footer-copy {
    font-size: 0.74rem;
  }
}

/* Stable key-based styling to reduce rerun flicker from :has selectors */
[class*="st-key-search_shell"] {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-left: 4px solid #dbe4f0 !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
  margin-bottom: 0.95rem !important;
}
[class*="st-key-search_shell"] textarea {
  border: 1px solid #e2e8f0 !important;
  border-radius: 12px !important;
  padding: 0.75rem 0.85rem !important;
  background: #ffffff !important;
  color: #0f172a !important;
  -webkit-text-fill-color: #0f172a !important;
  caret-color: #0f172a !important;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06) !important;
  min-height: 96px !important;
}
[class*="st-key-search_shell"] textarea:focus {
  border-color: #673ab7 !important;
  box-shadow: 0 0 0 3px rgba(103, 58, 183, 0.2) !important;
}

/* Scopus Author IDs textarea: magnifier middle-left (vertically centered on left strip); copy left-aligned */
[class*="st-key-search_shell"] [class*="st-key-scopus_author_ids"] textarea {
  border: 2px solid #cbd5e1 !important;
  border-radius: 12px !important;
  padding: 0.8rem 0.95rem 0.8rem 2.85rem !important;
  background-color: #ffffff !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.3-4.3'/%3E%3C/svg%3E") !important;
  background-repeat: no-repeat !important;
  background-position: 1rem center !important;
  background-size: 1.22rem 1.22rem !important;
  box-shadow:
    0 2px 8px rgba(15, 23, 42, 0.07),
    0 1px 3px rgba(103, 58, 183, 0.06) !important;
  min-height: 104px !important;
  text-align: left !important;
  box-sizing: border-box !important;
}
/* Empty field: placeholder lines vertically centered as a block; still left-aligned */
[class*="st-key-search_shell"] [class*="st-key-scopus_author_ids"] textarea:placeholder-shown {
  align-content: center !important;
}
[class*="st-key-search_shell"] [class*="st-key-scopus_author_ids"] textarea:focus {
  border-color: #7c3aed !important;
  box-shadow:
    0 0 0 3px rgba(124, 58, 237, 0.2),
    0 3px 10px rgba(15, 23, 42, 0.08) !important;
}
[class*="st-key-search_shell"] [class*="st-key-scopus_author_ids"] textarea::placeholder {
  color: #64748b !important;
  opacity: 1 !important;
  -webkit-text-fill-color: #64748b !important;
}

/* Metrics merged into search shell: single card (no nested white/purple frame) */
[class*="st-key-search_shell"] [class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) {
  background: transparent !important;
  border: none !important;
  border-left: none !important;
  border-radius: 0 !important;
  padding: 0.1rem 0 0 0 !important;
  margin: 0.1rem 0 0 0 !important;
  box-shadow: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
[class*="st-key-search_shell"] [class*="st-key-metrics_panel_shell"] {
  margin-bottom: 0 !important;
}

[class*="st-key-metrics_panel_shell"] {
  background: #ffffff !important;
  border: 1px solid rgba(226, 232, 240, 0.95) !important;
  border-left: 4px solid #7c3aed !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
  /* Tighten gap before Analyze row (button remains outside this shell) */
  margin-bottom: -0.5rem !important;
}
[class*="st-key-metrics_grid_shell"],
[class*="st-key-collab_metrics_shell"] {
  background: transparent !important;
  border: none !important;
  overflow: visible !important;
}

/* Metrics grid + st.html: (i) panels use position:absolute and must escape ancestor clip */
[class*="st-key-search_shell"],
[class*="st-key-metrics_panel_shell"],
[class*="st-key-metrics_grid_shell"],
[class*="st-key-metrics_grid_row"] {
  overflow: visible !important;
}
[class*="st-key-metrics_grid_shell"] [data-testid="element-container"],
[class*="st-key-metrics_grid_row"] [data-testid="element-container"],
[class*="st-key-metric_cell_"] [data-testid="element-container"] {
  overflow: visible !important;
}
[class*="st-key-metrics_grid_shell"] [data-testid="column"],
[class*="st-key-metrics_grid_row"] [data-testid="column"] {
  overflow: visible !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHtml"],
[class*="st-key-metric_cell_"] [data-testid="element-container"]:has([data-testid="stHtml"]) {
  overflow: visible !important;
}

/* -------- Streamlit DOM-safe final overrides (keep at end) --------
   Key classes (st-key-*) are more stable than deep DOM selectors.
*/
[class*="st-key-filter_panel_blue"],
[class*="st-key-filter_panel_mint"],
[class*="st-key-filter_panel_peach"] {
  min-height: 280px !important;
  border-width: 1px !important;
  border-top-width: 1px !important;
  border-radius: 16px !important;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.06) !important;
  padding: 1.15rem 1rem !important;
}
[class*="st-key-filter_panel_blue"] {
  background: #f0f7ff !important;
  border-color: #c9ddef !important;
}
[class*="st-key-filter_panel_mint"] {
  background: #f2faf5 !important;
  border-color: #cde7d6 !important;
}
[class*="st-key-filter_panel_peach"] {
  background: #fff9f0 !important;
  border-color: #e8dac1 !important;
}

/* Make each panel behave like a fixed-height flex column */
[class*="st-key-filter_panel_blue"] [data-testid="stVerticalBlock"],
[class*="st-key-filter_panel_mint"] [data-testid="stVerticalBlock"],
[class*="st-key-filter_panel_peach"] [data-testid="stVerticalBlock"] {
  display: flex !important;
  flex-direction: column !important;
  min-height: 260px !important;
}

/* Keep helper caption anchored near the bottom across all cards */
[class*="st-key-filter_panel_blue"] [data-testid="stCaption"],
[class*="st-key-filter_panel_mint"] [data-testid="stCaption"],
[class*="st-key-filter_panel_peach"] [data-testid="stCaption"] {
  margin-top: auto !important;
  padding-top: 0.65rem !important;
}

/* Icon badge: white circle + line-art SVG (final pixel polish) */
.filter-panel-icon-wrap {
  width: 48px !important;
  height: 48px !important;
  border-radius: 50% !important;
  background: #ffffff !important;
  border: 1px solid rgba(15, 23, 42, 0.1) !important;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08) !important;
}
.filter-panel-head--blue .filter-panel-icon-wrap { color: #1d4ed8 !important; }
.filter-panel-head--mint .filter-panel-icon-wrap { color: #0d9488 !important; }
.filter-panel-head--peach .filter-panel-icon-wrap { color: #c2410c !important; }

/* Input/radio spacing consistency */
[class*="st-key-filter_panel_blue"] [data-baseweb="select"] > div,
[class*="st-key-filter_panel_mint"] [data-baseweb="select"] > div {
  min-height: 46px !important;
}
[class*="st-key-filter_panel_peach"] [data-testid="stRadio"] {
  min-height: 46px !important;
  display: flex !important;
  align-items: center !important;
}

/* Select metrics: badge stays outside horizontal scroll so circular rim is not clipped
   (overflow-x:auto on an ancestor forces overflow-y to clip children). */
.metrics-panel-heading-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0 0 0.55rem 0;
  overflow: visible;
}
.metrics-panel-heading-row > .metrics-panel-heading-icon.minimal-filter-icon-badge {
  flex-shrink: 0;
  width: 2rem !important;
  height: 2rem !important;
  min-width: 2rem !important;
  min-height: 2rem !important;
}
.metrics-panel-heading-row > .metrics-panel-heading-icon.minimal-filter-icon-badge svg {
  width: 1rem !important;
  height: 1rem !important;
}
.metrics-panel-heading-row > .metrics-panel-heading-scrollstrip {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}
.metrics-panel-heading-inline {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.35rem;
  white-space: nowrap;
  margin: 0;
  scrollbar-width: thin;
}
.metrics-panel-heading-lead {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}
.metrics-panel-heading-row .metrics-panel-heading {
  margin: 0 !important;
}
[class*="st-key-metrics_panel_shell"] [data-testid="stMarkdownContainer"]:has(.metrics-panel-heading-row),
[class*="st-key-search_shell"]
  [class*="st-key-metrics_panel_shell"]
  [data-testid="stMarkdownContainer"]:has(.metrics-panel-heading-row) {
  overflow: visible !important;
}
.metrics-panel-heading-icon.minimal-filter-icon-badge {
  align-self: center;
}
.metrics-panel-head-caption-inline {
  font-size: 0.8rem;
  font-weight: 400;
  color: #64748b;
  line-height: 1.35;
  text-align: left;
  padding: 0;
}
.metrics-panel-heading {
  font-size: 1.05rem;
  font-weight: 800;
  color: #1e1b4b;
  margin: 0 0 0.55rem 0;
  padding: 0;
  border: none;
  border-bottom: none !important;
  box-shadow: none !important;
}
[class*="st-key-metrics_panel_shell"] [data-testid="stMarkdownContainer"] h3 {
  border-bottom: none !important;
  box-shadow: none !important;
  padding-bottom: 0 !important;
}

/* Export results: header row (badge + copy) */
.export-results-head {
  margin: 0 0 1rem 0;
  padding: 0;
}
.export-results-head-row {
  display: flex;
  align-items: flex-start;
  gap: 0.9rem;
}
.export-results-badge {
  flex-shrink: 0;
  width: 2.55rem;
  height: 2.55rem;
  border-radius: 12px;
  background: linear-gradient(145deg, #6ee7b7 0%, #34d399 100%);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 12px rgba(52, 211, 153, 0.4);
}
.export-results-badge svg {
  width: 1.22rem;
  height: 1.22rem;
}
.export-results-title {
  margin: 0 0 0.35rem 0;
  font-size: 1.14rem;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
}
.export-results-sub {
  margin: 0;
  font-size: 0.9rem;
  color: #64748b;
  line-height: 1.45;
  max-width: 46rem;
}
[class*="st-key-export_results_shell"] [data-testid="stTextInput"] {
  margin-bottom: 0.65rem !important;
  display: block !important;
  width: 100% !important;
  max-width: min(100%, 28rem) !important;
}
/* Filename field: clear bordered box (Streamlit BaseWeb + plain input) */
[class*="st-key-export_results_shell"] [data-testid="stTextInput"] div[data-baseweb="input"] {
  border: 1px solid #64748b !important;
  border-radius: 10px !important;
  background-color: #ffffff !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06) !important;
  min-height: 2.65rem !important;
}
[class*="st-key-export_results_shell"] [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
  border-color: #673ab7 !important;
  box-shadow: 0 0 0 2px rgba(103, 58, 183, 0.2) !important;
}
[class*="st-key-export_results_shell"] [data-testid="stTextInput"] div[data-baseweb="input"] input {
  border: none !important;
  box-shadow: none !important;
  outline: none !important;
  background: transparent !important;
  color: #0f172a !important;
  -webkit-text-fill-color: #0f172a !important;
  font-size: 0.95rem !important;
  padding: 0.55rem 0.75rem !important;
}

/* Validation toasts — amber styling if ``st.toast`` is used elsewhere */
[data-testid="stToast"] {
  background: linear-gradient(180deg, #fffbeb 0%, #fef3c7 100%) !important;
  border: 2px solid #f59e0b !important;
  border-radius: 14px !important;
  box-shadow:
    0 16px 48px rgba(15, 23, 42, 0.16),
    0 6px 16px rgba(245, 158, 11, 0.22) !important;
  color: #78350f !important;
  font-weight: 600 !important;
  font-size: 0.95rem !important;
  padding: 0.85rem 1.15rem !important;
  max-width: min(92vw, 26rem) !important;
}
[data-testid="stToast"] p,
[data-testid="stToast"] span {
  color: inherit !important;
}
[data-testid="stToast"] [data-testid="stMarkdownContainer"] {
  color: inherit !important;
}

</style>
        """,
        unsafe_allow_html=True,
    )
    _inject_export_download_styles()


def _render_footer_html() -> None:
    """Footer: HKUST mark, library contact/address, copyright."""
    year = datetime.now().year
    st.markdown(
        f"""
<footer class="site-footer" role="contentinfo">
  <div class="site-footer-inner">
    <div class="site-footer-main">
      <div class="site-footer-brand">
        <a href="https://hkust.edu.hk/" target="_blank" rel="noopener noreferrer" aria-label="HKUST home">
          <img class="site-footer-logo" src="{HKUST_LOGO}" alt="HKUST logo" />
        </a>
      </div>
      <div class="site-footer-info" aria-label="Library contact and location">
        <div>
          <p class="site-footer-block-title">Contact &amp; Support</p>
          <ul class="site-footer-lines">
            <li>
              <a href="mailto:lbrs@ust.hk">
                <svg class="site-footer-line-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75"/></svg>
                lbrs@ust.hk
              </a>
            </li>
            <li>
              <a href="tel:+85223586772">
                <svg class="site-footer-line-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 0 0 2.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 0 1-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 0 0-1.091-.852H4.5A2.25 2.25 0 0 0 2.25 4.5v2.25Z"/></svg>
                +852 2358 6772
              </a>
            </li>
          </ul>
        </div>
        <div>
          <p class="site-footer-block-title">HKUST Library</p>
          <p class="site-footer-address">
            Hong Kong University of Science and Technology<br />
            Clear Water Bay, Hong Kong
          </p>
        </div>
      </div>
    </div>
    <p class="site-footer-copy">
      Copyright &copy; {year} The Hong Kong University of Science and Technology. All rights reserved.
    </p>
  </div>
</footer>
        """,
        unsafe_allow_html=True,
    )


def _render_header_html() -> None:
    st.markdown(
        f"""
<div class="dash-top-header">
  <div class="dash-top-inner">
    <div class="dash-logos">
      <a href="https://hkust.edu.hk/" target="_blank" rel="noopener noreferrer">
        <img src="{HKUST_LOGO}" alt="HKUST" />
      </a>
      <div class="dash-logo-rule"></div>
      <a href="https://library.hkust.edu.hk/" target="_blank" rel="noopener noreferrer">
        <img src="{LIB_LOGO}" alt="HKUST Library" />
      </a>
    </div>
    <div class="dash-title-row">
      <div class="dash-icon-badge" aria-hidden="true">📊</div>
      <div>
        <p class="dash-title-text" style="display:inline;">Research Impact Dashboard</p>
        <span class="dash-badge-beta">BETA</span>
        <p class="dash-subtitle">Analyze author metrics and research impact</p>
      </div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


DEFAULT_METRICS = [
    {
        "id": "publication",
        "label": "Publications",
        "description": (
            "Number of Scopus-indexed publications (SciVal scholarly output) in the selected window."
        ),
        "enabled": True,
    },
    {
        "id": "fwci",
        "label": "Field-Weighted Citation Impact (FWCI)",
        "description": (
            "FWCI: citations vs. peer average for similar papers (1.0 = average); "
            "most volatile when the number of publications is small."
        ),
        "enabled": True,
    },
    {
        "id": "topJournal",
        "label": "Publications in Top 10% Journals",
        "description": (
            "Share of publications in journals that SciVal ranks in the top tenth by CiteScore percentile."
        ),
        "enabled": True,
    },
    {
        "id": "citationCount",
        "label": "Citation Count",
        "description": "Citation count: citations received by the selected publications, grouped by publication year.",
        "enabled": True,
    },
    {
        "id": "hIndex",
        "label": "H-Index",
        "description": "H-index: greatest h such that at least h publications have been cited at least h times each.",
        "enabled": True,
    },
    {
        "id": "citationsPerPublication",
        "label": "Citations Per Publication",
        "description": "Citations per publication: average citations received per publication in the selected window.",
        "enabled": True,
    },
    {
        "id": "collaborationInternational",
        "label": "International collaboration",
        "description": (
            "International collaboration: multi-author; addresses span more than one country/region."
        ),
        "enabled": False,
    },
    {
        "id": "collaborationNational",
        "label": "National collaboration",
        "description": (
            "National collaboration: multi-author, one country/region, two or more SciVal institutions."
        ),
        "enabled": False,
    },
    {
        "id": "collaborationInstitutional",
        "label": "Institutional collaboration",
        "description": (
            "Institutional collaboration: multi-author, one country/region, one SciVal institution."
        ),
        "enabled": False,
    },
    {
        "id": "collaborationSingleAuthorship",
        "label": "Single authorship",
        "description": "Single authorship: one author; no co-authors.",
        "enabled": False,
    },
    {
        "id": "academicCorporateWith",
        "label": "Academic–corporate collaboration",
        "description": (
            "Share of publications SciVal classifies as involving both academic and corporate affiliations."
        ),
        "enabled": False,
    },
    {
        "id": "academicCorporateWithout",
        "label": "No academic–corporate collaboration",
        "description": "Share of publications not classified by SciVal as academic–corporate collaboration.",
        "enabled": False,
    },
]

# Panel display order for grouped accordions (IDs must match ``DEFAULT_METRICS``).
METRIC_IDS_CORE = (
    "publication",
    "citationCount",
    "citationsPerPublication",
    "topJournal",
    "fwci",
    "hIndex",
)
METRIC_IDS_COLLABORATIVE = (
    "collaborationInternational",
    "collaborationNational",
    "collaborationInstitutional",
    "collaborationSingleAuthorship",
    "academicCorporateWith",
    "academicCorporateWithout",
)


def _metrics_for_panel_ordered(
    am_list: list[dict], id_order: tuple[str, ...]
) -> list[dict]:
    """Return metrics from ``am_list`` in ``id_order``, skipping unknown ids."""
    by_id = {m["id"]: m for m in am_list}
    return [by_id[i] for i in id_order if i in by_id]

# Metric info (i) panels: ``{Topic}: …`` lead line, then detail; collaboration types use bullets.
METRIC_INFO_TEXT: dict[str, str] = {
    "publication": (
        "Publications (SciVal scholarly output): number of Scopus-indexed publications for this entity "
        "in the selected document-type and year window. Values are grouped by publication year."
    ),
    "fwci": (
        "FWCI: citations on this entity’s papers vs. the average for similar papers worldwide "
        "(field, document type, age). 1.0 matches that peer-group average; small samples move easily."
    ),
    "topJournal": (
        "Publications in the top 10% of journals: share of publications in journals that SciVal ranks in the "
        "top tenth by CiteScore percentile. Publications without CiteScore journal metrics "
        "(e.g. many books) are out of scope."
    ),
    "citationCount": (
        "Citation count: total citations received on the entity’s publications. "
        "Year axes use publication year of cited papers, not the year a citation occurred."
    ),
    "hIndex": (
        "H-index: greatest h such that at least h publications have been cited at least h times each. "
        "Combines how many qualifying papers you have with how often they are cited."
    ),
    "citationsPerPublication": (
        "Citations per publication: average citations received per publication in the selected "
        "document-type and year window. The self-citation setting applies where SciVal supports it."
    ),
    "collaborationInternational": (
        "International collaboration:\n"
        "• More than one author\n"
        "• More than one country/region among publication addresses"
    ),
    "collaborationNational": (
        "National collaboration:\n"
        "• More than one author\n"
        "• One country/region on the publication\n"
        "• Affiliations map to two or more SciVal institutions in that country/region"
    ),
    "collaborationInstitutional": (
        "Institutional collaboration:\n"
        "• More than one author\n"
        "• One country/region on the publication\n"
        "• Every affiliation maps to the same SciVal institution"
    ),
    "collaborationSingleAuthorship": (
        "Single authorship: exactly one author; no co-authors on the publication."
    ),
    "academicCorporateWith": (
        "Academic–corporate collaboration: share of publications where SciVal maps at least one "
        "affiliation to an academic organization and at least one affiliation to a corporate "
        "(industrial) organization."
    ),
    "academicCorporateWithout": (
        "No academic–corporate collaboration: share of publications not classified by SciVal as "
        "academic–corporate collaboration."
    ),
}


def _metric_title_with_info_html(metric_id: str, label: str) -> str:
    """Metric label plus (i) hover / focus panel with SciVal-style definition text."""
    body = METRIC_INFO_TEXT.get(metric_id, "").strip()
    label_esc = html.escape(label)
    if not body:
        return f'<p class="metric-compact-title">{label_esc}</p>'
    body_esc = html.escape(body)
    aria = html.escape(f"SciVal definition: {label}")
    _mid = re.sub(r"[^a-zA-Z0-9_-]", "_", metric_id)
    return (
        '<p class="metric-compact-title metric-compact-title--with-info">'
        f'<span class="metric-title-text">{label_esc}</span>'
        f'<span class="metric-info-wrap" tabindex="0" aria-describedby="metric-info-{_mid}">'
        f'<span class="metric-info-icon" aria-label="{aria}">i</span>'
        f'<span class="metric-info-panel" id="metric-info-{_mid}" role="tooltip">'
        f'<span class="metric-info-panel-inner">{body_esc}</span></span>'
        "</span></p>"
    )


# Default on/off per metric id (used when creating ``met_*`` session keys).
# Core metrics on; collaboration metrics off → "6 of 12" selected by default.
DEFAULT_METRIC_TOGGLE_DEFAULT: dict[str, bool] = {
    m["id"]: (m["id"] in METRIC_IDS_CORE) for m in DEFAULT_METRICS
}


def _render_metric_toggle_grid_rows(
    metrics_slice: list[dict], row_key_prefix: str
) -> None:
    """Render 3-column rows of metric toggle cards (toggle left; title + (i); Baseweb switch)."""
    _ncols = 3
    for row_idx, row_start in enumerate(range(0, len(metrics_slice), _ncols)):
        row_key = f"{row_key_prefix}_{row_idx}"
        row = metrics_slice[row_start : row_start + _ncols]
        with st.container(border=False, key=row_key):
            cols = st.columns(_ncols, gap="small")
            for i, metric in enumerate(row):
                with cols[i]:
                    with st.container(key=f"metric_cell_{metric['id']}"):
                        csw, ct = st.columns([0.28, 1], gap="small")
                        with csw:
                            _mk = f"met_{metric['id']}"
                            _def_on = DEFAULT_METRIC_TOGGLE_DEFAULT.get(
                                metric["id"], False
                            )
                            _cur = bool(st.session_state.get(_mk, _def_on))
                            st.session_state[_mk] = _cur
                            metric["enabled"] = st.toggle(
                                metric["label"],
                                value=_cur,
                                key=_mk,
                                label_visibility="collapsed",
                            )
                        with ct:
                            st.html(
                                _metric_title_with_info_html(
                                    str(metric["id"]),
                                    str(metric["label"]),
                                ),
                                width="content",
                            )


# Bump when default metric toggles change so Streamlit widget keys (met_*) resync.
# v5: reset stuck "all off" sessions; ensure defaults come from DEFAULT_METRICS, not stale dict copies.
# v6: default UI count is again "all metrics on" (8 of 8) after one-time key refresh.
# v7: all metrics on by default again (explicit True + one-time met_* refresh).
# v8: Collaboration split into four SciVal ``collabType`` metrics (one API ``Collaboration`` fetch).
# v9: Academic–corporate split into two SciVal ``collabType`` rows (one API fetch).
# v10: Collaboration metric labels + descriptions (operational definitions).
# v11: Academic–corporate metric descriptions + (i) help text (SciVal definition).
# v12: Collaboration submetrics UI/export order (international → national → institutional → single).
# v13: Re-init metric toggles; pass explicit ``value=`` + scope card CSS to Baseweb switch (default on).
# v14: Default selection is six core metrics on, six collaboration metrics off.
_METRICS_SESSION_DEFAULT_VERSION = 14

YEAR_OPTIONS = {
    "3yrs": "Last 3 completed calendar years — compact recent window",
    "3yrsAndCurrent": (
        "Last 3 completed calendar years + current year — includes the calendar year still in progress"
    ),
    "3yrsAndCurrentAndFuture": (
        "Last 3 completed calendar years + current + future — adds indexed manuscripts "
        "whose official publication date is still in the future"
    ),
    "5yrs": "Last 5 completed calendar years — balanced default window",
    "5yrsAndCurrent": (
        "Last 5 completed calendar years + current year — includes the calendar year still in progress"
    ),
    "5yrsAndCurrentAndFuture": (
        "Last 5 completed calendar years + current + future — widest recent window plus indexed "
        "manuscripts whose official publication date is still in the future"
    ),
    "10yrs": "Last 10 completed calendar years — long-term trend view",
}
MAX_AUTHORS_PER_RUN = 10

# Short labels for dropdowns (matches compact SaaS-style UI)
YEAR_OPTIONS_DISPLAY = {
    "3yrs": "Last 3 completed calendar years",
    "3yrsAndCurrent": "Last 3 completed calendar years + current year",
    "3yrsAndCurrentAndFuture": "Last 3 completed calendar years + current + future",
    "5yrs": "Last 5 completed calendar years (default)",
    "5yrsAndCurrent": "Last 5 completed calendar years + current year",
    "5yrsAndCurrentAndFuture": "Last 5 completed calendar years + current + future",
    "10yrs": "Last 10 completed calendar years",
}

DOCS_OPTIONS = {
    "AllPublicationTypes": "All types — articles, reviews, books, conference papers, …",
    "ArticlesOnly": "Articles only — peer-reviewed articles",
    "ArticlesReviews": "Articles & reviews — excludes books and conference items",
    "ArticlesReviewsConferencePapers": "Articles, reviews & conference papers",
    "ArticlesConferencePapers": "Articles & conference papers",
    "BooksAndBookChapters": "Books & book chapters only",
}

DOCS_OPTIONS_DISPLAY = {
    "AllPublicationTypes": "All publication types (default)",
    "ArticlesOnly": "Articles only",
    "ArticlesReviews": "Articles & reviews",
    "ArticlesReviewsConferencePapers": "Articles, reviews & conference papers",
    "ArticlesConferencePapers": "Articles & conference papers",
    "BooksAndBookChapters": "Books & book chapters",
}

SELF_CIT_RADIO_LABELS = {
    "include": "Include",
    "exclude": "Exclude",
}

YEAR_FOOTNOTES = {
    "3yrs": "3 completed calendar years",
    "3yrsAndCurrent": "3 completed calendar years plus current year",
    "3yrsAndCurrentAndFuture": (
        "3 completed calendar years, current year, and manuscripts indexed before their official publication date"
    ),
    "5yrs": "5 completed calendar years",
    "5yrsAndCurrent": "5 completed calendar years plus current year",
    "5yrsAndCurrentAndFuture": (
        "5 completed calendar years, current year, and manuscripts indexed before their official publication date"
    ),
    "10yrs": "10 completed calendar years",
}

# Streamlit selectbox “?” — precise definition of the selected preset (SciVal yearRange).
YEAR_SELECT_HELP = {
    "3yrs": (
        "For this preset, metrics use publication years in the last 3 completed calendar years only "
        "(SciVal yearRange 3yrs)."
    ),
    "3yrsAndCurrent": (
        "For this preset, metrics use the last 3 completed calendar years plus the ongoing calendar year "
        "(SciVal yearRange 3yrsAndCurrent)."
    ),
    "3yrsAndCurrentAndFuture": (
        "For this preset, metrics use the last 3 completed calendar years, the current calendar year, "
        "and indexed manuscripts whose official publication date is still in the future "
        "(SciVal 3yrsAndCurrentAndFuture). "
        "Record inclusion depends on SciVal–Scopus indexing and updates."
    ),
    "5yrs": (
        "For this preset, metrics use publication years in the last 5 completed calendar years only "
        "(SciVal yearRange 5yrs)."
    ),
    "5yrsAndCurrent": (
        "For this preset, metrics use the last 5 completed calendar years plus the ongoing calendar year "
        "(SciVal yearRange 5yrsAndCurrent)."
    ),
    "5yrsAndCurrentAndFuture": (
        "For this preset, metrics use the last 5 completed calendar years, the current calendar year, "
        "and indexed manuscripts whose official publication date is still in the future "
        "(SciVal 5yrsAndCurrentAndFuture). "
        "Record inclusion depends on SciVal–Scopus indexing and updates."
    ),
    "10yrs": (
        "For this preset, metrics use publication years in the last 10 completed calendar years only "
        "(SciVal yearRange 10yrs)."
    ),
}

# Year filter info tooltip — short summary of what the year window can include.
YEAR_FILTER_LABEL_TOOLTIP_HTML = (
    "<strong>Year range:</strong><br />"
    "• Completed calendar years<br />"
    "• The current calendar year<br />"
    "• Indexed manuscripts with a future official publication date<br />"
)

SELF_CIT_LABEL_TOOLTIP_HTML = (
    "Self-citations are citations where an author cites their own previous work. "
    "Including them may increase citation counts and H-index values."
)

SELF_CIT_HELP = (
    "Self-citations are citations where an author cites their own previous work. "
    "Including them may increase citation counts and H-index values."
)

DOCS_SELECTION_CAPTION = "Include all types matching your selection above."


def _init_session() -> None:
    if "disclaimer_ok" not in st.session_state:
        st.session_state.disclaimer_ok = False
    if st.session_state.get("_metrics_session_default_version") != _METRICS_SESSION_DEFAULT_VERSION:
        st.session_state._metrics_session_default_version = _METRICS_SESSION_DEFAULT_VERSION
        st.session_state.available_metrics = [dict(m) for m in DEFAULT_METRICS]
        # Drop old widget keys so st.toggle does not keep a mismatched internal state.
        for _k in list(st.session_state.keys()):
            if isinstance(_k, str) and _k.startswith("met_"):
                try:
                    del st.session_state[_k]
                except KeyError:
                    pass
        for m in DEFAULT_METRICS:
            mid = m["id"]
            st.session_state[f"met_{mid}"] = DEFAULT_METRIC_TOGGLE_DEFAULT.get(
                mid, False
            )
    elif "available_metrics" not in st.session_state:
        st.session_state.available_metrics = [dict(m) for m in DEFAULT_METRICS]
        for m in DEFAULT_METRICS:
            mk = f"met_{m['id']}"
            if mk not in st.session_state:
                st.session_state[mk] = DEFAULT_METRIC_TOGGLE_DEFAULT.get(m["id"], False)
    if "results" not in st.session_state:
        st.session_state.results = []
    if "loading" not in st.session_state:
        st.session_state.loading = False
    if "error_msg" not in st.session_state:
        st.session_state.error_msg = ""
    if "entitlement_error" not in st.session_state:
        st.session_state.entitlement_error = False
    if "rate_limit_error" not in st.session_state:
        st.session_state.rate_limit_error = False
    if "scopus_author_ids" not in st.session_state:
        st.session_state.scopus_author_ids = ""
    if "find_scopus_panel_open" not in st.session_state:
        st.session_state.find_scopus_panel_open = False
    if "self_cit_radio" not in st.session_state:
        st.session_state.self_cit_radio = (
            "include" if st.session_state.get("self_cit_include", True) else "exclude"
        )


def _enabled_metric_ids(metrics: list) -> list:
    return [m["id"] for m in metrics if m.get("enabled")]


def _resolve_year_columns(metrics_payload: dict, data_source: dict | None) -> list[int]:
    """Year columns for tables and charts (same rules as the metrics table)."""
    m = metrics_payload
    ds = data_source or {}
    start = ds.get("metricStartYear")
    end = ds.get("metricEndYear")
    if start is not None and end is not None:
        return list(range(int(start), int(end) + 1))
    year_sets = []
    for key in (
        "scholarlyOutput",
        "fwci",
        "topJournal",
        "citationCount",
        "citationsPerPublication",
    ):
        year_sets.extend((m.get(key) or {}).get("byYear") or {})
    for _cid in COLLABORATION_SUBMETRIC_IDS:
        year_sets.extend((m.get(_cid) or {}).get("byYear") or {})
    for _aid in ACADEMIC_CORPORATE_SUBMETRIC_IDS:
        year_sets.extend((m.get(_aid) or {}).get("byYear") or {})
    ys = sorted({int(y) for y in year_sets if str(y).isdigit()})
    return ys if ys else [2019, 2020, 2021, 2022, 2023, 2024]


def _build_metrics_table_rows(
    metrics_payload: dict,
    data_source: dict | None,
    selected_ids: list,
    order: list,
) -> tuple[list, list]:
    """Returns (column_names, rows) for st.dataframe."""
    m = metrics_payload
    ds = data_source or {}
    years = _resolve_year_columns(m, ds)

    def _fmt_pct(v: float | int) -> str:
        fv = float(v)
        return f"{int(fv)}%" if fv.is_integer() else f"{fv:.2f}%"

    row_defs = [
        ("publication", "Publications", lambda x: x["scholarlyOutput"], True, False),
        ("citationCount", "Citation Count", lambda x: x["citationCount"], True, False),
        (
            "citationsPerPublication",
            "Citations Per Publication",
            lambda x: x["citationsPerPublication"],
            True,
            False,
        ),
        ("fwci", "FWCI", lambda x: x["fwci"], True, False),
        ("topJournal", "Publications in Top 10% Journals", lambda x: x["topJournal"], True, True),
        (
            "hIndex",
            "H-Index",
            lambda x: {"byYear": {}, "total": x["hIndex"]["value"]},
            False,
            False,
        ),
        (
            "collaborationInternational",
            "International collaboration %",
            lambda x: x.get("collaborationInternational")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
        (
            "collaborationNational",
            "National collaboration %",
            lambda x: x.get("collaborationNational")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
        (
            "collaborationInstitutional",
            "Institutional collaboration %",
            lambda x: x.get("collaborationInstitutional")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
        (
            "collaborationSingleAuthorship",
            "Single authorship %",
            lambda x: x.get("collaborationSingleAuthorship")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
        (
            "academicCorporateWith",
            "Academic–corporate collaboration %",
            lambda x: x.get("academicCorporateWith")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
        (
            "academicCorporateWithout",
            "No academic–corporate collaboration %",
            lambda x: x.get("academicCorporateWithout")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
    ]
    by_id = {r[0]: r for r in row_defs}
    ordered = [by_id[i] for i in order if i in by_id and i in selected_ids]

    cols = ["Metric"] + [str(y) for y in years] + ["Total / Avg"]
    rows = []
    for mid, label, getter, is_year_based, is_pct in ordered:
        d = getter(m)
        by_y = d.get("byYear") or {}
        tot = d.get("total")
        if is_year_based:
            cells = [label]
            for y in years:
                v = by_y.get(str(y))
                if v is None:
                    cells.append("N/A")
                elif is_pct or mid == "topJournal":
                    cells.append(_fmt_pct(v))
                elif mid in ("fwci", "citationsPerPublication"):
                    cells.append(f"{float(v):.2f}")
                else:
                    cells.append(str(round(v)) if isinstance(v, (int, float)) else str(v))
            if isinstance(tot, (int, float)):
                if mid in ("fwci", "citationsPerPublication", "topJournal") or is_pct:
                    cells.append(
                        _fmt_pct(tot) if is_pct or mid == "topJournal" else f"{tot:.2f}"
                    )
                else:
                    cells.append(str(round(tot)))
            else:
                cells.append(str(tot))
        else:
            cells = [label] + ["N/A"] * len(years)
            cells.append(str(tot) if tot is not None else "N/A")
        rows.append(cells)
    return cols, rows


def _extract_metric_by_year(metrics_payload: dict, metric_id: str) -> dict[str, float | int]:
    """Extract `byYear` values for year-based metrics.

    Returns an empty dict if the metric is not year-based or missing from payload.
    """
    payload_key_map = {
        "publication": "scholarlyOutput",
        "citationCount": "citationCount",
        "citationsPerPublication": "citationsPerPublication",
        "fwci": "fwci",
        "topJournal": "topJournal",
        "collaborationInternational": "collaborationInternational",
        "collaborationNational": "collaborationNational",
        "collaborationInstitutional": "collaborationInstitutional",
        "collaborationSingleAuthorship": "collaborationSingleAuthorship",
        "academicCorporateWith": "academicCorporateWith",
        "academicCorporateWithout": "academicCorporateWithout",
    }
    payload_key = payload_key_map.get(metric_id)
    if not payload_key:
        return {}
    obj = metrics_payload.get(payload_key) or {}
    by_year = obj.get("byYear") or {}
    # Values can be ints/floats; keep as-is and let downstream chart handle None.
    return by_year


def _intersection_years(year_lists: list[list[int]]) -> list[int]:
    if not year_lists:
        return []
    s = set(year_lists[0])
    for lst in year_lists[1:]:
        s &= set(lst)
    return sorted(s)


def _scalar_metric_for_year(
    metrics_payload: dict, metric_id: str, year: int
) -> float | None:
    by_year = _extract_metric_by_year(metrics_payload, metric_id)
    if not by_year:
        return None
    v = by_year.get(str(year))
    if v is None or (isinstance(v, (int, float)) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _scalar_metric_total(metrics_payload: dict, metric_id: str) -> float | None:
    """SciVal aggregate / Total column for the metric window (not a single calendar year)."""
    if metric_id == "hIndex":
        h = metrics_payload.get("hIndex") or {}
        v = h.get("value")
        if v is None or v == "N/A":
            return None
        if isinstance(v, str) and v.strip().upper() == "N/A":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    payload_key_map = {
        "publication": "scholarlyOutput",
        "citationCount": "citationCount",
        "citationsPerPublication": "citationsPerPublication",
        "fwci": "fwci",
        "topJournal": "topJournal",
        "collaborationInternational": "collaborationInternational",
        "collaborationNational": "collaborationNational",
        "collaborationInstitutional": "collaborationInstitutional",
        "collaborationSingleAuthorship": "collaborationSingleAuthorship",
        "academicCorporateWith": "academicCorporateWith",
        "academicCorporateWithout": "academicCorporateWithout",
    }
    key = payload_key_map.get(metric_id)
    if not key:
        return None
    obj = metrics_payload.get(key) or {}
    tot = obj.get("total")
    if tot is None or tot == "N/A":
        return None
    if isinstance(tot, str) and tot.strip().upper() == "N/A":
        return None
    if isinstance(tot, str):
        try:
            return float(tot)
        except ValueError:
            return None
    if isinstance(tot, (int, float)):
        if pd.isna(tot):
            return None
        return float(tot)
    return None


def _metric_short_label(label_map: dict, metric_id: str) -> str:
    """Prefer a real acronym in parentheses (e.g. ``(FWCI)``).

    Labels that end with a literal ``(%)`` placeholder are not acronyms; stripping
    them avoids chart titles like ``% (%)`` or duplicated ``(%)`` when the axis
    already adds a percent unit.
    """
    full = str(label_map.get(metric_id, metric_id))
    matches = list(re.finditer(r"\(([^)]*)\)", full))
    if not matches:
        return full
    for m in reversed(matches):
        inner = (m.group(1) or "").strip()
        if inner and inner != "%":
            return inner
    cleaned = re.sub(r"(\s*\(%\))+$", "", full).strip()
    return cleaned or full


def _bubble_symbol_sizes(raw: list[float | None]) -> list[float]:
    valid = [v for v in raw if v is not None]
    if not valid:
        return [20.0] * len(raw)
    mn, mx = min(valid), max(valid)
    if mx == mn:
        return [32.0 if v is not None else 12.0 for v in raw]
    out = []
    for v in raw:
        if v is None:
            out.append(12.0)
        else:
            out.append(12.0 + (float(v) - mn) / (mx - mn) * 48.0)
    return out


def _compare_toolbox() -> dict:
    # Only export-as-image — restore/dataZoom toolbox buttons rarely work in embedded
    # Streamlit ECharts and confuse users.
    # Larger icon + accent stroke so Download reads as a primary control (vs faint grey default).
    return {
        "show": True,
        "itemSize": 22,
        "iconStyle": {
            "borderColor": "#7c3aed",
            "borderWidth": 1.75,
        },
        "emphasis": {
            "iconStyle": {
                "borderColor": "#5b21b6",
                "borderWidth": 2.25,
                "shadowBlur": 8,
                "shadowColor": "rgba(124, 58, 237, 0.35)",
            },
        },
        "feature": {
            "saveAsImage": {"show": True, "title": "Download", "pixelRatio": 2},
        },
    }


def _metrics_fetch_loading_detail(detail_ph, message: str) -> None:
    """Single line inside the loading popup (plain text, escaped)."""
    detail_ph.markdown(
        '<p class="metrics-fetch-loading-detail" role="status" aria-live="polite">'
        f"{html.escape(message)}"
        "</p>",
        unsafe_allow_html=True,
    )


def _fetch_multi_author_metrics_with_progress(
    svc,
    resolved_ids: list[str],
    api_key_effective,
    year_key: str,
    am_payload: list,
    docs_key: str,
    self_cit: bool,
    *,
    detail_ph,
    flush_prog,
) -> list[dict]:
    """Load each author sequentially so the UI can show real progress (and respect direct-API pacing)."""
    n = len(resolved_ids)
    out: list[dict] = []
    for i, aid in enumerate(resolved_ids):
        _metrics_fetch_loading_detail(
            detail_ph,
            f"Fetching author {i + 1} of {n} ({aid})…",
        )
        flush_prog.progress((i + 1) / max(n, 1))
        try:
            d = svc.get_author_metrics(
                aid,
                api_key_effective,
                year_key,
                am_payload,
                docs_key,
                self_cit,
            )
            out.append(
                {
                    "id": aid,
                    "data": d,
                    "isEntitlementError": False,
                    "isRateLimitError": False,
                }
            )
        except APIError as ie:
            out.append(
                {
                    "id": aid,
                    "data": {
                        "error": str(ie),
                        "metrics": _placeholder_metrics(),
                    },
                    "isEntitlementError": ie.is_entitlement_error,
                    "isRateLimitError": ie.is_rate_limit_error,
                }
            )
        if USE_DIRECT_API and i < n - 1:
            time.sleep(1.0)
    return out


def _export_step_heading_html(step: int, text: str) -> str:
    """HTML for a numbered export step label; ``text`` is plain (escaped)."""
    badge = html.escape(f"({step})")
    text_esc = html.escape(text)
    return (
        f'<p class="export-step-label">'
        f'<span class="export-step-badge" aria-hidden="true">{badge}</span>'
        f'<span class="export-step-label-text">{text_esc}</span></p>'
    )


def _render_export_results_block(
    export_rows: list, n_valid: int, *, embedded_in_workspace: bool = False
) -> None:
    """Anchor, copy, filename, and PDF / Word / Excel downloads."""
    st.markdown(
        '<div id="export-downloads-anchor"></div>',
        unsafe_allow_html=True,
    )
    export_dl_hint = "Set the filename, then download PDF, Word, or Excel."
    export_body_sub = (
        f"{export_dl_hint} "
        "The file uses authors from (1) and metric rows plus order from (2)–(3)."
        if n_valid > 1
        else export_dl_hint
    )
    _shell_border = not embedded_in_workspace
    _shell_key = (
        "export_results_shell_bundle" if embedded_in_workspace else "export_results_shell"
    )
    with st.container(border=_shell_border, key=_shell_key):
        if embedded_in_workspace:
            st.markdown(
                '<div class="export-downloads-section">'
                '<p class="export-downloads-kicker">Downloads</p>'
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="export-results-head">'
                '<div class="export-results-head-row">'
                '<div class="export-results-badge" aria-hidden="true">'
                f"{_FILTER_ICON_DOCUMENT}"
                "</div>"
                '<div class="export-results-head-text">'
                '<p class="export-results-title">Export Options</p>'
                '<p class="export-results-sub">'
                f"{html.escape(export_body_sub)}"
                "</p>"
                "</div></div></div>",
                unsafe_allow_html=True,
            )
        fn = st.text_input(
            "Export filename (without extension)", value="research-metrics"
        )
        st.caption(export_body_sub)
        with st.container(border=False, key="export_download_row"):
            b1, b2, b3 = st.columns(3, gap="xxsmall")
            with b1:
                pdf_b, pdf_n = export_pdf_bytes(export_rows, fn)
                st.download_button(
                    "Export as PDF",
                    pdf_b,
                    file_name=pdf_n,
                    mime="application/pdf",
                    use_container_width=False,
                )
            with b2:
                doc_b, doc_n = export_docx_bytes(export_rows, fn)
                st.download_button(
                    "Export as Word",
                    doc_b,
                    file_name=doc_n,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=False,
                )
            with b3:
                xl_b, xl_n = export_excel_bytes(export_rows, fn)
                st.download_button(
                    "Export as Excel",
                    xl_b,
                    file_name=xl_n,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=False,
                )


def _render_single_author_export_workspace(
    export_rows: list,
    *,
    opt_list: list[str],
    label_map: dict[str, str],
    order_state_key: str,
    sortable_key: str,
    removed_key: str,
    author_id: str,
    author_name: object,
    metrics: object,
    data_source: object,
) -> None:
    """One workspace: bundle-style Export Options + filename + metric order + PDF/Word/Excel."""
    with st.container(border=False, key="export_workspace_stack"):
        st.markdown(
            '<div id="export-downloads-anchor"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            _export_options_heading_html(),
            unsafe_allow_html=True,
        )
        with st.container(border=True, key="export_results_shell_single"):
            _render_pick_via_metric_order_section(
                opt_list,
                label_map,
                order_state_key=order_state_key,
                sortable_key=sortable_key,
                removed_key=removed_key,
                step_order=None,
                embed_in_export_workspace=True,
            )
            _ord_final = [
                m for m in st.session_state.get(order_state_key, []) if m in opt_list
            ]
            export_rows.clear()
            if _ord_final:
                export_rows.append(
                    {
                        "authorId": author_id,
                        "authorName": author_name,
                        "metrics": metrics,
                        "dataSource": data_source,
                        "selectedMetrics": list(_ord_final),
                        "metricOrder": list(_ord_final),
                    }
                )
            fn = st.text_input(
                "Export filename (without extension)",
                value="research-metrics",
                key="export_fn_single_author_workspace",
            )
            if export_rows:
                st.caption("Set the filename, then download PDF, Word, or Excel.")
                with st.container(border=False, key="export_download_row"):
                    b1, b2, b3 = st.columns(3, gap="xxsmall")
                    with b1:
                        pdf_b, pdf_n = export_pdf_bytes(export_rows, fn)
                        st.download_button(
                            "Export as PDF",
                            pdf_b,
                            file_name=pdf_n,
                            mime="application/pdf",
                            use_container_width=False,
                            key="export_pdf_single_author_ws",
                        )
                    with b2:
                        doc_b, doc_n = export_docx_bytes(export_rows, fn)
                        st.download_button(
                            "Export as Word",
                            doc_b,
                            file_name=doc_n,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=False,
                            key="export_docx_single_author_ws",
                        )
                    with b3:
                        xl_b, xl_n = export_excel_bytes(export_rows, fn)
                        st.download_button(
                            "Export as Excel",
                            xl_b,
                            file_name=xl_n,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=False,
                            key="export_xlsx_single_author_ws",
                        )
            else:
                st.caption("Choose at least one metric in **Step 1** to export.")


def _sync_pick_via_metric_order_session(
    opt_list: list[str], order_state_key: str
) -> tuple[list[str], list[str], str]:
    """Seed session state for single-author metric order; no widgets."""
    removed_key = f"{order_state_key}__removed"
    raw_shown = st.session_state.get(order_state_key)
    raw_removed = st.session_state.get(removed_key)
    removed: list[str] = (
        [m for m in raw_removed if m in opt_list]
        if isinstance(raw_removed, list)
        else []
    )
    if isinstance(raw_shown, list):
        shown = [m for m in raw_shown if m in opt_list]
    else:
        shown = [m for m in opt_list if m not in removed]
    removed = [m for m in removed if m not in shown]
    for m in opt_list:
        if m not in shown and m not in removed:
            shown.append(m)
    st.session_state[order_state_key] = shown
    st.session_state[removed_key] = removed
    order_pick = list(shown)
    picked = list(order_pick)
    return picked, order_pick, removed_key


_METRIC_SORTABLE_STYLE = """
.sortable-component {
  border: 1px solid #dbeafe;
  border-radius: 10px;
  padding: 0.55rem;
  background: #f8fbff;
}
.sortable-container {
  background: transparent;
  border: 1px dashed #bfdbfe;
  border-radius: 10px;
  padding: 0.45rem;
}
.sortable-container-header {
  color: #334155;
  font-size: 0.82rem;
  font-weight: 700;
  padding: 0.15rem 0.2rem 0.45rem;
}
.sortable-container-body {
  min-height: 2.4rem;
}
.sortable-item, .sortable-item:hover {
  background: #e0ecff;
  border: 1px solid #bfd3ff;
  border-radius: 8px;
  color: #1f2937;
  cursor: grab;
  font-weight: 600;
  margin: 0.25rem 0;
  padding: 0.65rem 0.8rem;
}
.sortable-item.dragging {
  cursor: grabbing;
}
"""


def _metric_sortable_label_maps(
    metric_ids: list[str], label_map: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    labels = [label_map.get(mid, mid) for mid in metric_ids]
    duplicate_labels = {label for label in labels if labels.count(label) > 1}
    id_to_label: dict[str, str] = {}
    label_to_id: dict[str, str] = {}
    for mid in metric_ids:
        label = label_map.get(mid, mid)
        if label in duplicate_labels:
            label = f"{label} ({mid})"
        id_to_label[mid] = label
        label_to_id[label] = mid
    return id_to_label, label_to_id


def _restore_metric_to_multiselect(sortable_key: str, metric_id: str) -> None:
    """Append one metric id to the Step 1 multiselect widget session value."""
    wkey = f"{sortable_key}_visible_ms"
    cur = list(st.session_state.get(wkey, []))
    if metric_id not in cur:
        cur.append(metric_id)
    st.session_state[wkey] = cur


def _toggle_session_bool_key(key: str) -> None:
    st.session_state[key] = not bool(st.session_state.get(key, False))


def _render_metric_visibility_controls(
    *,
    opt_list: list[str],
    label_map: dict[str, str],
    order_state_key: str,
    removed_key: str,
    sortable_key: str,
    pick_heading_markdown: str | None = "**Pick metrics**",
    multiselect_label: str = "Metrics to display",
    show_all_visible_caption: bool = False,
) -> list[str]:
    active_ids = [m for m in st.session_state.get(order_state_key, []) if m in opt_list]
    # Only seed defaults when session has never set this list. If the user clears
    # all chips, order_state_key is [] and must stay empty (otherwise removing the
    # last chip repopulates all metrics and feels like a “double delete”).
    if order_state_key not in st.session_state:
        active_ids = [m for m in opt_list if m not in st.session_state.get(removed_key, [])]

    if pick_heading_markdown:
        st.markdown(pick_heading_markdown)
    selected_ids = st.multiselect(
        multiselect_label,
        options=opt_list,
        default=active_ids,
        format_func=lambda i: label_map.get(i, i),
        # Stable key: do not embed the selected set in the key — changing keys
        # remounts the widget and Streamlit reapplies default=, which often
        # needs a second click to persist chip removal.
        key=f"{sortable_key}_visible_ms",
        label_visibility="collapsed",
        help="Remove a chip to hide. Open the list to add it back.",
    )
    selected_ids = [m for m in selected_ids if m in opt_list]
    # Keep the user's existing display order for selected metrics, then append
    # any newly restored chips in the canonical option order.
    ordered_selected = [m for m in active_ids if m in selected_ids]
    ordered_selected.extend(
        m for m in opt_list if m in selected_ids and m not in ordered_selected
    )
    removed_ids = [m for m in opt_list if m not in ordered_selected]
    n_hidden = len(removed_ids)
    panel_key = f"{sortable_key}_restore_hidden_open"
    if n_hidden == 0:
        st.session_state.pop(panel_key, None)
        if show_all_visible_caption:
            st.caption("All metrics shown.")
    else:
        cap_col, btn_col = st.columns([3, 1], vertical_alignment="center")
        with cap_col:
            st.caption(
                f"**{n_hidden} hidden** — use the metric picker above, or **Show hidden metrics**."
            )
        with btn_col:
            open_panel = bool(st.session_state.get(panel_key))
            st.button(
                "Hide list" if open_panel else "Show hidden metrics",
                key=f"{sortable_key}_toggle_restore_hidden",
                help="Expand a list of hidden metrics and restore them with one click.",
                on_click=_toggle_session_bool_key,
                args=(panel_key,),
            )
        if st.session_state.get(panel_key):
            with st.container(border=True):
                st.caption(
                    "**Hidden metrics** — each row is currently off your table; "
                    "click **Restore** to add it back."
                )
                for mid in removed_ids:
                    lbl = label_map.get(mid, mid)
                    row_l, row_r = st.columns([4, 1], vertical_alignment="center")
                    with row_l:
                        st.text(str(lbl))
                    with row_r:
                        st.button(
                            "Restore",
                            key=f"{sortable_key}_restore_btn_{mid}",
                            on_click=_restore_metric_to_multiselect,
                            args=(sortable_key, mid),
                        )

    st.session_state[order_state_key] = ordered_selected
    st.session_state[removed_key] = removed_ids
    return ordered_selected


def _render_metric_sort_order(
    *,
    metric_ids: list[str],
    label_map: dict[str, str],
    order_state_key: str,
    sortable_key: str,
    header: str,
) -> list[str]:
    active_ids = [m for m in metric_ids if m]
    if not active_ids:
        st.info("No metrics to sort.")
        st.session_state[order_state_key] = []
        return []
    if sort_items is None:
        st.warning("Install `streamlit-sortables` (see requirements.txt) to drag-sort.")
        st.session_state[order_state_key] = active_ids
        return active_ids

    # Include the selected set in the key so removing a chip in Step 1 remounts the
    # sortable; otherwise streamlit-sortables keeps stale items for a stable key.
    _set_sig = hashlib.md5(",".join(sorted(active_ids)).encode()).hexdigest()[:12]
    id_to_label, label_to_id = _metric_sortable_label_maps(active_ids, label_map)
    sorted_labels = sort_items(
        [id_to_label[mid] for mid in active_ids],
        header=header,
        direction="vertical",
        custom_style=_METRIC_SORTABLE_STYLE,
        key=f"{sortable_key}_sort_{_set_sig}",
    )
    if isinstance(sorted_labels, list):
        ordered = [
            label_to_id[item]
            for item in sorted_labels
            if item in label_to_id
        ]
        _seen = set(ordered)
        ordered.extend(m for m in active_ids if m not in _seen)
        active_ids = ordered

    st.session_state[order_state_key] = active_ids
    return active_ids


def _render_pick_via_metric_order_section(
    opt_list: list[str],
    label_map: dict[str, str],
    *,
    order_state_key: str,
    sortable_key: str,
    removed_key: str,
    step_order: int | None = None,
    embed_in_export_workspace: bool = False,
) -> tuple[list[str], list[str]]:
    """Metric controls use chips for visibility and drag-and-drop for ordering."""
    _order_heading = (
        "Order" if len(opt_list) > 1 else "Display order (top to bottom)"
    )
    _pick_ms_label = (
        "Pick metrics" if len(opt_list) > 1 else "Metrics to display"
    )
    _sort_header = (
        "Sort metrics (drag and drop)"
        if len(opt_list) > 1
        else "Sort metrics"
    )
    if embed_in_export_workspace:
        pass
    elif step_order is not None:
        st.markdown(
            _export_step_heading_html(step_order, _order_heading),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"##### {_order_heading}")

    order_pick = _render_metric_visibility_controls(
        opt_list=opt_list,
        label_map=label_map,
        order_state_key=order_state_key,
        sortable_key=sortable_key,
        removed_key=removed_key,
        multiselect_label=_pick_ms_label,
    )
    st.markdown("**Order**")
    order_pick = _render_metric_sort_order(
        metric_ids=order_pick,
        label_map=label_map,
        order_state_key=order_state_key,
        sortable_key=sortable_key,
        header=_sort_header,
    )
    picked = list(order_pick)
    if not picked:
        st.caption("Pick at least one metric in **Step 1**.")
        return [], []
    return picked, order_pick


def _metrics_multiselect_and_order_ui(
    opt_list: list[str],
    label_map: dict[str, str],
    *,
    order_state_key: str,
    sortable_key: str,
    multiselect_label: str,
    step_multiselect: int | None = None,
    step_order: int | None = None,
) -> tuple[list[str], list[str]]:
    """Export bundle: metric chips with hidden restore panel + drag/drop ordering."""
    _multi_opts = len(opt_list) > 1
    eff_multiselect_label = (
        "Pick metrics"
        if _multi_opts
        else (multiselect_label or "Metrics to export")
    )
    eff_order_heading = (
        "Order" if _multi_opts else "Display order (top to bottom)"
    )
    eff_sort_header = (
        "Sort metrics (drag and drop)"
        if _multi_opts
        else "Sort metrics"
    )
    if step_multiselect is not None:
        st.markdown(
            _export_step_heading_html(step_multiselect, eff_multiselect_label),
            unsafe_allow_html=True,
        )
    removed_key = f"{order_state_key}__removed"
    picked_norm = _render_metric_visibility_controls(
        opt_list=opt_list,
        label_map=label_map,
        order_state_key=order_state_key,
        removed_key=removed_key,
        sortable_key=sortable_key,
        pick_heading_markdown=None,
        multiselect_label=eff_multiselect_label,
    )
    if not picked_norm:
        st.caption("Select at least one metric.")
        return [], []

    order_pick = list(picked_norm)

    if step_order is not None:
        st.markdown(
            _export_step_heading_html(step_order, eff_order_heading),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(eff_order_heading)

    order_pick = [m for m in order_pick if m in opt_list]
    order_pick = [m for m in order_pick if m in picked_norm]
    st.session_state[order_state_key] = order_pick

    order_pick = _render_metric_sort_order(
        metric_ids=order_pick,
        label_map=label_map,
        order_state_key=order_state_key,
        sortable_key=sortable_key,
        header=eff_sort_header,
    )

    order_pick = [m for m in st.session_state.get(order_state_key, []) if m in opt_list]
    picked = list(order_pick)
    st.session_state[order_state_key] = order_pick
    if not picked:
        st.caption("Select at least one metric.")
        return [], []
    return picked, order_pick


def _render_compare_authors_charts(valid: list, label_map: dict) -> None:
    """Multi-author line (years × metric) and bubble (X × Y × size totals) for len(valid) >= 2."""
    en = _enabled_metric_ids(st.session_state.available_metrics)
    order_opts = [
        "publication",
        "citationCount",
        "citationsPerPublication",
        "fwci",
        "topJournal",
        "hIndex",
        *list(COLLABORATION_SUBMETRIC_IDS),
        *list(ACADEMIC_CORPORATE_SUBMETRIC_IDS),
    ]
    compare_opts = [i for i in order_opts if i in en and i != "hIndex"]
    if len(valid) < 2 or not compare_opts:
        return

    year_lists = [
        _resolve_year_columns(r["data"].get("metrics") or {}, r["data"].get("dataSource"))
        for r in valid
    ]
    inter_years = _intersection_years(year_lists)

    def _pick_metric_idx(metric_id: str, default: str) -> int:
        try:
            return compare_opts.index(metric_id)
        except ValueError:
            try:
                return compare_opts.index(default)
            except ValueError:
                return 0

    # --- Line chart (multi-author): metric + chart type left, chart right ---
    st.markdown("##### Metrics by Year")
    with st.container(border=False, key="compare_trends_row"):
        col_filt, col_chart = st.columns([1, 3.5], gap="small", vertical_alignment="top")
        with col_filt:
            st.markdown(
                '<p class="compare-filter-mini">Metric</p>',
                unsafe_allow_html=True,
            )
            line_metric = st.selectbox(
                "Metric",
                options=compare_opts,
                index=_pick_metric_idx("publication", "fwci"),
                format_func=lambda i: label_map.get(i, i),
                key="compare_line_metric",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p class="compare-filter-mini" style="margin-top:0.45rem;">Chart type</p>',
                unsafe_allow_html=True,
            )
            line_chart_type = st.radio(
                "Chart type",
                options=["Line", "Bar"],
                horizontal=True,
                index=0,
                key="compare_line_type",
                label_visibility="collapsed",
            )
        line_short = _metric_short_label(label_map, line_metric)
        _line_is_pct = (
            line_metric == "topJournal"
            or line_metric in COLLABORATION_SUBMETRIC_IDS
            or line_metric in ACADEMIC_CORPORATE_SUBMETRIC_IDS
        )

        with col_chart:
            if not inter_years:
                st.caption(
                    "No overlapping years across authors. "
                    "Adjust search or year range so authors share a common window."
                )
            else:
                x_years = [str(y) for y in inter_years]
                line_series = []
                symbols = ["circle", "rect", "triangle", "diamond", "roundRect", "pin"]
                for idx, r in enumerate(valid):
                    mp = r["data"].get("metrics") or {}
                    by_y = _extract_metric_by_year(mp, line_metric)
                    if not by_y:
                        continue
                    author_name = r["data"].get("authorName") or f"Author {r['id']}"
                    vals = []
                    for y in inter_years:
                        v = by_y.get(str(y))
                        if v is None or (isinstance(v, (int, float)) and pd.isna(v)):
                            vals.append(None)
                        else:
                            vals.append(v)
                    ser: dict = {
                        "name": author_name,
                        "type": line_chart_type.lower(),
                        "data": vals,
                        "symbol": symbols[idx % len(symbols)],
                        "symbolSize": 8,
                        "smooth": line_chart_type == "Line",
                    }
                    if line_chart_type == "Bar":
                        ser["label"] = {
                            "show": True,
                            "position": "top",
                            "formatter": "{c}%" if _line_is_pct else "{c}",
                            "fontSize": 11,
                            "color": "#334155",
                        }
                    line_series.append(ser)
                if line_series:
                    toolbox_line = _compare_toolbox()
                    toolbox_line["right"] = 40
                    toolbox_line["top"] = 8
                    line_legend_rows = max(1, (len(line_series) + 4) // 5)
                    line_grid_top = 128 + max(0, line_legend_rows - 1) * 22
                    _yaxis_line = {
                        "type": "value",
                        "name": (f"{line_short} (%)" if _line_is_pct else line_short),
                        "nameLocation": "middle",
                        "nameGap": 58,
                        "nameRotate": 90,
                        "nameTextStyle": {"fontSize": 11, "color": "#475569"},
                    }
                    if _line_is_pct:
                        _yaxis_line["axisLabel"] = {"formatter": "{value}%"}
                    line_opts = {
                        "animation": True,
                        "title": {
                            "text": "Metrics by Year",
                            "subtext": line_short,
                            "left": "center",
                            "top": 8,
                            "textStyle": {
                                "fontSize": 15,
                                "fontWeight": 600,
                                "color": "#1e293b",
                            },
                            "subtextStyle": {"fontSize": 11, "color": "#64748b"},
                        },
                        "tooltip": {"trigger": "axis"},
                        "legend": {
                            "type": "plain",
                            "orient": "horizontal",
                            "top": 56,
                            "left": 20,
                            "right": 118,
                            "data": [s["name"] for s in line_series],
                            "itemWidth": 12,
                            "itemHeight": 12,
                            "itemGap": 14,
                            "padding": [4, 8, 2, 8],
                            "textStyle": {"fontSize": 10, "lineHeight": 15},
                        },
                        "toolbox": toolbox_line,
                        "grid": {
                            "left": "10%",
                            "right": "8%",
                            "top": line_grid_top,
                            "bottom": 78,
                            "containLabel": True,
                        },
                        "xAxis": {
                            "type": "category",
                            "name": "Year",
                            "nameLocation": "middle",
                            "nameGap": 32,
                            "nameTextStyle": {"fontSize": 11, "color": "#475569"},
                            "data": x_years,
                        },
                        "yAxis": _yaxis_line,
                        "series": line_series,
                        "dataZoom": [
                            {"type": "inside"},
                            {"type": "slider", "height": 16, "bottom": 12},
                        ],
                    }
                    st_echarts(
                        options=line_opts,
                        height="600px",
                        key=f"compare_line_v2_{line_metric}_{line_chart_type}",
                    )
                    def _fmt_line_val(v) -> str:
                        if v is None or (isinstance(v, (int, float)) and pd.isna(v)):
                            return "N/A"
                        if isinstance(v, (int, float)):
                            if _line_is_pct:
                                if v % 1 == 0:
                                    return f"{int(v)}%"
                                s = f"{float(v):.2f}".rstrip("0").rstrip(".")
                                return f"{s}%"
                            return f"{v:.4f}".rstrip("0").rstrip(".")
                        return str(v)

                    trends_tbl = pd.DataFrame(
                        [
                            {
                                "Author": s["name"],
                                **{
                                    x_years[i]: _fmt_line_val(s["data"][i])
                                    for i in range(len(x_years))
                                },
                            }
                            for s in line_series
                        ]
                    )
                    st.caption(
                        f"Values used in trends chart ({label_map.get(line_metric, line_metric)} by year):"
                    )
                    st.dataframe(trends_tbl, use_container_width=True, hide_index=True)
                    trends_stub = re.sub(
                        r"[^a-z0-9]+",
                        "-",
                        f"trends-by-years-{line_metric}-{line_chart_type}".lower(),
                    ).strip("-")
                    st.download_button(
                        "Download trends table (.csv)",
                        data=trends_tbl.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"{trends_stub}.csv",
                        mime="text/csv",
                        key=f"dl_trends_tbl_csv_{line_metric}_{line_chart_type}",
                        use_container_width=True,
                    )
                else:
                    st.caption(
                        "No series to plot for this metric (missing year data for all authors)."
                    )

    st.divider()

    # --- Bubble chart (three dimensions: SciVal period totals, no year) ---
    st.markdown("##### Benchmarking (Bubble chart)")
    st.caption(
        "Values on both axes and for bubble size are **Total** values for your selected "
        "metric window, not for a single calendar year."
    )
    bubble_metric_opts = [i for i in order_opts if i in en]

    def _bubble_default_axis_indices(opts: list[str]) -> tuple[int, int, int]:
        """Defaults for X, Y, bubble size: prefer FWCI on X when enabled, all three distinct."""
        if len(opts) < 3:
            return (0, min(1, len(opts) - 1), min(2, len(opts) - 1))
        prefer = [
            "fwci",
            "topJournal",
            "publication",
            "citationCount",
            "citationsPerPublication",
            "hIndex",
        ]
        x_id = next((p for p in prefer if p in opts), opts[0])
        y_id = next((p for p in prefer if p in opts and p != x_id), None)
        if y_id is None:
            y_id = next((p for p in opts if p != x_id), opts[0])
        z_id = next((p for p in prefer if p in opts and p not in (x_id, y_id)), None)
        if z_id is None:
            z_id = next((p for p in opts if p not in (x_id, y_id)), opts[0])
        return (opts.index(x_id), opts.index(y_id), opts.index(z_id))

    if len(bubble_metric_opts) < 3:
        st.caption(
            "Enable at least three metrics in Settings to map X, Y, and bubble size."
        )
        return

    _ix, _iy, _iz = _bubble_default_axis_indices(bubble_metric_opts)

    with st.container(border=False, key="compare_bubble_row"):
        col_bfilt, col_bchart = st.columns(
            [1, 3.5], gap="small", vertical_alignment="top"
        )
        with col_bfilt:
            st.markdown(
                '<p class="compare-filter-mini">X-axis</p>',
                unsafe_allow_html=True,
            )
            x_metric = st.selectbox(
                "X-axis",
                options=bubble_metric_opts,
                index=_ix,
                format_func=lambda i: label_map.get(i, i),
                key="compare_bubble_x_v3",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p class="compare-filter-mini" style="margin-top:0.45rem;">Y-axis</p>',
                unsafe_allow_html=True,
            )
            y_metric = st.selectbox(
                "Y-axis",
                options=bubble_metric_opts,
                index=_iy,
                format_func=lambda i: label_map.get(i, i),
                key="compare_bubble_y_v3",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p class="compare-filter-mini" style="margin-top:0.45rem;">Bubble size</p>',
                unsafe_allow_html=True,
            )
            size_metric = st.selectbox(
                "Bubble size",
                options=bubble_metric_opts,
                index=_iz,
                format_func=lambda i: label_map.get(i, i),
                key="compare_bubble_size_v3",
                label_visibility="collapsed",
            )

        with col_bchart:
            if len({x_metric, y_metric, size_metric}) < 3:
                st.warning(
                    "Choose three different metrics for X, Y, and bubble size."
                )
            else:
                y_lbl = _metric_short_label(label_map, y_metric)
                x_lbl = _metric_short_label(label_map, x_metric)
                sz_lbl = _metric_short_label(label_map, size_metric)
                x_name = label_map.get(x_metric, x_metric)
                y_name = label_map.get(y_metric, y_metric)
                z_name = label_map.get(size_metric, size_metric)

                plotted: list[tuple[str, float, float, float]] = []
                for r in valid:
                    mp = r["data"].get("metrics") or {}
                    xv = _scalar_metric_total(mp, x_metric)
                    yv = _scalar_metric_total(mp, y_metric)
                    sv = _scalar_metric_total(mp, size_metric)
                    if xv is None or yv is None or sv is None:
                        continue
                    author_name = r["data"].get("authorName") or f"Author {r['id']}"
                    plotted.append((author_name, xv, yv, sv))

                if not plotted:
                    st.caption(
                        "No complete Total values for all three metrics. "
                        "Try other metrics or confirm the API returned totals."
                    )
                else:

                    def _bubble_pct_metric(mid: str) -> bool:
                        return (
                            mid == "topJournal"
                            or mid in COLLABORATION_SUBMETRIC_IDS
                            or mid in ACADEMIC_CORPORATE_SUBMETRIC_IDS
                        )

                    def _fmt_bubble_val(v: float, mid: str) -> str:
                        if _bubble_pct_metric(mid):
                            if v % 1 == 0:
                                return f"{int(v)}%"
                            s = f"{float(v):.2f}".rstrip("0").rstrip(".")
                            return f"{s}%"
                        if float(v).is_integer():
                            return str(int(v))
                        return f"{v:.4f}".rstrip("0").rstrip(".")

                    _x_pct = _bubble_pct_metric(x_metric)
                    _y_pct = _bubble_pct_metric(y_metric)
                    _z_pct = _bubble_pct_metric(size_metric)

                    size_px = _bubble_symbol_sizes([p[3] for p in plotted])

                    bubble_series = []
                    for i, (author_name, xv, yv, sv) in enumerate(plotted):
                        tooltip_text = (
                            f"{author_name}\n"
                            f"{y_name}: {_fmt_bubble_val(yv, y_metric)}\n"
                            f"{x_name}: {_fmt_bubble_val(xv, x_metric)}\n"
                            f"{z_name}: {_fmt_bubble_val(sv, size_metric)}"
                        )
                        bubble_series.append(
                            {
                                "name": author_name,
                                "type": "scatter",
                                "data": [{"name": tooltip_text, "value": [xv, yv, sv]}],
                                "symbolSize": size_px[i],
                                "itemStyle": {"opacity": 0.78},
                                "label": {
                                    "show": True,
                                    "position": "top",
                                    "formatter": author_name,
                                    "fontSize": 11,
                                },
                            }
                        )

                    toolbox_bubble = _compare_toolbox()
                    toolbox_bubble["right"] = 40
                    toolbox_bubble["top"] = 8

                    bubble_opts = {
                        "animation": True,
                        "title": {
                            "text": f"{y_lbl} vs {x_lbl}",
                            "subtext": (
                                f"Bubble size: {sz_lbl} (%) (period totals)"
                                if _z_pct
                                else f"Bubble size: {sz_lbl} (period totals)"
                            ),
                            "left": "center",
                            "top": 6,
                            "textStyle": {"fontSize": 15, "color": "#1e293b"},
                            "subtextStyle": {"fontSize": 11, "color": "#64748b"},
                        },
                        "grid": {
                            "left": "6%",
                            "right": "4%",
                            "top": 128,
                            "bottom": 118,
                            "containLabel": True,
                        },
                        "tooltip": {
                            "trigger": "item",
                            "renderMode": "richText",
                            "textStyle": {"lineHeight": 20},
                            "formatter": "{b}",
                        },
                        "legend": {
                            "type": "plain",
                            "data": [s["name"] for s in bubble_series],
                            "top": 52,
                            "left": "center",
                            "itemWidth": 10,
                            "itemHeight": 10,
                            "itemGap": 8,
                            "textStyle": {"fontSize": 10},
                        },
                        "toolbox": toolbox_bubble,
                        "xAxis": {
                            "type": "value",
                            "name": (f"{x_name} (%)" if _x_pct else x_name),
                            "nameLocation": "middle",
                            "nameGap": 40,
                            "nameTextStyle": {
                                "fontSize": 11,
                                "color": "#475569",
                                "padding": [0, 0, 4, 0],
                            },
                            "axisLabel": (
                                {"margin": 10, "formatter": "{value}%"}
                                if _x_pct
                                else {"margin": 10}
                            ),
                            # ECharts default scale=True zooms positive-only data and often omits 0 — OK for FWCI-style axes,
                            # but percentage metrics read better with a true 0% baseline.
                            **({"min": 0, "scale": False} if _x_pct else {"scale": True}),
                        },
                        "yAxis": {
                            "type": "value",
                            "name": (f"{y_name} (%)" if _y_pct else y_name),
                            "nameLocation": "middle",
                            "nameGap": 46,
                            "nameRotate": 90,
                            "nameTextStyle": {"fontSize": 11, "color": "#475569"},
                            **(
                                {"axisLabel": {"formatter": "{value}%"}}
                                if _y_pct
                                else {}
                            ),
                            **({"min": 0, "scale": False} if _y_pct else {"scale": True}),
                        },
                        "series": bubble_series,
                        "dataZoom": [
                            {"type": "inside"},
                            {
                                "type": "slider",
                                "xAxisIndex": 0,
                                "height": 22,
                                "bottom": 8,
                            },
                        ],
                    }
                    st_echarts(
                        options=bubble_opts,
                        height="580px",
                        key=f"bubble_{x_metric}_{y_metric}_{size_metric}_totals",
                    )

                    tbl_df = pd.DataFrame(
                        [
                            {
                                "Author": p[0],
                                x_lbl: p[1],
                                y_lbl: p[2],
                                sz_lbl: p[3],
                            }
                            for p in plotted
                        ]
                    )
                    tbl_df[x_lbl] = tbl_df[x_lbl].map(lambda v: _fmt_bubble_val(float(v), x_metric))
                    tbl_df[y_lbl] = tbl_df[y_lbl].map(lambda v: _fmt_bubble_val(float(v), y_metric))
                    tbl_df[sz_lbl] = tbl_df[sz_lbl].map(lambda v: _fmt_bubble_val(float(v), size_metric))
                    st.caption(
                        "Period totals or averages used for position and bubble size "
                        "(same search window as your results):"
                    )
                    st.dataframe(
                        tbl_df, use_container_width=True, hide_index=True
                    )
                    # Bubble totals quick export (same data shown in table).
                    export_stub = re.sub(
                        r"[^a-z0-9]+",
                        "-",
                        f"bubble-totals-{x_metric}-{y_metric}-{size_metric}".lower(),
                    ).strip("-")
                    csv_bytes = tbl_df.to_csv(index=False).encode("utf-8-sig")

                    st.download_button(
                        "Download bubble totals (.csv)",
                        data=csv_bytes,
                        file_name=f"{export_stub}.csv",
                        mime="text/csv",
                        key=f"dl_bubble_totals_csv_{x_metric}_{y_metric}_{size_metric}",
                        use_container_width=True,
                    )


def _merge_scopus_author_id_into_search_box(new_id: str) -> str:
    """Merge resolved ID into ``scopus_author_ids``. Returns ``added``, ``duplicate``, or ``noop``."""
    new_id = (new_id or "").strip()
    if not new_id:
        return "noop"
    existing = (st.session_state.get("scopus_author_ids") or "").strip()
    if not existing:
        st.session_state.scopus_author_ids = new_id
        return "added"
    parts = [x.strip() for x in re.split(r"[,\n;]+", existing) if x.strip()]
    if new_id in parts:
        return "duplicate"
    if "\n" in existing:
        sep = "\n"
    elif "," in existing:
        sep = ", "
    else:
        sep = "\n"
    st.session_state.scopus_author_ids = existing + sep + new_id
    return "added"


def _invoke_notice_dialog(body: str, *, variant: str = "warning") -> None:
    """Centered Notice modal (warning | error | info); dismiss with OK."""
    st.session_state["_notice_dialog_body"] = body
    st.session_state["_notice_dialog_variant"] = variant
    _render_notice_dialog()


@st.dialog("Notice")
def _render_notice_dialog() -> None:
    body = str(st.session_state.get("_notice_dialog_body") or "")
    variant = str(st.session_state.get("_notice_dialog_variant") or "warning")
    if variant == "error":
        st.error(body)
    elif variant == "info":
        st.info(body)
    else:
        st.warning(body)
    _ok_l, _ok_c, _ok_r = st.columns([1, 2, 1])
    with _ok_c:
        if st.button(
            "OK",
            type="primary",
            use_container_width=True,
            key="notice_dialog_ok",
        ):
            st.session_state.pop("_notice_dialog_body", None)
            st.session_state.pop("_notice_dialog_variant", None)
            st.rerun()


def _render_find_scopus_author_id_help(api_key_effective: str | None) -> None:
    """HKUST Research Portal, Scopus lookup, optional ORCID → Scopus Author ID."""
    with st.container(border=False, key="find_scopus_help_panel"):
        st.markdown(
            '<div class="find-scopus-banner" role="heading" aria-level="3">'
            '<span class="minimal-filter-icon-badge minimal-filter-icon-badge--person '
            'find-scopus-banner-badge" aria-hidden="true">'
            f"{_FILTER_ICON_PERSON}</span>"
            "<span>Find Scopus Author ID</span></div>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.markdown("**For HKUST Researchers (Selected)**")
            st.caption(
                "Browse HKUST researcher profiles to find Scopus Author IDs."
            )
            st.image(
                str(_ROOT / "Scholar_Profiles.png"),
                use_container_width=True,
            )
            st.link_button(
                "Open HKUST Research Portal",
                "https://researchportal.hkust.edu.hk/en/persons/",
                icon=":material/open_in_new:",
                use_container_width=True,
            )
        with st.container(border=True):
            st.markdown("**For non-HKUST researchers**")
            st.markdown(
                "To find a Scopus Author profile and ID, search on Scopus using these steps:"
            )
            st.markdown(
                "1. Go to [Scopus](https://www.scopus.com/home.uri) and click **Author Search**.\n\n"
                "2. Enter a **first name**, **last name**, and **affiliation**, then click **Search**.\n\n"
                "3. Open the matching record to view the Scopus Author ID."
            )
            st.link_button(
                "Open Scopus",
                "https://www.scopus.com/home.uri",
                icon=":material/open_in_new:",
                use_container_width=True,
            )
        with st.container(border=True):
            st.markdown("**Find by ORCID**")
            st.markdown(
                "About ORCID: [https://orcid.org/](https://orcid.org/)"
            )
            _orch = st.text_input(
                "ORCID Identifier",
                placeholder="XXXX-XXXX-XXXX-XXXX (16-digit identifier)",
                key="find_scopus_orcid_input",
            )
            if st.button(
                "Find Scopus Author ID",
                key="find_scopus_orcid_submit",
                type="secondary",
                use_container_width=True,
            ):
                if not api_key_effective:
                    _invoke_notice_dialog(
                        "Add a SciVal API key in the sidebar (or environment) to look up ORCID."
                    )
                elif not (_orch or "").strip():
                    _invoke_notice_dialog(
                        "Enter an ORCID (16-digit identifier or URL)."
                    )
                else:
                    try:
                        sid, name = lookup_scopus_id_from_orcid(
                            _orch, api_key_effective
                        )
                        _action = _merge_scopus_author_id_into_search_box(sid)
                        _nm = (name or "").strip()
                        if _action == "duplicate":
                            _invoke_notice_dialog(
                                f"Scopus Author ID **{sid}** is already in the search box."
                                + (f" ({_nm})" if _nm else ""),
                                variant="info",
                            )
                        else:
                            st.success(
                                f"Added Scopus Author ID **{sid}** to the search box."
                                + (f" ({_nm})" if _nm else "")
                            )
                    except APIError as e:
                        _invoke_notice_dialog(
                            format_error_message_for_user(str(e)),
                            variant="error",
                        )


def main() -> None:
    _init_session()
    _inject_theme_css()

    with st.sidebar:
        st.markdown('<p class="section-kicker">Settings</p>', unsafe_allow_html=True)
        st.markdown("### API mode")
        _mode_caption = (
            "Direct API" if USE_DIRECT_API else "Supabase proxy (set VITE_USE_DIRECT_API=true for direct)."
        )
        if (SCIVAL_HTTP_PROXY or "").strip():
            _mode_caption += " SciVal traffic uses SCIVAL_HTTP_PROXY (Elsevier via institutional proxy)."
        st.caption(_mode_caption)
        custom_key = st.text_input(
            "Optional SciVal API key",
            type="password",
            help="Overrides env key for this session only.",
        )
        api_key_effective = (custom_key or SCIVAL_API_KEY or "").strip() or None

    _render_header_html()

    if not st.session_state.disclaimer_ok:
        st.markdown(
            """
<div class="disclaimer-card-wrap">
  <div class="disclaimer-card">
    <p class="disclaimer-heading"><span aria-hidden="true">⚠️</span> Research Impact Dashboard — Disclaimer</p>
    <p>
      This dashboard provides a high-level summary of research-impact indicators using Elsevier&rsquo;s SciVal APIs.
      It is intended as a starting point for exploration, not a substitute for the full SciVal platform.
      For granular benchmarking and comprehensive longitudinal data, please consult the
      <a href="https://lbdiscover.hkust.edu.hk/bib/991012525864503412" target="_blank" rel="noopener noreferrer">SciVal platform</a> via HKUST Library.
    </p>
    <p>
      <strong>Important: Metric accuracy depends on a correct Scopus Author ID and profile. We strongly recommend
      verifying your profile so that citations and publications are attributed correctly.</strong>
    </p>
    <p>
      Where institutional policy governs hiring, reappointment, tenure, or promotion, do not rely on this dashboard
      alone; follow unit- and university-approved evidence and procedures.
    </p>
    <div class="disclaimer-links">
      Resources:
      <a href="https://researchportal.hkust.edu.hk/" target="_blank" rel="noopener noreferrer">HKUST Research Portal</a>
      &nbsp;&middot;&nbsp;
      <a href="https://www.elsevier.com/solutions/scopus/how-scopus-works/author-profile-updates" target="_blank" rel="noopener noreferrer">Manage Scopus ID</a>
      &nbsp;&middot;&nbsp;
      <a href="https://libguides.hkust.edu.hk/research-impact/author-impact" target="_blank" rel="noopener noreferrer">Metric Guidance</a>
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Acknowledge & continue", type="primary", key="disclaimer_ack"):
            st.session_state.disclaimer_ok = True
            st.rerun()
        st.stop()

    # --- Search + filters + metrics (compact search/filter shell) ---
    analyze_metrics_inline = False
    with st.container():
        with st.container(border=True, key="search_shell"):
            # Extra width on the right so “Find Scopus Author ID” fits on one line
            _hdr_l, _hdr_r = st.columns([11, 5])
            with _hdr_l:
                st.markdown(
                    '<p class="search-config-title">Enter Scopus Author ID, select '
                    "Search Scope and Metrics</p>",
                    unsafe_allow_html=True,
                )
            with _hdr_r:
                _panel_open = bool(st.session_state.get("find_scopus_panel_open"))
                _find_scopus_icon = (
                    ":material/chevron_right:"
                    if _panel_open
                    else ":material/expand_more:"
                )
                if st.button(
                    "Find Scopus Author ID",
                    key="toggle_find_scopus_panel",
                    use_container_width=True,
                    type="secondary",
                    icon=_find_scopus_icon,
                ):
                    st.session_state.find_scopus_panel_open = not _panel_open

            if st.session_state.get("find_scopus_panel_open"):
                _render_find_scopus_author_id_help(api_key_effective)

            _raw_header_ids = st.session_state.get("scopus_author_ids") or ""
            _parsed_header_ids = [
                x.strip() for x in re.split(r"[,\n;]+", _raw_header_ids) if x.strip()
            ]
            _limit_cls_header = (
                "author-limit-hint--warn"
                if len(_parsed_header_ids) > MAX_AUTHORS_PER_RUN
                else "author-limit-hint--ok"
            )
            st.markdown(
                '<div class="author-input-header-row">'
                '<span class="author-input-header-title">Scopus Author ID</span>'
                '<div class="author-limit-hint author-limit-hint-inline '
                f'{_limit_cls_header}"><span class="minimal-filter-icon-badge '
                'minimal-filter-icon-badge--compact minimal-filter-icon-badge--users '
                f'author-limit-icon" aria-hidden="true">{_FILTER_ICON_USERS}</span>'
                "<span><strong>Search up to "
                f"{MAX_AUTHORS_PER_RUN} author IDs in one run.</strong> "
                "Use commas, semicolons, or line breaks to separate entries. "
                '<span class="author-limit-count">'
                f"{len(_parsed_header_ids)}/{MAX_AUTHORS_PER_RUN} entered"
                "</span></span></div></div>",
                unsafe_allow_html=True,
            )
            author_ids = st.text_area(
                "Scopus Author ID",
                placeholder=(
                    "Enter Scopus Author ID(s). Don't know your ID? "
                    "Use Find Scopus Author ID above."
                ),
                label_visibility="collapsed",
                key="scopus_author_ids",
                height=96,
            )
            parsed_author_ids = [
                x.strip() for x in re.split(r"[,\n;]+", author_ids) if x.strip()
            ]

            fy, fd, fs = st.columns(3, gap="small")
            with fy:
                st.markdown(
                    '<div class="minimal-filter-label">'
                    f'<span class="minimal-filter-icon-badge minimal-filter-icon-badge--calendar" '
                    f'aria-hidden="true">{_FILTER_ICON_CALENDAR}</span>'
                    '<span class="year-filter-label-with-tip">'
                    "<span>Year</span>"
                    '<span class="year-filter-tip" tabindex="0" role="button" '
                    'aria-label="Year range information, details in tooltip">'
                    f'<span class="minimal-filter-icon-badge minimal-filter-icon-badge--compact minimal-filter-icon-badge--info year-filter-tip-marker" aria-hidden="true">{_FILTER_ICON_INFO_SMALL}</span>'
                    '<span class="year-filter-tip-popup" role="tooltip" '
                    'id="year-range-options-tooltip">'
                    f"{YEAR_FILTER_LABEL_TOOLTIP_HTML}"
                    "</span></span></span></div>",
                    unsafe_allow_html=True,
                )
                _year_help_key = st.session_state.get("year_filter_select", "5yrs")
                year_key = st.selectbox(
                    "Year",
                    options=list(YEAR_OPTIONS.keys()),
                    format_func=lambda k: YEAR_OPTIONS_DISPLAY[k],
                    index=list(YEAR_OPTIONS.keys()).index("5yrs"),
                    label_visibility="collapsed",
                    key="year_filter_select",
                    help=YEAR_SELECT_HELP.get(
                        _year_help_key, YEAR_SELECT_HELP["5yrs"]
                    ),
                )
            with fd:
                st.markdown(
                    '<div class="minimal-filter-label">'
                    f'<span class="minimal-filter-icon-badge minimal-filter-icon-badge--document" '
                    f'aria-hidden="true">{_FILTER_ICON_DOCUMENT}</span><span>Document Type</span></div>',
                    unsafe_allow_html=True,
                )
                docs_key = st.selectbox(
                    "Document Type",
                    options=list(DOCS_OPTIONS.keys()),
                    format_func=lambda k: DOCS_OPTIONS_DISPLAY[k],
                    label_visibility="collapsed",
                    key="docs_filter_select",
                )
            with fs:
                st.markdown(
                    '<div class="minimal-filter-label">'
                    f'<span class="minimal-filter-icon-badge minimal-filter-icon-badge--funnel" '
                    f'aria-hidden="true">{_FILTER_ICON_FUNNEL}</span>'
                    '<span class="year-filter-label-with-tip">'
                    "<span>Self-citations</span>"
                    '<span class="year-filter-tip" tabindex="0" role="button" '
                    'aria-label="Self-citations information, details in tooltip">'
                    f'<span class="minimal-filter-icon-badge minimal-filter-icon-badge--compact '
                    'minimal-filter-icon-badge--info year-filter-tip-marker" aria-hidden="true">'
                    f"{_FILTER_ICON_INFO_SMALL}</span>"
                    '<span class="year-filter-tip-popup" role="tooltip" '
                    'id="self-citations-tooltip">'
                    f"{SELF_CIT_LABEL_TOOLTIP_HTML}"
                    "</span></span></span></div>",
                    unsafe_allow_html=True,
                )
                st.radio(
                    " ",
                    options=["include", "exclude"],
                    format_func=lambda k: SELF_CIT_RADIO_LABELS[k],
                    horizontal=True,
                    key="self_cit_radio",
                    label_visibility="collapsed",
                )
                self_cit = st.session_state.self_cit_radio == "include"

            # --- Metrics (same bordered search configuration section) ---
            with st.container(border=False, key="metrics_panel_shell"):
                st.markdown(
                    '<span class="skin-metrics-panel-shell" aria-hidden="true"></span>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="metrics-panel-heading-row">'
                    '<span class="minimal-filter-icon-badge minimal-filter-icon-badge--compact '
                    'minimal-filter-icon-badge--metrics metrics-panel-heading-icon" '
                    f'aria-hidden="true">{_FILTER_ICON_METRICS_MENU}</span>'
                    '<p class="metrics-panel-heading metrics-panel-heading-inline '
                    'metrics-panel-heading-scrollstrip">'
                    '<span class="metrics-panel-heading-lead">'
                    "<span>Select Metrics</span>"
                    "</span>"
                    '<span class="metrics-panel-head-caption-inline">(Toggle metrics on/off)</span>'
                    "</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )

                am = st.session_state.available_metrics
                # Seed ``met_*`` in session before toggles; each toggle also passes
                # ``value=`` so new widgets default on (serde default is otherwise False).
                for m in am:
                    mk = f"met_{m['id']}"
                    if mk not in st.session_state:
                        st.session_state[mk] = DEFAULT_METRIC_TOGGLE_DEFAULT.get(
                            m["id"], False
                        )
                    m["enabled"] = bool(st.session_state[mk])
                with st.container(border=False, key="metrics_toolbar_shell"):
                    # Select/Clear toolbar buttons are intentionally hidden.
                    # Keep count bar synced with current toggle state.
                    for m in am:
                        _mk = f"met_{m['id']}"
                        if _mk not in st.session_state:
                            st.session_state[_mk] = DEFAULT_METRIC_TOGGLE_DEFAULT.get(
                                m["id"], False
                            )
                        m["enabled"] = bool(st.session_state[_mk])
                    n_on = sum(1 for m in am if m.get("enabled"))
                    st.markdown(
                        f'<span class="metrics-count-bar">{n_on} of {len(am)} metrics selected</span>',
                        unsafe_allow_html=True,
                    )

                core_metrics = _metrics_for_panel_ordered(am, METRIC_IDS_CORE)
                collab_metrics = _metrics_for_panel_ordered(am, METRIC_IDS_COLLABORATIVE)

                with st.container(border=False, key="metrics_grid_shell"):
                    with st.expander(
                        "Metrics (Default)",
                        expanded=True,
                        icon=":material/analytics:",
                    ):
                        _render_metric_toggle_grid_rows(
                            core_metrics, "metrics_grid_row_core"
                        )
                    with st.expander(
                        "More Metrics",
                        expanded=False,
                        icon=":material/hub:",
                    ):
                        _render_metric_toggle_grid_rows(
                            collab_metrics, "metrics_grid_row_collab"
                        )

            st.markdown(
                '<div class="minimal-section-divider"></div>',
                unsafe_allow_html=True,
            )
            _, _analyze_inline_col, _ = st.columns([1, 2, 1])
            with _analyze_inline_col:
                analyze_metrics_inline = st.button(
                    "📊 Analyze Metrics",
                    type="primary",
                    use_container_width=True,
                    key="analyze_metrics_inline",
                )

        st.markdown(
            '<div id="analyze-metrics-anchor" class="analyze-anchor-tight"></div>',
            unsafe_allow_html=True,
        )
        if not st.session_state.get("_deep_link_analyze_injected"):
            st.session_state._deep_link_analyze_injected = True
            components.html(_DEEP_LINK_ANALYZE_HTML, height=0, width=0)
        if analyze_metrics_inline:
            st.session_state.error_msg = ""
            st.session_state.entitlement_error = False
            st.session_state.rate_limit_error = False
            st.session_state.results = []
            # Parsed with same separators shown in the author input hint.
            ids = parsed_author_ids
            selected_metric_count = sum(
                1 for m in st.session_state.available_metrics if m.get("enabled")
            )
            if not ids:
                _invoke_notice_dialog("Enter at least one Scopus author ID.")
            elif selected_metric_count == 0:
                _invoke_notice_dialog("Turn on at least one metric (all are off).")
            elif len(ids) > MAX_AUTHORS_PER_RUN:
                _invoke_notice_dialog(
                    f"Please limit to {MAX_AUTHORS_PER_RUN} Scopus Author IDs per run."
                )
            else:
                svc = get_api_service()
                am_payload = [dict(m) for m in st.session_state.available_metrics]
                _metrics_fetch_loading_ph = st.empty()
                try:
                    with _metrics_fetch_loading_ph.container():
                        with st.container(key="metrics_fetch_loading_overlay"):
                            with st.container(key="metrics_fetch_loading_inner"):
                                st.markdown(
                                    '<p class="metrics-fetch-loading-title">'
                                    "Fetching metrics…"
                                    "</p>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    '<p class="metrics-fetch-loading-hint">'
                                    "SciVal can take up to ~1 min; retry on timeout."
                                    "</p>",
                                    unsafe_allow_html=True,
                                )
                                _hold_on_gif = _ROOT / "hold-on.gif"
                                if _hold_on_gif.exists():
                                    _g_l, _g_c, _g_r = st.columns([3, 2, 3])
                                    with _g_c:
                                        try:
                                            _gif_b64 = base64.b64encode(
                                                _hold_on_gif.read_bytes()
                                            ).decode("ascii")
                                            st.markdown(
                                                '<div style="display:flex;justify-content:center;">'
                                                f'<img src="data:image/gif;base64,{_gif_b64}" alt="Loading" '
                                                'style="width:96px;height:96px;object-fit:contain;" />'
                                                "</div>",
                                                unsafe_allow_html=True,
                                            )
                                        except OSError:
                                            st.caption("Loading…")
                                _detail_ph = st.empty()
                                _flush_prog = st.progress(0)

                    _metrics_fetch_loading_detail(_detail_ph, "Resolving author IDs…")

                    resolved_ids, resolution_warnings = (
                        resolve_author_ids_for_metrics_safe(
                            ids, api_key_effective
                        )
                    )
                    _notice_resolution_parts: list[str] = []
                    if resolution_warnings:
                        _notice_resolution_parts.append(
                            "Skipped unresolved input(s):\n- "
                            + "\n- ".join(resolution_warnings)
                        )
                    if not resolved_ids:
                        _notice_resolution_parts.append(
                            "No valid Scopus Author ID could be resolved from the input."
                        )
                    if _notice_resolution_parts:
                        _invoke_notice_dialog(
                            "\n\n".join(_notice_resolution_parts),
                            variant="error" if not resolved_ids else "warning",
                        )
                    _flush_prog.progress(0.12)
                    if not resolved_ids:
                        st.session_state.results = []
                    elif len(resolved_ids) == 1:
                        try:
                            _metrics_fetch_loading_detail(
                                _detail_ph,
                                f"Fetching author 1 of 1 ({resolved_ids[0]})…",
                            )
                            _flush_prog.progress(1.0)
                            data = svc.get_author_metrics(
                                resolved_ids[0],
                                api_key_effective,
                                year_key,
                                am_payload,
                                docs_key,
                                self_cit,
                            )
                            st.session_state.results = [
                                {
                                    "id": resolved_ids[0],
                                    "data": data,
                                    "isEntitlementError": False,
                                    "isRateLimitError": False,
                                }
                            ]
                        except APIError as e:
                            st.session_state.error_msg = str(e)
                            st.session_state.entitlement_error = (
                                e.is_entitlement_error
                            )
                            st.session_state.rate_limit_error = (
                                e.is_rate_limit_error
                            )
                            if is_missing_scival_api_key_error(
                                str(e)
                            ) or is_scival_authentication_error(str(e)):
                                st.session_state.results = []
                            else:
                                st.session_state.results = [
                                    {
                                        "id": resolved_ids[0],
                                        "data": {
                                            "error": str(e),
                                            "metrics": _placeholder_metrics(),
                                        },
                                        "isEntitlementError": e.is_entitlement_error,
                                        "isRateLimitError": e.is_rate_limit_error,
                                    }
                                ]
                    else:
                        st.session_state.results = (
                            _fetch_multi_author_metrics_with_progress(
                                svc,
                                resolved_ids,
                                api_key_effective,
                                year_key,
                                am_payload,
                                docs_key,
                                self_cit,
                                detail_ph=_detail_ph,
                                flush_prog=_flush_prog,
                            )
                        )
                except APIError as e:
                    st.session_state.error_msg = str(e)
                    st.session_state.results = []
                except Exception as e:
                    st.session_state.error_msg = str(e)
                finally:
                    _metrics_fetch_loading_ph.empty()

    if st.session_state.error_msg:
        st.error(
            format_error_message_for_user(
                st.session_state.error_msg,
                is_entitlement_error=st.session_state.entitlement_error,
                is_rate_limit_error=st.session_state.rate_limit_error,
            )
        )

    results = st.session_state.results
    valid = [r for r in results if not (r.get("data") or {}).get("error")]

    if valid:
        with st.container(border=True):
            label_map_global = {x["id"]: x["label"] for x in DEFAULT_METRICS}
            _render_compare_authors_charts(valid, label_map_global)
            if len(valid) > 1:
                st.markdown(
                    '<hr class="charts-export-divider" aria-hidden="true" />',
                    unsafe_allow_html=True,
                )
            export_rows = []
            if len(valid) > 1:
                with st.container(border=False, key="export_workspace_bundle"):
                    en_m = _enabled_metric_ids(st.session_state.available_metrics)
                    order_opts_m = [
                        "publication",
                        "citationCount",
                        "citationsPerPublication",
                        "fwci",
                        "topJournal",
                        "hIndex",
                        *list(COLLABORATION_SUBMETRIC_IDS),
                        *list(ACADEMIC_CORPORATE_SUBMETRIC_IDS),
                    ]
                    label_map_m = {x["id"]: x["label"] for x in DEFAULT_METRICS}
                    opt_list_m = [i for i in order_opts_m if i in en_m]
                    st.markdown(
                        _export_options_heading_html(),
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        _export_step_heading_html(1, "Select Author(s)"),
                        unsafe_allow_html=True,
                    )
                    _prev_bundle_pick = st.session_state.get("export_bundle_scholar_pick")
                    with st.container(border=False, key="export_scholar_shell"):
                        for r in valid:
                            aid = r["id"]
                            chk_key = f"export_scholar_inc_{aid}"
                            if chk_key not in st.session_state:
                                if isinstance(_prev_bundle_pick, list):
                                    st.session_state[chk_key] = aid in _prev_bundle_pick
                                else:
                                    st.session_state[chk_key] = True
                            _nm = str(r["data"].get("authorName") or f"Author {aid}")
                            st.checkbox(_nm, key=chk_key)
                    picked_m, order_pick_m = _metrics_multiselect_and_order_ui(
                        opt_list_m,
                        label_map_m,
                        order_state_key="export_bundle_metrics_ord_state",
                        sortable_key="export_bundle_metrics_sort",
                        multiselect_label="Metrics to export",
                        step_multiselect=2,
                        step_order=3,
                    )
                    export_scholar_pick = [
                        r["id"]
                        for r in valid
                        if st.session_state.get(f"export_scholar_inc_{r['id']}", True)
                    ]
                    if not picked_m or not export_scholar_pick:
                        st.info("Pick at least one metric and one author.")
                    for r in valid:
                        if r["id"] not in export_scholar_pick:
                            continue
                        d = r["data"]
                        aid = r["id"]
                        export_rows.append(
                            {
                                "authorId": aid,
                                "authorName": d.get("authorName"),
                                "metrics": d.get("metrics"),
                                "dataSource": d.get("dataSource"),
                                "selectedMetrics": picked_m,
                                "metricOrder": order_pick_m,
                            }
                        )
                    st.markdown(
                        '<hr class="export-bundle-divider" aria-hidden="true" />',
                        unsafe_allow_html=True,
                    )
                    _render_export_results_block(
                        export_rows, len(valid), embedded_in_workspace=True
                    )
            else:
                for card_idx, r in enumerate(valid):
                    aid = r["id"]
                    d = r["data"]
                    en = _enabled_metric_ids(st.session_state.available_metrics)

                    st.divider()
                    title = d.get("authorName") or f"Author {aid}"
                    title_safe = html.escape(str(title))
                    aid_safe = html.escape(str(aid))
                    st.markdown(
                        f'<p class="section-title" style="margin-bottom:0.25rem;">{title_safe}</p>'
                        f'<p class="metrics-grid-hint" style="margin-top:0;">Scopus Author ID: <code>{aid_safe}</code></p>',
                        unsafe_allow_html=True,
                    )
                    ds = d.get("dataSource")
                    if ds:
                        st.caption(
                            f"Source: {ds.get('sourceName', '')} · "
                            f"Updated: {ds.get('lastUpdated', '')} · "
                            f"Years: {ds.get('metricStartYear', '')}–{ds.get('metricEndYear', '')}"
                        )

                    order_opts = [
                        "publication",
                        "citationCount",
                        "citationsPerPublication",
                        "fwci",
                        "topJournal",
                        "hIndex",
                        *list(COLLABORATION_SUBMETRIC_IDS),
                        *list(ACADEMIC_CORPORATE_SUBMETRIC_IDS),
                    ]
                    label_map = {x["id"]: x["label"] for x in DEFAULT_METRICS}
                    opt_list = [i for i in order_opts if i in en]

                    order_state_key = f"multiord_state_{aid}_{card_idx}"
                    sortable_key = f"multiord_sort_{aid}_{card_idx}"
                    _picked0, _order0, removed_key = (
                        _sync_pick_via_metric_order_session(opt_list, order_state_key)
                    )

                    col_names, table_rows = _build_metrics_table_rows(
                        d.get("metrics") or {},
                        ds,
                        _picked0,
                        _order0,
                    )
                    years: list[int] = []
                    for c in col_names[1:-1]:
                        try:
                            years.append(int(float(c)))
                        except Exception:
                            continue
                    chart_options = [
                        m
                        for m in st.session_state.get(order_state_key, [])
                        if m in opt_list
                    ]
                    if not chart_options:
                        chart_options = list(_picked0) or list(opt_list)

                    if years and chart_options:
                        c_filters, c_chart = st.columns([1, 3], vertical_alignment="top")
                        with c_filters:
                            st.markdown("#### Metric by Year")
                            default_plot_metric = (
                                "publication"
                                if "publication" in chart_options
                                else chart_options[0]
                            )
                            plot_metric = st.selectbox(
                                "Metric",
                                options=chart_options,
                                index=chart_options.index(default_plot_metric),
                                format_func=lambda i: label_map.get(i, i),
                                key=f"chart_metric_{aid}",
                            )
                            chart_type = st.radio(
                                "Type",
                                options=["Bar", "Line"],
                                horizontal=False,
                                index=0,
                                key=f"chart_type_{aid}",
                            )

                        with c_chart:
                            series_name_short = _metric_short_label(
                                label_map, plot_metric
                            )
                            _plot_is_pct = (
                                plot_metric == "topJournal"
                                or plot_metric in COLLABORATION_SUBMETRIC_IDS
                                or plot_metric in ACADEMIC_CORPORATE_SUBMETRIC_IDS
                            )
                            metrics_payload = d.get("metrics") or {}
                            by_year = _extract_metric_by_year(metrics_payload, plot_metric)
                            if not by_year:
                                st.caption(
                                    "Chart is not available for this metric row (for example, H-Index)."
                                )
                            else:
                                values = [by_year.get(str(y)) for y in years]
                                values = [
                                    None
                                    if (
                                        v is None
                                        or (isinstance(v, (int, float)) and pd.isna(v))
                                    )
                                    else v
                                    for v in values
                                ]
                                x_years = [str(y) for y in years]
                                _yaxis_single = {
                                    "type": "value",
                                    "name": (
                                        f"{series_name_short} (%)"
                                        if _plot_is_pct
                                        else series_name_short
                                    ),
                                    "nameLocation": "middle",
                                    "nameGap": 56,
                                    "nameRotate": 90,
                                    "nameTextStyle": {"fontSize": 11, "color": "#475569"},
                                }
                                if _plot_is_pct:
                                    _yaxis_single["axisLabel"] = {"formatter": "{value}%"}
                                _single_lbl_fmt = "{c}%" if _plot_is_pct else "{c}"
                                echarts_options = {
                                    "animation": True,
                                    "title": {
                                        "text": f"{series_name_short} over Years",
                                        "left": "center",
                                        "top": 8,
                                        "textStyle": {"fontSize": 15},
                                    },
                                    "tooltip": {"trigger": "axis"},
                                    # Single-series chart: hide legend to prevent duplicate
                                    # label text colliding with the title area.
                                    "legend": {"show": False},
                                    "toolbox": {
                                        **_compare_toolbox(),
                                        "top": 8,
                                        "right": 40,
                                    },
                                    "grid": {
                                        "left": "6%",
                                        "right": "5%",
                                        "top": 84,
                                        "bottom": 74,
                                        "containLabel": True,
                                    },
                                    "xAxis": {
                                        "type": "category",
                                        "name": "Year",
                                        "nameLocation": "middle",
                                        "nameGap": 28,
                                        "nameTextStyle": {"fontSize": 11, "color": "#475569"},
                                        "data": x_years,
                                    },
                                    "yAxis": _yaxis_single,
                                    "series": [
                                        {
                                            "name": series_name_short,
                                            "type": chart_type.lower(),
                                            "data": values,
                                            "smooth": chart_type == "Line",
                                            "label": {
                                                "show": True,
                                                "position": "top",
                                                "formatter": _single_lbl_fmt,
                                            },
                                        }
                                    ],
                                    "dataZoom": [
                                        {"type": "inside"},
                                        {"type": "slider", "height": 18},
                                    ],
                                }
                                st_echarts(
                                    options=echarts_options,
                                    height="460px",
                                    key=f"echarts_{aid}_{plot_metric}",
                                )

                    author_export_payload = {
                        "authorId": aid,
                        "authorName": d.get("authorName"),
                        "metrics": d.get("metrics"),
                        "dataSource": d.get("dataSource"),
                        "selectedMetrics": _picked0,
                        "metricOrder": _order0,
                    }
                    col_names, table_rows = _build_metrics_table_rows(
                        d.get("metrics") or {},
                        ds,
                        _picked0,
                        _order0,
                    )

                    if table_rows:
                        df = pd.DataFrame(table_rows, columns=col_names)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        try:
                            dl_w, dl_x = st.columns(2, gap="xxsmall")
                            doc_author_b, doc_author_n = export_docx_bytes(
                                [author_export_payload],
                                f"research-metrics-{aid}",
                            )
                            with dl_w:
                                st.download_button(
                                    "Download this table (Word)",
                                    doc_author_b,
                                    file_name=doc_author_n,
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"export_docx_author_{aid}_{card_idx}",
                                    use_container_width=False,
                                )
                            xl_author_b, xl_author_n = export_excel_bytes(
                                [author_export_payload],
                                f"research-metrics-{aid}",
                            )
                            with dl_x:
                                st.download_button(
                                    "Download this table (Excel)",
                                    xl_author_b,
                                    file_name=xl_author_n,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"export_xl_author_{aid}_{card_idx}",
                                    use_container_width=False,
                                )
                        except Exception:
                            st.caption("Could not build Word/Excel file for this author.")

                    if len(valid) == 1:
                        _render_single_author_export_workspace(
                            export_rows,
                            opt_list=opt_list,
                            label_map=label_map,
                            order_state_key=order_state_key,
                            sortable_key=sortable_key,
                            removed_key=removed_key,
                            author_id=aid,
                            author_name=d.get("authorName"),
                            metrics=d.get("metrics"),
                            data_source=d.get("dataSource"),
                        )

    elif results:
        for r in results:
            err = (r.get("data") or {}).get("error")
            if err:
                aid_disp = html.escape(str(r["id"]))
                st.error(
                    f"**{aid_disp}** — {format_error_message_for_user(str(err), is_entitlement_error=bool(r.get('isEntitlementError')), is_rate_limit_error=bool(r.get('isRateLimitError')))}"
                )

    _render_footer_html()


def _placeholder_metrics() -> dict:
    na = {"byYear": {}, "total": "N/A"}
    out = {
        "hIndex": {"value": "N/A"},
        "scholarlyOutput": dict(na),
        "fwci": dict(na),
        "topJournal": dict(na),
        "citationCount": dict(na),
        "citationsPerPublication": dict(na),
    }
    for _cid in COLLABORATION_SUBMETRIC_IDS:
        out[_cid] = dict(na)
    for _aid in ACADEMIC_CORPORATE_SUBMETRIC_IDS:
        out[_aid] = dict(na)
    return out


if __name__ == "__main__":
    main()
