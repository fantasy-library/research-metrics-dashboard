"""
Research Impact Dashboard — Streamlit port of the React/Vite app.
Run from repository root:  streamlit run streamlit_app/app.py
"""

from __future__ import annotations

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
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>'
    '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
)
_FILTER_ICON_DOCUMENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
    '<line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>'
)
_FILTER_ICON_FUNNEL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>'
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

/* Full-width Analyze CTA (sibling after metrics card; marker span for styling) */
[class*="st-key-analyze_zone"] {
  width: 100% !important;
  margin-top: 0.35rem !important;
  margin-bottom: 0.5rem !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"],
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"] {
  width: 100% !important;
  min-height: 3rem !important;
  height: auto !important;
  font-size: 1.02rem !important;
  border-radius: 12px !important;
  background: linear-gradient(180deg, #f8fbff 0%, #edf3fb 100%) !important;
  background-color: transparent !important;
  color: #4a5568 !important;
  border: 1px solid #7b92b1 !important;
  box-shadow: 0 10px 24px rgba(123, 146, 177, 0.12) !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em !important;
  transition: all 0.2s ease !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"]:hover,
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"]:hover {
  background: linear-gradient(180deg, #6f86a8 0%, #5c7cfa 100%) !important;
  border-color: #5c7cfa !important;
  color: #ffffff !important;
  box-shadow: 0 14px 30px rgba(92, 124, 250, 0.20) !important;
  transform: translateY(-1px);
}

/* Metric toggle cards: stronger “on” vs “off” affordance */
[class*="st-key-metric_card_"]:has(input:checked),
[class*="st-key-metric_card_"]:has(input:checked),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="true"]),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="true"]) {
  border-color: #a78bfa !important;
  background: linear-gradient(165deg, #faf5ff 0%, #ffffff 55%) !important;
  box-shadow:
    0 2px 8px rgba(124, 58, 237, 0.12),
    0 8px 20px rgba(15, 23, 42, 0.06) !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)),
