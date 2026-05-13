from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from app.schemas import MetricWeight, NormalizationMethod


def compute_scores_and_deciles(
    df: pd.DataFrame,
    id_column: str,
    metric_weights: List[MetricWeight],
    normalization: NormalizationMethod,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float], Dict[str, List[float]], Dict[str, List[float]], Dict[str, Dict[str, float]]]:
    metrics = [item.metric for item in metric_weights]
    weights = np.array([item.weight / 100.0 for item in metric_weights])

    missing_metrics = [metric for metric in metrics if metric not in df.columns]
    if missing_metrics:
        raise ValueError(f"Selected metrics not found in dataset: {missing_metrics}")

    work_df = df[[id_column] + metrics].copy()

    # Deciling is explicitly based on min-max normalized metrics as requested.
    # This ensures composite scores are non-negative and cumulative decile formula
    # behaves exactly like the spreadsheet implementation.
    scaler = MinMaxScaler()
    scaled_values = np.nan_to_num(scaler.fit_transform(work_df[metrics].values))
    composite_scores = np.dot(scaled_values, weights)
    work_df["composite_score"] = composite_scores

    work_df = work_df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    # Decile formula mirrors spreadsheet logic:
    # IF(10-FLOOR(10*cumulative_score/total_score,1)=0,1,10-FLOOR(...))
    cumulative_scores = work_df["composite_score"].cumsum()
    total_score = float(work_df["composite_score"].sum())
    work_df["cumulative_composite_score"] = cumulative_scores
    work_df["total_composite_score"] = total_score

    if total_score <= 0:
        decile_numbers = np.ones(len(work_df), dtype=int)
    else:
        # Excel-equivalent:
        # IF(10-FLOOR(10*cumulative/total,1)=0,1,10-FLOOR(10*cumulative/total,1))
        raw_deciles = 10 - np.floor((10 * cumulative_scores) / total_score).astype(int)
        raw_deciles = np.where(raw_deciles == 0, 1, raw_deciles)
        decile_numbers = np.clip(raw_deciles, 1, 10)

    work_df["decile_numeric"] = decile_numbers
    work_df["decile"] = [f"D{value}" for value in decile_numbers]

    corr = work_df[metrics].corr().fillna(0)
    correlation_matrix = corr.round(3)

    driver_strength = {metric: float(corr.loc[metric, metrics].abs().mean()) for metric in metrics}

    concentration_curve = build_lorenz_curve(work_df, "composite_score")
    distributions = build_distributions(work_df, metrics)
    metric_summary = summarize_metrics(work_df, metrics)

    return work_df, correlation_matrix, driver_strength, concentration_curve, distributions, metric_summary


def normalize(metric_df: pd.DataFrame, normalization: NormalizationMethod) -> np.ndarray:
    if normalization == "zscore":
        scaler = StandardScaler()
    else:
        scaler = MinMaxScaler()
    values = scaler.fit_transform(metric_df.values)
    return np.nan_to_num(values)


def build_lorenz_curve(df: pd.DataFrame, value_column: str) -> Dict[str, List[float]]:
    ordered = df[value_column].sort_values(ascending=False).values
    cumulative_values = np.cumsum(ordered)
    cumulative_values = cumulative_values / cumulative_values[-1] if cumulative_values[-1] != 0 else cumulative_values
    x_axis = np.linspace(0, 1, len(cumulative_values))
    return {
        "population_share": x_axis.round(4).tolist(),
        "value_share": cumulative_values.round(4).tolist(),
    }


def build_distributions(df: pd.DataFrame, metrics: List[str]) -> Dict[str, List[float]]:
    distribution_payload: Dict[str, List[float]] = {}
    comp_hist, comp_bins = np.histogram(df["composite_score"], bins=20)
    distribution_payload["composite_score_counts"] = comp_hist.tolist()
    distribution_payload["composite_score_bins"] = comp_bins[:-1].round(4).tolist()

    for metric in metrics:
        counts, bins = np.histogram(df[metric], bins=20)
        distribution_payload[f"{metric}_counts"] = counts.tolist()
        distribution_payload[f"{metric}_bins"] = bins[:-1].round(4).tolist()

    return distribution_payload


def summarize_metrics(df: pd.DataFrame, metrics: List[str]) -> Dict[str, Dict[str, float]]:
    summary = {}
    for metric in metrics:
        summary[metric] = {
            "mean": float(df[metric].mean()),
            "median": float(df[metric].median()),
            "std": float(df[metric].std(ddof=0)),
            "min": float(df[metric].min()),
            "max": float(df[metric].max()),
        }
    return summary
