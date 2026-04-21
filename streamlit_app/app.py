"""
Research Impact Dashboard — Streamlit port of the React/Vite app.
Run from repository root:  streamlit run streamlit_app/app.py
"""

from __future__ import annotations

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
from streamlit_sortables import sort_items

from streamlit_app.api_service import (
    APIError,
    format_error_message_for_user,
    get_api_service,
    is_missing_scival_api_key_error,
    is_scival_authentication_error,
    resolve_author_ids_for_metrics_safe,
)
from streamlit_app.config import SCIVAL_API_KEY, USE_DIRECT_API
from streamlit_app.export_utils import export_excel_bytes, export_pdf_bytes

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

# Filter card header icons — line-art SVG on white circular badge
_FILTER_ICON_CALENDAR = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>'
    '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
)
_FILTER_ICON_DOCUMENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
    '<line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>'
)
_FILTER_ICON_FUNNEL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>'
)
# Export workspace strip — “outputs” glyph (separate from analysis / charts)
_EXPORT_WORKSPACE_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'
)


def _inject_export_download_styles() -> None:
    """Lighter PDF/Excel export buttons with file + download icons (data-URI SVGs)."""
    from urllib.parse import quote

    svg_pdf = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm0 1.4L18.6 9H14V3.4zM8 12.5h8v1.25H8v-1.25zm0 3h6v1.25H8v-1.25z"/>'
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
    u_pdf, u_xls, u_dl = (
        quote(svg_pdf, safe=""),
        quote(svg_xls, safe=""),
        quote(svg_dl, safe=""),
    )
    st.markdown(
        f"""
<style>
/* Compact export row: hug content, minimal space between PDF + Excel */
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] {{
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: wrap !important;
  align-items: center !important;
  gap: 0.35rem !important;
  column-gap: 0.35rem !important;
  justify-content: flex-start !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
  flex: 0 0 auto !important;
  flex-grow: 0 !important;
  width: auto !important;
  min-width: 0 !important;
  max-width: fit-content !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  margin: 0 !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] > div {{
  gap: 0 !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] .block-container {{
  padding-left: 0 !important;
  padding-right: 0 !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] [data-testid="stDownloadButton"],
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] .stDownloadButton {{
  width: auto !important;
  min-width: 0 !important;
}}

[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button,
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(1) .stDownloadButton > button,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(1) .stDownloadButton > button {{
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
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button:hover,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button:hover {{
  filter: brightness(1.05) saturate(1.05);
  box-shadow: 0 3px 16px rgba(239, 68, 68, 0.4) !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button::before,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button::before {{
  content: "" !important;
  display: block !important;
  width: 1.05rem !important;
  height: 1.05rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_pdf}") center / contain no-repeat !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stDownloadButton"] button::after,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(1) [data-testid="stDownloadButton"] button::after {{
  content: "" !important;
  display: block !important;
  width: 0.9rem !important;
  height: 0.9rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_dl}") center / contain no-repeat !important;
}}

[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button,
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(2) .stDownloadButton > button,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(2) .stDownloadButton > button {{
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
  box-shadow: 0 2px 12px rgba(34, 197, 94, 0.32) !important;
  background: linear-gradient(145deg, #6ee7b7 0%, #34d399 42%, #16a34a 100%) !important;
  text-shadow: 0 1px 0 rgba(15, 23, 42, 0.1) !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button:hover,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button:hover {{
  filter: brightness(1.05) saturate(1.05);
  box-shadow: 0 3px 16px rgba(22, 163, 74, 0.38) !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button::before,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button::before {{
  content: "" !important;
  display: block !important;
  width: 1.05rem !important;
  height: 1.05rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_xls}") center / contain no-repeat !important;
}}
[class*="st-key-export_results_shell"] [data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stDownloadButton"] button::after,
[class*="st-key-export_results_shell"] div[data-testid="column"]:nth-of-type(2) [data-testid="stDownloadButton"] button::after {{
  content: "" !important;
  display: block !important;
  width: 0.9rem !important;
  height: 0.9rem !important;
  flex-shrink: 0 !important;
  background: url("data:image/svg+xml,{u_dl}") center / contain no-repeat !important;
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

/* Analyze CTA — full-width pill (label centered, wide bar like reference) */
[class*="st-key-analyze_zone"] {
  width: 100% !important;
  /* Pull button up toward metrics panel bottom border (stays outside the panel) */
  margin-top: -1.35rem !important;
  margin-bottom: 0.3rem !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: stretch !important;
}
[class*="st-key-analyze_zone"] [data-testid="stVerticalBlock"] {
  width: 100% !important;
  align-items: stretch !important;
}
[class*="st-key-analyze_zone"] [data-testid="element-container"] {
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
}
[class*="st-key-analyze_zone"] .stButton {
  display: block !important;
  width: 100% !important;
  max-width: 100% !important;
}
[class*="st-key-analyze_zone"] .stButton > button {
  width: 100% !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"],
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"] {
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
    -webkit-text-fill-color 0.2s ease !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"] p,
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"] p,
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"] span,
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"] span {
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"]:hover,
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"]:hover {
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
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"]:focus-visible,
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"]:focus-visible {
  outline: 2px solid #673ab7 !important;
  outline-offset: 3px !important;
}

/* Metric toggle cards: stronger “on” vs “off” affordance */
[class*="st-key-metric_card_"]:has(input:checked),
[class*="st-key-metric_card_"]:has(input:checked),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-dense_metric_"]:has(input:checked),
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-metric_cell_"]:has(input:checked),
[class*="st-key-metric_cell_"]:has([role="switch"][aria-checked="true"]) {
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
[class*="st-key-metric_cell_"]:has(input:not(:checked)),
[class*="st-key-metric_cell_"]:has([role="switch"][aria-checked="false"]) {
  border-color: #e5e7eb !important;
  background: #fafafa !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)) label,
[class*="st-key-metric_card_"]:has(input:not(:checked)) label,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-metric_cell_"]:has([role="switch"][aria-checked="false"]) label {
  color: #64748b !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)) p.metric-subtext,
[class*="st-key-metric_card_"]:has(input:not(:checked)) p.metric-subtext,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-dense_metric_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-metric_cell_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext {
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
  padding: 0.5rem 1.1rem;
  background: linear-gradient(135deg, #ffffff 0%, #f5f3ff 100%);
  border: 1px solid #ddd6fe;
  border-radius: 999px;
  font-weight: 800;
  font-size: 0.88rem;
  color: #5b21b6;
  box-shadow: 0 3px 14px rgba(124, 58, 237, 0.15), inset 0 1px 0 #fff;
}

/* —— Search configuration (shell + widgets: final shell tokens live in “Stable key-based” block) —— */
.search-config-title {
  margin: 0 0 0.65rem 0 !important;
  font-family: 'Inter', 'Segoe UI', sans-serif !important;
  font-size: 1.25rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.055em !important;
  text-transform: uppercase !important;
  color: #111827 !important;
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
.year-filter-tip-marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.15rem;
  height: 1.15rem;
  border-radius: 50%;
  font-size: 0.68rem;
  font-weight: 800;
  line-height: 1;
  color: #4b5563;
  background: #e5e7eb;
  border: 1px solid #d1d5db;
  cursor: help;
}
.year-filter-tip:hover .year-filter-tip-marker,
.year-filter-tip:focus .year-filter-tip-marker,
.year-filter-tip:focus-within .year-filter-tip-marker {
  background: #ede7f6;
  border-color: #b39ddb;
  color: #5e35b1;
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
/* Circular “FAB” badge: white disc, hairline border, soft shadow (filter row icons) */
.minimal-filter-icon-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.55rem;
  height: 2.55rem;
  border-radius: 50%;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.1),
    0 1px 3px rgba(15, 23, 42, 0.08);
  flex-shrink: 0;
}
.minimal-filter-icon-badge svg {
  width: 1.28rem;
  height: 1.28rem;
  flex-shrink: 0;
}
.minimal-filter-icon-badge--calendar svg {
  color: #2563eb !important;
}
.minimal-filter-icon-badge--document svg {
  color: #0d9488 !important;
}
.minimal-filter-icon-badge--funnel svg {
  color: #9c4121 !important;
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
  align-items: flex-start;
  gap: 0.52rem;
  margin: 0.35rem 0 0.1rem 0;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  font-size: 0.84rem;
  line-height: 1.35;
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
[class*="st-key-search_shell"] .author-limit-icon {
  font-size: 0.95rem;
  line-height: 1.2;
}
[class*="st-key-search_shell"] .author-limit-count {
  font-weight: 700;
  margin-left: 0.25rem;
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
  background: #ede9fe !important;
  border-color: #ddd6fe !important;
  color: #5b21b6 !important;
  -webkit-text-fill-color: #5b21b6 !important;
  box-shadow: none !important;
}
/* Nested Streamlit text must match light chip (dark violet, not white) */
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked) p,
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked) span,
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] p,
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] span {
  color: #5b21b6 !important;
  -webkit-text-fill-color: #5b21b6 !important;
}
[class*="st-key-search_shell"] [data-testid="stRadio"] label:has(input:checked) div,
[class*="st-key-search_shell"] [data-testid="stRadio"] label[aria-checked="true"] div {
  color: #5b21b6 !important;
  -webkit-text-fill-color: #5b21b6 !important;
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
/* Minimal 2×4 metrics grid (Select Metrics to Include) */
[class*="st-key-metrics_toolbar_shell"] {
  margin-bottom: 0.5rem !important;
  padding-bottom: 0 !important;
}
[class*="st-key-metrics_grid_shell"] {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
[class*="st-key-metrics_grid_row0"] {
  margin-bottom: 0.75rem !important;
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
}
[class*="st-key-metric_cell_"] {
  border: 1px solid #e5e7eb !important;
  border-radius: 0.5rem !important;
  padding: 0.45rem 0.55rem !important;
  margin: 0 !important;
  min-height: 5.5rem !important;
  height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  box-sizing: border-box !important;
  background: #ffffff !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05) !important;
  overflow: hidden !important;
}
[class*="st-key-metric_cell_"] > div[data-testid="stVerticalBlock"] {
  gap: 0 !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] {
  gap: 0.35rem !important;
  align-items: stretch !important;
  flex: 1 1 auto !important;
  margin-bottom: 0 !important;
  min-height: 3.35rem !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child {
  flex: 1 1 auto !important;
  min-width: 0 !important;
  display: flex !important;
  align-items: flex-start !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child {
  flex: 0 0 auto !important;
  width: auto !important;
  display: flex !important;
  align-items: flex-start !important;
  justify-content: flex-end !important;
}
[class*="st-key-metric_cell_"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child [data-testid="stVerticalBlock"] {
  align-items: flex-end !important;
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
  transform: scale(0.92);
  transform-origin: top right !important;
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

/* Export workspace — self-contained lane (analysis/charts live above) */
[class*="st-key-export_workspace_stack"] {
  margin-top: 0.85rem !important;
  margin-bottom: 0.35rem !important;
  padding: 1.35rem 1.45rem 1.55rem 1.55rem !important;
  border-radius: 18px !important;
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
[class*="st-key-export_workspace_stack"]::before {
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
[class*="st-key-export_prep_inner"] {
  background: rgba(255, 255, 255, 0.88) !important;
  border-radius: 14px !important;
  padding: 1rem 1.2rem 1.15rem !important;
  margin-bottom: 1.05rem !important;
  border: 1px solid rgba(148, 163, 184, 0.35) !important;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04) !important;
}
[class*="st-key-export_prep_inner"] p.prepare-export-heading {
  margin-top: 0.15rem !important;
}
hr.export-workspace-split {
  border: none !important;
  height: 0 !important;
  margin: 0.2rem 0 1.15rem 0 !important;
  border-top: 2px dashed rgba(16, 185, 129, 0.45) !important;
  opacity: 1 !important;
}
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

/* Site footer — light “glass” panel */
.site-footer {
  margin-top: 3rem;
  margin-bottom: 2.25rem;
  padding: 2rem 1.75rem 1.5rem;
  background: linear-gradient(165deg, #ffffff 0%, #f9fbfd 45%, #f4f7fb 100%);
  border: 1px solid rgba(148, 163, 184, 0.22) !important;
  border-radius: 12px;
  box-shadow:
    0 4px 14px rgba(15, 23, 42, 0.04),
    0 12px 28px rgba(148, 163, 184, 0.06);
  scroll-margin-bottom: 3rem;
}
.site-footer-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 2rem 2.5rem;
  max-width: 1100px;
  margin: 0 auto;
}
@media (max-width: 768px) {
  .site-footer-grid {
    grid-template-columns: 1fr;
  }
}
.site-footer h4 {
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #5f74a0;
  margin: 0 0 0.85rem 0;
}
.site-footer .sf-body {
  margin: 0;
  font-size: 0.92rem;
  color: #4a5568;
  line-height: 1.6;
}
.site-footer .sf-body + .sf-body {
  margin-top: 0.5rem;
}
.site-footer a {
  color: #5c7cfa;
  font-weight: 600;
  text-decoration: none;
}
.site-footer a:hover {
  text-decoration: underline;
  color: #4263eb;
}
.site-footer .sf-contact-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin: 0 0 0.55rem 0;
  font-size: 0.92rem;
  color: #4a5568;
}
.site-footer .sf-contact-row:last-child {
  margin-bottom: 0;
}
.site-footer .sf-icon {
  flex-shrink: 0;
  color: #7b92b1;
  opacity: 0.95;
}
.site-footer-copy {
  text-align: center;
  margin: 2rem 0 0;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 0.78rem;
  color: #4a5568;
  line-height: 1.5;
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

/* Select metrics: no rule under heading */
.metrics-panel-heading {
  font-size: 1.05rem;
  font-weight: 800;
  color: #1e1b4b;
  margin: 0 0 0.35rem 0;
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
</style>
        """,
        unsafe_allow_html=True,
    )
    _inject_export_download_styles()


