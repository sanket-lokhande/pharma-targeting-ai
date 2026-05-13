from __future__ import annotations

from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.figure import Figure

from app.schemas import MetricWeight
from app.services.analysis_engine import build_analysis_payload
from app.services.exporter import build_excel_output
from app.services.validation import validate_dataframe


st.set_page_config(page_title="Pharma Targeting AI", page_icon="💊", layout="wide")

st.title("Pharma Targeting AI")
st.caption("Decile-based HCP segmentation, comparison, and market insights")


# ---------- Sidebar inputs ----------
with st.sidebar:
    st.header("Inputs")
    current_file = st.file_uploader("Current period file (.xlsx) *", type=["xlsx"], key="current")
    previous_file = st.file_uploader("Previous period file (.xlsx, optional)", type=["xlsx"], key="previous")
    disease_market = st.text_input("Disease Market", placeholder="e.g., aGvHD, cGvHD, Hematology")
    enable_live_research = st.checkbox("Enable live internet research", value=False)

    st.divider()
    st.header("Segmentation settings")
    algorithm = st.selectbox("Segmentation algorithm", ["kmeans", "hierarchical", "rule_based"], index=0)
    n_clusters = st.number_input("Number of clusters", min_value=2, max_value=8, value=3, step=1)
    normalization = st.selectbox("Normalization", ["minmax", "zscore"], index=0)


# ---------- Load current file & metrics ----------
if not current_file:
    st.info("Upload a current period .xlsx file in the sidebar to begin.")
    st.stop()

try:
    current_raw = pd.read_excel(current_file, engine="openpyxl")
    id_column, metric_columns, validation_notes, current_df = validate_dataframe(current_raw)
except Exception as exc:
    st.error(f"Could not process current file: {exc}")
    st.stop()

st.success(f"Detected ID column: **{id_column}**  •  {len(metric_columns)} numeric metrics  •  {len(current_df)} rows")


# ---------- Weight assignment ----------
st.subheader("Assign metric weights (total must equal 100)")
st.caption("Set a weight to 0 to exclude a metric from the analysis.")

default_weight = round(100.0 / max(len(metric_columns), 1), 2)
weights: dict[str, float] = {}

cols = st.columns(2)
for idx, metric in enumerate(metric_columns):
    with cols[idx % 2]:
        weights[metric] = st.number_input(
            metric,
            min_value=0.0,
            max_value=100.0,
            value=float(default_weight),
            step=1.0,
            key=f"w_{metric}",
        )

total = round(sum(weights.values()), 2)
if abs(total - 100.0) < 0.01:
    st.success(f"Total: {total}")
else:
    st.warning(f"Total: {total} (must equal 100)")


# ---------- Run analysis ----------
run = st.button("Run Analysis", type="primary", disabled=abs(total - 100.0) > 0.01)

if not run:
    st.stop()

selected_weights = {m: w for m, w in weights.items() if w > 0}
if not selected_weights:
    st.error("Select at least one metric with weight greater than 0.")
    st.stop()

metric_weights = [MetricWeight(metric=m, weight=w) for m, w in selected_weights.items()]

previous_df = None
previous_id_column = None
if previous_file:
    try:
        previous_raw = pd.read_excel(previous_file, engine="openpyxl")
        previous_id_column, _, _, previous_df = validate_dataframe(previous_raw)
    except Exception as exc:
        st.error(f"Could not process previous file: {exc}")
        st.stop()

with st.spinner("Running analysis..."):
    try:
        payload = build_analysis_payload(
            current_df=current_df,
            id_column=id_column,
            metric_weights=metric_weights,
            normalization=normalization,
            segmentation_algorithm=algorithm,
            n_clusters=int(n_clusters),
            validation_notes=validation_notes,
            previous_df=previous_df,
            previous_id_column=previous_id_column,
            disease_market=disease_market.strip() or None,
            enable_live_research=enable_live_research,
        )
    except Exception as exc:
        st.exception(exc)
        st.stop()


# ---------- Summary ----------
st.subheader("Summary insights")
for item in payload.get("summary_insights", []):
    st.write(f"- {item}")


