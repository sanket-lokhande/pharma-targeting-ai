from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from app.schemas import MetricWeight


def generate_insights(
    scored_df: pd.DataFrame,
    metric_weights: List[MetricWeight],
    driver_strength: Dict[str, float],
) -> Dict[str, List[str]]:
    weighted_metrics = sorted(metric_weights, key=lambda x: x.weight, reverse=True)
    top_drivers = weighted_metrics[: min(3, len(weighted_metrics))]

    top_deciles = scored_df[scored_df["decile"].isin(["D10", "D9", "D8"])]
    low_deciles = scored_df[scored_df["decile"].isin(["D1", "D2", "D3"])]

    insights: List[str] = []

    if "decile" in scored_df.columns:
        total_hcps = max(int(len(scored_df)), 1)
        top_pool = scored_df[scored_df["decile"].isin(["D10", "D9", "D8"])]
        mid_pool = scored_df[scored_df["decile"].isin(["D7", "D6", "D5", "D4"])]
        low_pool = scored_df[scored_df["decile"].isin(["D3", "D2", "D1"])]

        top_hcp_pct = round((len(top_pool) / total_hcps) * 100, 1)
        mid_hcp_pct = round((len(mid_pool) / total_hcps) * 100, 1)
        low_hcp_pct = round((len(low_pool) / total_hcps) * 100, 1)

        total_potential = float(scored_df["composite_score"].sum())
        top_potential = float(top_pool["composite_score"].sum())
        mid_potential = float(mid_pool["composite_score"].sum())
        low_potential = float(low_pool["composite_score"].sum())

        top_potential_pct = round((top_potential / total_potential) * 100, 1) if total_potential else 0.0
        mid_potential_pct = round((mid_potential / total_potential) * 100, 1) if total_potential else 0.0
        low_potential_pct = round((low_potential / total_potential) * 100, 1) if total_potential else 0.0

        insights.append(
            f"Top deciles (D8-D10) are {top_hcp_pct}% of HCPs but contribute {top_potential_pct}% of composite potential, indicating strong concentration for focused coverage."
        )
        insights.append(
            f"Mid deciles (D4-D7) represent {mid_hcp_pct}% of HCPs and {mid_potential_pct}% of potential; this is the primary conversion cohort for growth campaigns."
        )
        insights.append(
            f"Low deciles (D1-D3) account for {low_hcp_pct}% of HCPs and {low_potential_pct}% of potential; route to scaled digital nurture with trigger-based upgrades."
        )

    for metric_item in top_drivers:
        metric = metric_item.metric
        top_avg = top_deciles[metric].mean() if not top_deciles.empty else 0
        low_avg = low_deciles[metric].mean() if not low_deciles.empty else 0
        ratio = (top_avg / low_avg) if low_avg not in [0, np.nan] else np.inf
        ratio_text = "infinite" if ratio == np.inf else f"{ratio:.2f}x"
        insights.append(
            f"Top-tier HCPs outperform low-tier HCPs by {ratio_text} on '{metric}', indicating strong lift potential."
        )

    strongest_correlation = sorted(driver_strength.items(), key=lambda x: x[1], reverse=True)[:3]
    for metric, value in strongest_correlation:
        insights.append(
            f"Metric '{metric}' shows high interaction with peer metrics (avg abs corr={value:.2f}), suggesting it is a stable score driver."
        )

    if "segment_label" in scored_df.columns:
        segment_score = scored_df.groupby("segment_label")["composite_score"].agg(["mean", "count"]).sort_values(
            "mean", ascending=False
        )
        if not segment_score.empty:
            best_segment = segment_score.index[0]
            best_mean = float(segment_score.iloc[0]["mean"])
            best_count = int(segment_score.iloc[0]["count"])
            insights.append(
                f"'{best_segment}' is the strongest segment with {best_count} HCPs and average composite score {best_mean:.3f}; prioritize this cohort for field time and call quality."
            )

    segment_observations = []
    segment_summary = scored_df.groupby("segment_label")["composite_score"].agg(["mean", "count"]).sort_values(
        "mean", ascending=False
    )
    for segment, row in segment_summary.iterrows():
        segment_observations.append(
            f"Segment '{segment}' contains {int(row['count'])} HCPs with mean composite score {row['mean']:.3f}."
        )

    recommendations = [
        "Set call-plan intensity by decile: highest for D8-D10, medium for D4-D7, and low-touch digital for D1-D3.",
        "Use top weighted metrics as message levers in targeting briefs because they explain most of the score separation.",
        "Track month-over-month movement between deciles to identify accounts that are accelerating or at risk.",
        "Recalibrate metric weights quarterly and validate score spread to prevent segment compression.",
    ]

    return {
        "summary_insights": insights + segment_observations,
        "recommendations": recommendations,
    }


def build_validation_notes(validation_notes: List[str], scored_df: pd.DataFrame) -> List[str]:
    notes = validation_notes.copy()
    if scored_df["composite_score"].nunique() <= 3:
        notes.append("Composite score has very low variability; review selected metrics and weights")

    max_score = scored_df["composite_score"].max()
    min_score = scored_df["composite_score"].min()
    if max_score - min_score < 0.05:
        notes.append("Score spread is narrow; segmentation may be less discriminative")

    return notes
