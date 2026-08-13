"""
Auto-chart heuristic for arbitrary NL-to-SQL results.

Not every result is chartable, and this doesn't try to force one — a
single-row aggregate ("average resolution time for High priority incidents")
has nothing to plot, and returning None for that case is correct behavior,
not a missing feature. Only two shapes are handled, because they're the only
two shapes that come up naturally from this schema and views:
  - a time series (the monthly-trend shape: 'period' + 'incident_count')
  - one category column + one numeric measure, small enough to read as bars

No Streamlit import here, same convention as the rest of src/ — app.py calls
st.pyplot() on whatever Figure this returns.
"""
import matplotlib

matplotlib.use("Agg")  # headless rendering, no display backend needed on a server
import matplotlib.pyplot as plt
import pandas as pd

ACCENT = "#7C6CF0"
BG = "#141826"
TEXT = "#E7E9F5"
GRID = "#2A3040"

MAX_CATEGORIES = 15  # past this, a bar chart stops being readable — skip it, table only


def build_result_chart(df: pd.DataFrame):
    """Returns a matplotlib Figure, or None if this result isn't chartable."""
    if df is None or df.empty:
        return None

    if "period" in df.columns and "incident_count" in df.columns and len(df) > 1:
        return _time_series_chart(df, "period", "incident_count")

    if len(df.columns) == 2:
        col_a, col_b = df.columns[0], df.columns[1]
        numeric_cols = [c for c in (col_a, col_b) if pd.api.types.is_numeric_dtype(df[c])]
        label_cols = [c for c in (col_a, col_b) if c not in numeric_cols]
        if len(numeric_cols) == 1 and len(label_cols) == 1 and 1 < len(df) <= MAX_CATEGORIES:
            return _category_bar_chart(df, label_cols[0], numeric_cols[0])

    return None


def _style_axes(ax, fig):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=TEXT, labelsize=9)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    for spine_name in ("top", "right"):
        ax.spines[spine_name].set_visible(False)
    for spine_name in ("left", "bottom"):
        ax.spines[spine_name].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.6, alpha=0.6)
    ax.set_axisbelow(True)


def _time_series_chart(df: pd.DataFrame, x_col: str, y_col: str):
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=150)
    x = pd.to_datetime(df[x_col])
    ax.bar(x, df[y_col], width=20, color=ACCENT)
    ax.set_ylabel(y_col.replace("_", " ").title())
    _style_axes(ax, fig)
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout()
    return fig


def _category_bar_chart(df: pd.DataFrame, label_col: str, value_col: str):
    plot_df = df.sort_values(value_col, ascending=True)
    labels = plot_df[label_col].astype(str)
    horizontal = len(plot_df) > 6 or labels.str.len().max() > 12

    if horizontal:
        fig, ax = plt.subplots(figsize=(7, max(2.5, 0.4 * len(plot_df) + 1)), dpi=150)
        ax.barh(labels, plot_df[value_col], color=ACCENT)
        ax.set_xlabel(value_col.replace("_", " ").title())
    else:
        fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)
        ax.bar(labels, plot_df[value_col], color=ACCENT)
        ax.set_ylabel(value_col.replace("_", " ").title())
        plt.setp(ax.get_xticklabels(), rotation=20, ha="right")

    _style_axes(ax, fig)
    fig.tight_layout()
    return fig
