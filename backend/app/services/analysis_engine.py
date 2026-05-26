"""Orchestrates: scoring -> deciles -> band mapping -> specialty matrix -> comparison."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.schemas import DecileBand, MetricWeight
from app.services.analytics import (
    compute_scores_and_deciles,
    decile_summary,
    lorenz_data,
)
from app.services.comparison import compute_movement, compute_new_lost_existing
from app.services.clustering import build_hcp_clusters
from app.services.segmentation import apply_bands, band_summary, default_bands
from app.services.specialty_matrix import build_specialty_decile_matrix, specialty_totals


def build_analysis_payload(
    current_df: pd.DataFrame,
    id_column: str,
    metric_weights: List[MetricWeight],
    bands: Optional[List[DecileBand]] = None,
    n_clusters: int = 5,
    specialty_column: Optional[str] = None,
    previous_df: Optional[pd.DataFrame] = None,
    previous_id_column: Optional[str] = None,
    previous_specialty_column: Optional[str] = None,
    current_original_df: Optional[pd.DataFrame] = None,
    normalization_method: str = "minmax",
) -> Dict[str, Any]:
    bands = bands or default_bands()

    scored, metrics_used = compute_scores_and_deciles(current_df, id_column, metric_weights, normalization_method=normalization_method)
    banded = apply_bands(scored, bands)
    clustering_metrics = _cluster_metric_columns(current_df, id_column, specialty_column)
    clustered, cluster_profile, cluster_heatmap = build_hcp_clusters(
        banded,
        metric_columns=clustering_metrics,
        n_clusters=n_clusters,
    )

    decile_table = decile_summary(clustered)
    band_table = band_summary(clustered, bands)
    lorenz_table = lorenz_data(clustered)
    specialty_total_table = specialty_totals(clustered, specialty_column)
    specialty_count_matrix, specialty_pct_matrix = build_specialty_decile_matrix(clustered, specialty_column)

    # Build output sheet: original user values + derived columns only.
    # This ensures the export never shows coerced/imputed metric values.
    _DERIVED_COLS = [
        "composite_score", "cumulative_composite_score", "total_composite_score",
        "decile_numeric", "decile", "band", "cluster_id", "segment_name",
    ]
    derived = clustered[[id_column] + [c for c in _DERIVED_COLS if c in clustered.columns]].copy()
    derived["Rank"] = derived["composite_score"].rank(ascending=False, method="first").astype(int)

    if current_original_df is not None and id_column in current_original_df.columns:
        export_df = current_original_df.copy()
        export_df[id_column] = export_df[id_column].astype(str).str.strip()
        derived_id_col = derived[id_column].astype(str).str.strip()
        derived = derived.copy()
        derived[id_column] = derived_id_col
        # Check for duplicate IDs in the original data
        if export_df[id_column].duplicated().any():
            raise ValueError(f"Duplicate IDs found in your uploaded file for column '{id_column}'. Please ensure all IDs are unique.")
        export_df = export_df.merge(derived, on=id_column, how="left")
    else:
        export_df = clustered.copy()
        export_df["Rank"] = export_df["composite_score"].rank(ascending=False, method="first").astype(int)

    payload: Dict[str, Any] = {
        "id_column": id_column,
        "specialty_column": specialty_column,
        "metrics_used": metrics_used,
        "bands": [b.model_dump() for b in bands],
        "raw_with_scores": export_df,
        "decile_summary": decile_table,
        "segment_band_summary": band_table,
        "cluster_profile": cluster_profile,
        "cluster_heatmap": cluster_heatmap,
        "lorenz_curve": lorenz_table,
        "specialty_totals": specialty_total_table,
        "specialty_decile_count": specialty_count_matrix,
        "specialty_decile_pct": specialty_pct_matrix,
        "has_previous": False,
    }

    if previous_df is not None and previous_id_column is not None:
        prev_work = previous_df.copy()
        if previous_id_column != id_column:
            prev_work = prev_work.rename(columns={previous_id_column: id_column})

        prev_banded = _prepare_previous_banded(
            prev_work=prev_work,
            id_column=id_column,
            metric_weights=metric_weights,
            bands=bands,
        )

        movement_table = compute_movement(banded, prev_banded, id_column)
        nle = compute_new_lost_existing(banded, prev_banded, id_column)

        prev_band_table = _band_summary_by_label(prev_banded)
        band_change = _band_change_table(band_table, prev_band_table)

        payload.update(
            {
                "has_previous": True,
                "previous_segment_band_summary": prev_band_table,
                "segment_band_change": band_change,
                "movement_analysis": movement_table,
                "new_vs_lost_existing": nle,
            }
        )

    return payload


def _cluster_metric_columns(
    current_df: pd.DataFrame,
    id_column: str,
    specialty_column: Optional[str],
) -> List[str]:
    """Raw numeric metric columns used for clustering (independent of weights)."""
    exclude = {id_column}
    if specialty_column:
        exclude.add(specialty_column)

    metrics: List[str] = []
    for col in current_df.columns:
        if col in exclude:
            continue
        if pd.api.types.is_numeric_dtype(current_df[col]):
            metrics.append(col)
    return metrics


def _band_change_table(
    current_band_summary: pd.DataFrame,
    previous_band_summary: pd.DataFrame,
) -> pd.DataFrame:
    if current_band_summary.empty:
        return pd.DataFrame()
    current_work = current_band_summary.copy()
    current_work["_band_key"] = current_work["Band"].map(_normalize_band_label)

    previous_work = previous_band_summary.copy()
    previous_work["_band_key"] = previous_work["Band"].map(_normalize_band_label)

    merged = current_work.merge(
        previous_work[["_band_key", "Band", "# HCPs", "% of Total"]].rename(
            columns={"# HCPs": "Previous # HCPs", "% of Total": "Previous % of Total"}
        ),
        on="_band_key",
        how="left",
        suffixes=("", "_previous"),
    )

    prev_counts = merged["Previous # HCPs"].fillna(0).astype(float)
    curr_counts = merged["# HCPs"].fillna(0).astype(float)

    # Percent change formula requested by user:
    # ((current - previous) / previous) * 100
    # If previous == 0 and current > 0, mark as +inf (newly created segment).
    pct_change = pd.Series(index=merged.index, dtype=float)
    has_prev = prev_counts > 0
    pct_change.loc[has_prev] = ((curr_counts.loc[has_prev] - prev_counts.loc[has_prev]) / prev_counts.loc[has_prev]) * 100.0
    pct_change.loc[~has_prev & (curr_counts > 0)] = float("inf")
    pct_change.loc[~has_prev & (curr_counts <= 0)] = 0.0

    merged["% Change vs Previous"] = pct_change.round(2)
    return merged.drop(columns=["_band_key"])


def _band_summary_by_label(banded_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize bands using labels present in the dataframe as-is."""
    if banded_df.empty or "band" not in banded_df.columns:
        return pd.DataFrame(columns=["Band", "# HCPs", "% of Total"])

    total = len(banded_df)
    summary = (
        banded_df["band"].fillna("Unassigned").astype(str).str.strip().replace({"": "Unassigned"})
        .value_counts()
        .rename_axis("Band")
        .reset_index(name="# HCPs")
    )
    summary["% of Total"] = (summary["# HCPs"] / total * 100).round(2) if total else 0.0
    return summary


