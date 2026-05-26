"""User-defined band segmentation. Replaces clustering.

A band is a named group of deciles (e.g. 'High Value' -> ['D8','D9','D10']).
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from app.schemas import DEFAULT_BANDS, BandConfig, DecileBand


UNASSIGNED_LABEL = "Unassigned"


def apply_bands(
    scored_df: pd.DataFrame,
    bands: List[DecileBand],
) -> pd.DataFrame:
    """Add a `band` column to scored_df based on the decile->band mapping."""
    BandConfig(bands=bands)  # validate (no overlap)
    mapping = _decile_to_band_map(bands)

    out = scored_df.copy()
    if "decile" not in out.columns:
        raise ValueError("scored_df must contain a 'decile' column")
    out["band"] = out["decile"].map(mapping).fillna(UNASSIGNED_LABEL)
    return out


def _decile_to_band_map(bands: List[DecileBand]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for band in bands:
        for d in band.deciles:
            mapping[d] = band.name
    return mapping


def band_summary(banded_df: pd.DataFrame, bands: List[DecileBand]) -> pd.DataFrame:
    """For each user-defined band: HCP count and % of total. Preserves band order."""
    if banded_df.empty or "band" not in banded_df.columns:
        return pd.DataFrame(columns=["Band", "# HCPs", "% of Total"])

    total = len(banded_df)
    counts = banded_df["band"].value_counts().to_dict()

    rows = []
    for band in bands:
        count = int(counts.get(band.name, 0))
        rows.append(
            {
                "Band": band.name,
                "Deciles": ", ".join(sorted(band.deciles, key=lambda d: int(d[1:]), reverse=True)),
                "# HCPs": count,
                "% of Total": round((count / total * 100), 2) if total else 0.0,
            }
        )

    # Include anything unassigned (shouldn't happen with full mapping)
    unassigned = int(counts.get(UNASSIGNED_LABEL, 0))
    if unassigned:
        rows.append(
            {
                "Band": UNASSIGNED_LABEL,
                "Deciles": "",
                "# HCPs": unassigned,
                "% of Total": round((unassigned / total * 100), 2),
            }
        )
    return pd.DataFrame(rows)


def default_bands() -> List[DecileBand]:
    return [DecileBand(name=b.name, deciles=list(b.deciles)) for b in DEFAULT_BANDS]
