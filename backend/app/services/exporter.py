from __future__ import annotations

from io import BytesIO
from typing import Dict, List

import pandas as pd
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


def _to_dataframe(payload: object) -> pd.DataFrame:
    if isinstance(payload, pd.DataFrame):
        return payload
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        if all(isinstance(v, (list, tuple)) for v in payload.values()):
            return pd.DataFrame(payload)
        return pd.DataFrame([payload])
    return pd.DataFrame()


def _auto_fit_columns(ws: Worksheet, max_width: int = 48) -> None:
    for idx, column_cells in enumerate(ws.columns, start=1):
        max_len = 0
        for cell in column_cells:
            if cell.value is None:
                continue
            cell_len = len(str(cell.value))
            if cell_len > max_len:
                max_len = cell_len
        ws.column_dimensions[get_column_letter(idx)].width = min(max(max_len + 2, 10), max_width)


def _format_sheet(ws: Worksheet) -> None:
    if ws.max_row < 1 or ws.max_column < 1:
        return

    header_rows = 2 if ws.title == "New vs Missing HCPs" else 1

    header_fill = PatternFill(fill_type="solid", fgColor="4472C4")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    alt_fill = PatternFill(fill_type="solid", fgColor="D9E8F5")
    border = Border(
        left=Side(style="thin", color="B4C7E7"),
        right=Side(style="thin", color="B4C7E7"),
        top=Side(style="thin", color="B4C7E7"),
        bottom=Side(style="thin", color="B4C7E7"),
    )

    for header_row in range(1, header_rows + 1):
        for header_cell in ws[header_row]:
            header_cell.fill = header_fill
            header_cell.font = header_font
            header_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            header_cell.border = border

    for row in range(header_rows + 1, ws.max_row + 1):
        if row % 2 == 0:
            for col in range(1, ws.max_column + 1):
                ws.cell(row=row, column=col).fill = alt_fill
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            cell.alignment = Alignment(vertical="top", wrap_text=False, horizontal="center")
            cell.border = border

    ws.freeze_panes = "A3" if header_rows == 2 else "A2"
    if ws.max_row > 1 and ws.max_column > 0:
        ws.auto_filter.ref = ws.dimensions
    _auto_fit_columns(ws)


def _build_correlation_matrix_df(raw: object) -> pd.DataFrame:
    """Reconstruct a proper N×N correlation matrix DataFrame from a dict-of-dicts."""
    if isinstance(raw, pd.DataFrame):
        return raw
    if isinstance(raw, dict):
        df = pd.DataFrame(raw)
        # ensure row order matches column order
        cols = list(df.columns)
        df = df.reindex(index=cols)
        df.index.name = "Metric"
        return df.round(3)
    return pd.DataFrame()


def _build_new_vs_missing_df(raw: object, comparison_summary: object) -> pd.DataFrame:
    """Build grouped summary table matching expected New vs Missing HCP layout."""
    if not isinstance(raw, dict) or not raw:
        return pd.DataFrame()

    new_hcps = raw.get("new_hcps", [])
    missing_hcps = raw.get("missing_hcps", [])
    new_top_tier = raw.get("new_top_tier_count", 0)
    new_low_tier = raw.get("new_low_tier_count", 0)
    lost_high_value = raw.get("lost_high_value_hcps", [])

    movement = comparison_summary if isinstance(comparison_summary, dict) else {}
    high_to_low = movement.get("high_to_low", 0)
    low_to_high = movement.get("low_to_high", 0)

    columns = pd.MultiIndex.from_tuples(
        [
            ("# New HCPs", "Total new HCPs"),
            ("# New HCPs", "High decile"),
            ("# New HCPs", "Low Decile"),
            ("# HCPs lost", "Total lost HCPs"),
            ("# HCPs lost", "High decile"),
            ("# HCPs lost", "Low Decile"),
            ("Existing HCPs moved to", "High decile from low decile"),
            ("Existing HCPs moved to", "Low decile from High decile"),
        ]
    )

    values = [[
        len(new_hcps),
        new_top_tier,
        new_low_tier,
        len(missing_hcps),
        len(lost_high_value),
        max(len(missing_hcps) - len(lost_high_value), 0),
        low_to_high,
        high_to_low,
    ]]
    df = pd.DataFrame(values, columns=columns)
    # Keep index column blank so pandas can write MultiIndex headers without errors.
    df.index = [""]
    return df


