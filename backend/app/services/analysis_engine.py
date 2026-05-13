from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from app.schemas import MetricWeight
from app.services.analytics import compute_scores_and_deciles
from app.services.comparison import compare_current_vs_previous
from app.services.internet_research import fetch_live_market_insights
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
    disease_market: str | None = None,
    enable_live_research: bool = False,
) -> Dict[str, Any]:
    scored_df, corr_matrix, driver_strength, lorenz_curve, distributions, metric_summary = compute_scores_and_deciles(
        df=current_df,
        id_column=id_column,
        metric_weights=metric_weights,
        normalization=normalization,
    )

    metrics = [item.metric for item in metric_weights]
    segmented_df, explainability, segment_labels = segment_hcps(
        scored_df=scored_df,
        feature_columns=metrics + ["composite_score"],
        algorithm=segmentation_algorithm,
        n_clusters=n_clusters,
    )

    live_market_insights: List[str] = []
    if enable_live_research and disease_market:
        live_market_insights = fetch_live_market_insights(disease_market)

    insight_payload = generate_insights(
        segmented_df,
        metric_weights,
        driver_strength,
        disease_market=disease_market,
        live_market_insights=live_market_insights,
    )
    merged_validation_notes = build_validation_notes(validation_notes, segmented_df)

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
            feature_columns=metrics + ["composite_score"],
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
        "validation_notes": merged_validation_notes,
        "disease_market": disease_market or "",
        "enable_live_research": enable_live_research,
        **insight_payload,
        **comparison_payload,
    }
