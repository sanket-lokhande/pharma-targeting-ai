"""Movement / New / Lost / Existing analysis between two banded period datasets."""
from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _decile_to_int(value: object) -> int:
    text = str(value).strip().upper().replace("D", "")
    try:
        return int(text)
    except ValueError:
        return 0


def compute_movement(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    id_column: str,
) -> pd.DataFrame:
    """Movement for HCPs present in BOTH datasets.

    Columns: HCP ID, Previous Decile, Current Decile, Movement (Up/Down/Same).
    """
    if id_column not in current_df.columns or id_column not in previous_df.columns:
        return pd.DataFrame(columns=[id_column, "Previous Decile", "Current Decile", "Movement"])

    current_keys = current_df[[id_column, "decile"]].rename(columns={"decile": "Current Decile"})
    previous_keys = previous_df[[id_column, "decile"]].rename(columns={"decile": "Previous Decile"})

    joined = previous_keys.merge(current_keys, on=id_column, how="inner")
    if joined.empty:
        return joined.rename(columns={id_column: id_column})

    prev_num = joined["Previous Decile"].map(_decile_to_int)
    curr_num = joined["Current Decile"].map(_decile_to_int)

    def _label(prev: int, curr: int) -> str:
        if curr > prev:
            return "Up"
        if curr < prev:
            return "Down"
        return "Same"

    joined["Movement"] = [_label(p, c) for p, c in zip(prev_num, curr_num)]
    return joined[[id_column, "Previous Decile", "Current Decile", "Movement"]].reset_index(drop=True)


def compute_new_lost_existing(
    current_banded: pd.DataFrame,
    previous_banded: pd.DataFrame,
    id_column: str,
) -> Dict[str, pd.DataFrame]:
    """Return tables for NEW, LOST, EXISTING and existing band-movement.

    NEW: in current, NOT in previous (counts/% based on CURRENT bands).
    LOST: in previous, NOT in current (counts/% based on PREVIOUS bands).
    EXISTING: in both — broken into Up / Down / Same (band-based movement).
    """
    current_ids = set(current_banded[id_column])
    previous_ids = set(previous_banded[id_column])

    new_ids = current_ids - previous_ids
    lost_ids = previous_ids - current_ids
    existing_ids = current_ids & previous_ids

    new_df = current_banded[current_banded[id_column].isin(new_ids)]
    lost_df = previous_banded[previous_banded[id_column].isin(lost_ids)]

    new_summary = _band_breakdown(new_df, total=len(new_df))
    lost_summary = _band_breakdown(lost_df, total=len(lost_df))

    existing_summary, existing_detail = _existing_movement(
        current_banded[current_banded[id_column].isin(existing_ids)],
        previous_banded[previous_banded[id_column].isin(existing_ids)],
        id_column,
    )

    totals = pd.DataFrame(
        [
            {"Group": "NEW (in current, not in previous)", "# HCPs": len(new_ids)},
            {"Group": "LOST (in previous, not in current)", "# HCPs": len(lost_ids)},
            {"Group": "EXISTING (in both)", "# HCPs": len(existing_ids)},
        ]
    )

    return {
        "totals": totals,
        "new_hcps_by_band": new_summary,
        "lost_hcps_by_band": lost_summary,
        "existing_movement_summary": existing_summary,
        "existing_movement_detail": existing_detail,
    }


def _band_breakdown(df: pd.DataFrame, total: int) -> pd.DataFrame:
    if df.empty or "band" not in df.columns:
        return pd.DataFrame(columns=["Band", "# HCPs", "% of Group"])
    counts = df["band"].value_counts()
    rows: List[Dict[str, object]] = []
    for band_name, count in counts.items():
        rows.append(
            {
                "Band": str(band_name),
                "# HCPs": int(count),
                "% of Group": round((count / total * 100), 2) if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _existing_movement(
    current_existing: pd.DataFrame,
    previous_existing: pd.DataFrame,
    id_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if current_existing.empty or previous_existing.empty:
        return (
            pd.DataFrame(columns=["Transition", "# HCPs", "% of Existing"]),
            pd.DataFrame(columns=[id_column, "Previous Band", "Current Band", "Transition"]),
        )

    prev = previous_existing[[id_column, "band"]].rename(columns={"band": "Previous Band"})
    curr = current_existing[[id_column, "band"]].rename(columns={"band": "Current Band"})
    joined = prev.merge(curr, on=id_column, how="inner")

    rank = _band_rank_map(list(current_existing["band"].unique()) + list(previous_existing["band"].unique()))

    def _classify(prev_band: str, curr_band: str) -> str:
        if prev_band == curr_band:
            return "Same band"
        p_rank = rank.get(prev_band, 0)
        c_rank = rank.get(curr_band, 0)
        if c_rank > p_rank:
            return f"{prev_band} -> {curr_band} (Up)"
        return f"{prev_band} -> {curr_band} (Down)"

    joined["Transition"] = [
        _classify(str(p), str(c)) for p, c in zip(joined["Previous Band"], joined["Current Band"])
    ]

    total = len(joined)
    summary = (
        joined["Transition"].value_counts().rename_axis("Transition").reset_index(name="# HCPs")
    )
    summary["% of Existing"] = (summary["# HCPs"] / total * 100).round(2) if total else 0.0

    return summary, joined.reset_index(drop=True)


def _band_rank_map(band_names: List[str]) -> Dict[str, int]:
    """Heuristic rank: 'High' > 'Medium' > 'Low' by name keyword; fallback alphabetical."""
    priority_keywords = [
        ("high", 3),
        ("growth", 2),
        ("medium", 2),
        ("mid", 2),
        ("low", 1),
        ("nurture", 1),
    ]
    rank: Dict[str, int] = {}
    for name in set(band_names):
        lname = str(name).lower()
        score = 0
        for kw, value in priority_keywords:
            if kw in lname:
                score = max(score, value)
        rank[name] = score
    return rank
