"""Smoke test for the HCP/Account Targeting Tool pipeline.

Generates synthetic current + previous datasets (with blank rows/columns and a
shifted header to test flexible input), runs the full analysis, and writes a
sample Excel workbook to disk.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.schemas import DecileBand, MetricWeight  # noqa: E402
from app.services.analysis_engine import build_analysis_payload  # noqa: E402
from app.services.exporter import build_excel_output  # noqa: E402
from app.services.validation import load_excel_flexible, validate_dataframe  # noqa: E402


def _build_messy_excel(df: pd.DataFrame) -> bytes:
    """Write df to xlsx with blank header rows/columns to test flexible loader."""
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data", index=False, startrow=3, startcol=2)
    return out.getvalue()


def main() -> None:
    rng = np.random.default_rng(42)
    n = 250
    specialties = rng.choice(
        ["Cardiology", "Oncology", "Neurology", "Endocrinology", "Pulmonology"],
        size=n,
        p=[0.35, 0.25, 0.15, 0.15, 0.10],
    )
    current = pd.DataFrame(
        {
            "HCP_ID": [f"H{1000 + i}" for i in range(n)],
            "Specialty": specialties,
            "TRx": rng.integers(0, 500, size=n),
            "NRx": rng.integers(0, 200, size=n),
            "Reach": rng.uniform(0.0, 1.0, size=n).round(3),
            "Engagement": rng.uniform(0.0, 5.0, size=n).round(2),
        }
    )

    # Previous period: drop ~10% of HCPs, add ~5% new, perturb metrics
    drop_idx = rng.choice(n, size=int(n * 0.1), replace=False)
    previous_base = current.drop(index=drop_idx).reset_index(drop=True)
    new_n = int(n * 0.05)
    new_rows = pd.DataFrame(
        {
            "HCP_ID": [f"P{2000 + i}" for i in range(new_n)],
            "Specialty": rng.choice(["Cardiology", "Oncology", "Neurology"], size=new_n),
            "TRx": rng.integers(0, 300, size=new_n),
            "NRx": rng.integers(0, 120, size=new_n),
            "Reach": rng.uniform(0.0, 1.0, size=new_n).round(3),
            "Engagement": rng.uniform(0.0, 5.0, size=new_n).round(2),
        }
    )
    previous = pd.concat([previous_base, new_rows], ignore_index=True)
    for col in ["TRx", "NRx"]:
        previous[col] = (previous[col] * rng.uniform(0.7, 1.3, size=len(previous))).round().astype(int)

    current_bytes = _build_messy_excel(current)
    previous_bytes = _build_messy_excel(previous)

    # 1) Flexible loader
    current_loaded = load_excel_flexible(io.BytesIO(current_bytes))
    previous_loaded = load_excel_flexible(io.BytesIO(previous_bytes))
    print(f"Loaded current: {current_loaded.shape} cols={list(current_loaded.columns)}")
    print(f"Loaded previous: {previous_loaded.shape}")

    # 2) Validate
    c_id, c_metrics, c_specialty, c_notes, c_df, _ = validate_dataframe(current_loaded)
    p_id, _, p_specialty, _, p_df, _ = validate_dataframe(previous_loaded)
    print(f"current id={c_id} metrics={c_metrics} specialty={c_specialty}")
    if c_notes:
        for n_ in c_notes:
            print("  note:", n_)

    # 3) Weights & bands
    metric_weights = [
        MetricWeight(metric="TRx", weight=40),
        MetricWeight(metric="NRx", weight=30),
        MetricWeight(metric="Reach", weight=15),
        MetricWeight(metric="Engagement", weight=15),
    ]
    bands = [
        DecileBand(name="High Value", deciles=["D8", "D9", "D10"]),
        DecileBand(name="Medium", deciles=["D4", "D5", "D6", "D7"]),
        DecileBand(name="Low", deciles=["D1", "D2", "D3"]),
    ]

    # 4) Run analysis
    payload = build_analysis_payload(
        current_df=c_df,
        id_column=c_id,
        metric_weights=metric_weights,
        bands=bands,
        specialty_column=c_specialty,
        previous_df=p_df,
        previous_id_column=p_id,
        previous_specialty_column=p_specialty,
    )

    print("\nBand summary:")
    print(payload["segment_band_summary"].to_string(index=False))
    print("\nDecile summary:")
    print(payload["decile_summary"].to_string(index=False))
    print("\nLorenz (first 10):")
    print(payload["lorenz_curve"].head(10).to_string(index=False))
    print("\nSpecialty totals:")
    print(payload["specialty_totals"].to_string(index=False))
    print("\nNew vs Lost vs Existing totals:")
    print(payload["new_vs_lost_existing"]["totals"].to_string(index=False))
    print("\nMovement counts:")
    print(payload["movement_analysis"]["Movement"].value_counts())

    # Reconciliation checks
    total_hcps = len(c_df)
    band_total = int(payload["segment_band_summary"]["# HCPs"].sum())
    decile_total = int(payload["decile_summary"]["# HCPs"].sum())
    assert band_total == total_hcps, f"Band total {band_total} != HCPs {total_hcps}"
    assert decile_total == total_hcps, f"Decile total {decile_total} != HCPs {total_hcps}"
    # Every decile D1..D10 should be present
    assigned_deciles = set(payload["decile_summary"]["Decile"].tolist())
    missing = {f"D{i}" for i in range(1, 11)} - assigned_deciles
    assert not missing, f"Missing deciles: {missing}"
    print(f"\nReconciliation OK: HCPs={total_hcps} == decile_total == band_total")

    # 5) Excel export
    excel_bytes = build_excel_output(payload)
    out_path = ROOT / "sample_output.xlsx"
    out_path.write_bytes(excel_bytes)
    print(f"\nWrote {out_path} ({len(excel_bytes):,} bytes)")


if __name__ == "__main__":
    main()
