from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from app.schemas import AnalyzeRequest, MetricWeight
from app.services.analysis_engine import build_analysis_payload
from app.services.exporter import build_excel_output
from app.services.validation import validate_dataframe


def _prompt_choice(question: str, options: List[str], default: str) -> str:
    print(f"\n{question}")
    print("Options: " + ", ".join(options))
    value = input(f"Choose [{default}]: ").strip().lower()
    if not value:
        return default
    if value not in options:
        print(f"Invalid option '{value}', using default '{default}'.")
        return default
    return value


def _prompt_yes_no(question: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    raw = input(f"\n{question} [{default_text}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def _prompt_selected_metrics(metric_columns: List[str]) -> List[str]:
    print("\nDetected metrics:")
    for metric in metric_columns:
        print(f"- {metric}")

    raw = input("\nEnter comma-separated metrics to include (blank = all): ").strip()
    if not raw:
        return metric_columns

    selected = [item.strip() for item in raw.split(",") if item.strip()]
    selected = [item for item in selected if item in metric_columns]

    if not selected:
        print("No valid metrics selected. Using all metrics.")
        return metric_columns
    return selected


def _prompt_weights(selected_metrics: List[str]) -> List[MetricWeight]:
    print("\nEnter metric weights. Total must equal 100.")

    while True:
        raw_weights: List[float] = []
        remaining = 100.0

        for idx, metric in enumerate(selected_metrics):
            metrics_left = len(selected_metrics) - idx
            suggested = round(remaining / metrics_left, 2)
            raw = input(f"Weight for {metric} [{suggested}]: ").strip()
            value = suggested if not raw else float(raw)
            raw_weights.append(value)
            remaining -= value

        total = round(sum(raw_weights), 4)
        if abs(total - 100.0) <= 1e-6:
            return [MetricWeight(metric=m, weight=w) for m, w in zip(selected_metrics, raw_weights)]

        print(f"Total weight is {total}, but must equal 100. Please re-enter weights.")


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Local no-hosting runner for pharma deciling and segmentation."
    )
    parser.add_argument("--current", required=True, help="Path to current period .xlsx")
    parser.add_argument("--previous", help="Path to previous period .xlsx (optional)")
    parser.add_argument("--output", help="Output workbook path")
    args = parser.parse_args()

    current_path = Path(args.current)
    if not current_path.exists():
        raise FileNotFoundError(f"Current file not found: {current_path}")

    current_raw = pd.read_excel(current_path, engine="openpyxl")
    id_column, metric_columns, validation_notes, current_df = validate_dataframe(current_raw)

    selected_metrics = _prompt_selected_metrics(metric_columns)
    metric_weights = _prompt_weights(selected_metrics)
    normalization = _prompt_choice("Normalization method", ["minmax", "zscore"], "minmax")
    algorithm = _prompt_choice(
        "Segmentation algorithm", ["kmeans", "hierarchical", "rule_based"], "kmeans"
    )

    n_clusters = 3
    if algorithm in {"kmeans", "hierarchical"}:
        raw_clusters = input("\nNumber of clusters [3]: ").strip()
        if raw_clusters:
            n_clusters = int(raw_clusters)
        if n_clusters < 2 or n_clusters > 8:
            print("Cluster count must be between 2 and 8. Using default 3.")
            n_clusters = 3

    previous_df = None
    previous_id_column = None

    use_previous = bool(args.previous) or _prompt_yes_no("Compare against previous period file?", default=False)
    if use_previous:
        previous_path = Path(args.previous) if args.previous else Path(input("Enter previous .xlsx path: ").strip())
        if not previous_path.exists():
            raise FileNotFoundError(f"Previous file not found: {previous_path}")
        previous_raw = pd.read_excel(previous_path, engine="openpyxl")
        previous_id_column, _, _, previous_df = validate_dataframe(previous_raw)

    _ = AnalyzeRequest(
        current_dataset_id="local-current",
        metric_weights=metric_weights,
        normalization=normalization,
        segmentation_algorithm=algorithm,
        n_clusters=n_clusters,
        previous_dataset_id="local-previous" if previous_df is not None else None,
        previous_period="previous period" if previous_df is not None else None,
        previous_algorithm=algorithm if previous_df is not None else None,
    )

    analysis_payload = build_analysis_payload(
        current_df=current_df,
        id_column=id_column,
        metric_weights=metric_weights,
        normalization=normalization,
        segmentation_algorithm=algorithm,
        n_clusters=n_clusters,
        validation_notes=validation_notes,
        previous_df=previous_df,
        previous_id_column=previous_id_column,
    )

    output_path = Path(args.output) if args.output else Path.cwd() / (
        f"client_ready_targeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )

    output_path.write_bytes(build_excel_output(analysis_payload))

    print("\nRun complete.")
    print(f"Output: {output_path}")
    print(f"Metrics used: {[m.metric for m in metric_weights]}")
    weight_map = {m.metric: m.weight for m in metric_weights}
    print(f"Weights: {weight_map}")
    print(f"Normalization: {normalization}")
    print(f"Algorithm: {algorithm}, clusters: {n_clusters}")


if __name__ == "__main__":
    run()
