"""
PyECharts Excel visualizer for the exported `research-metrics.xlsx` report.

Run:
  streamlit run streamlit_app/excel_pyecharts_viz.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from pyecharts import options as opts
from pyecharts.charts import Bar, Line


DEFAULT_EXCEL_PATH = Path(r"C:\Users\User\Downloads\research-metrics.xlsx")
DEFAULT_SHEET_NAME = "Metrics"


def _find_header_row_index(raw_df: pd.DataFrame) -> int:
    """
    The Excel export is a compact table with some report metadata above the header.
    We detect the header row by looking for a first-cell value equal to `Metric`.
    """

    for i in range(len(raw_df)):
        v = raw_df.iat[i, 0]
        if isinstance(v, str) and v.strip().lower() == "metric":
            return i
    raise ValueError("Could not find the table header row (expected a row starting with 'Metric').")


def load_metrics_table(excel_path: Path, sheet_name: str = DEFAULT_SHEET_NAME) -> tuple[pd.DataFrame, list[int]]:
    raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row_index(raw)

    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row)

    # First column should be the metric name.
    cols = list(df.columns)
    if not cols:
        raise ValueError("Excel sheet appears to be empty.")
    df = df.rename(columns={cols[0]: "Metric"})

    df = df.dropna(subset=["Metric"]).copy()
    df["Metric"] = df["Metric"].astype(str).str.strip()

    # Detect year columns (export uses columns like 2020.0, 2021.0, ...).
    year_cols: dict[int, str] = {}
    for col in df.columns:
        if str(col).strip().lower() == "total":
            continue
        try:
            year_int = int(float(col))
        except Exception:
            continue
        year_cols[year_int] = col

    years = sorted(year_cols)
    if not years:
        raise ValueError("No year columns detected in the 'Metrics' sheet.")

    keep_cols = ["Metric"] + [year_cols[y] for y in years]
    df = df[keep_cols].copy()
    for c in keep_cols:
        if c == "Metric":
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df, years


def make_chart(
    chart_type: str,
    metric_name: str,
    years: list[int],
    values: list[float | None],
    invert_axes: bool,
):
    if invert_axes:
        # Interpret: X = metric values, Y = year.
        x_data = ["" if v is None else str(v) for v in values]
        y_data = years
        x_title = f"{metric_name} (value)"
        y_title = "Year"
    else:
        # Recommended: X = year, Y = metric value.
        x_data = [str(y) for y in years]
        y_data = [0 if v is None else v for v in values]
        x_title = "Year"
        y_title = metric_name

    if chart_type == "Bar":
        chart = Bar(init_opts=opts.InitOpts(width="100%", height="420px"))
        chart.add_xaxis(x_data)
        chart.add_yaxis(metric_name, y_data)
        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=f"{metric_name} ({'Year on X' if not invert_axes else 'Year on Y'})"),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            xaxis_opts=opts.AxisOpts(name=x_title),
            yaxis_opts=opts.AxisOpts(
                name=y_title,
                name_location="middle",
                name_gap=56,
                name_rotate=90 if not invert_axes else 0,
            ),
        )
        return chart

    chart = Line(init_opts=opts.InitOpts(width="100%", height="420px"))
    chart.add_xaxis(x_data)
    chart.add_yaxis(metric_name, y_data, is_smooth=True, is_symbol_show=True)
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=f"{metric_name} ({'Year on X' if not invert_axes else 'Year on Y'})"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name=x_title),
        yaxis_opts=opts.AxisOpts(
            name=y_title,
            name_location="middle",
            name_gap=56,
            name_rotate=90 if not invert_axes else 0,
        ),
    )
    return chart


def main() -> None:
    st.set_page_config(
        page_title="Excel -> PyECharts",
        page_icon="📊",
        layout="wide",
    )

    st.title("Research Metrics Excel Visualizer")
    st.caption("Reads the exported `Metrics` sheet and renders Bar/Line charts using PyECharts.")

    uploaded = st.file_uploader("Upload `research-metrics.xlsx` (recommended)", type=["xlsx"])

    if uploaded is not None:
        tmp_dir = Path(tempfile.gettempdir())
        excel_path = tmp_dir / uploaded.name
        excel_path.write_bytes(uploaded.getbuffer())
    else:
        excel_path = DEFAULT_EXCEL_PATH
        if not excel_path.exists():
            st.error("No upload provided, and the default file path does not exist.")
            st.write(str(DEFAULT_EXCEL_PATH))
            st.stop()

    try:
        metrics_df, years = load_metrics_table(excel_path)
    except Exception as e:
        st.exception(e)
        st.stop()

    st.subheader("Preview (detected)")
    st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    metric_options = metrics_df["Metric"].tolist()
    default_metric = (
        "Publications"
        if "Publications" in metric_options
        else (
            "Publication"
            if "Publication" in metric_options
            else ("Scholarly Output" if "Scholarly Output" in metric_options else None)
        )
    )
    selected_metric = st.selectbox(
        "Metric (rows in the Excel)",
        options=metric_options,
        index=metric_options.index(default_metric)
        if default_metric and default_metric in metric_options
        else 0,
    )
    st.caption("Tip: pick `Publications` to review counts by year (legacy sheets may still say `Publication`).")

    chart_type = st.radio("Chart type", options=["Bar", "Line"], horizontal=True, index=0)
    invert_axes = st.checkbox("Invert axes (metric value on X, year on Y)", value=False)

    row = metrics_df.loc[metrics_df["Metric"] == selected_metric].iloc[0]
    year_cols = [c for c in metrics_df.columns if c != "Metric"]
    values = [row[c] if pd.notna(row[c]) else None for c in year_cols]

    chart = make_chart(
        chart_type=chart_type,
        metric_name=selected_metric,
        years=years,
        values=values,
        invert_axes=invert_axes,
    )

    st.subheader("Visualization")
    html = chart.render_embed()
    components.html(html, height=460, scrolling=True)

    st.caption(
        "Note: in this Excel export, `Publications` is the metric row (older files may use `Publication`); years are columns, so the default chart plots publication year (X) vs count (Y)."
    )


if __name__ == "__main__":
    main()

