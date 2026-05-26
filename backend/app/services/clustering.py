"""Metric-based HCP clustering and segment naming.

Clustering is based on raw metric columns (no weight usage).
Segment names are derived from dominant raw centroid metrics.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans


def build_hcp_clusters(
    df: pd.DataFrame,
    metric_columns: List[str],
    n_clusters: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return clustered rows, cluster profile table, and heatmap matrix.

    - Clustering runs on raw metric values (missing values median-imputed).
    - Cluster names are generated from dominant centroid metrics.
    """
    if df.empty:
        return df.copy(), pd.DataFrame(), pd.DataFrame()

    metrics = [m for m in metric_columns if m in df.columns and pd.api.types.is_numeric_dtype(df[m])]
    if not metrics:
        out = df.copy()
        out["cluster_id"] = "C1"
        out["segment_name"] = "Unclustered"
        profile = pd.DataFrame([
            {"cluster_id": "C1", "segment_name": "Unclustered", "# HCPs": len(out), "% HCPs": 100.0}
        ])
        return out, profile, pd.DataFrame()

    # Raw metric matrix used directly for clustering (no weighting).
    feature_df = pd.DataFrame(index=df.index)
    for col in metrics:
        numeric = pd.to_numeric(df[col], errors="coerce")
        feature_df[col] = numeric.fillna(0.0)
    feature_df = feature_df.fillna(0.0)

    n = len(feature_df)
    n_clusters = int(max(2, min(n_clusters, n)))

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(feature_df.values)

    work = df.copy()
    work["cluster_numeric"] = labels.astype(int)

    centroid_df = (
        pd.DataFrame(kmeans.cluster_centers_, columns=metrics)
        .reset_index()
        .rename(columns={"index": "cluster_numeric"})
    )

    counts = work["cluster_numeric"].value_counts().sort_index()
    overall_means = feature_df.mean(axis=0)

    cluster_names = _generate_cluster_names(
        centroid_df=centroid_df,
        overall_means=overall_means,
        metrics=metrics,
    )

    work["cluster_id"] = work["cluster_numeric"].map(lambda x: f"C{int(x) + 1}")
    work["segment_name"] = work["cluster_numeric"].map(cluster_names)

    rows: List[Dict[str, object]] = []
    for cid in sorted(centroid_df["cluster_numeric"].tolist()):
        cluster_id = f"C{int(cid) + 1}"
        row: Dict[str, object] = {
            "cluster_id": cluster_id,
            "segment_name": cluster_names[cid],
            "# HCPs": int(counts.get(cid, 0)),
            "% HCPs": round((counts.get(cid, 0) / n) * 100, 2),
        }
        center = centroid_df[centroid_df["cluster_numeric"] == cid].iloc[0]
        top_metric, top_ratio = _dominant_metric(center, overall_means, metrics)
        row["dominant_metric"] = top_metric
        row["dominance_vs_overall"] = round(top_ratio, 2)
        for metric in metrics:
            row[metric] = round(float(center[metric]), 4)
        rows.append(row)

    profile = pd.DataFrame(rows).sort_values("# HCPs", ascending=False).reset_index(drop=True)

    heatmap = profile[["cluster_id", "segment_name", *metrics]].copy()
    return work.drop(columns=["cluster_numeric"]), profile, heatmap


def _pretty_metric_name(metric: str) -> str:
    # Preserve original casing (e.g. AGVHD) and only improve separators.
    return str(metric).replace("_", " ").replace("-", " ").strip()


def _dominant_metric(center_row: pd.Series, overall_means: pd.Series, metrics: List[str]) -> tuple[str, float]:
    if not metrics:
        return "Metric", 1.0
    values = np.array([float(center_row[m]) for m in metrics], dtype=float)
    top_idx = int(np.argmax(values))
    top_metric_raw = metrics[top_idx]
    top_metric = _pretty_metric_name(top_metric_raw)

    base = float(overall_means.get(top_metric_raw, 0.0))
    denom = base if base > 1e-9 else 1e-9
    ratio = float(values[top_idx] / denom)
    return top_metric, ratio


