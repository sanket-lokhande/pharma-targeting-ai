from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ParsedNLQConfig:
    selected_metrics: List[str]
    metric_weights: Dict[str, float]
    normalization: str = "minmax"
    segmentation_algorithm: str = "kmeans"
    n_clusters: int = 3
    compare_previous: bool = False
    notes: List[str] = field(default_factory=list)


def parse_nlq(text: str, metric_columns: List[str]) -> ParsedNLQConfig:
    query = (text or "").strip().lower()
    notes: List[str] = []

    normalization = "zscore" if any(k in query for k in ["zscore", "z-score"]) else "minmax"

    segmentation_algorithm = "kmeans"
    if "hierarchical" in query:
        segmentation_algorithm = "hierarchical"
    elif "rule_based" in query or "rule-based" in query or "rule based" in query:
        segmentation_algorithm = "rule_based"

    n_clusters = 3
    cluster_match = re.search(r"(\d+)\s*(cluster|clusters|segment|segments)", query)
    if cluster_match:
        n_clusters = int(cluster_match.group(1))
    n_clusters = max(2, min(8, n_clusters))

    compare_previous = any(
        k in query
        for k in [
            "compare",
            "comparison",
            "previous",
            "last period",
            "prior period",
            "vs previous",
        ]
    )

    selected_metrics = [metric for metric in metric_columns if metric.lower() in query]
    if "all metrics" in query or "all columns" in query:
        selected_metrics = metric_columns[:]

    metric_weights = _extract_metric_weights(query, metric_columns)

    if not selected_metrics and metric_weights:
        selected_metrics = [metric for metric in metric_columns if metric in metric_weights]

    if not selected_metrics:
        selected_metrics = metric_columns[:]
        notes.append("No specific metrics detected in NLQ. Defaulted to all metric columns.")

    if not metric_weights:
        equal_weight = round(100.0 / max(len(selected_metrics), 1), 2)
        metric_weights = {metric: equal_weight for metric in selected_metrics}
        _rebalance_weight_rounding(metric_weights)
        notes.append("No explicit weights detected. Assigned equal weights.")
    else:
        metric_weights = {metric: metric_weights.get(metric, 0.0) for metric in selected_metrics}
        _normalize_weights(metric_weights, notes)

    if segmentation_algorithm == "rule_based" and any(k in query for k in ["clusters", "cluster"]):
        notes.append("Cluster count is ignored for rule_based segmentation.")

    return ParsedNLQConfig(
        selected_metrics=selected_metrics,
        metric_weights=metric_weights,
        normalization=normalization,
        segmentation_algorithm=segmentation_algorithm,
        n_clusters=n_clusters,
        compare_previous=compare_previous,
        notes=notes,
    )


def _extract_metric_weights(query: str, metric_columns: List[str]) -> Dict[str, float]:
    weights: Dict[str, float] = {}

    for metric in metric_columns:
        metric_key = metric.lower()
        escaped_metric = re.escape(metric_key)

        after_metric = re.search(escaped_metric + r"[^0-9]{0,12}(\d+(?:\.\d+)?)\s*%?", query)
        before_metric = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*(for|to)\s*" + escaped_metric, query)

        match = after_metric or before_metric
        if match:
            weights[metric] = float(match.group(1))

    return weights


def _normalize_weights(metric_weights: Dict[str, float], notes: List[str]) -> None:
    total = sum(metric_weights.values())
    if total <= 0:
        equal_weight = round(100.0 / max(len(metric_weights), 1), 2)
        for metric in metric_weights:
            metric_weights[metric] = equal_weight
        _rebalance_weight_rounding(metric_weights)
        notes.append("Detected invalid weight total. Replaced with equal weights.")
        return

    if abs(total - 100.0) <= 1e-6:
        return

    ratio = 100.0 / total
    for metric in metric_weights:
        metric_weights[metric] = round(metric_weights[metric] * ratio, 4)

    _rebalance_weight_rounding(metric_weights)
    notes.append(f"Weight total was {round(total, 4)}. Weights were normalized to total 100.")


def _rebalance_weight_rounding(metric_weights: Dict[str, float]) -> None:
    if not metric_weights:
        return

    total = round(sum(metric_weights.values()), 4)
    delta = round(100.0 - total, 4)
    first_key = next(iter(metric_weights.keys()))
    metric_weights[first_key] = round(metric_weights[first_key] + delta, 4)
