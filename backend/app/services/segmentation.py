from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from sklearn.cluster import KMeans

from app.schemas import SegmentationAlgorithm


SEGMENT_LABELS = ["High Value", "Growth", "Low Value", "Strategic", "Nurture", "Emerging"]


def segment_hcps(
    scored_df: pd.DataFrame,
    feature_columns: List[str],
    algorithm: SegmentationAlgorithm,
    n_clusters: int,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]], List[str]]:
    work_df = scored_df.copy()

    if algorithm == "rule_based":
        work_df["segment_id"] = work_df["decile"].apply(decile_to_segment_id)
    elif algorithm == "hierarchical":
        linkage_matrix = linkage(work_df[feature_columns], method="ward")
        work_df["segment_id"] = fcluster(linkage_matrix, n_clusters, criterion="maxclust") - 1
    else:
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        work_df["segment_id"] = model.fit_predict(work_df[feature_columns])

    mapping = map_segment_labels(work_df)
    work_df["segment_label"] = work_df["segment_id"].map(mapping)

    explainability = build_segment_explainability(work_df, feature_columns)

    return work_df, explainability, [mapping[idx] for idx in sorted(mapping)]


def decile_to_segment_id(decile: str) -> int:
    high = {"D10", "D9", "D8"}
    growth = {"D4", "D5", "D6", "D7"}
    if decile in high:
        return 0
    if decile in growth:
        return 1
    return 2


def map_segment_labels(df: pd.DataFrame) -> Dict[int, str]:
    segment_means = df.groupby("segment_id")["composite_score"].mean().sort_values(ascending=False)
    mapping: Dict[int, str] = {}
    for idx, segment_id in enumerate(segment_means.index):
        mapping[int(segment_id)] = SEGMENT_LABELS[idx % len(SEGMENT_LABELS)]
    return mapping


def build_segment_explainability(df: pd.DataFrame, feature_columns: List[str]) -> Dict[str, Dict[str, float]]:
    explainability: Dict[str, Dict[str, float]] = {}
    grouped = df.groupby("segment_label")
    global_means = df[feature_columns].mean()

    for segment_name, seg_df in grouped:
        ratios = {}
        for col in feature_columns:
            baseline = global_means[col] if global_means[col] != 0 else 1
            ratio = seg_df[col].mean() / baseline
            ratios[col] = float(np.round(ratio, 3))
        explainability[segment_name] = ratios

    return explainability
