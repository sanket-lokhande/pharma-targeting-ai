"""Flexible Excel input loader and basic validation.

Handles input files where:
- Data does NOT start at A1
- Blank rows or blank columns exist
- Header row needs to be auto-detected
"""
from __future__ import annotations

from typing import IO, List, Optional, Tuple, Union

import pandas as pd


_ID_HINTS = ("hcp", "npi", "id", "prescriber", "physician", "doctor", "account")
_SPECIALTY_HINTS = ("special", "segment_type", "practice")


def load_excel_flexible(
    source: Union[str, IO[bytes]],
    sheet_name: Optional[Union[str, int]] = 0,
) -> pd.DataFrame:
    """Read an .xlsx file, auto-detect the header row, drop blank rows/cols.

    The function reads the sheet with no header, finds the first row that
    contains at least 2 non-null values that look like headers (mostly strings),
    promotes it to the header, and returns a tidy DataFrame.
    """
    raw = pd.read_excel(source, sheet_name=sheet_name, header=None, engine="openpyxl")
    if isinstance(raw, dict):  # sheet_name=None
        raw = next(iter(raw.values()))

    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        raise ValueError("Uploaded file has no data")

    header_row_idx = _detect_header_row(raw)
    header_values = raw.iloc[header_row_idx].tolist()

    df = raw.iloc[header_row_idx + 1 :].copy()
    df.columns = [_clean_header(v, i) for i, v in enumerate(header_values)]
    df = df.reset_index(drop=True)

    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.loc[:, ~df.columns.duplicated()]
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _detect_header_row(raw: pd.DataFrame) -> int:
    """Return the index of the most likely header row.

    Heuristic: pick the first row where:
    - at least 2 non-null cells exist
    - majority of non-null cells are strings (not numbers)
    """
    max_scan = min(len(raw), 15)
    best_idx = 0
    best_score = -1.0
    for i in range(max_scan):
        row = raw.iloc[i]
        non_null = row.dropna()
        if len(non_null) < 2:
            continue
        string_count = sum(1 for v in non_null if isinstance(v, str) and str(v).strip() != "")
        score = string_count / max(len(non_null), 1)
        if score >= 0.6 and len(non_null) > best_score:
            best_score = float(len(non_null))
            best_idx = i
            break
    return best_idx


def _clean_header(value: object, position: int) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return f"col_{position + 1}"
    text = str(value).strip()
    return text if text else f"col_{position + 1}"


def validate_dataframe(
    df: pd.DataFrame,
) -> Tuple[str, List[str], Optional[str], List[str], pd.DataFrame, pd.DataFrame]:
    """Identify the ID column, numeric metric columns and (optional) specialty column.

    Returns:
        id_column, metric_columns, specialty_column, notes, cleaned_df, original_df

    ``original_df`` preserves the exact cell values from the uploaded file
    (after header/blank cleanup but before any numeric coercion or imputation).
    It is used as the base for the "Raw Data with Scores" output sheet so that
    the values the user sees in the export always match what they uploaded.
    """
    notes: List[str] = []
    if df.empty:
        raise ValueError("Uploaded file is empty")

    work = df.copy()
    work.columns = [str(c).strip() for c in work.columns]

    id_column = _detect_id_column(work)
    if work[id_column].isna().any():
        before = len(work)
        work = work[work[id_column].notna()].copy()
        notes.append(f"Removed {before - len(work)} rows missing the ID column '{id_column}'")

    work[id_column] = work[id_column].astype(str).str.strip()
    duplicate_count = int(work[id_column].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"Found {duplicate_count} duplicate IDs in '{id_column}'")

    # Snapshot BEFORE any coercion or imputation — this is what the user uploaded.
    original_df = work.copy()

    specialty_column = _detect_specialty_column(work, exclude={id_column})
    if specialty_column is not None:
        work[specialty_column] = (
            work[specialty_column].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
        )

    metric_columns: List[str] = []
    for col in work.columns:
        if col == id_column or col == specialty_column:
            continue
        coerced = pd.to_numeric(work[col], errors="coerce")
        non_null = coerced.notna().sum()
        if non_null >= max(3, int(0.5 * len(work))):
            work[col] = coerced.fillna(0.0)
            missing = int(coerced.isna().sum())
            if missing:
                notes.append(
                    f"Metric '{col}' had {missing} missing/non-numeric values; filled with 0"
                )
            metric_columns.append(col)

    if not metric_columns:
        raise ValueError("No numeric metric columns detected. Provide at least one numeric column.")

    return id_column, metric_columns, specialty_column, notes, work, original_df


def _detect_id_column(df: pd.DataFrame) -> str:
    for col in df.columns:
        lower = str(col).lower()
        if any(hint in lower for hint in _ID_HINTS):
            return col
    return df.columns[0]


def _detect_specialty_column(df: pd.DataFrame, exclude: set[str]) -> Optional[str]:
    for col in df.columns:
        if col in exclude:
            continue
        lower = str(col).lower()
        if any(hint in lower for hint in _SPECIALTY_HINTS):
            return col

    # Fallback: pick first low-cardinality string column
    for col in df.columns:
        if col in exclude:
            continue
        series = df[col]
        if pd.api.types.is_object_dtype(series):
            unique = series.dropna().nunique()
            if 2 <= unique <= 50 and unique < len(series) * 0.5:
                return col
    return None
