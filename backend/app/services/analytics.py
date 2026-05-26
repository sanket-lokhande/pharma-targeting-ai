"""Composite score computation, min-max normalization and decile assignment."""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from app.schemas import MetricWeight


def minmax_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalize. If max == min, return zeros (edge case)."""
    numeric = pd.to_numeric(series, errors="coerce")
    s_min = numeric.min()
    s_max = numeric.max()
    if pd.isna(s_min) or pd.isna(s_max) or s_max == s_min:
        return pd.Series(np.zeros(len(series)), index=series.index)
    normalized = (numeric - s_min) / (s_max - s_min)
    return normalized.fillna(0.0)


def compute_scores_and_deciles(
    df: pd.DataFrame,
    id_column: str,
    metric_weights: List[MetricWeight],
    normalization_method: str = "minmax",
) -> Tuple[pd.DataFrame, List[str]]:
    """Add `composite_score` and `decile` columns to df. Returns (df, metrics_used).

    - Only numeric metrics with weight > 0 are used.
    - Min-max normalize each metric, then weighted sum (weights normalized to 1).
    - Sort desc by score; assign deciles D10 (top 10%) to D1 (bottom 10%) using
      equal-size buckets via pandas qcut on the rank (ensures equal distribution).
    - Preserves all original columns.
    """
    if df.empty:
        raise ValueError("Input dataframe is empty")

    # Case-insensitive / whitespace-insensitive column lookup so that a
    # previous-period file with slightly different header casing or spacing
    # still matches the current file's weighted metrics.
    def _norm(name: str) -> str:
        return "".join(str(name).lower().split())

    col_lookup = {_norm(c): c for c in df.columns}

    weighted = [m for m in metric_weights if m.weight > 0]
    active: List[MetricWeight] = []
    missing: List[str] = []
    for m in weighted:
        actual = col_lookup.get(_norm(m.metric))
        if actual is None:
            missing.append(m.metric)
            continue
        # Re-bind to the dataframe's actual column name (preserves original casing).
        active.append(MetricWeight(metric=actual, weight=m.weight))

    if not active:
        available = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        raise ValueError(
            "No active numeric metric weights match the dataset columns.\n"
            f"  Weighted metrics expected: {[m.metric for m in weighted]}\n"
            f"  Missing from this file:    {missing}\n"
            f"  Numeric columns available: {available}\n"
            "Tip: ensure the previous-period file uses the same metric column "
            "names as the current file (case / spacing is auto-normalized)."
        )

    # Restrict to truly numeric columns
    numeric_active: List[MetricWeight] = []
    non_numeric: List[str] = []
    for m in active:
        if pd.api.types.is_numeric_dtype(df[m.metric]):
            numeric_active.append(m)
        else:
            non_numeric.append(m.metric)
    if not numeric_active:
        raise ValueError(
            "None of the weighted metrics are numeric in this file. "
            f"Non-numeric columns matched: {non_numeric}"
        )

    weights = np.array([m.weight for m in numeric_active], dtype=float)
    weights = weights / weights.sum()
    metrics = [m.metric for m in numeric_active]

    work = df.copy()


    def percentile_normalize(series: pd.Series) -> pd.Series:
        """Percentile-based normalization: returns the percentile rank of each value in [0, 1]."""
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.rank(pct=True, method="average").fillna(0.0)

    normalized = pd.DataFrame(index=work.index)
    for metric in metrics:
        if normalization_method == "percentile":
            normalized[metric] = percentile_normalize(work[metric])
        else:
            normalized[metric] = minmax_normalize(work[metric])

    work["composite_score"] = normalized[metrics].values.dot(weights)

    work = work.sort_values("composite_score", ascending=False, kind="mergesort").reset_index(drop=True)
    work["cumulative_composite_score"] = work["composite_score"].cumsum()
    total_score = float(work["composite_score"].sum())
    work["total_composite_score"] = total_score
    work["decile_numeric"] = _assign_deciles(work["cumulative_composite_score"], total_score)
    work["decile"] = work["decile_numeric"].map(lambda d: f"D{int(d)}")

    return work, metrics


def _assign_deciles(cumulative_scores: pd.Series, total_score: float) -> pd.Series:
    """Excel-equivalent decile formula on the cumulative composite score.

    For each HCP (rows already sorted descending by composite score):
        =IF(10 - FLOOR(10 * cumulative / total, 1) = 0,
            1,
            10 - FLOOR(10 * cumulative / total, 1))

    Top HCP -> D10, bottom HCP -> D1. Values are clipped to [1, 10].
    """
    n = len(cumulative_scores)
    if n == 0:
        return pd.Series(dtype=int)
    if total_score <= 0:
        return pd.Series(np.ones(n, dtype=int), index=cumulative_scores.index)

    floored = np.floor(10.0 * cumulative_scores.values / total_score).astype(int)
    raw = 10 - floored
    raw = np.where(raw == 0, 1, raw)
    raw = np.clip(raw, 1, 10)
    return pd.Series(raw.astype(int), index=cumulative_scores.index)


def decile_summary(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Per-decile count, %, and contribution to total composite score."""
    if scored_df.empty or "decile_numeric" not in scored_df.columns:
        return pd.DataFrame(columns=["Decile", "# HCPs", "% HCPs", "% of Potential"])

    total_hcps = len(scored_df)
    total_score = float(scored_df["composite_score"].sum()) or 1.0
    grouped = (
        scored_df.groupby("decile_numeric", as_index=False)
        .agg(hcp_count=("composite_score", "count"), potential=("composite_score", "sum"))
        .sort_values("decile_numeric", ascending=False)
    )
    grouped["Decile"] = grouped["decile_numeric"].astype(int).map(lambda d: f"D{d}")
    grouped["% HCPs"] = (grouped["hcp_count"] / total_hcps * 100).round(2)
    grouped["% of Potential"] = (grouped["potential"] / total_score * 100).round(2)
    grouped = grouped.reset_index(drop=True)
    grouped["Cumulative % HCPs"] = grouped["% HCPs"].cumsum().round(2)
    grouped["Cumulative % of Potential"] = grouped["% of Potential"].cumsum().round(2)
    return grouped[["Decile", "hcp_count", "% HCPs", "% of Potential", "Cumulative % HCPs", "Cumulative % of Potential"]].rename(
        columns={"hcp_count": "# HCPs"}
    )


def lorenz_data(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Build the Lorenz curve table.

    Columns:
    - Cumulative % of Prescribers
    - Cumulative % of Potential
    Rows ordered from top HCP (D10) to bottom (D1). No artificial start row.
    """
    if scored_df.empty or "composite_score" not in scored_df.columns:
        return pd.DataFrame(columns=["Cumulative % of Prescribers", "Cumulative % of Potential"])

    sorted_scores = scored_df["composite_score"].sort_values(ascending=False).reset_index(drop=True)
    n = len(sorted_scores)
    total_potential = float(sorted_scores.sum()) or 1.0

    cum_prescribers_pct = ((np.arange(1, n + 1) / n) * 100).round(2)
    cum_potential_pct = (sorted_scores.cumsum() / total_potential * 100).round(2)

    return pd.DataFrame(
        {
            "Cumulative % of Prescribers": cum_prescribers_pct,
            "Cumulative % of Potential": cum_potential_pct.values,
        }
    )
