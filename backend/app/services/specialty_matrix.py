"""Specialty x Decile matrix (count and % of total HCPs)."""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd


def build_specialty_decile_matrix(
    banded_df: pd.DataFrame,
    specialty_column: Optional[str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (count_matrix, pct_matrix).

    Rows: D10 -> D1 (deciles).
    Columns: distinct specialties, sorted by total HCP count DESC (highest on LEFT).
    Values: counts and % of total HCPs (global %).
    Includes 'Total' row and column.
    """
    if banded_df.empty or specialty_column is None or specialty_column not in banded_df.columns:
        return pd.DataFrame(), pd.DataFrame()
    if "decile" not in banded_df.columns:
        return pd.DataFrame(), pd.DataFrame()

    work = banded_df[["decile", specialty_column]].copy()
    work[specialty_column] = work[specialty_column].fillna("Unknown").astype(str).str.strip()
    work.loc[work[specialty_column] == "", specialty_column] = "Unknown"

    count_matrix = pd.crosstab(work["decile"], work[specialty_column])

    # Order rows D10 -> D1
    decile_order = [f"D{i}" for i in range(10, 0, -1)]
    count_matrix = count_matrix.reindex(index=[d for d in decile_order if d in count_matrix.index])

    # Order columns by total count desc
    column_totals = count_matrix.sum(axis=0).sort_values(ascending=False)
    count_matrix = count_matrix[column_totals.index]

    # Append totals
    count_matrix["Total"] = count_matrix.sum(axis=1)
    total_row = count_matrix.sum(axis=0).to_frame().T
    total_row.index = ["Total"]
    count_matrix = pd.concat([count_matrix, total_row])

    total_hcps = int(count_matrix.loc["Total", "Total"]) or 1
    pct_matrix = (count_matrix / total_hcps * 100).round(2)

    count_matrix.index.name = "Decile"
    pct_matrix.index.name = "Decile"
    return count_matrix.reset_index(), pct_matrix.reset_index()


def specialty_totals(banded_df: pd.DataFrame, specialty_column: Optional[str]) -> pd.DataFrame:
    """One-row-per-specialty summary: count and % of total HCPs."""
    if banded_df.empty or specialty_column is None or specialty_column not in banded_df.columns:
        return pd.DataFrame(columns=["Specialty", "# HCPs", "% of Total"])

    total = len(banded_df)
    series = banded_df[specialty_column].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    counts = series.value_counts()
    df = pd.DataFrame(
        {
            "Specialty": counts.index,
            "# HCPs": counts.values,
            "% of Total": (counts.values / total * 100).round(2),
        }
    )
    return df