def _normalize_band_label(label: object) -> str:
    return " ".join(str(label).strip().lower().split())


# ---------------------------------------------------------------------------
# Previous-period preparation
# ---------------------------------------------------------------------------
_DECILE_HINTS = ("decile", "decil", "tier")
_BAND_HINTS = ("band", "segment", "tier_group", "group")


def _norm(name: str) -> str:
    return "".join(str(name).lower().split())


def _find_column(df: pd.DataFrame, hints: tuple[str, ...]) -> Optional[str]:
    for col in df.columns:
        lower = str(col).lower()
        if any(h in lower for h in hints):
            return col
    return None


def _coerce_decile_label(value: object) -> Optional[str]:
    """Normalize various decile representations to 'D1'..'D10', else None."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text or text in {"NA", "NAN", "NONE"}:
        return None
    if text.startswith("D"):
        text = text[1:]
    text = text.replace("DECILE", "").strip()
    try:
        as_float = float(text)
    except ValueError:
        return None
    if pd.isna(as_float):
        return None
    as_int = int(round(as_float))
    if as_int < 1 or as_int > 10:
        return None
    return f"D{as_int}"


def _prepare_previous_banded(
    prev_work: pd.DataFrame,
    id_column: str,
    metric_weights: List[MetricWeight],
    bands: List[DecileBand],
) -> pd.DataFrame:
    """Build a banded previous-period dataframe.

    Comparison is driven by Decile and Band, NOT by metric weights. So the
    previous file does NOT need to share metric columns with the current file.

    Strategy (in order):
      1. If the previous file already contains a Decile column, use it as-is
         (normalized to 'D1'..'D10'). Bands are taken from the previous file
         if a Band/Segment column exists; otherwise the current band mapping
         is applied to the previous deciles.
      2. Otherwise, fall back to scoring the previous file using whatever
         weighted metrics it shares (case/space-insensitive) with the current
         file.
      3. If neither is possible, raise a clear, actionable error.
    """
    if id_column not in prev_work.columns:
        raise ValueError(
            f"Previous file is missing the ID column '{id_column}'. "
            "Choose the matching ID column in the previous file or rename it."
        )

    decile_col = _find_column(prev_work, _DECILE_HINTS)
    band_col = _find_column(prev_work, _BAND_HINTS)

    if decile_col is not None:
        out = prev_work.copy()
        out["decile"] = out[decile_col].map(_coerce_decile_label)
        missing = int(out["decile"].isna().sum())
        if missing:
            # Drop rows we cannot interpret rather than failing the whole run.
            out = out[out["decile"].notna()].copy()
        if out.empty:
            raise ValueError(
                f"Previous file column '{decile_col}' did not yield any valid "
                "decile values (expected D1..D10 or 1..10)."
            )
        out["decile_numeric"] = out["decile"].str.replace("D", "", regex=False).astype(int)

        if band_col is not None:
            out["band"] = out[band_col].astype(str).str.strip().replace({"": "Unassigned", "nan": "Unassigned"})
        else:
            out = apply_bands(out, bands)

        # Provide a placeholder composite_score so downstream code that
        # references it (e.g. previous-period band summary) does not break.
        if "composite_score" not in out.columns:
            out["composite_score"] = 0.0
        return out

    # No decile column -> fall back to metric-overlap scoring.
    prev_cols_norm = {_norm(c): c for c in prev_work.columns}
    prev_weights: List[MetricWeight] = []
    for m in metric_weights:
        actual = prev_cols_norm.get(_norm(m.metric))
        if actual is None or not pd.api.types.is_numeric_dtype(prev_work[actual]):
            continue
        prev_weights.append(MetricWeight(metric=actual, weight=m.weight))

    if not prev_weights:
        raise ValueError(
            "Cannot build previous-period comparison.\n"
            "  The previous file has no Decile/Segment column AND none of the "
            "current weighted metrics are present in it.\n"
            f"  Previous file columns: {list(prev_work.columns)}\n"
            "Tip: include a 'Decile' (D1..D10) column in the previous file, "
            "or use matching metric column names."
        )

    prev_scored, _ = compute_scores_and_deciles(prev_work, id_column, prev_weights)
    return apply_bands(prev_scored, bands)
