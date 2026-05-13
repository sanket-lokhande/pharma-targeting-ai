from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def validate_dataframe(df: pd.DataFrame) -> Tuple[str, List[str], List[str], pd.DataFrame]:
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"DataFrame shape: {df.shape}, columns: {list(df.columns)}")
    
    if df.empty:
        raise ValueError("Uploaded file is empty")

    id_column = df.columns[0]
    notes: List[str] = []

    if df[id_column].isna().any():
        raise ValueError(f"ID column '{id_column}' contains empty values")

    duplicate_count = int(df[id_column].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"Found {duplicate_count} duplicate IDs in '{id_column}'")

    metric_columns = [col for col in df.columns[1:]]
    if not metric_columns:
        raise ValueError("At least one metric column is required")

    converted_df = df.copy()
    for col in metric_columns:
        converted_df[col] = pd.to_numeric(converted_df[col], errors="coerce")
        missing_after_conversion = int(converted_df[col].isna().sum())
        if missing_after_conversion:
            notes.append(
                f"Metric '{col}' has {missing_after_conversion} non-numeric or missing values; filled with median"
            )
            converted_df[col] = converted_df[col].fillna(converted_df[col].median())

    if converted_df[metric_columns].isna().any().any():
        converted_df[metric_columns] = converted_df[metric_columns].fillna(0)
        notes.append("Some metric values could not be imputed with median; fallback value 0 used")

    outlier_notes = detect_outliers(converted_df, metric_columns)
    notes.extend(outlier_notes)

    return id_column, metric_columns, notes, converted_df


def detect_outliers(df: pd.DataFrame, metric_columns: List[str]) -> List[str]:
    notes: List[str] = []
    for col in metric_columns:
        series = df[col]
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)
        outlier_count = int(((series < lower_bound) | (series > upper_bound)).sum())
        if outlier_count:
            pct = np.round((outlier_count / len(df)) * 100, 2)
            notes.append(f"Metric '{col}' has {outlier_count} outliers ({pct}%) by IQR rule")
    return notes
