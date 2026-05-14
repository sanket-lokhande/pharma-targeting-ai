from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from app.schemas import MetricWeight
from app.services.analytics import compute_scores_and_deciles
from app.services.comparison import compare_current_vs_previous
from app.services.insights import build_validation_notes, generate_insights
from app.services.segmentation import segment_hcps


def build_analysis_payload(
    current_df: pd.DataFrame,
    id_column: str,
    metric_weights: List[MetricWeight],
    normalization: str,
    segmentation_algorithm: str,
    n_clusters: int,
    validation_notes: List[str],
    previous_df: pd.DataFrame | None = None,
    previous_id_column: str | None = None,
) -> Dict[str, Any]:
    scored_df, corr_matrix, driver_strength, lorenz_curve, distributions, metric_summary = compute_scores_and_deciles(
        df=current_df,
        id_column=id_column,
        metric_weights=metric_weights,
        normalization=normalization,
    )

    segmented_df, explainability, segment_labels = segment_hcps(
        scored_df=scored_df,
        # Segmentation is intentionally done only on the weighted composite score.
        feature_columns=["composite_score"],
        algorithm=segmentation_algorithm,
        n_clusters=n_clusters,
    )

    insight_payload = generate_insights(
        segmented_df,
        metric_weights,
        driver_strength,
    )
    merged_validation_notes = build_validation_notes(validation_notes, segmented_df)
    segment_band_summary = _build_segment_band_summary(segmented_df)
    decile_specialty_summary = _build_decile_specialty_summary(segmented_df)

    comparison_payload: Dict[str, Any] = {
        "movement_analysis": [],
        "hcp_movement_details": [],
        "new_vs_missing": {},
        "segment_shift_analysis": [],
        "comparison_summary": {},
        "comparison_context": {},
    }

    if previous_df is not None and previous_id_column is not None:
        prev_work = previous_df.copy()
        if previous_id_column != id_column:
            prev_work = prev_work.rename(columns={previous_id_column: id_column})

        prev_scored, _, _, _, _, _ = compute_scores_and_deciles(
            df=prev_work,
            id_column=id_column,
            metric_weights=metric_weights,
            normalization=normalization,
        )
        prev_segmented, _, _ = segment_hcps(
            scored_df=prev_scored,
            feature_columns=["composite_score"],
            algorithm=segmentation_algorithm,
            n_clusters=n_clusters,
        )

        comparison_payload = compare_current_vs_previous(
            current_df=segmented_df,
            previous_df=prev_segmented,
            id_column=id_column,
        )

        movement_map = {
            row["id"]: row for row in comparison_payload.get("hcp_movement_details", [])
        }
        segmented_df["movement_type"] = segmented_df[id_column].map(
            lambda hcp_id: movement_map.get(hcp_id, {}).get("movement_type", "New HCP")
            if hcp_id in set(segmented_df[id_column])
            else "New HCP"
        )
        segmented_df["delta_decile"] = segmented_df[id_column].map(
            lambda hcp_id: movement_map.get(hcp_id, {}).get("delta_decile", "")
        )

        new_hcp_set = set(comparison_payload.get("new_vs_missing", {}).get("new_hcps", []))
        segmented_df.loc[segmented_df[id_column].isin(new_hcp_set), "movement_type"] = "New HCP"
        segmented_df.loc[segmented_df[id_column].isin(new_hcp_set), "delta_decile"] = ""
    else:
        segmented_df["movement_type"] = ""
        segmented_df["delta_decile"] = ""

    return {
        "raw_with_scores": segmented_df.to_dict(orient="records"),
        "segmentation_results": segmented_df[[id_column, "composite_score", "decile", "segment_label"]].to_dict(
            orient="records"
        ),
        "correlation_matrix": corr_matrix.to_dict(),
        "lorenz_curve": lorenz_curve,
        "distributions": distributions,
        "metric_summary": metric_summary,
        "segment_explainability": explainability,
        "segment_labels": segment_labels,
        "segment_band_summary": segment_band_summary,
        "decile_specialty_summary": decile_specialty_summary,
        "validation_notes": merged_validation_notes,
        **insight_payload,
        **comparison_payload,
    }


def _build_segment_band_summary(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if "decile_numeric" not in df.columns:
        return []

    work = df[["decile_numeric"]].copy()
    work["segment_band"] = work["decile_numeric"].apply(
        lambda d: "High (7-10)" if d >= 7 else ("Medium (4-6)" if d >= 4 else "Low (1-3)")
    )
    summary = work.groupby("segment_band", as_index=False).size().rename(columns={"size": "hcp_count"})
    total = int(summary["hcp_count"].sum()) if not summary.empty else 0
    summary["hcp_pct"] = summary["hcp_count"].apply(lambda x: round((x / total) * 100, 1) if total else 0.0)

    order = ["High (7-10)", "Medium (4-6)", "Low (1-3)"]
    summary["segment_band"] = pd.Categorical(summary["segment_band"], categories=order, ordered=True)
    summary = summary.sort_values("segment_band")
    return summary.to_dict(orient="records")


def _detect_specialty_column(df: pd.DataFrame) -> str | None:
    excluded = {
        "composite_score",
        "cumulative_composite_score",
        "total_composite_score",
        "decile",
        "decile_numeric",
        "segment_id",
        "segment_label",
        "movement_type",
        "delta_decile",
    }

    candidate_cols = [col for col in df.columns if col not in excluded]
    preferred = [col for col in candidate_cols if "special" in str(col).lower()]
    if preferred:
        return preferred[0]

    for col in candidate_cols:
        series = df[col]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_categorical_dtype(series):
            unique_count = series.nunique(dropna=True)
            if 2 <= unique_count <= 25:
                return col
    return None


def _build_decile_specialty_summary(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if "decile_numeric" not in df.columns:
        return []

    specialty_column = _detect_specialty_column(df)
    if specialty_column is None:
        return []

    work = df[["decile_numeric", specialty_column]].copy()
    work[specialty_column] = work[specialty_column].fillna("Unknown").astype(str)
    pivot = (
        pd.crosstab(work["decile_numeric"], work[specialty_column])
        .sort_index(ascending=False)
        .reset_index()
    )
    pivot = pivot.rename(columns={"decile_numeric": "Decile"})
    pivot["Decile"] = pivot["Decile"].astype(int).map(lambda value: f"D{value}")
    return pivot.to_dict(orient="records")