# ---------- Excel download ----------
excel_bytes = build_excel_output(payload)
file_name = f"client_ready_targeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
st.download_button(
    label="⬇ Download client-ready Excel workbook",
    data=excel_bytes,
    file_name=file_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ---------- Dashboard ----------
st.subheader("Dashboard")

raw = payload.get("raw_with_scores", [])
if not raw:
    st.info("No scored data available for charts.")
    st.stop()

df = pd.DataFrame(raw)
if df.empty or "decile" not in df.columns or "composite_score" not in df.columns:
    st.info("Charts unavailable: missing decile/composite_score columns.")
    st.stop()


def plot_lorenz(ax, df: pd.DataFrame) -> None:
    work = df[["decile", "composite_score"]].copy()
    work["decile_num"] = work["decile"].astype(str).str.replace("D", "", regex=False).astype(int)
    grouped = (
        work.groupby("decile_num", as_index=False)
        .agg(prescribers=("composite_score", "count"), potential=("composite_score", "sum"))
        .sort_values("decile_num", ascending=False)
    )
    grouped["cum_prescribers"] = grouped["prescribers"].cumsum()
    grouped["cum_potential"] = grouped["potential"].cumsum()
    total_p = grouped["prescribers"].sum() or 1
    total_v = grouped["potential"].sum() or 1
    x = (grouped["cum_potential"] / total_v) * 100
    y = (grouped["cum_prescribers"] / total_p) * 100
    x = pd.concat([pd.Series([0.0]), x], ignore_index=True)
    y = pd.concat([pd.Series([0.0]), y], ignore_index=True)
    ax.plot(x, y, marker="o", linewidth=2.6, color="#2A6FBA")
    ax.plot([0, 100], [0, 100], linestyle="--", linewidth=1.2, color="#A0A7B4")
    ax.fill_between(x, y, alpha=0.15, color="#2A6FBA")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_title("Lorenz Curve for HCPs", fontweight="bold")
    ax.set_xlabel("Cumulative % of Potential")
    ax.set_ylabel("Cumulative % of Prescribers")
    ax.grid(alpha=0.3)


def plot_bubble(ax, df: pd.DataFrame, selected_metrics: list[str]) -> None:
    axis_metrics = [m for m in selected_metrics if m in df.columns][:2]
    if len(axis_metrics) < 2:
        axis_metrics = ["composite_score", "decile_numeric"] if "decile_numeric" in df.columns else ["composite_score", "composite_score"]
    x_col, y_col = axis_metrics[0], axis_metrics[1]
    labels = df["segment_label"].fillna("Segment") if "segment_label" in df.columns else pd.Series(["Segment"] * len(df))
    unique_labels = sorted(labels.unique())
    comp = df["composite_score"].astype(float)
    cmin, cmax = float(comp.min()), float(comp.max())
    sizes = np.full(len(df), 90.0) if cmax - cmin <= 1e-9 else 60 + 340 * ((comp - cmin) / (cmax - cmin))
    palette = ["#2A6FBA", "#EF476F", "#06D6A0", "#8D6CAB", "#F4A261", "#118AB2", "#8338EC"]
    for idx, label in enumerate(unique_labels):
        mask = labels == label
        ax.scatter(
            df.loc[mask, x_col], df.loc[mask, y_col],
            s=sizes[mask.values], alpha=0.65,
            color=palette[idx % len(palette)],
            edgecolors="#2F3B52", linewidths=0.4, label=str(label),
        )
    ax.set_title("Cluster Bubble View", fontweight="bold")
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=8, frameon=False)


def plot_decile(ax, df: pd.DataFrame) -> None:
    counts = (
        df["decile"].astype(str).str.replace("D", "", regex=False).astype(int)
        .value_counts().sort_index(ascending=False)
    )
    deciles = [f"D{d}" for d in counts.index.tolist()]
    vals = counts.values.tolist()
    bars = ax.bar(deciles, vals, color="#457B9D", edgecolor="#2F3B52", linewidth=0.6)
    ax.set_title("HCP Count by Decile", fontweight="bold")
    ax.set_xlabel("Decile")
    ax.set_ylabel("Number of HCPs")
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(value),
                ha="center", va="bottom", fontsize=8)


col1, col2 = st.columns(2)
with col1:
    fig1 = Figure(figsize=(6, 4.2))
    plot_lorenz(fig1.add_subplot(111), df)
    fig1.tight_layout()
    st.pyplot(fig1)
with col2:
    fig2 = Figure(figsize=(6, 4.2))
    plot_bubble(fig2.add_subplot(111), df, list(selected_weights.keys()))
    fig2.tight_layout()
    st.pyplot(fig2)

fig3 = Figure(figsize=(12, 3.6))
plot_decile(fig3.add_subplot(111), df)
fig3.tight_layout()
st.pyplot(fig3)


# ---------- Scored data preview ----------
with st.expander("Scored data (first 100 rows)"):
    st.dataframe(df.head(100), use_container_width=True)
