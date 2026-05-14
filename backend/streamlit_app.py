from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.schemas import MetricWeight
from app.services.analysis_engine import build_analysis_payload
from app.services.exporter import build_excel_output
from app.services.validation import validate_dataframe


st.set_page_config(page_title="Pharma Targeting AI", page_icon="💊", layout="wide")

st.title("Pharma Targeting AI")
st.caption("Interactive decile and composite-score targeting dashboard")
st.info("Web build marker: 2026-05-14-UI-R3")


# ---------- Sidebar inputs ----------
with st.sidebar:
    st.header("Inputs")
    current_file = st.file_uploader("Current period file (.xlsx) *", type=["xlsx"], key="current")
    previous_file = st.file_uploader("Previous period file (.xlsx, optional)", type=["xlsx"], key="previous")

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
        )
    except Exception as exc:
        st.exception(exc)
        st.stop()


# ---------- Summary ----------
st.subheader("Summary insights")
for item in payload.get("summary_insights", []):
    st.write(f"- {item}")


st.subheader("Segment Summary")
segment_band_df = pd.DataFrame(payload.get("segment_band_summary", []))
if not segment_band_df.empty:
    cards = st.columns(3)
    for idx, row in segment_band_df.iterrows():
        with cards[idx % 3]:
            st.metric(label=str(row["segment_band"]), value=f"{int(row['hcp_count']):,}", delta=f"{float(row['hcp_pct']):.1f}% of HCPs")
else:
    st.info("Segment band summary is unavailable for this run.")


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

def _build_lorenz(df: pd.DataFrame) -> pd.DataFrame:
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
    lorenz_df = pd.DataFrame(
        {
            "cum_prescribers_pct": (grouped["cum_prescribers"] / total_p) * 100,
            "cum_potential_pct": (grouped["cum_potential"] / total_v) * 100,
            "decile": grouped["decile_num"].astype(int).map(lambda x: f"D{x}"),
        }
    )
    start = pd.DataFrame([{"cum_prescribers_pct": 0.0, "cum_potential_pct": 0.0, "decile": "Start"}])
    return pd.concat([start, lorenz_df], ignore_index=True)


def _build_decile_counts(df: pd.DataFrame) -> pd.DataFrame:
    decile_nums = (
        df["decile"].astype(str).str.replace("D", "", regex=False).astype(int)
    )
    series = decile_nums.value_counts().sort_index(ascending=False)
    return pd.DataFrame({
        "decile_num": [int(d) for d in series.index],
        "decile": [f"D{int(d)}" for d in series.index],
        "hcp_count": series.values,
    })


col1, col2 = st.columns(2)

with col1:
    lorenz_df = _build_lorenz(df)
    lorenz_fig = go.Figure()
    lorenz_fig.add_trace(
        go.Scatter(
            x=lorenz_df["cum_prescribers_pct"],
            y=lorenz_df["cum_potential_pct"],
            mode="lines+markers",
            line={"width": 3, "color": "#1f77b4"},
            name="Lorenz curve",
            hovertemplate="Cum. Prescribers: %{x:.1f}%<br>Cum. Potential: %{y:.1f}%<extra></extra>",
        )
    )
    lorenz_fig.add_trace(
        go.Scatter(
            x=[0, 100],
            y=[0, 100],
            mode="lines",
            line={"dash": "dash", "color": "#9aa6b2"},
            name="Parity line",
            hoverinfo="skip",
        )
    )
    lorenz_fig.update_layout(
        title="Cumulative % of Potential",
        xaxis_title="Cum. % of Prescribers",
        yaxis_title="Cum. % of Potential",
        xaxis={"range": [0, 100]},
        yaxis={"range": [0, 100]},
        legend={"orientation": "h", "y": -0.2},
    )
    st.plotly_chart(lorenz_fig, use_container_width=True)

with col2:
    decile_counts = _build_decile_counts(df)
    decile_bar = px.bar(
        decile_counts,
        x="decile",
        y="hcp_count",
        text="hcp_count",
        title="# of HCPs by Decile",
        color_discrete_sequence=["#2f6ea8"],
    )
    decile_bar.update_traces(textposition="outside")
    decile_bar.update_layout(xaxis_title="Decile", yaxis_title="# of HCPs")
    st.plotly_chart(decile_bar, use_container_width=True)

segment_chart_df = pd.DataFrame(payload.get("segment_band_summary", []))
if not segment_chart_df.empty:
    segment_bar = px.bar(
        segment_chart_df,
        x="segment_band",
        y="hcp_count",
        text="hcp_count",
        title="HCPs in High / Medium / Low Segments",
        color="segment_band",
        color_discrete_map={"High (7-10)": "#006d77", "Medium (4-6)": "#ee9b00", "Low (1-3)": "#bb3e03"},
    )
    segment_bar.update_layout(showlegend=False, xaxis_title="Segment", yaxis_title="# of HCPs")
    segment_bar.update_traces(textposition="outside")
    st.plotly_chart(segment_bar, use_container_width=True)

st.subheader("Decile-Specialty Summary")
decile_specialty_df = pd.DataFrame(payload.get("decile_specialty_summary", []))
if decile_specialty_df.empty:
    st.info("No specialty column was detected, so decile-specialty summary is unavailable.")
else:
    st.dataframe(decile_specialty_df, use_container_width=True)


# ---------- Scored data preview ----------
with st.expander("Scored data (first 100 rows)"):
    st.dataframe(df.head(100), use_container_width=True)
