from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from app.schemas import MetricWeight


def generate_insights(
    scored_df: pd.DataFrame,
    metric_weights: List[MetricWeight],
    driver_strength: Dict[str, float],
    disease_market: str | None = None,
    live_market_insights: List[str] | None = None,
) -> Dict[str, List[str]]:
    weighted_metrics = sorted(metric_weights, key=lambda x: x.weight, reverse=True)
    top_drivers = weighted_metrics[: min(3, len(weighted_metrics))]

    top_deciles = scored_df[scored_df["decile"].isin(["D10", "D9", "D8"])]
    low_deciles = scored_df[scored_df["decile"].isin(["D1", "D2", "D3"])]

    insights: List[str] = []
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

    segment_observations = []
    segment_summary = scored_df.groupby("segment_label")["composite_score"].agg(["mean", "count"]).sort_values(
        "mean", ascending=False
    )
    for segment, row in segment_summary.iterrows():
        segment_observations.append(
            f"Segment '{segment}' contains {int(row['count'])} HCPs with mean composite score {row['mean']:.3f}."
        )

    business_context: List[str] = []
    if disease_market:
        market = disease_market.strip()
        business_context = [
            f"For the {market} market, focus account planning on D1-D3 prescribers to protect near-term share of voice.",
            f"In {market}, prioritize D4-D7 HCPs for conversion campaigns using tailored clinical content and access messaging.",
            f"For {market}, use D8-D10 as nurture cohorts with digital-only tactics and trigger-based reactivation.",
        ]

    recommendations = [
        "Prioritize D8-D10 and High Value segments for field force coverage and omni-channel reinforcement.",
        "Deploy growth plays for mid-tier HCPs (D4-D7) using tailored education and patient support pathways.",
        "Use low-tier HCPs (D1-D3) for low-cost digital nurture programs and monitor for conversion signals.",
        "Revisit metric weights quarterly to align scoring with market dynamics and brand strategy.",
    ]
    if disease_market:
        recommendations.insert(0, f"Align {disease_market.strip()} brand objectives to decile-based call planning and resource allocation.")

    live_context = live_market_insights or []

    return {
        "summary_insights": live_context + business_context + insights + segment_observations,
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
