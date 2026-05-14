from __future__ import annotations

from io import BytesIO
from typing import Dict

import pandas as pd
from openpyxl.chart import LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

START_ROW = 1  # Excel row 2
START_COL = 1  # Excel column B


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


def _write_df(
    writer: object,
    sheet_name: str,
    df: pd.DataFrame,
    index: bool = False,
) -> Worksheet:
    df.to_excel(
        writer,
        sheet_name=sheet_name,
        index=index,
        startrow=START_ROW,
        startcol=START_COL,
    )
    return writer.sheets[sheet_name]


def _auto_fit_columns(ws: Worksheet, min_col: int = 2, max_width: int = 48) -> None:
    for col_idx in range(min_col, ws.max_column + 1):
        max_len = 0
        for row_idx in range(1, ws.max_row + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value is None:
                continue
            max_len = max(max_len, len(str(value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 10), max_width)


def _format_sheet(ws: Worksheet, header_rows: int = 1) -> None:
    if ws.max_row < 2 or ws.max_column < 2:
        ws.sheet_view.showGridLines = False
        return

    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    alt_fill = PatternFill(fill_type="solid", fgColor="ECF3FA")
    body_border = Border(
        left=Side(style="thin", color="B7C7D9"),
        right=Side(style="thin", color="B7C7D9"),
        top=Side(style="thin", color="B7C7D9"),
        bottom=Side(style="thin", color="B7C7D9"),
    )

    header_start = START_ROW + 1
    header_end = header_start + header_rows - 1

    for row in range(header_start, header_end + 1):
        for col in range(START_COL + 1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = body_border

    for row in range(header_end + 1, ws.max_row + 1):
        if (row - header_end) % 2 == 0:
            for col in range(START_COL + 1, ws.max_column + 1):
                ws.cell(row=row, column=col).fill = alt_fill
        for col in range(START_COL + 1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = body_border

    ws.freeze_panes = "B3" if header_rows == 1 else "B4"
    ws.auto_filter.ref = f"B{header_start}:{get_column_letter(ws.max_column)}{ws.max_row}"
    ws.sheet_view.showGridLines = False
    _auto_fit_columns(ws)


def _build_correlation_matrix_df(raw: object) -> pd.DataFrame:
    if isinstance(raw, pd.DataFrame):
        corr = raw.copy()
    elif isinstance(raw, dict):
        corr = pd.DataFrame(raw)
    else:
        return pd.DataFrame()

    cols = list(corr.columns)
    corr = corr.reindex(index=cols)
    corr = corr.abs() * 100
    corr = corr.round(1)
    corr.index.name = "Metric"
    return corr


def _build_new_vs_missing_df(raw: object, comparison_summary: object) -> pd.DataFrame:
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
            ("# New HCPs", "Low decile"),
            ("# HCPs lost", "Total lost HCPs"),
            ("# HCPs lost", "High decile"),
            ("# HCPs lost", "Low decile"),
            ("Existing HCPs moved to", "High decile from low decile"),
            ("Existing HCPs moved to", "Low decile from high decile"),
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
    result = pd.DataFrame(values, columns=columns)
    result.index = [""]
    return result


def _build_lorenz_by_decile_df(raw_with_scores: object) -> pd.DataFrame:
    df = _to_dataframe(raw_with_scores)
    if df.empty or "decile" not in df.columns or "composite_score" not in df.columns:
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

    total_prescribers = grouped["prescribers"].sum() or 1
    total_potential = grouped["potential"].sum() or 1

    grouped["cumulative_prescribers_pct"] = grouped["cumulative_prescribers"] / total_prescribers * 100
    grouped["cumulative_potential_pct"] = grouped["cumulative_potential"] / total_potential * 100

    lorenz = pd.DataFrame(
        {
            "Decile": grouped["decile_num"].astype(int).map(lambda d: f"D{d}"),
            "# of Prescribers": grouped["prescribers"],
            "Cumulative # of Prescribers": grouped["cumulative_prescribers"],
            "Cumulative % of Prescribers": grouped["cumulative_prescribers_pct"].round(1),
            "Cumulative % of Potential": grouped["cumulative_potential_pct"].round(1),
        }
    )

    start_row = pd.DataFrame(
        [{
            "Decile": "Start",
            "# of Prescribers": 0,
            "Cumulative # of Prescribers": 0,
            "Cumulative % of Prescribers": 0.0,
            "Cumulative % of Potential": 0.0,
        }]
    )
    return pd.concat([start_row, lorenz], ignore_index=True)


def _build_decile_hcp_summary(raw_with_scores: object) -> pd.DataFrame:
    df = _to_dataframe(raw_with_scores)
    if df.empty or "decile" not in df.columns:
        return pd.DataFrame()

    decile_nums = (
        df["decile"].astype(str).str.replace("D", "", regex=False).astype(int)
    )
    series = decile_nums.value_counts().sort_index(ascending=False)
    counts = pd.DataFrame({
        "Decile": [f"D{int(d)}" for d in series.index],
        "# HCPs": series.values,
    })
    return counts


def _apply_correlation_formatting(ws: Worksheet) -> None:
    # Data area for index=True write at B2:
    # index names in B3:B..., values in C3:...
    if ws.max_row < 3 or ws.max_column < 3:
        return

    value_start_col = START_COL + 2
    value_start_row = START_ROW + 2
    value_end_col = ws.max_column
    value_end_row = ws.max_row

    value_range = f"{get_column_letter(value_start_col)}{value_start_row}:{get_column_letter(value_end_col)}{value_end_row}"

    ws.conditional_formatting.add(
        value_range,
        ColorScaleRule(
            start_type="num",
            start_value=0,
            start_color="F8696B",
            mid_type="num",
            mid_value=0.5,
            mid_color="FFEB84",
            end_type="num",
            end_value=1,
            end_color="63BE7B",
        ),
    )

    for row in range(value_start_row, value_end_row + 1):
        for col in range(value_start_col, value_end_col + 1):
            ws.cell(row=row, column=col).number_format = "0.0%"
            current_value = ws.cell(row=row, column=col).value
            if isinstance(current_value, (int, float)):
                ws.cell(row=row, column=col).value = float(current_value) / 100.0


def _add_lorenz_chart(ws: Worksheet, row_count: int) -> None:
    if row_count <= 1:
        return

    chart = LineChart()
    chart.title = "Cumulative % of Potential"
    chart.style = 10
    chart.height = 9
    chart.width = 16
    chart.y_axis.title = "Cum. % of Potential"
    chart.x_axis.title = "Cum. % of Prescribers"

    # Table starts at B2. Header row is 2. Data starts row 3.
    x_col = START_COL + 4  # E: cumulative % prescribers
    y_col = START_COL + 5  # F: cumulative % potential
    start_data_row = START_ROW + 2
    end_data_row = START_ROW + 1 + row_count

    data = Reference(ws, min_col=y_col, min_row=START_ROW + 1, max_row=end_data_row)
    categories = Reference(ws, min_col=x_col, min_row=start_data_row, max_row=end_data_row)

    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)

    ws.add_chart(chart, "H3")


def build_excel_output(analysis_payload: Dict[str, object]) -> bytes:
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _write_df(writer, "Raw Data with Scores", _to_dataframe(analysis_payload.get("raw_with_scores", [])), index=False)
        _write_df(
            writer,
            "Segmentation Results",
            _to_dataframe(analysis_payload.get("segmentation_results", [])),
            index=False,
        )
        _write_df(
            writer,
            "Decile HCP Summary",
            _build_decile_hcp_summary(analysis_payload.get("raw_with_scores", [])),
            index=False,
        )
        _write_df(
            writer,
            "Segment Band Summary",
            _to_dataframe(analysis_payload.get("segment_band_summary", [])),
            index=False,
        )
        _write_df(
            writer,
            "Decile Specialty Summary",
            _to_dataframe(analysis_payload.get("decile_specialty_summary", [])),
            index=False,
        )

        corr_ws = _write_df(
            writer,
            "Correlation Matrix",
            _build_correlation_matrix_df(analysis_payload.get("correlation_matrix", {})),
            index=True,
        )

        _write_df(
            writer,
            "Movement Analysis",
            _to_dataframe(analysis_payload.get("movement_analysis", [])),
            index=False,
        )

        new_missing_df = _build_new_vs_missing_df(
            analysis_payload.get("new_vs_missing", {}),
            analysis_payload.get("comparison_summary", {}),
        )
        _write_df(writer, "New vs Missing HCPs", new_missing_df, index=True)

        _write_df(
            writer,
            "Summary Insights",
            _to_dataframe({"summary_insights": analysis_payload.get("summary_insights", [])}),
            index=False,
        )
        _write_df(
            writer,
            "Recommendations",
            _to_dataframe({"recommendations": analysis_payload.get("recommendations", [])}),
            index=False,
        )
        _write_df(
            writer,
            "Validation Notes",
            _to_dataframe({"validation_notes": analysis_payload.get("validation_notes", [])}),
            index=False,
        )

        lorenz_df = _build_lorenz_by_decile_df(analysis_payload.get("raw_with_scores", []))
        lorenz_ws = _write_df(writer, "Lorenz Curve", lorenz_df, index=False)

        for sheet in writer.book.worksheets:
            header_rows = 2 if sheet.title == "New vs Missing HCPs" else 1
            _format_sheet(sheet, header_rows=header_rows)

        _apply_correlation_formatting(corr_ws)
        if not lorenz_df.empty:
            _add_lorenz_chart(lorenz_ws, row_count=len(lorenz_df))

    buffer.seek(0)
    return buffer.getvalue()