def _build_lorenz_by_decile_df(raw_with_scores: object) -> pd.DataFrame:
    if isinstance(raw_with_scores, pd.DataFrame):
        df = raw_with_scores.copy()
    elif isinstance(raw_with_scores, list):
        df = pd.DataFrame(raw_with_scores)
    else:
        return pd.DataFrame()

    if "decile" not in df.columns or "composite_score" not in df.columns:
        return pd.DataFrame()

    work = df[["decile", "composite_score"]].copy()
    work["decile_num"] = work["decile"].astype(str).str.replace("D", "", regex=False).astype(int)

    grouped = (
        work.groupby("decile_num", as_index=False)
        .agg(prescribers=("composite_score", "count"), potential=("composite_score", "sum"))
        .sort_values("decile_num", ascending=False)
        .reset_index(drop=True)
    )

    grouped["cumulative_prescribers"] = grouped["prescribers"].cumsum()
    grouped["cumulative_potential"] = grouped["potential"].cumsum()

    total_prescribers = grouped["prescribers"].sum()
    total_potential = grouped["potential"].sum()

    grouped["cumulative_prescribers_pct"] = (
        grouped["cumulative_prescribers"] / total_prescribers * 100 if total_prescribers else 0
    )
    grouped["cumulative_potential_pct"] = (
        grouped["cumulative_potential"] / total_potential * 100 if total_potential else 0
    )

    result = pd.DataFrame(
        {
            "Decile": grouped["decile_num"],
            "# of Prescribers": grouped["prescribers"],
            "Cumulative # of Prescribers": grouped["cumulative_prescribers"],
            "Cumulative % of Prescribers": grouped["cumulative_prescribers_pct"].round(1),
            "Cumulative % of Potential": grouped["cumulative_potential_pct"].round(1),
        }
    )
    return result


def build_excel_output(analysis_payload: Dict[str, object]) -> bytes:
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _to_dataframe(analysis_payload["raw_with_scores"]).to_excel(
            writer, sheet_name="Raw Data with Scores", index=False
        )
        _to_dataframe(analysis_payload["segmentation_results"]).to_excel(
            writer, sheet_name="Segmentation Results", index=False
        )
        _build_correlation_matrix_df(analysis_payload["correlation_matrix"]).to_excel(
            writer, sheet_name="Correlation Matrix", index=True
        )
        _to_dataframe(analysis_payload.get("movement_analysis", [])).to_excel(
            writer, sheet_name="Movement Analysis", index=False
        )
        _build_new_vs_missing_df(
            analysis_payload.get("new_vs_missing", {}),
            analysis_payload.get("comparison_summary", {}),
        ).to_excel(writer, sheet_name="New vs Missing HCPs", index=True)
        _to_dataframe({"summary_insights": analysis_payload["summary_insights"]}).to_excel(
            writer, sheet_name="Summary Insights", index=False
        )
        _to_dataframe({"recommendations": analysis_payload["recommendations"]}).to_excel(
            writer, sheet_name="Recommendations", index=False
        )
        _to_dataframe({"validation_notes": analysis_payload["validation_notes"]}).to_excel(
            writer, sheet_name="Validation Notes", index=False
        )

        # Add Lorenz curve sheet by decile using raw scores.
        _add_lorenz_curve_sheet(writer, analysis_payload.get("raw_with_scores", []))

        for sheet in writer.book.worksheets:
            _format_sheet(sheet)

    buffer.seek(0)
    return buffer.getvalue()


def _add_lorenz_curve_sheet(writer: object, raw_with_scores: object) -> None:
    """Add Lorenz curve sheet based on deciles with chart and table."""
    curve_df = _build_lorenz_by_decile_df(raw_with_scores)
    if curve_df.empty:
        return

    curve_df.to_excel(writer, sheet_name="Lorenz Curve", index=False)
    ws = writer.sheets["Lorenz Curve"]

    chart = LineChart()
    chart.title = "HCP Lorenz Curve by Decile"
    chart.x_axis.title = "Cumulative % of Prescribers"
    chart.y_axis.title = "Cumulative % Score"
    chart.height = 10
    chart.width = 18

    data = Reference(ws, min_col=5, min_row=1, max_row=len(curve_df) + 1)
    categories = Reference(ws, min_col=4, min_row=2, max_row=len(curve_df) + 1)

    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    chart.style = 12

    ws.add_chart(chart, "D2")
