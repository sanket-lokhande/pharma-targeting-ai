"""HCP/Account Targeting Tool — Streamlit dashboard."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.decomposition import PCA

from app.schemas import ALL_DECILES, DecileBand, MetricWeight
from app.services.analysis_engine import build_analysis_payload
from app.services.exporter import build_excel_output
from app.services.segmentation import default_bands
from app.services.validation import load_excel_flexible, validate_dataframe


APP_TITLE = "Targeting & Segmentation Tool"

st.set_page_config(page_title=APP_TITLE, page_icon="⚕", layout="wide") 
st.title(APP_TITLE)
st.caption("Composite scoring · Deciles · Segmentation · Specialty ·  Comparative analytics")


# ----------------------- Sidebar: file uploads -----------------------
with st.sidebar:
    # --- AI Targeting Context Inputs ---
    st.header("Targeting Context")
    disease_market = st.text_input("Disease Market", key="disease_market")
    manufacturer = st.text_input("Drug Manufacturer", key="manufacturer")
    product = st.text_input("Product", key="product")

    recommend_weights = st.button("Recommend Metric Weights")

    # --- Placeholder for AI recommendation logic ---
    ai_metric_weights = {}
    ai_reasoning = []
    if recommend_weights and 'current_file' in locals() and current_file is not None:
        preview_df = load_excel_flexible(current_file)
        available_metrics = [c for c in preview_df.columns if c not in ["HCP_ID", "Specialty", "Decile"] and preview_df[c].dtype in [float, int]]
        # Simple heuristics for demo
        if "oncology" in disease_market.lower():
            for m in available_metrics:
                if "rx" in m.lower():
                    ai_metric_weights[m] = 40
                    ai_reasoning.append(f"Metric '{m}' prioritized due to relevance in oncology prescribing.")
                elif "peer" in m.lower() or "influence" in m.lower():
                    ai_metric_weights[m] = 30
                    ai_reasoning.append(f"Metric '{m}' weighted for peer influence importance in oncology.")
                else:
                    ai_metric_weights[m] = 30 // max(1, len(available_metrics)-2)
        elif "cardio" in disease_market.lower():
            for m in available_metrics:
                if "volume" in m.lower():
                    ai_metric_weights[m] = 50
                    ai_reasoning.append(f"Metric '{m}' prioritized for high prescription volume in cardiology.")
                else:
                    ai_metric_weights[m] = 50 // max(1, len(available_metrics)-1)
        else:
            # Default: equal weights
            for m in available_metrics:
                ai_metric_weights[m] = round(100.0 / max(1, len(available_metrics)), 2)
                ai_reasoning.append(f"Metric '{m}' weighted equally (no strong domain signal detected).")
        # Normalize to 100
        total = sum(ai_metric_weights.values())
        for k in ai_metric_weights:
            ai_metric_weights[k] = round(ai_metric_weights[k] * 100.0 / total, 2)
        st.session_state['ai_metric_weights'] = ai_metric_weights
        st.session_state['ai_reasoning'] = ai_reasoning
        st.success("AI metric weight recommendations generated below.")

    # Show recommendations if available
    if 'ai_metric_weights' in st.session_state:
        st.subheader("AI Metric Weight Recommendations")
        st.write(st.session_state['ai_metric_weights'])
        for reason in st.session_state.get('ai_reasoning', []):
            st.caption(f"Reason: {reason}")
        if st.button("Auto-fill Weights with AI Recommendation"):
            st.session_state['autofill_weights'] = True

    st.header("Upload data")
    current_file = st.file_uploader(
        "Current period (.xlsx) *", type=["xlsx"], key="current_file"
    )
    previous_file = st.file_uploader(
        "Previous period (.xlsx, optional)", type=["xlsx"], key="previous_file"
    )

    # Data quality preview: show missing values and columns before user selects options
    if current_file is not None:
        try:
            preview_df = load_excel_flexible(current_file)
            # Missing values
            missing_summary = preview_df.isnull().sum()
            missing_cols = missing_summary[missing_summary > 0]
            missing_str = ""
            if not missing_cols.empty:
                missing_str = "Missing values detected in columns: " + ", ".join([f"{col} ({cnt})" for col, cnt in missing_cols.items()])
            # Duplicate IDs
            id_col = preview_df.columns[0]
            duplicate_id_count = preview_df.duplicated(subset=[id_col]).sum()
            duplicate_str = ""
            if duplicate_id_count > 0:
                duplicate_str = f"Duplicate IDs detected:  {id_col} ({duplicate_id_count})"
            # Combine warnings in consistent format
            warning_message = ""
            if missing_str and duplicate_str:
                warning_message = f"{missing_str} {duplicate_str}."
            elif missing_str:
                warning_message = f"{missing_str}."
            elif duplicate_str:
                warning_message = f"{duplicate_str}."
            if warning_message:
                st.warning(warning_message)
        except Exception:
            pass

# ----------------------- Data Quality Options -----------------------
st.sidebar.header("Data Quality Options")
missing_value_option = st.sidebar.selectbox(
    "How to handle missing values?",
    ["Impute with median (recommended)", "Impute with mean", "Drop rows with missing values"],
    index=0
)
duplicate_id_option = st.sidebar.selectbox(
    "How to handle duplicate IDs?",
    ["Keep first occurrence (recommended)", "Drop all duplicates", "Keep all"],
    index=0
)
null_id_option = st.sidebar.selectbox(
    "How to handle null/blank IDs?",
    ["Drop rows with null IDs (recommended)", "Keep all rows"],
    index=0
)

if current_file is None:
    st.info("Upload a current period .xlsx file in the sidebar to begin.")
    st.stop()


# ----------------------- Load + validate -----------------------
def _load_and_validate(uploaded_file) -> tuple:
    raw_df = load_excel_flexible(uploaded_file)
    df = raw_df.copy()
    warnings = []
    # Null/blank ID handling
    id_col = df.columns[0]
    null_id_count = df[id_col].isnull().sum() + (df[id_col] == '').sum()
    if null_id_count > 0:
        warnings.append(f"{null_id_count} null/blank IDs detected.")
        if null_id_option.startswith("Drop"):
            df = df[df[id_col].notnull() & (df[id_col] != '')]
    # Duplicate ID handling
    duplicate_id_count = df.duplicated(subset=[id_col]).sum()
    if duplicate_id_count > 0:
        warnings.append(f"{duplicate_id_count} duplicate IDs detected.")
        if duplicate_id_option.startswith("Keep first"):
            df = df.drop_duplicates(subset=[id_col], keep='first')
        elif duplicate_id_option.startswith("Drop all"):
            df = df.drop_duplicates(subset=[id_col], keep=False)
    # Missing value handling
    missing_count = df.isnull().sum().sum()
    if missing_count > 0:
        warnings.append(f"{missing_count} missing values detected.")
        if missing_value_option.startswith("Impute with median"):
            for col in df.select_dtypes(include='number').columns:
                if df[col].isnull().any():
                    median = df[col].median()
                    df[col] = df[col].fillna(median)
        elif missing_value_option.startswith("Impute with mean"):
            for col in df.select_dtypes(include='number').columns:
                if df[col].isnull().any():
                    mean = df[col].mean()
                    df[col] = df[col].fillna(mean)
        elif missing_value_option.startswith("Drop rows"):
            df = df.dropna()
    # Remove outliers (z-score > 3)
    from scipy.stats import zscore
    num_cols = df.select_dtypes(include='number').columns
    outlier_rows = pd.Series([False]*len(df))
    if not df[num_cols].empty:
        zscores = df[num_cols].apply(zscore)
        outlier_rows = (zscores.abs() > 3).any(axis=1)
        outlier_count = outlier_rows.sum()
        if outlier_count > 0:
            warnings.append(f"{outlier_count} outlier rows detected (z-score > 3). Rows removed.")
            df = df[~outlier_rows]
    # Suggest optimal cluster count (elbow method, simple heuristic)
    optimal_clusters = 5
    if len(num_cols) > 1 and len(df) > 10:
        from sklearn.cluster import KMeans
        inertias = []
        for k in range(2, 9):
            kmeans = KMeans(n_clusters=k, n_init=5, random_state=42)
            kmeans.fit(df[num_cols])
            inertias.append(kmeans.inertia_)
        diffs = [inertias[i-1] - inertias[i] for i in range(1, len(inertias))]
        if diffs:
            optimal_clusters = diffs.index(max(diffs)) + 2
    st.session_state['suggested_clusters'] = optimal_clusters
    st.session_state['data_quality_warnings'] = warnings
    return validate_dataframe(df)


try:
    current_id_col, current_metrics, current_specialty_col, current_notes, current_df, current_original_df = _load_and_validate(current_file)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not process current file: {exc}")
    st.stop()

previous_df: Optional[pd.DataFrame] = None
previous_id_col: Optional[str] = None
previous_specialty_col: Optional[str] = None
if previous_file is not None:
    # Comparison is driven by Decile/Segment, not metrics, so the previous
    # file is only required to have an ID column (and ideally a Decile or
    # Segment column). Try the strict validator first, then fall back to a
    # lenient loader that just identifies the ID column.
    try:
        previous_id_col, _previous_metrics, previous_specialty_col, _, previous_df, _ = _load_and_validate(previous_file)
    except Exception:  # noqa: BLE001
        try:
            previous_file.seek(0)
        except Exception:  # noqa: BLE001
            pass
        try:
            raw_prev = load_excel_flexible(previous_file)
            # Pick an ID column using the same hints as the strict validator.
            id_hints = ("hcp", "npi", "id", "prescriber", "physician", "doctor", "account")
            previous_id_col = next(
                (c for c in raw_prev.columns if any(h in str(c).lower() for h in id_hints)),
                str(raw_prev.columns[0]),
            )
            raw_prev = raw_prev[raw_prev[previous_id_col].notna()].copy()
            raw_prev[previous_id_col] = raw_prev[previous_id_col].astype(str).str.strip()
            previous_df = raw_prev
            previous_specialty_col = None
            st.info(
                "Previous file loaded in lenient mode (no numeric metrics required). "
                "Comparison will use the Decile/Segment columns from this file."
            )
        except Exception as exc2:  # noqa: BLE001
            st.error(f"Could not process previous file: {exc2}")
            st.stop()

with st.expander("Detected schema", expanded=False):
    st.write(f"**ID column:** `{current_id_col}`")
    st.write(f"**Numeric metric columns ({len(current_metrics)}):** {', '.join(current_metrics)}")
    st.write(f"**Specialty column:** `{current_specialty_col}`" if current_specialty_col else "**Specialty column:** _not detected_")
    if current_notes:
        st.write("Loader notes:")
        for n in current_notes:
            st.write(f"- {n}")


# ----------------------- Weights -----------------------
st.subheader("1. Metric weights (total = 100)")
st.caption("Set a weight to 0 to exclude a metric. Only numeric columns can be weighted.")

weights: dict[str, float] = {}
weight_cols = st.columns(min(3, max(1, len(current_metrics))))
for i, metric in enumerate(current_metrics):
    with weight_cols[i % len(weight_cols)]:
        if st.session_state.get('autofill_weights') and 'ai_metric_weights' in st.session_state and metric in st.session_state['ai_metric_weights']:
            weights[metric] = st.number_input(
                metric,
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state['ai_metric_weights'][metric]),
                step=1.0,
                key=f"weight_{metric}",
            )
        else:
            default_weight = round(100.0 / max(len(current_metrics), 1), 2)
            weights[metric] = st.number_input(
                metric,
                min_value=0.0,
                max_value=100.0,
                value=float(default_weight),
                step=1.0,
                key=f"weight_{metric}",
            )

total_weight = round(sum(weights.values()), 2)
if abs(total_weight - 100.0) < 0.01:
    st.success(f"Weight total: {total_weight}")
else:
    st.warning(f"Weight total: {total_weight} (must equal 100)")

# ----------------------- Normalization method selection -----------------------
st.subheader("2. Normalization method")
normalization_method = st.radio(
    "Select normalization method:",
    ["Min-max", "Percentile"],
    index=0,
    help="Choose how to normalize metrics before scoring and deciling."
)
normalization_method = "minmax" if normalization_method == "Min-max" else "percentile"


# ----------------------- User-defined decile bands -----------------------
st.subheader("3. User-defined decile bands")
st.caption("Map each decile to a band. Each decile must belong to exactly one band.")

if "band_config" not in st.session_state:
    st.session_state["band_config"] = [
        {"name": b.name, "deciles": list(b.deciles)} for b in default_bands()
    ]


def _add_band() -> None:
    st.session_state["band_config"].append({"name": f"Band {len(st.session_state['band_config']) + 1}", "deciles": []})


def _remove_band(idx: int) -> None:
    if 0 <= idx < len(st.session_state["band_config"]):
        st.session_state["band_config"].pop(idx)


band_rows = st.session_state["band_config"]
to_remove: List[int] = []
for idx, band in enumerate(band_rows):
    cols = st.columns([3, 6, 1])
    band["name"] = cols[0].text_input("Band name", value=band["name"], key=f"band_name_{idx}")
    band["deciles"] = cols[1].multiselect(
        "Deciles in this band",
        options=ALL_DECILES,
        default=band["deciles"],
        key=f"band_deciles_{idx}",
    )
    if cols[2].button("✕", key=f"remove_band_{idx}", help="Remove this band"):
        to_remove.append(idx)

for idx in sorted(to_remove, reverse=True):
    _remove_band(idx)
    st.rerun()

st.button("+ Add band", on_click=_add_band)

# Validate bands
assigned: dict[str, str] = {}
band_error: Optional[str] = None
bands_typed: List[DecileBand] = []
for band in band_rows:
    name = (band["name"] or "").strip()
    if not name:
        band_error = "Each band must have a name."
        break
    if not band["deciles"]:
        band_error = f"Band '{name}' has no deciles assigned."
        break
    for d in band["deciles"]:
        if d in assigned:
            band_error = f"Decile {d} appears in both '{assigned[d]}' and '{name}'."
            break
        assigned[d] = name
    if band_error:
        break
    bands_typed.append(DecileBand(name=name, deciles=list(band["deciles"])))

unassigned = [d for d in ALL_DECILES if d not in assigned]
if not band_error and unassigned:
    band_error = f"These deciles are not in any band: {', '.join(unassigned)}"

if band_error:
    st.error(band_error)


# --- Algorithm selection and recommendations ---
st.subheader("4. Segmentation Algorithm Selection")
algorithm_options = [
    "KMeans (recommended for balanced, spherical clusters)",
    "Agglomerative Clustering (good for hierarchical/grouped data)",
    "DBSCAN (detects arbitrary shapes, robust to outliers)",
]
algorithm_short = ["KMeans", "Agglomerative", "DBSCAN"]
algorithm = st.selectbox(
    "Select segmentation algorithm:",
    algorithm_options,
    index=0
)

suggested_clusters = st.session_state.get('suggested_clusters', 5)
cluster_count = st.number_input(
    "Number of clusters",
    min_value=2,
    max_value=99,
    value=int(suggested_clusters),
    step=1,
    help=f"Suggested: {suggested_clusters}",
)

# --- Recommendation logic ---
recommendation = ""
if algorithm.startswith("KMeans"):
    recommendation = (
        f"**Recommendation:** KMeans is recommended when clusters are expected to be roughly equal in size and spherical in shape. "
        f"The suggested number of clusters ({suggested_clusters}) is based on the elbow method, which balances cluster compactness and separation."
    )
elif algorithm.startswith("Agglomerative"):
    recommendation = (
        "**Recommendation:** Agglomerative Clustering is useful for hierarchical or nested groupings. "
        "Choose this if you expect natural groupings or want to visualize a dendrogram. "
        f"Suggested clusters: {suggested_clusters} (based on elbow method for KMeans, but you may adjust for your hierarchy)."
    )
elif algorithm.startswith("DBSCAN"):
    recommendation = (
        "**Recommendation:** DBSCAN is robust to outliers and can find clusters of arbitrary shape. "
        "Choose this if your data has noise or non-spherical clusters. "
        "Note: DBSCAN does not require a preset number of clusters, but you may need to tune its parameters (epsilon, min_samples)."
    )
if recommendation:
    st.info(recommendation)


# ----------------------- Run analysis -----------------------
can_run = abs(total_weight - 100.0) < 0.01 and band_error is None
run = st.button("Run analysis", type="primary", disabled=not can_run)

if not run:
    st.stop()

metric_weights = [MetricWeight(metric=m, weight=w) for m, w in weights.items() if w > 0]

with st.spinner("Running analysis..."):
    try:
        payload = build_analysis_payload(
            current_df=current_df,
            current_original_df=current_original_df,
            id_column=current_id_col,
            metric_weights=metric_weights,
            bands=bands_typed,
            n_clusters=cluster_count,
            specialty_column=current_specialty_col,
            previous_df=previous_df,
            previous_id_column=previous_id_col,
            previous_specialty_column=previous_specialty_col,
            normalization_method=normalization_method,
        )
    except Exception as exc:  # noqa: BLE001
        st.exception(exc)
        st.stop()

# ----------------------- Insights & Recommendations -----------------------
st.subheader("Insights & Recommendations")
insights = []
reasonings = []

# Actionable Specialty Insight
specialty_totals_df = payload.get("specialty_totals", pd.DataFrame())
if not specialty_totals_df.empty:
    top_specialty = specialty_totals_df.sort_values("# HCPs", ascending=False).iloc[0]
    insights.append(f"**Top specialty by HCPs:** {top_specialty['Specialty']} ({int(top_specialty['# HCPs'])} HCPs, {top_specialty['% of Total']:.2f}% of total)")
    reasonings.append(f"The specialty '{top_specialty['Specialty']}' has the highest number of HCPs, indicating a larger field force opportunity. Prioritizing this specialty can maximize reach and impact.")
    if specialty_totals_df["% of Total"].max() > 50:
        insights.append(f"**Dominant specialty detected:** {top_specialty['Specialty']} represents more than half of all HCPs.")
        reasonings.append(f"A dominant specialty means field force efforts can be concentrated for greater efficiency.")

# Anomaly detection (simple outlier check)
decile_df = payload.get("decile_summary", pd.DataFrame())
if not decile_df.empty:
    mean_hcps = decile_df["# HCPs"].mean()
    outliers = decile_df[decile_df["# HCPs"] > mean_hcps * 2]
    for _, row in outliers.iterrows():
        insights.append(f"**Anomaly:** {row['Decile']} has unusually high HCP count: {int(row['# HCPs'])} (>{mean_hcps*2:.0f} avg)")
        reasonings.append(f"A very high HCP count in {row['Decile']} may indicate data skew or a need to review segmentation criteria.")

# Example: Cluster recommendation
suggested_clusters = st.session_state.get('suggested_clusters', 5)
insights.append(f"**Recommended number of clusters:** {suggested_clusters}")
reasonings.append(f"This is based on the elbow method, which balances cluster compactness and separation for optimal segmentation.")

# Display insights with reasoning
if insights:
    for i, insight in enumerate(insights):
        st.info(insight)
        if i < len(reasonings):
            st.caption(f"Reason: {reasonings[i]}")
else:
    st.info("No major trends or actionable insights detected in this dataset.")


# ----------------------- A. Segment summary widget -----------------------
st.subheader("Decile Band Summary")
band_df = payload["segment_band_summary"]
change_df = payload.get("segment_band_change")
has_previous = payload.get("has_previous", False)

if band_df.empty:
    st.info("No band summary available.")
else:
    summary_cols = st.columns(len(band_df))
    for i, (_, row) in enumerate(band_df.iterrows()):
        with summary_cols[i]:
            delta = None
            delta_color = "normal"
            if has_previous and change_df is not None and not change_df.empty:
                match = change_df[change_df["Band"] == row["Band"]]
                if not match.empty:
                    pct = float(match["% Change vs Previous"].iloc[0])
                    if pct == float("inf"):
                        delta = "+inf%"
                        delta_color = "normal"
                    else:
                        sign = "+" if pct >= 0 else ""
                        delta = f"{sign}{pct:.2f}%"
                        # Streamlit: 'normal' is green for positive, red for negative (default behavior).
                        delta_color = "normal"
            st.metric(
                label=str(row["Band"]),
                value=f"{int(row['# HCPs']):,} HCPs",
                delta=delta,
                delta_color=delta_color if delta else "off",
            )
            st.caption(f"{row['% of Total']:.2f}% of total · {row['Deciles']}")


# ----------------------- A2. Metric-based clusters -----------------------
st.subheader("Segmentation Cluster Profiles")
cluster_profile_df = payload.get("cluster_profile", pd.DataFrame())
cluster_heatmap_df = payload.get("cluster_heatmap", pd.DataFrame())


if isinstance(cluster_profile_df, pd.DataFrame) and not cluster_profile_df.empty:
    # Add % sign to '% HCPs' column if present
    df_to_show = cluster_profile_df.copy()
    if '% HCPs' in df_to_show.columns:
        df_to_show['% HCPs'] = df_to_show['% HCPs'].round(2).astype(str) + '%'
    st.dataframe(df_to_show, use_container_width=True, hide_index=True)

    non_metric_cols = {
        "cluster_id",
        "segment_name",
        "# HCPs",
        "% HCPs",
        "dominant_metric",
        "dominance_vs_overall",
    }
    metric_cols = [
        c
        for c in cluster_profile_df.columns
        if c not in non_metric_cols and pd.api.types.is_numeric_dtype(cluster_profile_df[c])
    ]

    # PCA-based scatter plot to visualize cluster separation at HCP level.
    scored_df = payload.get("raw_with_scores", pd.DataFrame())
    if isinstance(scored_df, pd.DataFrame) and not scored_df.empty and metric_cols:
        required_cols = [*metric_cols, current_id_col, "segment_name", "cluster_id"]
        available_cols = [c for c in required_cols if c in scored_df.columns]
        scatter_source = scored_df[available_cols].copy()

        for c in metric_cols:
            if c in scatter_source.columns:
                scatter_source[c] = pd.to_numeric(scatter_source[c], errors="coerce")
        scatter_source = scatter_source.dropna(subset=[c for c in metric_cols if c in scatter_source.columns])

        if len(scatter_source) >= 2 and len([c for c in metric_cols if c in scatter_source.columns]) >= 2:
            pca_cols = [c for c in metric_cols if c in scatter_source.columns]
            pca = PCA(n_components=2, random_state=42)
            coords = pca.fit_transform(scatter_source[pca_cols].values)
            scatter_plot_df = pd.DataFrame(
                {
                    "PC1": coords[:, 0],
                    "PC2": coords[:, 1],
                    current_id_col: scatter_source[current_id_col].astype(str).values,
                    "segment_name": scatter_source["segment_name"].astype(str).values,
                    "cluster_id": scatter_source["cluster_id"].astype(str).values,
                }
            )

            scatter_fig = px.scatter(
                scatter_plot_df,
                x="PC1",
                y="PC2",
                color="segment_name",
                symbol="cluster_id",
                hover_data=[current_id_col, "cluster_id", "segment_name"],
                title="Cluster scatter plot (PCA projection)",
                opacity=0.75,
            )
            scatter_fig.update_traces(marker={"size": 9, "line": {"width": 0.5, "color": "white"}})
            scatter_fig.update_layout(height=520, legend={"orientation": "h", "y": -0.25})
            st.plotly_chart(scatter_fig, use_container_width=True)

    viz_col1, viz_col2 = st.columns(2)

    with viz_col1:
        # Bar chart for clusters: # HCPs, % HCPs, dominant metric
        cluster_bar_df = cluster_profile_df.copy()
        cluster_bar_df = cluster_bar_df.sort_values("# HCPs", ascending=False)
        bar_colors = ["#1f4e78"] * len(cluster_bar_df)
        bar = go.Figure()
        bar.add_trace(
            go.Bar(
                x=cluster_bar_df["cluster_id"],
                y=cluster_bar_df["# HCPs"],
                text=[f"{row['dominant_metric']}<br>{row['% HCPs']:.2f}%" for _, row in cluster_bar_df.iterrows()],
                textposition="outside",
                marker_color=bar_colors,
                name="# HCPs",
            )
        )
        bar.update_layout(
            title="HCPs per Cluster (Dominant Metric)",
            xaxis_title="Cluster",
            yaxis_title="# HCPs",
            height=520,
        )
        st.plotly_chart(bar, use_container_width=True)

    with viz_col2:
        if metric_cols:
            radar_fig = go.Figure()
            for _, r in cluster_profile_df.iterrows():
                radar_fig.add_trace(
                    go.Scatterpolar(
                        r=[float(r[m]) for m in metric_cols],
                        theta=metric_cols,
                        fill="toself",
                        name=f"{r['cluster_id']} - {r['segment_name']}",
                    )
                )
            radar_fig.update_layout(
                title="Cluster profile radar",
                polar={"radialaxis": {"visible": True}},
                legend={"orientation": "h", "y": -0.2},
                height=520,
            )
            st.plotly_chart(radar_fig, use_container_width=True)
else:
    st.info("Cluster segmentation unavailable. Ensure at least one numeric metric is provided.")


# ----------------------- B. Specialty bar chart -----------------------
st.subheader("Specialty distribution")


specialty_totals_df = payload["specialty_totals"]
if specialty_totals_df.empty:
    st.info("Specialty column was not detected in the dataset.")
else:
    # Group specialties under 'Others' if they contribute to only 20% of HCP population (cumulative)
    sorted_df = specialty_totals_df.sort_values("# HCPs", ascending=False).reset_index(drop=True)
    sorted_df["cumulative_pct"] = sorted_df["# HCPs"].cumsum() / sorted_df["# HCPs"].sum() * 100
    dominant_mask = sorted_df["cumulative_pct"] <= 80
    dominant_specialties = sorted_df[dominant_mask].copy()
    others = sorted_df[~dominant_mask].copy()
    if not others.empty:
        others_row = {
            "Specialty": "Others",
            "# HCPs": others["# HCPs"].sum(),
            "% of Total": others["% of Total"].sum(),
        }
        dominant_specialties = pd.concat([dominant_specialties, pd.DataFrame([others_row])], ignore_index=True)
    # Sort dominant_specialties descending, put 'Others' at the end
    dominant_specialties = dominant_specialties[dominant_specialties["Specialty"] != "Others"]
    dominant_specialties = dominant_specialties.sort_values("# HCPs", ascending=False)
    if not others.empty:
        dominant_specialties = pd.concat([dominant_specialties, pd.DataFrame([others_row])], ignore_index=True)
    # Assign lighter color to 'Others'
    bar_colors = ["#1f4e78"] * (len(dominant_specialties) - 1)
    if len(dominant_specialties) > 0:
        bar_colors.append("#b0c4de")  # Lighter blue for 'Others'
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=dominant_specialties["Specialty"],
            y=dominant_specialties["# HCPs"],
            name="# HCPs",
            marker_color=bar_colors,
            yaxis="y1",
            text=dominant_specialties["# HCPs"],
            textposition="outside",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dominant_specialties["Specialty"],
            y=dominant_specialties["% of Total"],
            name="% HCPs",
            mode="lines+markers",
            marker={"color": "#d62728"},
            yaxis="y2",
        )
    )
    fig.update_layout(
        title="HCPs by specialty",
        xaxis_title="Specialty",
        yaxis={"title": "# HCPs"},
        yaxis2={"title": "% HCPs", "overlaying": "y", "side": "right", "ticksuffix": "%"},
        legend={"orientation": "h", "y": -0.25},
        height=460,
    )
    st.plotly_chart(fig, use_container_width=True)


# ----------------------- C. Decile x Specialty visualization -----------------------
st.subheader("Decile × Specialty")


count_matrix = payload["specialty_decile_count"]
pct_matrix = payload["specialty_decile_pct"]
specialty_totals_df = payload["specialty_totals"]
if count_matrix.empty or specialty_totals_df.empty:
    st.info("Specialty matrix unavailable (no specialty column detected).")
else:
    # Use the same dominant specialties as in the bar chart (top 80% cumulative)
    sorted_df = specialty_totals_df.sort_values("# HCPs", ascending=False).reset_index(drop=True)
    sorted_df["cumulative_pct"] = sorted_df["# HCPs"].cumsum() / sorted_df["# HCPs"].sum() * 100
    dominant_specialties = list(sorted_df[sorted_df["cumulative_pct"] <= 80]["Specialty"])
    # Always put 'Others' at the end
    def group_specialties(df):
        df = df.copy()
        # Get the actual order of dominant specialties by total HCPs
        dominant_cols = [c for c in dominant_specialties if c in df.columns]
        other_cols = [c for c in df.columns if c not in dominant_cols and c != "Decile"]
        if other_cols:
            df["Others"] = df[other_cols].sum(axis=1)
            df = df.drop(columns=other_cols)
        col_order = ["Decile"] + dominant_cols + (["Others"] if "Others" in df.columns else [])
        df = df[[c for c in col_order if c in df.columns]]
        return df
    count_matrix_grouped = group_specialties(count_matrix)
    pct_matrix_grouped = group_specialties(pct_matrix)
    tab_count, tab_pct = st.tabs(["Count", "% of Total"])
    with tab_count:
        st.dataframe(count_matrix_grouped, use_container_width=True, hide_index=True)
    with tab_pct:
        st.dataframe(pct_matrix_grouped, use_container_width=True, hide_index=True)


# ----------------------- Decile summary + Lorenz -----------------------
st.subheader("Decile distribution")

# --- Decile summary and Lorenz curve side by side, with Lorenz showing decile dots ---
decile_df = payload["decile_summary"]
lorenz_df = payload["lorenz_curve"]
cols = st.columns([1, 1])
with cols[0]:
    st.subheader("# of HCPs by decile")
    if decile_df.empty:
        st.info("No decile summary available.")
    else:
        # Only cumulative columns
        display_cols = ["Decile", "# HCPs", "Cumulative % HCPs", "Cumulative % of Potential"]
        df = decile_df[display_cols].copy()
        # Find the row where Cumulative % of Potential is closest to 80 (before converting to string)
        df["_diff80"] = (df["Cumulative % of Potential"] - 80).abs()
        highlight_idx = df["_diff80"].idxmin()
        # Now round percent columns and add % symbol
        df["Cumulative % HCPs"] = df["Cumulative % HCPs"].round(0).astype(int).astype(str) + "%"
        df["Cumulative % of Potential"] = df["Cumulative % of Potential"].round(0).astype(int).astype(str) + "%"
        def highlight_80(row):
            style = ["" for _ in row]
            if row.name == highlight_idx:
                style[3] = "background-color: #fff3cd; font-weight: bold;"  # yellow bg, bold
            return style
        st.plotly_chart(px.bar(
            df,
            x="Decile",
            y="# HCPs",
            text="# HCPs",
            color_discrete_sequence=["#2f6ea8"],
        ).update_traces(textposition="outside"), use_container_width=True)
        # Prepare for st.dataframe: remove helper column, format percent columns, no index
        styled_df = df.drop(columns=["_diff80"]).copy()
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
with cols[1]:
    st.subheader("Lorenz Curve")
    if lorenz_df.empty:
        st.info("Lorenz curve unavailable.")
    else:
        # Lorenz Curve: plot only the 10 points for D1-D10 using the decile table rows
        # Assume decile table is available as decile_df and has columns: Decile, Cum % HCPs, Cum % Potential
        decile_labels = [f"D{i}" for i in range(1, 11)]
        decile_points = decile_df[decile_df["Decile"].isin(decile_labels)]
        # Use the correct columns from the table: '% HCPs' and '% of Potential'
        x_vals = decile_points["% HCPs"].cumsum().tolist()
        y_vals = decile_points["% of Potential"].cumsum().tolist()
        lorenz_fig = go.Figure()
        lorenz_fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="lines+markers",
                line={"shape": "spline", "smoothing": 1.3, "width": 1, "color": "#4a7ac7"},
                marker=dict(size=8, color="#4a7ac7"),
                name="Lorenz Deciles",
                text=decile_points["Decile"].tolist(),
                hovertemplate="Decile: %{text}<br>Cum % HCPs: %{x}<br>Cum % Potential: %{y}<extra></extra>",
            )
        )
        lorenz_fig.update_layout(
            xaxis_title="<b>Cumulative % of HCPs</b>",
            yaxis_title="<b>Cumulative % of Composite Score (Potential)</b>",
            xaxis={"range": [0, 100], "tickformat": ".0f", "ticksuffix": "%"},
            yaxis={"range": [0, 100], "tickformat": ".0f", "ticksuffix": "%"},
            legend={"orientation": "h", "y": -0.2},
            font={"family": "Arial", "size": 14},
            margin={"t": 40, "b": 40, "l": 60, "r": 40}
        )
        st.plotly_chart(lorenz_fig, use_container_width=True)


# ----------------------- Movement / New / Lost / Existing -----------------------
if has_previous:
    st.subheader("Comparison Analysis: Movement, New vs Lost HCPs (Benchmarking)")
    nle = payload.get("new_vs_lost_existing", {})
    totals_df = nle.get("totals")
    if isinstance(totals_df, pd.DataFrame) and not totals_df.empty:
        cols = st.columns(len(totals_df))
        for i, (_, row) in enumerate(totals_df.iterrows()):
            with cols[i]:
                st.metric(label=row["Group"], value=f"{int(row['# HCPs']):,}")

    tabs = st.tabs(
        ["Movement (Up/Down/Same)", "NEW HCPs", "LOST HCPs", "EXISTING movement"]
    )
    with tabs[0]:
        movement = payload.get("movement_analysis")
        if isinstance(movement, pd.DataFrame) and not movement.empty:
            st.dataframe(movement, use_container_width=True, hide_index=True)
            counts = movement["Movement"].value_counts().reset_index()
            counts.columns = ["Movement", "# HCPs"]
            st.plotly_chart(
                px.bar(counts, x="Movement", y="# HCPs", text="# HCPs",
                       color="Movement",
                       color_discrete_map={"Up": "#67aa67", "Down": "#d47373", "Same": "#969696"}),
                use_container_width=True,
            )
        else:
            st.info("No overlapping HCPs between current and previous periods.")
    with tabs[1]:
        new_by_band = nle.get("new_hcps_by_band")
        if isinstance(new_by_band, pd.DataFrame) and not new_by_band.empty:
            st.dataframe(new_by_band, use_container_width=True, hide_index=True)
        else:
            st.info("No new HCPs.")
    with tabs[2]:
        lost_by_band = nle.get("lost_hcps_by_band")
        if isinstance(lost_by_band, pd.DataFrame) and not lost_by_band.empty:
            st.dataframe(lost_by_band, use_container_width=True, hide_index=True)
        else:
            st.info("No lost HCPs.")
    with tabs[3]:
        existing_summary = nle.get("existing_movement_summary")
        existing_detail = nle.get("existing_movement_detail")
        if isinstance(existing_summary, pd.DataFrame) and not existing_summary.empty:
            st.dataframe(existing_summary, use_container_width=True, hide_index=True)
        if isinstance(existing_detail, pd.DataFrame) and not existing_detail.empty:
            with st.expander("Existing HCP movement detail"):
                st.dataframe(existing_detail, use_container_width=True, hide_index=True)


# ----------------------- Excel download -----------------------
st.subheader("Export to Excel")
excel_bytes = build_excel_output(payload)
filename = f"hcp_targeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
st.download_button(
    label="⬇ Download Excel workbook",
    data=excel_bytes,
    file_name=filename,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ----------------------- Scored data preview -----------------------
with st.expander("Scored data (first 200 rows)"):
    st.dataframe(payload["raw_with_scores"].head(200), use_container_width=True, hide_index=True)
