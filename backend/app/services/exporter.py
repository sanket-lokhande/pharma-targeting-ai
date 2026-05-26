"""Standardized Excel output.

Conventions for every sheet:
- Title in cell B2 (same as the sheet name)
- Data starts at B4 (header row at B4, data rows from B5)
- Auto-fit column widths
- Clean formatting, gridlines hidden

No insights / recommendations / validation / correlation sheets.
Lorenz Curve sheet contains data only (no chart) and highlights the row
where Cumulative % of Potential first reaches 80%.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


TITLE_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
TITLE_FONT = Font(color="FFFFFF", bold=True, size=14)
HEADER_FILL = PatternFill(fill_type="solid", fgColor="2E75B6")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
ALT_FILL = PatternFill(fill_type="solid", fgColor="ECF3FA")
HIGHLIGHT_FILL = PatternFill(fill_type="solid", fgColor="FFEB84")

THIN_SIDE = Side(style="thin", color="B7C7D9")
BODY_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)


def build_excel_output(payload: Dict[str, Any]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)

    _write_sheet(wb, "Raw Data with Scores", _coerce_df(payload.get("raw_with_scores")))
    _write_sheet(wb, "Decile Summary", _coerce_df(payload.get("decile_summary")))
    _write_sheet(wb, "Segment Band Summary", _coerce_df(payload.get("segment_band_summary")))
    _write_sheet(wb, "Cluster Profile", _coerce_df(payload.get("cluster_profile")))
    _write_sheet(wb, "Cluster Heatmap Matrix", _coerce_df(payload.get("cluster_heatmap")))

    specialty_count = _coerce_df(payload.get("specialty_decile_count"))
    specialty_pct = _coerce_df(payload.get("specialty_decile_pct"))
    if not specialty_count.empty:
        _write_sheet(wb, "Specialty x Decile (Count)", specialty_count)
    if not specialty_pct.empty:
        _write_sheet(wb, "Specialty x Decile (%)", specialty_pct, percent_columns="auto")

    specialty_totals_df = _coerce_df(payload.get("specialty_totals"))
    if not specialty_totals_df.empty:
        _write_sheet(wb, "Specialty Totals", specialty_totals_df)

    lorenz_df = _coerce_df(payload.get("lorenz_curve"))
    if not lorenz_df.empty:
        _write_lorenz_sheet(wb, "Lorenz Curve", lorenz_df)

    if payload.get("has_previous"):
        movement = _coerce_df(payload.get("movement_analysis"))
        if not movement.empty:
            _write_sheet(wb, "Movement Analysis", movement)

        nle = payload.get("new_vs_lost_existing") or {}
        totals = _coerce_df(nle.get("totals"))
        if not totals.empty:
            _write_sheet(wb, "New vs Lost vs Existing", totals)

        new_by_band = _coerce_df(nle.get("new_hcps_by_band"))
        if not new_by_band.empty:
            _write_sheet(wb, "NEW HCPs by Band", new_by_band)

        lost_by_band = _coerce_df(nle.get("lost_hcps_by_band"))
        if not lost_by_band.empty:
            _write_sheet(wb, "LOST HCPs by Band", lost_by_band)

        existing_summary = _coerce_df(nle.get("existing_movement_summary"))
        if not existing_summary.empty:
            _write_sheet(wb, "Existing HCPs Movement", existing_summary)

        existing_detail = _coerce_df(nle.get("existing_movement_detail"))
        if not existing_detail.empty:
            _write_sheet(wb, "Existing Movement Detail", existing_detail)

        change_table = _coerce_df(payload.get("segment_band_change"))
        if not change_table.empty:
            _write_sheet(wb, "Segment Band Change", change_table)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _coerce_df(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame([value])
    return pd.DataFrame()


def _safe_sheet_name(name: str) -> str:
    invalid = '[]:*?/\\'
    cleaned = "".join("_" if c in invalid else c for c in name)
    return cleaned[:31] or "Sheet"


def _write_sheet(
    wb: Workbook,
    title: str,
    df: pd.DataFrame,
    percent_columns: Optional[Any] = None,
) -> Worksheet:
    sheet_name = _safe_sheet_name(title)
    ws = wb.create_sheet(title=sheet_name)
    ws.sheet_view.showGridLines = False

    # Title in B2
    ws.cell(row=2, column=2, value=title)
    title_cell = ws.cell(row=2, column=2)
    title_cell.font = TITLE_FONT
    title_cell.fill = TITLE_FILL
    title_cell.alignment = Alignment(horizontal="left", vertical="center")

    if df.empty:
        ws.cell(row=4, column=2, value="No data available")
        ws.column_dimensions["B"].width = 30
        return ws

    columns = list(df.columns)

    # Header at row 4 starting at column B
    for idx, col_name in enumerate(columns):
        cell = ws.cell(row=4, column=2 + idx, value=str(col_name))
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BODY_BORDER

    # Data rows from row 5
    for row_offset, (_, row) in enumerate(df.iterrows(), start=5):
        for col_offset, col_name in enumerate(columns):
            value = row[col_name]
            if pd.isna(value):
                value = None
            elif hasattr(value, "item"):
                try:
                    value = value.item()
                except Exception:
                    pass
            cell = ws.cell(row=row_offset, column=2 + col_offset, value=value)
            cell.border = BODY_BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center")
            if (row_offset - 5) % 2 == 1:
                cell.fill = ALT_FILL

    last_row = 4 + len(df)
    last_col = 1 + len(columns)

    # Apply percent format
    pct_cols: list[int] = []
    if percent_columns == "auto":
        pct_cols = list(range(2, last_col + 1))
    elif isinstance(percent_columns, (list, tuple)):
        for name in percent_columns:
            if name in columns:
                pct_cols.append(2 + columns.index(name))

    for col_idx in pct_cols:
        for r in range(5, last_row + 1):
            ws.cell(row=r, column=col_idx).number_format = "0.00\"%\""

    # Auto-detect "%" column names and format as percent text
    for idx, col_name in enumerate(columns):
        lname = str(col_name).lower()
        if "%" in lname and (2 + idx) not in pct_cols:
            for r in range(5, last_row + 1):
                ws.cell(row=r, column=2 + idx).number_format = "0.00\"%\""

    _auto_fit_columns(ws, min_col=2, max_col=last_col)
    ws.freeze_panes = ws.cell(row=5, column=2).coordinate
    return ws


def _write_lorenz_sheet(wb: Workbook, title: str, df: pd.DataFrame) -> Worksheet:
    """Lorenz sheet: data only, highlight first row where Cum % Potential >= 80%."""
    ws = _write_sheet(wb, title, df, percent_columns="auto")
    if df.empty:
        return ws

    if "Cumulative % of Potential" not in df.columns:
        return ws

    col_index = 2 + list(df.columns).index("Cumulative % of Potential")
    highlight_idx = None
    for idx, value in enumerate(df["Cumulative % of Potential"].tolist()):
        try:
            if float(value) >= 80.0:
                highlight_idx = idx
                break
        except (TypeError, ValueError):
            continue

    if highlight_idx is not None:
        row = 5 + highlight_idx
        for col_offset in range(len(df.columns)):
            cell = ws.cell(row=row, column=2 + col_offset)
            cell.fill = HIGHLIGHT_FILL
            cell.font = Font(bold=True)

    # Override the 80% target cell formatting
    _ = col_index  # keep for clarity
    return ws


def _auto_fit_columns(ws: Worksheet, min_col: int, max_col: int, max_width: int = 50) -> None:
    for col_idx in range(min_col, max_col + 1):
        max_len = 0
        for row_idx in range(2, ws.max_row + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value is None:
                continue
            text_len = len(str(value))
            if text_len > max_len:
                max_len = text_len
        width = min(max(max_len + 2, 12), max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