def _render_footer_html() -> None:
    """Footer: Resources / Contact / Address + copyright (light band, matches page theme)."""
    year = datetime.now().year
    st.markdown(
        f"""
<footer class="site-footer" role="contentinfo">
  <div class="site-footer-grid">
    <div>
      <h4>Resources</h4>
      <p class="sf-body"><a href="https://library.hkust.edu.hk/" target="_blank" rel="noopener noreferrer">HKUST Library</a></p>
    </div>
    <div>
      <h4>Contact &amp; Support</h4>
      <div class="sf-contact-row">
        <svg class="sf-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="m22 6-10 7L2 6" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <a href="mailto:lbrs@ust.hk">lbrs@ust.hk</a>
      </div>
      <div class="sf-contact-row">
        <svg class="sf-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <a href="tel:+85223586772">+852 2358 6772</a>
      </div>
    </div>
    <div>
      <h4>HKUST Library</h4>
      <p class="sf-body">Hong Kong University of Science and Technology</p>
      <p class="sf-body">Clear Water Bay, Hong Kong</p>
    </div>
  </div>
  <p class="site-footer-copy">
    © {year} Hong Kong University of Science and Technology Library. All rights reserved.
  </p>
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
        "label": "Publication",
        "description": "Scholarly output count by year",
        "enabled": True,
    },
    {
        "id": "fwci",
        "label": "Field-Weighted Citation Impact (FWCI)",
        "description": "Citation impact normalized by field",
        "enabled": True,
    },
    {
        "id": "topJournal",
        "label": "Top 10% Journal Percentile",
        "description": "Publications in top-tier journals",
        "enabled": True,
    },
    {
        "id": "citationCount",
        "label": "Citation Count",
        "description": "Total citation count",
        "enabled": True,
    },
    {
        "id": "hIndex",
        "label": "H-Index",
        "description": "Author productivity and citation impact",
        "enabled": True,
    },
    {
        "id": "citationsPerPublication",
        "label": "Citations Per Publication",
        "description": "Average citations per publication",
        "enabled": True,
    },
    {
        "id": "collaboration",
        "label": "Collaboration",
        "description": "Collaboration patterns by type (institutional, international, national, single authorship)",
        "enabled": True,
    },
    {
        "id": "academicCorporateCollaboration",
        "label": "Academic Corporate Collaboration",
        "description": "Academic–corporate collaboration breakdown",
        "enabled": True,
    },
]

# Default on/off per metric id (used when creating ``met_*`` session keys).
DEFAULT_METRIC_TOGGLE_DEFAULT: dict[str, bool] = {
    m["id"]: bool(m.get("enabled", True)) for m in DEFAULT_METRICS
}

# Bump when default metric toggles change so Streamlit widget keys (met_*) resync.
# v5: reset stuck "all off" sessions; ensure defaults come from DEFAULT_METRICS, not stale dict copies.
_METRICS_SESSION_DEFAULT_VERSION = 5

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

# Label “?” — three building blocks only; details live in the Year dropdown help.
YEAR_FILTER_LABEL_TOOLTIP_HTML = (
    "<strong>Year range:</strong><br />"
    "• Completed calendar years<br />"
    "• The current calendar year<br />"
    "• Indexed manuscripts with a future official publication date<br />"
    "<span style=\"font-size:0.85em;color:#64748b\">"
    "Open the <strong>Year</strong> dropdown and use its (?) help for the exact wording of each preset."
    "</span>"
)

SELF_CIT_HELP = (
    "Self-citations are citations where an author cites their own previous work."
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
                mid, True
            )
    elif "available_metrics" not in st.session_state:
        st.session_state.available_metrics = [dict(m) for m in DEFAULT_METRICS]
        for m in DEFAULT_METRICS:
            mk = f"met_{m['id']}"
            if mk not in st.session_state:
                st.session_state[mk] = DEFAULT_METRIC_TOGGLE_DEFAULT.get(m["id"], True)
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
    year_sets.extend((m.get("collaboration") or {}).get("byYear") or {})
    year_sets.extend((m.get("academicCorporateCollaboration") or {}).get("byYear") or {})
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

    row_defs = [
        ("publication", "Publication", lambda x: x["scholarlyOutput"], True, False),
        ("citationCount", "Citation Count", lambda x: x["citationCount"], True, False),
        (
            "citationsPerPublication",
            "Citations Per Publication",
            lambda x: x["citationsPerPublication"],
            True,
            False,
        ),
        ("fwci", "FWCI", lambda x: x["fwci"], True, False),
        ("topJournal", "Top 10 Journal %", lambda x: x["topJournal"], True, True),
        (
            "hIndex",
            "H-Index",
            lambda x: {"byYear": {}, "total": x["hIndex"]["value"]},
            False,
            False,
        ),
        (
            "collaboration",
            "Collaboration (International %)",
            lambda x: x.get("collaboration")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
        (
            "academicCorporateCollaboration",
            "Academic Corporate Collaboration %",
            lambda x: x.get("academicCorporateCollaboration")
            or {"byYear": {}, "total": "N/A"},
            True,
            True,
        ),
    ]
    by_id = {r[0]: r for r in row_defs}
    ordered = [by_id[i] for i in order if i in by_id and i in selected_ids]

    cols = ["Metric"] + [str(y) for y in years] + ["Total"]
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
                    cells.append(
                        f"{int(v)}%" if isinstance(v, (int, float)) and v % 1 == 0 else f"{float(v):.2f}%"
                    )
                elif mid in ("fwci", "citationsPerPublication"):
                    cells.append(f"{float(v):.2f}")
                else:
                    cells.append(str(round(v)) if isinstance(v, (int, float)) else str(v))
            if isinstance(tot, (int, float)):
                if mid in ("fwci", "citationsPerPublication", "topJournal") or is_pct:
                    cells.append(
                        f"{tot:.2f}%" if is_pct or mid == "topJournal" else f"{tot:.2f}"
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
        "collaboration": "collaboration",
        "academicCorporateCollaboration": "academicCorporateCollaboration",
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
        "collaboration": "collaboration",
        "academicCorporateCollaboration": "academicCorporateCollaboration",
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
    full = label_map.get(metric_id, metric_id)
    paren_match = re.search(r"\(([^)]+)\)", str(full))
    return paren_match.group(1).strip() if paren_match else str(full)


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
    return {
        "show": True,
        "feature": {
            "saveAsImage": {"show": True, "title": "Download"},
            "restore": {"show": True},
            "dataZoom": {"show": True},
        },
    }


def _fetch_multi_author_metrics_with_progress(
    svc,
    resolved_ids: list[str],
    api_key_effective,
    year_key: str,
    am_payload: list,
    docs_key: str,
    self_cit: bool,
) -> list[dict]:
    """Load each author sequentially so the UI can show real progress (and respect direct-API pacing)."""
    n = len(resolved_ids)
    progress = st.progress(0, text=f"Loading {n} author(s)…")
    out: list[dict] = []
    for i, aid in enumerate(resolved_ids):
        progress.progress(
            i / max(n, 1),
            text=f"Fetching author {i + 1} of {n} ({aid})…",
        )
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
    progress.progress(1.0, text=f"Finished loading {n} author(s).")
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


def _export_workspace_module_head_html(*, bundle_prep: bool) -> str:
    """Banner for the export lane (separate from charts / analysis above)."""
    title = "Export workspace"
    if bundle_prep:
        desc = (
            "Choose export options below, then download PDF or Excel."
        )
    else:
        desc = "Choose export options below, then download PDF or Excel."
    return (
        '<header class="export-workspace-module-head" role="presentation">'
        '<div class="export-workspace-module-head-row">'
        '<div class="export-workspace-module-icon" aria-hidden="true">'
        f"{_EXPORT_WORKSPACE_ICON}</div>"
        '<div class="export-workspace-module-copy">'
        f'<p class="export-workspace-module-title">{html.escape(title)}</p>'
        f'<p class="export-workspace-module-desc">{html.escape(desc)}</p>'
        "</div></div></header>"
    )


def _render_export_results_block(export_rows: list, n_valid: int) -> None:
    """Anchor, copy, filename, and PDF/Excel downloads (used inside export workspace)."""
    st.markdown(
        '<div id="export-downloads-anchor"></div>',
        unsafe_allow_html=True,
    )
    export_body_sub = (
        "Download your research metrics in PDF or Excel. Set the filename below. "
        "The export uses the metrics and table row order from steps (1)–(2), "
        "and only the author(s) checked in step (3)."
        if n_valid > 1
        else (
            "Download your research metrics in PDF or Excel. Set the filename below."
        )
    )
    with st.container(border=True, key="export_results_shell"):
        st.markdown(
            '<div class="export-results-head">'
            '<div class="export-results-head-row">'
            '<div class="export-results-badge" aria-hidden="true">'
            f"{_FILTER_ICON_DOCUMENT}"
            "</div>"
            '<div class="export-results-head-text">'
            '<p class="export-results-title">Export Results</p>'
            '<p class="export-results-sub">'
            f"{html.escape(export_body_sub)}"
            "</p>"
            "</div></div></div>",
            unsafe_allow_html=True,
        )
        fn = st.text_input(
            "Export filename (without extension)", value="research-metrics"
        )
        b1, b2 = st.columns(2, gap="xxsmall")
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
            xl_b, xl_n = export_excel_bytes(export_rows, fn)
            st.download_button(
                "Export as Excel",
                xl_b,
                file_name=xl_n,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=False,
            )


def _metrics_multiselect_and_order_ui(
    opt_list: list[str],
    label_map: dict[str, str],
    *,
    multiselect_label: str,
    multiselect_key: str,
    order_state_key: str,
    sortable_key: str,
    fallback_key: str,
    step_multiselect: int | None = None,
    step_order: int | None = None,
) -> tuple[list[str], list[str]]:
    """Pick metrics and drag-to-order rows. Returns ``(picked, order_pick)``."""
    if step_multiselect is not None:
        st.markdown(
            _export_step_heading_html(step_multiselect, multiselect_label),
            unsafe_allow_html=True,
        )
    picked = st.multiselect(
        multiselect_label,
        options=opt_list,
        default=opt_list,
        format_func=lambda i: label_map.get(i, i),
        key=multiselect_key,
        label_visibility="collapsed" if step_multiselect is not None else "visible",
    )
    if not picked:
        st.caption("Select at least one metric row to display.")
        return [], []

    existing_order = st.session_state.get(order_state_key, picked.copy())
    existing_order = [m for m in existing_order if m in picked]
    for m in picked:
        if m not in existing_order:
            existing_order.append(m)
    st.session_state[order_state_key] = existing_order
    order_pick = existing_order

    # Remount sortables when the multiselect set changes so removed metrics drop
    # from the list (streamlit-sortables can otherwise keep stale items).
    _pick_sig = hashlib.md5(",".join(sorted(picked)).encode()).hexdigest()[:12]

    if step_order is not None:
        st.markdown(
            _export_step_heading_html(step_order, "Display order (top to bottom)"),
            unsafe_allow_html=True,
        )
    else:
        st.markdown("Display order (top to bottom)")
    display_to_metric = {label_map.get(m, m): m for m in order_pick}
    sortable_style = """
                    .sortable-component {
                        border: 1px solid #e5e7eb;
                        border-radius: 10px;
                        padding: 8px;
                        background: #f8fafc;
                    }
                    .sortable-container-header {
                        display: none;
                    }
                    .sortable-item, .sortable-item:hover {
                        background: #e0ecff;
                        border: 1px solid #bfd3ff;
                        color: #1f2937;
                        font-weight: 600;
                        border-radius: 8px;
                    }
                    """
    sorted_display = sort_items(
        list(display_to_metric.keys()),
        direction="vertical",
        custom_style=sortable_style,
        key=f"{sortable_key}_{_pick_sig}",
    )
    if (
        isinstance(sorted_display, list)
        and sorted_display
        and all(isinstance(s, str) for s in sorted_display)
    ):
        order_pick = [
            display_to_metric[s]
            for s in sorted_display
            if s in display_to_metric and display_to_metric[s] in picked
        ]
    else:
        st.caption("Drag area unavailable for this card. Use fallback selector below.")
        fallback_display = st.multiselect(
            "Fallback order",
            options=list(display_to_metric.keys()),
            default=list(display_to_metric.keys()),
            key=f"{fallback_key}_{_pick_sig}",
            label_visibility="collapsed",
        )
        if fallback_display:
            order_pick = [
                display_to_metric[s]
                for s in fallback_display
                if s in display_to_metric and display_to_metric[s] in picked
            ]
        else:
            order_pick = [m for m in existing_order if m in picked]
    order_pick = [m for m in order_pick if m in picked]
    st.session_state[order_state_key] = order_pick
    st.caption("Current order: " + " -> ".join(label_map.get(i, i) for i in order_pick))
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
        "collaboration",
        "academicCorporateCollaboration",
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
    st.markdown("##### Trends by years")
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
                            "formatter": "{c}",
                            "fontSize": 11,
                            "color": "#334155",
                        }
                    line_series.append(ser)
                if line_series:
                    toolbox_line = _compare_toolbox()
                    toolbox_line["right"] = 12
                    toolbox_line["top"] = 8
                    line_legend_rows = max(1, (len(line_series) + 4) // 5)
                    line_grid_top = 128 + max(0, line_legend_rows - 1) * 22
                    line_opts = {
                        "animation": True,
                        "title": {
                            "text": "Trends by year",
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
                        "yAxis": {
                            "type": "value",
                            "name": line_short,
                            "nameLocation": "middle",
                            "nameGap": 58,
                            "nameRotate": 90,
                            "nameTextStyle": {"fontSize": 11, "color": "#475569"},
                        },
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

    def _bubble_pick_idx(metric_id: str, default: str) -> int:
        try:
            return bubble_metric_opts.index(metric_id)
        except ValueError:
            try:
                return bubble_metric_opts.index(default)
            except ValueError:
                return 0

    if len(bubble_metric_opts) < 3:
        st.caption(
            "Enable at least three metrics in Settings to map X, Y, and bubble size."
        )
        return

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
                index=_bubble_pick_idx("fwci", "publication"),
                format_func=lambda i: label_map.get(i, i),
                key="compare_bubble_x_v2",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p class="compare-filter-mini" style="margin-top:0.45rem;">Y-axis</p>',
                unsafe_allow_html=True,
            )
            y_metric = st.selectbox(
                "Y-axis",
                options=bubble_metric_opts,
                index=_bubble_pick_idx("topJournal", "fwci"),
                format_func=lambda i: label_map.get(i, i),
                key="compare_bubble_y_v2",
                label_visibility="collapsed",
            )
            st.markdown(
                '<p class="compare-filter-mini" style="margin-top:0.45rem;">Bubble size</p>',
                unsafe_allow_html=True,
            )
            size_metric = st.selectbox(
                "Bubble size",
                options=bubble_metric_opts,
                index=_bubble_pick_idx("publication", "citationCount"),
                format_func=lambda i: label_map.get(i, i),
                key="compare_bubble_size_v2",
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

                    def _fmt_val(v: float) -> str:
                        if float(v).is_integer():
                            return str(int(v))
                        return f"{v:.4f}".rstrip("0").rstrip(".")

                    size_px = _bubble_symbol_sizes([p[3] for p in plotted])

                    bubble_series = []
                    for i, (author_name, xv, yv, sv) in enumerate(plotted):
                        tooltip_text = (
                            f"{author_name}\n"
                            f"{y_name}: {_fmt_val(yv)}\n"
                            f"{x_name}: {_fmt_val(xv)}\n"
                            f"{z_name}: {_fmt_val(sv)}"
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
                    toolbox_bubble["right"] = 10
                    toolbox_bubble["top"] = 8

                    bubble_opts = {
                        "animation": True,
                        "title": {
                            "text": f"{y_lbl} vs {x_lbl}",
                            "subtext": f"Bubble size: {sz_lbl} (period totals)",
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
                            "name": x_name,
                            "nameLocation": "middle",
                            "nameGap": 40,
                            "nameTextStyle": {
                                "fontSize": 11,
                                "color": "#475569",
                                "padding": [0, 0, 4, 0],
                            },
                            "axisLabel": {"margin": 10},
                            "scale": True,
                        },
                        "yAxis": {
                            "type": "value",
                            "name": y_name,
                            "nameLocation": "middle",
                            "nameGap": 46,
                            "scale": True,
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
                    for col in (x_lbl, y_lbl, sz_lbl):
                        tbl_df[col] = tbl_df[col].map(_fmt_val)
                    st.caption(
                        "Totals used for position and bubble size "
                        "(same period as your search):"
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


def main() -> None:
    _init_session()
    _inject_theme_css()

    with st.sidebar:
        st.markdown('<p class="section-kicker">Settings</p>', unsafe_allow_html=True)
        st.markdown("### API mode")
        st.caption(
            "Direct API" if USE_DIRECT_API else "Supabase proxy (set VITE_USE_DIRECT_API=true for direct)."
        )
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
    with st.container():
        with st.container(border=True, key="search_shell"):
            st.markdown(
                '<p class="search-config-title">SEARCH CONFIGURATION</p>',
                unsafe_allow_html=True,
            )

            fy, fd, fs = st.columns(3, gap="small")
            with fy:
                st.markdown(
                    '<div class="minimal-filter-label">'
                    f'<span class="minimal-filter-icon-badge minimal-filter-icon-badge--calendar" '
                    f'aria-hidden="true">{_FILTER_ICON_CALENDAR}</span>'
                    '<span class="year-filter-label-with-tip">'
                    "<span>Year</span>"
                    '<span class="year-filter-tip" tabindex="0" role="button" '
                    'aria-label="Year range options, details in tooltip">'
                    '<span class="year-filter-tip-marker" aria-hidden="true">?</span>'
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
                    f'aria-hidden="true">{_FILTER_ICON_FUNNEL}</span><span>Self-Citation</span></div>',
                    unsafe_allow_html=True,
                )
                st.radio(
                    "Self-citation mode",
                    options=["include", "exclude"],
                    format_func=lambda k: SELF_CIT_RADIO_LABELS[k],
                    horizontal=True,
                    key="self_cit_radio",
                    label_visibility="collapsed",
                )
                self_cit = st.session_state.self_cit_radio == "include"

            st.markdown('<div class="minimal-section-divider"></div>', unsafe_allow_html=True)

            author_ids = st.text_area(
                "Scopus Author ID (preferred) or ORCID ID",
                placeholder="Enter Scopus Author ID(s) or ORCID(s)...",
                label_visibility="visible",
                key="scopus_author_ids",
                height=96,
            )
            parsed_author_ids = [
                x.strip() for x in re.split(r"[,\n;]+", author_ids) if x.strip()
            ]
            _limit_cls = (
                "author-limit-hint--warn"
                if len(parsed_author_ids) > MAX_AUTHORS_PER_RUN
                else "author-limit-hint--ok"
            )
            st.markdown(
                '<div class="author-limit-hint '
                f'{_limit_cls}"><span class="author-limit-icon" aria-hidden="true">👥</span>'
                "<span><strong>Search up to "
                f"{MAX_AUTHORS_PER_RUN} author IDs in one run.</strong> "
                "Use commas, semicolons, or line breaks to separate entries."
                '<span class="author-limit-count">'
                f"{len(parsed_author_ids)}/{MAX_AUTHORS_PER_RUN} entered"
                "</span></span></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="minimal-go-analyze-wrap">'
                '<a class="minimal-go-analyze-btn" href="#analyze-metrics-anchor">Go to Analyze</a>'
                "</div>",
                unsafe_allow_html=True,
            )

        # --- Metrics: own bordered panel (layered inside main card) ---
        with st.container(border=True, key="metrics_panel_shell"):
            st.markdown(
                '<span class="skin-metrics-panel-shell" aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="metrics-panel-heading">Select Metrics to Include</p>',
                unsafe_allow_html=True,
            )
            st.caption("Toggle metrics on or off.")

            am = st.session_state.available_metrics
            # Keep widget state as the single source of truth to avoid
            # Streamlit warnings about using both `value` and Session State.
            for m in am:
                mk = f"met_{m['id']}"
                if mk not in st.session_state:
                    st.session_state[mk] = DEFAULT_METRIC_TOGGLE_DEFAULT.get(
                        m["id"], True
                    )
                m["enabled"] = bool(st.session_state[mk])
            n_on = sum(1 for m in am if m.get("enabled"))
            with st.container(border=False, key="metrics_toolbar_shell"):
                tb1, tb2, tb3 = st.columns([2, 1, 1])
                with tb1:
                    st.markdown(
                        f'<span class="metrics-count-bar">{n_on} of {len(am)} metrics selected</span>',
                        unsafe_allow_html=True,
                    )
                with tb2:
                    if st.button(
                        "Select All",
                        key="metrics_select_all",
                        type="secondary",
                        use_container_width=True,
                    ):
                        for m in am:
                            m["enabled"] = True
                            st.session_state[f"met_{m['id']}"] = True
                with tb3:
                    if st.button(
                        "Clear All",
                        key="metrics_clear_all",
                        type="secondary",
                        use_container_width=True,
                    ):
                        for m in am:
                            m["enabled"] = False
                            st.session_state[f"met_{m['id']}"] = False

            with st.container(border=False, key="metrics_grid_shell"):
                for row_key, row_start in (
                    ("metrics_grid_row0", 0),
                    ("metrics_grid_row1", 4),
                ):
                    row = am[row_start : row_start + 4]
                    with st.container(border=False, key=row_key):
                        cols = st.columns(4, gap="small")
                        for i, metric in enumerate(row):
                            with cols[i]:
                                with st.container(key=f"metric_cell_{metric['id']}"):
                                    ct, csw = st.columns([1, 0.28], gap="small")
                                    with ct:
                                        st.markdown(
                                            f'<p class="metric-compact-title">{html.escape(metric["label"])}</p>',
                                            unsafe_allow_html=True,
                                        )
                                    with csw:
                                        _mk = f"met_{metric['id']}"
                                        _def_on = DEFAULT_METRIC_TOGGLE_DEFAULT.get(
                                            metric["id"], True
                                        )
                                        metric["enabled"] = st.toggle(
                                            metric["label"],
                                            value=bool(
                                                st.session_state.get(_mk, _def_on)
                                            ),
                                            key=_mk,
                                            label_visibility="collapsed",
                                        )

        st.markdown(
            '<div id="analyze-metrics-anchor" class="analyze-anchor-tight"></div>',
            unsafe_allow_html=True,
        )
        if not st.session_state.get("_deep_link_analyze_injected"):
            st.session_state._deep_link_analyze_injected = True
            components.html(_DEEP_LINK_ANALYZE_HTML, height=0, width=0)
        with st.container(border=False, key="analyze_zone"):
            st.markdown(
                '<span class="skin-analyze-zone" aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
            if st.button(
                "📊 Analyze Metrics",
                type="primary",
                use_container_width=True,
            ):
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
                    st.warning("Enter at least one Scopus Author ID or ORCID.")
                elif selected_metric_count == 0:
                    st.warning(
                        f"Select at least one metric before analyzing ({selected_metric_count} of {len(st.session_state.available_metrics)} metrics selected)."
                    )
                elif len(ids) > MAX_AUTHORS_PER_RUN:
                    st.warning(
                        f"Please limit to {MAX_AUTHORS_PER_RUN} Scopus Author IDs per run."
                    )
                else:
                    svc = get_api_service()
                    am_payload = [dict(m) for m in st.session_state.available_metrics]
                    try:
                        with st.spinner("Fetching metrics…"):
                            resolved_ids, resolution_warnings = (
                                resolve_author_ids_for_metrics_safe(
                                    ids, api_key_effective
                                )
                            )
                            if resolution_warnings:
                                msg = "Skipped unresolved ORCID input(s):\n- " + "\n- ".join(
                                    resolution_warnings
                                )
                                st.warning(msg)
                            if not resolved_ids:
                                st.session_state.error_msg = (
                                    "No valid Scopus Author ID could be resolved from the input."
                                )
                                st.session_state.results = []
                            elif len(resolved_ids) == 1:
                                try:
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
                                    st.session_state.entitlement_error = e.is_entitlement_error
                                    st.session_state.rate_limit_error = e.is_rate_limit_error
                                    if is_missing_scival_api_key_error(str(e)) or is_scival_authentication_error(
                                        str(e)
                                    ):
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
                                    )
                                )
                    except APIError as e:
                        st.session_state.error_msg = str(e)
                        st.session_state.results = []
                    except Exception as e:
                        st.session_state.error_msg = str(e)

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
                with st.container(border=False, key="export_workspace_stack"):
                    st.markdown(
                        _export_workspace_module_head_html(bundle_prep=True),
                        unsafe_allow_html=True,
                    )
                    if len(valid) >= 2:
                        st.markdown(
                            '<div class="analyze-hint" style="margin: 0 0 1rem 0;">'
                            '<div class="analyze-hint-inner">'
                            '<p class="analyze-hint-text">'
                            "Select metrics, their order, and which author(s) to include in the export, "
                            "then use Export Results below."
                            "</p>"
                            '<a class="analyze-hint-cta" href="#export-downloads-anchor">'
                            "Jump to export <span aria-hidden=\"true\">↓</span>"
                            "</a>"
                            "</div></div>",
                            unsafe_allow_html=True,
                        )
                    with st.container(border=False, key="export_prep_inner"):
                        en_m = _enabled_metric_ids(st.session_state.available_metrics)
                        order_opts_m = [
                            "publication",
                            "citationCount",
                            "citationsPerPublication",
                            "fwci",
                            "topJournal",
                            "hIndex",
                            "collaboration",
                            "academicCorporateCollaboration",
                        ]
                        label_map_m = {x["id"]: x["label"] for x in DEFAULT_METRICS}
                        opt_list_m = [i for i in order_opts_m if i in en_m]
                        st.markdown(
                            '<p class="prepare-export-heading">Export options</p>',
                            unsafe_allow_html=True,
                        )
                        st.caption(
                            "Choose metrics to include, drag to set row order, then pick one or more "
                            "authors. The PDF and Excel files produced in Export Results reflect only these choices."
                        )
                        picked_m, order_pick_m = _metrics_multiselect_and_order_ui(
                            opt_list_m,
                            label_map_m,
                            multiselect_label="Metrics to export",
                            multiselect_key="export_bundle_metrics_ms",
                            order_state_key="export_bundle_metrics_ord_state",
                            sortable_key="export_bundle_metrics_sort",
                            fallback_key="export_bundle_metrics_fallback",
                            step_multiselect=1,
                            step_order=2,
                        )
                        st.markdown(
                            '<p class="export-step-label" style="margin-top:0.65rem;">'
                            '<span class="export-step-badge" aria-hidden="true">(3)</span>'
                            '<span class="export-step-label-text">Author(s) to include in export</span></p>',
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
                        export_scholar_pick = [
                            r["id"]
                            for r in valid
                            if st.session_state.get(f"export_scholar_inc_{r['id']}", True)
                        ]
                        if not picked_m or not export_scholar_pick:
                            st.info(
                                "Select at least one metric and one author before generating the export."
                            )
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
                        '<hr class="export-workspace-split" aria-hidden="true" />',
                        unsafe_allow_html=True,
                    )
                    _render_export_results_block(export_rows, len(valid))
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
                        "collaboration",
                        "academicCorporateCollaboration",
                    ]
                    label_map = {x["id"]: x["label"] for x in DEFAULT_METRICS}
                    opt_list = [i for i in order_opts if i in en]

                    picked, order_pick = _metrics_multiselect_and_order_ui(
                        opt_list,
                        label_map,
                        multiselect_label="Rows to show in table",
                        multiselect_key=f"multisel_{aid}",
                        order_state_key=f"multiord_state_{aid}_{card_idx}",
                        sortable_key=f"multiord_sort_{aid}_{card_idx}",
                        fallback_key=f"multiord_fallback_{aid}_{card_idx}",
                    )

                    author_export_payload = {
                        "authorId": aid,
                        "authorName": d.get("authorName"),
                        "metrics": d.get("metrics"),
                        "dataSource": d.get("dataSource"),
                        "selectedMetrics": picked,
                        "metricOrder": order_pick,
                    }
                    col_names, table_rows = _build_metrics_table_rows(
                        d.get("metrics") or {},
                        ds,
                        picked,
                        order_pick,
                    )
                    if table_rows:
                        df = pd.DataFrame(table_rows, columns=col_names)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        try:
                            xl_author_b, xl_author_n = export_excel_bytes(
                                [author_export_payload],
                                f"research-metrics-{aid}",
                            )
                            st.download_button(
                                "Download this table (Excel)",
                                xl_author_b,
                                file_name=xl_author_n,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"export_xl_author_{aid}_{card_idx}",
                                use_container_width=False,
                            )
                        except Exception:
                            st.caption("Could not build Excel file for this author.")
    
                        years = []
                        for c in col_names[1:-1]:
                            try:
                                years.append(int(float(c)))
                            except Exception:
                                continue
                        if years:
                            c_filters, c_chart = st.columns([1, 3], vertical_alignment="top")
                            with c_filters:
                                st.markdown("#### Chart filters")
                                default_plot_metric = (
                                    "publication" if "publication" in picked else picked[0]
                                )
                                plot_metric = st.selectbox(
                                    "Metric",
                                    options=picked,
                                    index=picked.index(default_plot_metric),
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
                                st.caption("Axis is fixed: Year on X, Metric value on Y.")
    
                            with c_chart:
                                series_name_full = label_map.get(plot_metric, plot_metric)
                                # ECharts doesn't always handle long metric names well; use acronym
                                # (e.g. "Field-Weighted Citation Impact (FWCI)" -> "FWCI") for labels.
                                paren_match = re.search(r"\(([^)]+)\)", str(series_name_full))
                                series_name_short = (
                                    paren_match.group(1).strip()
                                    if paren_match
                                    else str(series_name_full)
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
                                            "show": True,
                                            "top": 8,
                                            "right": 10,
                                            "feature": {
                                                "saveAsImage": {"show": True, "title": "Download"},
                                                "restore": {"show": True},
                                                "dataZoom": {"show": True},
                                            },
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
                                            "data": x_years,
                                        },
                                        "yAxis": {"type": "value", "name": series_name_short},
                                        "series": [
                                            {
                                                "name": series_name_short,
                                                "type": chart_type.lower(),
                                                "data": values,
                                                "smooth": chart_type == "Line",
                                                "label": {
                                                    "show": True,
                                                    "position": "top",
                                                    "formatter": "{c}",
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
    
                    export_rows.append(author_export_payload)

            if len(valid) == 1:
                with st.container(border=False, key="export_workspace_stack"):
                    st.markdown(
                        _export_workspace_module_head_html(bundle_prep=False),
                        unsafe_allow_html=True,
                    )
                    _render_export_results_block(export_rows, len(valid))

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
    return {
        "hIndex": {"value": "N/A"},
        "scholarlyOutput": dict(na),
        "fwci": dict(na),
        "topJournal": dict(na),
        "citationCount": dict(na),
        "citationsPerPublication": dict(na),
        "collaboration": dict(na),
        "academicCorporateCollaboration": dict(na),
    }


if __name__ == "__main__":
    main()