[class*="st-key-metric_card_"]:has(input:not(:checked)),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]),
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) {
  border-color: #e5e7eb !important;
  background: #fafafa !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)) label,
[class*="st-key-metric_card_"]:has(input:not(:checked)) label,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) label,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) label {
  color: #64748b !important;
}
[class*="st-key-metric_card_"]:has(input:not(:checked)) p.metric-subtext,
[class*="st-key-metric_card_"]:has(input:not(:checked)) p.metric-subtext,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext,
[class*="st-key-metric_card_"]:has([role="switch"][aria-checked="false"]) p.metric-subtext {
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
/* Search, year/docs/self-cite filters, metrics: same white inset as .dash-top-header / .site-footer */
[class*="st-key-search_shell"],
[class*="st-key-metrics_panel_shell"] {
  padding: 2rem 1.75rem 1.5rem !important;
  background: #ffffff !important;
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

/* —— Search card (Netlify-style: bold title, lifted inputs) —— */
[class*="st-key-search_shell"] p.section-kicker {
  color: #4f46e5 !important;
  letter-spacing: 0.11em !important;
  font-weight: 800 !important;
}
[class*="st-key-search_shell"] p.section-title {
  font-size: 1.2rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.03em !important;
  color: #0f172a !important;
  padding-bottom: 0 !important;
  margin-bottom: 1.25rem !important;
  border-bottom: none !important;
  box-shadow: none !important;
}
[class*="st-key-search_shell"] [data-testid="stTextArea"] label p {
  font-weight: 800 !important;
  font-size: 1.02rem !important;
  color: #1e293b !important;
}
[class*="st-key-search_shell"] [data-testid="stTextArea"] {
  margin-top: 0.65rem !important;
}
[class*="st-key-search_shell"] textarea {
  border: 2px solid #e2e8f0 !important;
  border-radius: 16px !important;
  padding: 1rem 1.1rem !important;
  font-size: 0.95rem !important;
  line-height: 1.5 !important;
  background: #ffffff !important;
  /* Force readable text (paste/autofill/dark-mode quirks can set light fill) */
  color: #0f172a !important;
  -webkit-text-fill-color: #0f172a !important;
  caret-color: #0f172a !important;
  box-shadow:
    0 4px 18px rgba(15, 23, 42, 0.07),
    inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
  min-height: 132px !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
[class*="st-key-search_shell"] textarea::placeholder {
  color: #94a3b8 !important;
  opacity: 1 !important;
  -webkit-text-fill-color: #94a3b8 !important;
}
[class*="st-key-search_shell"] textarea::selection {
  background: rgba(99, 102, 241, 0.28) !important;
  color: #0f172a !important;
  -webkit-text-fill-color: #0f172a !important;
}
[class*="st-key-search_shell"] textarea:focus {
  border-color: #818cf8 !important;
  outline: none !important;
  box-shadow:
    0 0 0 4px rgba(129, 140, 248, 0.22),
    0 8px 28px rgba(79, 70, 229, 0.12) !important;
}

[class*="st-key-search_shell"] [data-testid="stCaption"] {
  font-size: 0.85rem !important;
  color: #4b5563 !important;
  margin-top: 0.35rem !important;
  margin-bottom: 0.2rem !important;
}

/* Search card: subtle left accent like the premium Netlify UI */
[class*="st-key-search_shell"] {
  border-left: 4px solid #e8eef7 !important;
}

/* Config panels: dropdown trigger — flat on panel tint */
[class*="st-key-filter_panel_blue"] [data-baseweb="select"] > div,
[class*="st-key-filter_panel_mint"] [data-baseweb="select"] > div {
  border-radius: 8px !important;
  border: 1px solid #dbe2ea !important;
  background: #ffffff !important;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06) !important;
  min-height: 44px !important;
}
[class*="st-key-filter_panel_blue"] [data-testid="stSelectbox"],
[class*="st-key-filter_panel_mint"] [data-testid="stSelectbox"] {
  background: transparent !important;
  border-radius: 8px !important;
}
[class*="st-key-filter_panel_blue"] [data-baseweb="select"] > div > div,
[class*="st-key-filter_panel_mint"] [data-baseweb="select"] > div > div {
  background: #ffffff !important;
}
[class*="st-key-filter_panel_blue"] [data-testid="stSelectbox"] label p,
[class*="st-key-filter_panel_mint"] [data-testid="stSelectbox"] label p {
  font-weight: 800 !important;
  font-size: 0.72rem !important;
  letter-spacing: 0.06em !important;
  text-transform: uppercase !important;
  color: #475569 !important;
}
/* Peach panel: radios directly on panel — no inner boxed well */
[class*="st-key-filter_panel_peach"] [data-testid="stRadio"] {
  margin-top: 0.15rem !important;
  padding: 0 !important;
  background: transparent !important;
  border-radius: 0 !important;
  border: none !important;
}
[class*="st-key-filter_panel_peach"] [data-testid="stRadio"] label {
  font-weight: 600 !important;
  font-size: 0.78rem !important;
  line-height: 1.38 !important;
  color: #7c2d12 !important;
}
[class*="st-key-filter_panel_peach"] [data-testid="stRadio"] label p {
  font-weight: 600 !important;
}
[class*="st-key-filter_panel_peach"] .stRadio input {
  accent-color: #ea580c !important;
}

/* Metrics container: white elevated card (same chrome as header/footer band) */
[class*="st-key-metrics_panel_shell"]:not(:has(span.skin-unified-form-shell)) {
  background: #f5f3ff !important;
  border: 1px solid rgba(226, 232, 240, 0.95) !important;
  border-left: 4px solid #7c3aed !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
  margin: 0.5rem 0 1.25rem 0 !important;
  box-shadow:
    0 4px 8px rgba(15, 23, 42, 0.04),
    0 14px 32px rgba(99, 102, 241, 0.08),
    0 24px 48px rgba(15, 23, 42, 0.06) !important;
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
/* Core research metrics: faint purple/gray well (toggles sit as white mini-cards on top) */
[class*="st-key-core_metrics_shell"]:not(:has(span.skin-unified-form-shell)) {
  background: transparent !important;
  border: none !important;
  border-radius: 12px !important;
  padding: 0 !important;
  margin-top: 0 !important;
  margin-bottom: 1rem !important;
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
}

/* Collaboration metrics group shell */
[class*="st-key-collab_metrics_shell"] {
  background: transparent !important;
}
/* Each toggle + subtext: premium grouped cell (marker span inside st.container) */
[class*="st-key-metric_card_"] {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 10px !important;
  padding: 0.85rem 0.95rem 0.65rem !important;
  margin-bottom: 0.8rem !important;
  min-height: 160px !important;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08) !important;
}
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
p.metric-subtext {
  color: #4b5563 !important;
  font-size: 0.85rem !important;
  margin-top: 4px !important;
  margin-bottom: 16px !important;
  padding: 0 !important;
  line-height: 1.5 !important;
}
/* Anchor for “Go to Analyze” link */
#analyze-metrics-anchor {
  scroll-margin-top: 1rem;
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
  background: linear-gradient(165deg, #f8fbff 0%, #eef3fa 55%, #e7edf6 100%);
  border: 1px solid rgba(123, 146, 177, 0.30) !important;
  border-radius: 12px;
  box-shadow:
    0 8px 20px rgba(15, 23, 42, 0.05),
    0 18px 40px rgba(123, 146, 177, 0.10);
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
  border-top: 1px solid rgba(123, 146, 177, 0.28);
  font-size: 0.78rem;
  color: #4a5568;
  line-height: 1.5;
}

/* Stable key-based styling to reduce rerun flicker from :has selectors */
[class*="st-key-search_shell"] {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  border-left: 4px solid #e8eef7 !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.1),
    0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
}
[class*="st-key-search_shell"] textarea {
  border: 2px solid #e2e8f0 !important;
  border-radius: 16px !important;
  background: #ffffff !important;
  color: #0f172a !important;
  -webkit-text-fill-color: #0f172a !important;
  caret-color: #0f172a !important;
}

[class*="st-key-metrics_panel_shell"] {
  background: #f5f3ff !important;
  border: 1px solid rgba(226, 232, 240, 0.95) !important;
  border-left: 4px solid #7c3aed !important;
  border-radius: 12px !important;
  padding: 2rem 1.75rem 1.5rem !important;
}
[class*="st-key-core_metrics_shell"],
[class*="st-key-collab_metrics_shell"] {
  background: transparent !important;
  border: none !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"],
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"] {
  width: 100% !important;
  min-height: 3rem !important;
  border-radius: 12px !important;
  background: linear-gradient(180deg, #f8fbff 0%, #edf3fb 100%) !important;
  background-color: transparent !important;
  color: #4a5568 !important;
  border: 1px solid #7b92b1 !important;
  box-shadow: 0 10px 24px rgba(123, 146, 177, 0.12) !important;
  font-weight: 700 !important;
  letter-spacing: 0.01em !important;
}
[class*="st-key-analyze_zone"] button[data-testid="stBaseButton-primary"]:hover,
[class*="st-key-analyze_zone"] button[data-testid="baseButton-primary"]:hover {
  background: linear-gradient(180deg, #6f86a8 0%, #5c7cfa 100%) !important;
  border-color: #5c7cfa !important;
  color: #ffffff !important;
  box-shadow: 0 14px 30px rgba(92, 124, 250, 0.20) !important;
  transform: translateY(-1px);
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
      <p class="sf-body">Clear Water Bay, Kowloon, Hong Kong</p>
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
        "enabled": False,
    },
    {
        "id": "academicCorporateCollaboration",
        "label": "Academic Corporate Collaboration",
        "description": "Academic–corporate collaboration breakdown",
        "enabled": False,
    },
]

YEAR_OPTIONS = {
    "3yrs": "Last 3 complete years — compact recent window",
    "3yrsAndCurrent": "Last 3 years + current year — includes in-progress year",
    "5yrs": "Last 5 complete years — balanced default window",
    "5yrsAndCurrent": "Last 5 years + current year — extended with current",
    "10yrs": "Last 10 complete years — long-term trend view",
}
MAX_AUTHORS_PER_RUN = 10

# Short labels for dropdowns (matches compact SaaS-style UI)
YEAR_OPTIONS_DISPLAY = {
    "3yrs": "Last 3 complete years",
    "3yrsAndCurrent": "Last 3 years + current year",
    "5yrs": "Last 5 years (default)",
    "5yrsAndCurrent": "Last 5 years + current year",
    "10yrs": "Last 10 complete years",
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
    "3yrs": "3 complete years",
    "3yrsAndCurrent": "3 complete years plus current year",
    "5yrs": "5 complete years",
    "5yrsAndCurrent": "5 complete years plus current year",
    "10yrs": "10 complete years",
}

SELF_CIT_HELP = (
    "Self-citations are citations where an author cites their own previous work."
)

DOCS_SELECTION_CAPTION = "Include all types matching your selection above."


def _init_session() -> None:
    if "disclaimer_ok" not in st.session_state:
        st.session_state.disclaimer_ok = False
    if "available_metrics" not in st.session_state:
        st.session_state.available_metrics = [dict(m) for m in DEFAULT_METRICS]
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

    st.markdown(
        '<p class="section-kicker" style="margin-bottom:0.25rem;">Compare</p>'
        '<p class="section-title">Authors across the same year range</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Uses the overlap of publication years from each author’s data. "
        "Charts are not included in PDF/Excel export."
    )

    def _pick_metric_idx(metric_id: str, default: str) -> int:
        try:
            return compare_opts.index(metric_id)
        except ValueError:
            try:
                return compare_opts.index(default)
            except ValueError:
                return 0

    # --- Line chart (SciVal-style multi-series) ---
    st.markdown("##### Metric over years (all authors)")
    line_metric = st.selectbox(
        "Metric",
        options=compare_opts,
        index=_pick_metric_idx("publication", "fwci"),
        format_func=lambda i: label_map.get(i, i),
        key="compare_line_metric",
    )
    line_chart_type = st.radio(
        "Chart type",
        options=["Line", "Bar"],
        horizontal=True,
        index=0,
        key="compare_line_type",
    )
    line_short = _metric_short_label(label_map, line_metric)

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
            toolbox_line["right"] = 10
            toolbox_line["top"] = 8
            line_opts = {
                "animation": True,
                "title": {
                    "text": f"{line_short} over years (all authors)",
                    "left": "center",
                    "top": 4,
                    "textStyle": {"fontSize": 15},
                },
                "tooltip": {"trigger": "axis"},
                "legend": {
                    "type": "plain",
                    "data": [s["name"] for s in line_series],
                    "top": 30,
                    "left": "center",
                    "right": 60,
                    "itemWidth": 10,
                    "itemHeight": 10,
                    "itemGap": 10,
                    "textStyle": {"fontSize": 11},
                },
                "toolbox": toolbox_line,
                "grid": {
                    "left": "6%",
                    "right": "5%",
                    "top": 116,
                    "bottom": 78,
                    "containLabel": True,
                },
                "xAxis": {"type": "category", "name": "Year", "data": x_years},
                "yAxis": {
                    "type": "value",
                    "name": line_short,
                    "nameLocation": "middle",
                    "nameGap": 55,
                },
                "series": line_series,
                "dataZoom": [
                    {"type": "inside"},
                    {"type": "slider", "height": 18, "bottom": 14},
                ],
            }
            st_echarts(
                options=line_opts,
                height="560px",
                key=f"compare_line_v2_{line_metric}_{line_chart_type}",
            )
            st.caption("Toolbar (top-right): camera icon to download image.")
        else:
            st.caption(
                "No series to plot for this metric (missing year data for all authors)."
            )

    st.divider()

    # --- Bubble chart (three dimensions: SciVal period totals, no year) ---
    st.markdown("##### Bubble chart (X × Y × size)")
    st.caption(
        "Each axis and bubble size use the **Total** value for your selected metric window "
        "(same SciVal period as the table), not a single calendar year."
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

    bx1, bx2, bx3 = st.columns(3)
    with bx1:
        y_metric = st.selectbox(
            "Y-axis",
            options=bubble_metric_opts,
            index=_bubble_pick_idx("topJournal", "fwci"),
            format_func=lambda i: label_map.get(i, i),
            key="compare_bubble_y_v2",
        )
    with bx2:
        x_metric = st.selectbox(
            "X-axis",
            options=bubble_metric_opts,
            index=_bubble_pick_idx("fwci", "publication"),
            format_func=lambda i: label_map.get(i, i),
            key="compare_bubble_x_v2",
        )
    with bx3:
        size_metric = st.selectbox(
            "Bubble size",
            options=bubble_metric_opts,
            index=_bubble_pick_idx("publication", "citationCount"),
            format_func=lambda i: label_map.get(i, i),
            key="compare_bubble_size_v2",
        )

    if len({x_metric, y_metric, size_metric}) < 3:
        st.warning("Choose three different metrics for X, Y, and bubble size.")
        return

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
        return

    size_px = _bubble_symbol_sizes([p[3] for p in plotted])

    def _fmt_val(v: float) -> str:
        if float(v).is_integer():
            return str(int(v))
        return f"{v:.4f}".rstrip("0").rstrip(".")

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
            "top": 8,
            "textStyle": {"fontSize": 15},
            "subtextStyle": {"fontSize": 12, "color": "#555"},
        },
        "grid": {
            "left": "6%",
            "right": "5%",
            "top": 138,
            "bottom": "14%",
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
            "top": 58,
            "left": "center",
            "itemWidth": 10,
            "itemHeight": 10,
            "itemGap": 10,
            "textStyle": {"fontSize": 11},
        },
        "toolbox": toolbox_bubble,
        "xAxis": {
            "type": "value",
            "name": x_name,
            "nameLocation": "middle",
            "nameGap": 36,
            "scale": True,
        },
        "yAxis": {
            "type": "value",
            "name": y_name,
            "nameLocation": "middle",
            "nameGap": 50,
            "scale": True,
        },
        "series": bubble_series,
        "dataZoom": [
            {"type": "inside"},
            {"type": "slider", "height": 18},
        ],
    }
    st_echarts(
        options=bubble_opts,
        height="520px",
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
    # Streamlit right-aligns numeric dtypes; cast metric columns to text for left alignment.
    for col in (x_lbl, y_lbl, sz_lbl):
        tbl_df[col] = tbl_df[col].map(_fmt_val)
    st.caption("Totals used for position and bubble size (same period as your search):")
    st.dataframe(tbl_df, use_container_width=True, hide_index=True)


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
      This dashboard provides a high-level synthesis of research impact via Elsevier&rsquo;s SciVal APIs.
      Designed for rapid insight, this dashboard serves as a strategic shortcut; for granular benchmarking and
      comprehensive longitudinal data, please consult the full <a href="https://lbdiscover.hkust.edu.hk/bib/991012525864503412" target="_blank" rel="noopener noreferrer">SciVal platform</a> via HKUST Library.
    </p>
    <p>
      <strong>Important: Metric accuracy is contingent upon your Scopus Author ID integrity. We strongly recommend
      verifying your profile to ensure all citations and publications are correctly attributed.</strong>
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

    # --- Search + filters + metrics (distinct white cards on slate page bg) ---
    with st.container():
        # Card 1: Search configuration
        with st.container(border=True, key="search_shell"):
            st.markdown(
                '<span class="skin-search-shell" aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="section-title" style="margin:0;">Search Configuration</p>',
                unsafe_allow_html=True,
            )

            author_ids = st.text_area(
                "Scopus Author ID (preferred) or ORCID ID",
                placeholder=(
                    "Scopus Author ID(s) or ORCID(s). ORCIDs are resolved automatically before metrics. "
                    "Separate multiple values with commas, semicolons, or new lines."
                ),
                help=(
                    f"Scopus Author ID and/or ORCID (max {MAX_AUTHORS_PER_RUN} per run). "
                    "ORCIDs are looked up via SciVal first, then metrics use the Scopus Author ID."
                ),
                label_visibility="visible",
                key="scopus_author_ids",
            )
            st.caption(
                "Need help with profiles? [Researcher Profile and Visibility](https://libguides.hkust.edu.hk/research-impact/research-visibility)"
            )
            parsed_ids_preview = [
                x.strip() for x in re.split(r"[,\n;]+", author_ids) if x.strip()
            ]
            st.caption(
                f"Parsed author IDs: {len(parsed_ids_preview)} / {MAX_AUTHORS_PER_RUN}."
            )
            if len(parsed_ids_preview) > MAX_AUTHORS_PER_RUN:
                st.warning(
                    f"You entered {len(parsed_ids_preview)} IDs. "
                    f"Please keep it to {MAX_AUTHORS_PER_RUN} or fewer per run."
                )

            st.markdown(
                '<div class="analyze-hint">'
                '<div class="analyze-hint-inner">'
                '<p class="analyze-hint-text">'
                "Select the metrics below and press <strong>Analyze Metrics</strong>."
                "</p>"
                '<a class="analyze-hint-cta" href="#analyze-metrics-anchor">'
                "Go to Analyze <span aria-hidden=\"true\">↗</span>"
                "</a>"
                "</div></div>",
                unsafe_allow_html=True,
            )

        # Card 2: Filter panels (3-column grid on white surface)
        with st.container(border=True, key="filter_deck_shell"):
            st.markdown(
                '<span class="skin-filter-deck-shell" aria-hidden="true"></span>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="filters-row-intro">'
                '<p class="filters-row-kicker">Analysis scope</p>'
                "<p class=\"filters-row-title\">Filters</p>"
                "<p class=\"filters-row-sub\">Set the time window, document types, and self-citation rules. "
                "Each panel applies before metrics are fetched.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            fy, fd, fs = st.columns(3)
            with fy:
                with st.container(border=True, key="filter_panel_blue"):
                    st.markdown(
                        '<span class="skin-filter-panel" data-theme="blue" aria-hidden="true"></span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '<div class="filter-panel-head filter-panel-head--blue">'
                        '<div class="filter-panel-icon-wrap" aria-hidden="true">'
                        f"{_FILTER_ICON_CALENDAR}"
                        "</div>"
                        "<div>"
                        '<p class="filter-panel-kicker">Year range</p>'
                        '<p class="filter-panel-title">Filter by Year Range</p>'
                        "<p class=\"filter-panel-sub\">Which publication years feed into SciVal metrics.</p>"
                        "</div></div>",
                        unsafe_allow_html=True,
                    )
                    year_key = st.selectbox(
                        "Time window",
                        options=list(YEAR_OPTIONS.keys()),
                        format_func=lambda k: YEAR_OPTIONS_DISPLAY[k],
                        index=list(YEAR_OPTIONS.keys()).index("5yrs"),
                        help=(
                            "SciVal applies this window consistently across scholarly output, "
                            "citations, FWCI, and related fields."
                        ),
                    )
                    st.caption(YEAR_FOOTNOTES.get(year_key, ""))
            with fd:
                with st.container(border=True, key="filter_panel_mint"):
                    st.markdown(
                        '<span class="skin-filter-panel" data-theme="mint" aria-hidden="true"></span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '<div class="filter-panel-head filter-panel-head--mint">'
                        '<div class="filter-panel-icon-wrap" aria-hidden="true">'
                        f"{_FILTER_ICON_DOCUMENT}"
                        "</div>"
                        "<div>"
                        '<p class="filter-panel-kicker">Document types</p>'
                        '<p class="filter-panel-title">Filter by Document Types</p>'
                        "<p class=\"filter-panel-sub\">Limit which document categories are counted.</p>"
                        "</div></div>",
                        unsafe_allow_html=True,
                    )
                    docs_key = st.selectbox(
                        "Document types",
                        options=list(DOCS_OPTIONS.keys()),
                        format_func=lambda k: DOCS_OPTIONS_DISPLAY[k],
                        help=(
                            "Filters the document set before metrics are computed. "
                            "Default includes all publication types."
                        ),
                    )
                    st.caption(DOCS_SELECTION_CAPTION)
            with fs:
                with st.container(border=True, key="filter_panel_peach"):
                    st.markdown(
                        '<span class="skin-filter-panel" data-theme="peach" aria-hidden="true"></span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '<div class="filter-panel-head filter-panel-head--peach">'
                        '<div class="filter-panel-icon-wrap" aria-hidden="true">'
                        f"{_FILTER_ICON_FUNNEL}"
                        "</div>"
                        "<div>"
                        '<p class="filter-panel-kicker">Self-citations</p>'
                        '<p class="filter-panel-title">Self-Citations Filter</p>'
                        "<p class=\"filter-panel-sub\">Include or exclude an author’s citations to their own work.</p>"
                        "</div></div>",
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
                    st.caption(SELF_CIT_HELP)

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
            st.caption("Toggle metrics on or off. Unchecked metrics are not requested from the API.")

            am = st.session_state.available_metrics
            # Keep widget state as the single source of truth to avoid
            # Streamlit warnings about using both `value` and Session State.
            for m in am:
                mk = f"met_{m['id']}"
                if mk not in st.session_state:
                    st.session_state[mk] = bool(m.get("enabled"))
                m["enabled"] = bool(st.session_state[mk])
            n_on = sum(1 for m in am if m.get("enabled"))
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

            core = am[:6]
            with st.container(border=True, key="core_metrics_shell"):
                st.markdown(
                    '<span class="skin-core-metrics-shell" aria-hidden="true"></span>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<p class="metrics-subhead" style="margin: 0 0 1rem 0;">Core research metrics</p>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Need additional metrics? [SciVal](https://lbdiscover.hkust.edu.hk/bib/991012525864503412)"
                )
                cols_c = st.columns(3)
                for i, metric in enumerate(core):
                    with cols_c[i % 3]:
                        with st.container(key=f"metric_card_{metric['id']}"):
                            st.markdown(
                                '<span class="toggle-metric-pair" aria-hidden="true"></span>',
                                unsafe_allow_html=True,
                            )
                            metric["enabled"] = st.toggle(
                                metric["label"],
                                key=f"met_{metric['id']}",
                            )
                            st.markdown(
                                f'<p class="metric-subtext">{html.escape(metric.get("description", ""))}</p>',
                                unsafe_allow_html=True,
                            )

            st.markdown(
                '<p class="metrics-subhead">Collaboration metrics</p>',
                unsafe_allow_html=True,
            )
            collab = am[6:]
            with st.container(border=True, key="collab_metrics_shell"):
                st.markdown(
                    '<span class="skin-collab-metrics-shell" aria-hidden="true"></span>',
                    unsafe_allow_html=True,
                )
                cols_b = st.columns(2)
                for i, metric in enumerate(collab):
                    with cols_b[i % 2]:
                        with st.container(key=f"metric_card_{metric['id']}"):
                            st.markdown(
                                '<span class="toggle-metric-pair" aria-hidden="true"></span>',
                                unsafe_allow_html=True,
                            )
                            metric["enabled"] = st.toggle(
                                metric["label"],
                                key=f"met_{metric['id']}",
                            )
                            st.markdown(
                                f'<p class="metric-subtext">{html.escape(metric.get("description", ""))}</p>',
                                unsafe_allow_html=True,
                            )

        st.markdown(
            '<div id="analyze-metrics-anchor"></div>',
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
                "📈 Analyze Metrics",
                type="primary",
                use_container_width=True,
            ):
                st.session_state.error_msg = ""
                st.session_state.entitlement_error = False
                st.session_state.rate_limit_error = False
                st.session_state.results = []
                # Accept common separators: commas, semicolons, and new lines.
                ids = [x.strip() for x in re.split(r"[,\n;]+", author_ids) if x.strip()]
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
            st.markdown(
                '<p class="section-kicker">Output</p><p class="section-title">Results & export</p>',
                unsafe_allow_html=True,
            )
            label_map_global = {x["id"]: x["label"] for x in DEFAULT_METRICS}
            _render_compare_authors_charts(valid, label_map_global)
            if len(valid) >= 2:
                st.markdown(
                    '<div class="analyze-hint" style="margin: 0.35rem 0 1.1rem 0;">'
                    '<div class="analyze-hint-inner">'
                    '<p class="analyze-hint-text">'
                    "PDF and Excel export are at the bottom of this results section."
                    "</p>"
                    '<a class="analyze-hint-cta" href="#export-downloads-anchor">'
                    "Download all — jump to export <span aria-hidden=\"true\">↓</span>"
                    "</a>"
                    "</div></div>",
                    unsafe_allow_html=True,
                )
            export_rows = []
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

                picked = st.multiselect(
                    "Rows to show in table",
                    options=opt_list,
                    default=opt_list,
                    format_func=lambda i: label_map.get(i, i),
                    key=f"multisel_{aid}",
                )
                if not picked:
                    st.caption("Select at least one metric row to display.")
                    order_pick = []
                else:
                    # Drag-and-drop reorder control for dynamic arrangement.
                    order_state_key = f"multiord_state_{aid}_{card_idx}"
                    existing_order = st.session_state.get(order_state_key, picked.copy())
                    existing_order = [m for m in existing_order if m in picked]
                    for m in picked:
                        if m not in existing_order:
                            existing_order.append(m)
                    st.session_state[order_state_key] = existing_order
                    order_pick = existing_order

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
                        key=f"multiord_sort_{aid}_{card_idx}",
                    )
                    # Defensive fallback: if component returns empty/invalid, keep previous order.
                    if (
                        isinstance(sorted_display, list)
                        and sorted_display
                        and all(isinstance(s, str) for s in sorted_display)
                    ):
                        order_pick = [
                            display_to_metric[s]
                            for s in sorted_display
                            if s in display_to_metric
                        ]
                    else:
                        st.caption(
                            "Drag area unavailable for this card. Use fallback selector below."
                        )
                        fallback_display = st.multiselect(
                            "Fallback order",
                            options=list(display_to_metric.keys()),
                            default=list(display_to_metric.keys()),
                            key=f"multiord_fallback_{aid}_{card_idx}",
                            label_visibility="collapsed",
                        )
                        if fallback_display:
                            order_pick = [
                                display_to_metric[s]
                                for s in fallback_display
                                if s in display_to_metric
                            ]
                        else:
                            order_pick = existing_order
                    st.session_state[order_state_key] = order_pick
                    st.caption(
                        "Current order: "
                        + " -> ".join(label_map.get(i, i) for i in order_pick)
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
                                st.caption(
                                    "Use the chart toolbar (top-right) -> camera icon to download image."
                                )

                export_rows.append(author_export_payload)

            st.markdown(
                '<div id="export-downloads-anchor"></div>',
                unsafe_allow_html=True,
            )
            st.divider()
            with st.container(border=True, key="export_results_shell"):
                st.markdown(
                    '<div class="export-results-head">'
                    '<div class="export-results-head-row">'
                    '<div class="export-results-badge" aria-hidden="true">'
                    f"{_FILTER_ICON_DOCUMENT}"
                    "</div>"
                    '<div class="export-results-head-text">'
                    '<p class="export-results-title">Export Results</p>'
                    "<p class=\"export-results-sub\">"
                    "Download your research metrics in PDF or Excel. "
                    "Set the filename below; the file includes all authors in this run."
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
