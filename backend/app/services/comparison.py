from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _decile_number(decile: str) -> int:
    return int(str(decile).replace("D", ""))


def compare_current_vs_previous(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    id_column: str,
) -> Dict[str, object]:
    current_ids = set(current_df[id_column])
    previous_ids = set(previous_df[id_column])

    new_ids = sorted(list(current_ids - previous_ids))
    missing_ids = sorted(list(previous_ids - current_ids))

    common_ids = sorted(list(current_ids.intersection(previous_ids)))

    prev_map = previous_df.set_index(id_column)
    curr_map = current_df.set_index(id_column)

    movement_rows: List[Dict[str, object]] = []
    segment_shift_rows: List[Dict[str, object]] = []
    hcp_movement_details: List[Dict[str, object]] = []

    low_tiers = {"D1", "D2", "D3"}
    high_tiers = {"D8", "D9", "D10"}

    low_to_high = 0
    high_to_low = 0

    for hcp_id in common_ids:
        prev_decile = str(prev_map.loc[hcp_id, "decile"])
        curr_decile = str(curr_map.loc[hcp_id, "decile"])
        prev_segment = str(prev_map.loc[hcp_id, "segment_label"])
        curr_segment = str(curr_map.loc[hcp_id, "segment_label"])
        prev_num = _decile_number(prev_decile)
        curr_num = _decile_number(curr_decile)
        delta_decile = curr_num - prev_num

        movement_type = "No decile movement"
        if delta_decile > 0:
            movement_type = "Moved to higher decile"
        elif delta_decile < 0:
            movement_type = "Moved to lower decile"

        hcp_movement_details.append(
            {
                "id": hcp_id,
                "movement_type": movement_type,
                "delta_decile": delta_decile,
                "previous_decile": prev_decile,
                "current_decile": curr_decile,
            }
        )

        if prev_decile in low_tiers and curr_decile in high_tiers:
            low_to_high += 1
        if prev_decile in high_tiers and curr_decile in low_tiers:
            high_to_low += 1

        if prev_decile != curr_decile:
            movement_rows.append(
                {
                    "id": hcp_id,
                    "previous_decile": prev_decile,
                    "current_decile": curr_decile,
                }
            )

        if prev_segment != curr_segment:
            segment_shift_rows.append(
                {
                    "id": hcp_id,
                    "previous_segment": prev_segment,
                    "current_segment": curr_segment,
                }
            )

    new_hcp_df = current_df[current_df[id_column].isin(new_ids)]
    new_top_tier_count = int(new_hcp_df["decile"].isin(high_tiers).sum())
    new_low_tier_count = int(new_hcp_df["decile"].isin(low_tiers).sum())

    lost_high_value = previous_df[
        (previous_df[id_column].isin(missing_ids)) & (previous_df["decile"].isin(high_tiers))
    ][id_column].tolist()

    summary = {
        "low_to_high": low_to_high,
        "high_to_low": high_to_low,
        "new_hcp_count": len(new_ids),
        "missing_hcp_count": len(missing_ids),
        "segment_shifts": len(segment_shift_rows),
        "lost_high_value_hcps": len(lost_high_value),
    }

    return {
        "movement_analysis": movement_rows,
        "hcp_movement_details": hcp_movement_details,
        "new_vs_missing": {
            "new_hcps": new_ids,
            "missing_hcps": missing_ids,
            "new_top_tier_count": new_top_tier_count,
            "new_low_tier_count": new_low_tier_count,
            "lost_high_value_hcps": lost_high_value,
        },
        "segment_shift_analysis": segment_shift_rows,
        "comparison_summary": summary,
    }