def _generate_cluster_names(
    centroid_df: pd.DataFrame,
    overall_means: pd.Series,
    metrics: List[str],
) -> Dict[int, str]:
    """Rule-based naming using dominant raw metric heaviness."""
    names: Dict[int, str] = {}
    used: Dict[str, int] = {}

    # First pass: collect dominant metric and value for each cluster
    cluster_info = []
    for _, row in centroid_df.iterrows():
        cid = int(row["cluster_numeric"])
        values = np.array([float(row[m]) for m in metrics], dtype=float)
        rel = []
        for m in metrics:
            base = float(overall_means.get(m, 0.0))
            denom = base if base > 1e-9 else 1e-9
            rel.append(float(row[m]) / denom)

        top_indices = np.argsort(values)[-2:][::-1] if len(values) >= 2 else [0]
        top_idx = top_indices[0]
        top_metric_raw = metrics[top_idx] if metrics else "Metric"
        top_metric = _pretty_metric_name(top_metric_raw)
        top_value = float(row[top_metric_raw]) if metrics else 0.0
        top_ratio = float(rel[top_idx]) if rel else 1.0

        if len(top_indices) > 1:
            second_idx = top_indices[1]
            second_metric = _pretty_metric_name(metrics[second_idx])
            second_ratio = float(rel[second_idx])
        else:
            second_metric = None
            second_ratio = 0.0

        use_two = second_metric is not None and second_ratio >= 0.85 * top_ratio

        overall_vals = np.array([float(overall_means.get(m, 0.0)) for m in metrics], dtype=float)
        overall_avg = float(overall_vals.mean()) if len(overall_vals) else 0.0
        centroid_avg = float(values.mean()) if len(values) else 0.0
        uniformity = float(values.std() / centroid_avg) if centroid_avg > 1e-9 else 0.0

        cluster_info.append({
            "cid": cid,
            "top_metric": top_metric,
            "top_metric_raw": top_metric_raw,
            "top_value": top_value,
            "top_ratio": top_ratio,
            "use_two": use_two,
            "second_metric": second_metric,
            "second_ratio": second_ratio,
            "overall_avg": overall_avg,
            "centroid_avg": centroid_avg,
            "uniformity": uniformity,
            "values": values,
        })

    # For each dominant metric, find the max value among clusters
    metric_to_max = {}
    metric_to_second_max = {}
    for info in cluster_info:
        m = info["top_metric_raw"]
        v = info["top_value"]
        if m not in metric_to_max or v > metric_to_max[m]:
            metric_to_max[m] = v
    # Find second max for each metric
    for m in metric_to_max:
        vals = [info["top_value"] for info in cluster_info if info["top_metric_raw"] == m]
        sorted_vals = sorted(vals, reverse=True)
        metric_to_second_max[m] = sorted_vals[1] if len(sorted_vals) > 1 else None

    # Group clusters by dominant metric for low/medium/high assignment
    from collections import defaultdict
    metric_to_clusters = defaultdict(list)
    for info in cluster_info:
        metric_to_clusters[info["top_metric_raw"]].append(info)

    # For each group, sort by top_value and assign nuanced labels if more than 1
    for metric, infos in metric_to_clusters.items():
        if len(infos) == 1:
            infos[0]["level_prefix"] = None
        else:
            sorted_infos = sorted(infos, key=lambda x: x["top_value"])
            n = len(sorted_infos)
            for i, info in enumerate(sorted_infos):
                q = i / (n - 1) if n > 1 else 0
                # Assign nuanced labels based on quantile
                if n == 2:
                    prefix = "Low" if i == 0 else "High"
                elif n == 3:
                    prefix = ["Low", "High", "Very High"][i] if i == 2 and sorted_infos[2]["top_value"] >= 1.5 * sorted_infos[1]["top_value"] else ["Low", "Mid-Tier", "High"][i]
                else:
                    # For >3, use quantiles and extremity
                    if q <= 0.15:
                        prefix = "Low"
                    elif q <= 0.45:
                        prefix = "Mid-Tier"
                    elif q <= 0.75:
                        prefix = "Moderate-to-High"
                    elif i == n - 1 and sorted_infos[i]["top_value"] >= 1.5 * sorted_infos[i-1]["top_value"]:
                        prefix = "Very High"
                    else:
                        prefix = "High"
                info["level_prefix"] = prefix

    for info in cluster_info:
        cid = info["cid"]
        top_metric = info["top_metric"]
        top_metric_raw = info["top_metric_raw"]
        top_value = info["top_value"]
        top_ratio = info["top_ratio"]
        use_two = info["use_two"]
        second_metric = info["second_metric"]
        second_ratio = info["second_ratio"]
        overall_avg = info["overall_avg"]
        centroid_avg = info["centroid_avg"]
        uniformity = info["uniformity"]
        values = info["values"]
        level_prefix = info.get("level_prefix")

        # Naming rules (preserve existing special cases)
        if len(values) and overall_avg > 0 and centroid_avg <= 0.70 * overall_avg:
            base_name = "Low Engagement HCPs"
        elif len(values) and overall_avg > 0 and centroid_avg >= 1.25 * overall_avg and uniformity <= 0.30:
            base_name = "High-Volume All-Rounders"
        elif len(values) and uniformity <= 0.18:
            base_name = "Balanced HCPs"
        elif use_two:
            base_name = f"{top_metric} + {second_metric} Mix Patient-Heavy HCPs"
        else:
            base_name = f"{top_metric} Patient-Heavy HCPs"

        # Check for extremity: if this cluster's top_value is at least 2x the overall mean for that metric,
        # or at least 1.5x the next highest cluster with the same dominant metric, mark as extreme
        overall_mean = float(overall_means.get(top_metric_raw, 0.0))
        second_max = metric_to_second_max.get(top_metric_raw)
        is_extreme = False
        if overall_mean > 0 and top_value >= 2.0 * overall_mean:
            is_extreme = True
        elif second_max is not None and top_value >= 1.5 * second_max:
            is_extreme = True

        # Add level prefix if present and not a special case
        if level_prefix and "Low Engagement" not in base_name and "High-Volume" not in base_name and "Balanced" not in base_name:
            # If level_prefix is 'Very High', do not add 'Extremely high' prefix
            if level_prefix == "Very High":
                base_name = f"Very High {base_name[0].lower() + base_name[1:]}"
            else:
                base_name = f"{level_prefix} {base_name[0].lower() + base_name[1:]}"
        # If no level prefix and is_extreme, add 'Extremely high' prefix
        elif is_extreme and "Low Engagement" not in base_name and "High-Volume" not in base_name and "Balanced" not in base_name:
            base_name = f"Extremely high {base_name[0].lower() + base_name[1:]}"

        names[cid] = base_name

    return names
