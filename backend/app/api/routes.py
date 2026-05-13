from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas import AnalyzeRequest, ConfigurationRecord, DatasetUploadResponse, SaveConfigurationRequest
from app.services.analytics import compute_scores_and_deciles
from app.services.comparison import compare_current_vs_previous
from app.services.exporter import build_excel_output
from app.services.insights import build_validation_notes, generate_insights
from app.services.segmentation import segment_hcps
from app.services.storage import store
from app.services.validation import validate_dataframe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analytics"])


def _read_excel(file: UploadFile) -> pd.DataFrame:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    try:
        # Read the file content into bytes to avoid issues with SpooledTemporaryFile
        file_contents = file.file.read()
        import io
        return pd.read_excel(io.BytesIO(file_contents), engine="openpyxl")
    except Exception as exc:
        logger.error(f"Failed to read Excel file: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {exc}") from exc


@router.post("/upload/current", response_model=DatasetUploadResponse)
async def upload_current(file: UploadFile = File(...)) -> DatasetUploadResponse:
    try:
        logger.info(f"Received upload request: filename={file.filename}, content_type={file.content_type}")
        if not file.filename:
            logger.error("File has no filename")
            raise HTTPException(status_code=400, detail="File has no filename")
        df = _read_excel(file)
        id_column, metric_columns, notes, validated_df = validate_dataframe(df)

        dataset_id = store.put_dataset(
            "current",
            validated_df,
            file.filename or "current.xlsx",
            id_column,
            metric_columns,
            notes,
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            row_count=len(validated_df),
            id_column=id_column,
            metric_columns=metric_columns,
            validation_notes=notes,
            data_preview=validated_df.head(10).to_dict(orient="records"),
        )
    except Exception as exc:
        logger.error(f"Unhandled error in upload_current: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload/previous", response_model=DatasetUploadResponse)
async def upload_previous(file: UploadFile = File(...)) -> DatasetUploadResponse:
    try:
        logger.info(f"Received upload request for previous: filename={file.filename}, content_type={file.content_type}")
        if not file.filename:
            logger.error("File has no filename")
            raise HTTPException(status_code=400, detail="File has no filename")
        df = _read_excel(file)
        id_column, metric_columns, notes, validated_df = validate_dataframe(df)

        dataset_id = store.put_dataset(
            "previous",
            validated_df,
            file.filename or "previous.xlsx",
            id_column,
            metric_columns,
            notes,
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            row_count=len(validated_df),
            id_column=id_column,
            metric_columns=metric_columns,
            validation_notes=notes,
            data_preview=validated_df.head(10).to_dict(orient="records"),
        )
    except Exception as exc:
        logger.error(f"Unhandled error in upload_previous: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agent/questionnaire/{dataset_id}")
async def get_agent_questionnaire(dataset_id: str) -> Dict[str, Any]:
    """Return guided questions that a Copilot agent can ask before running analysis."""
    try:
        dataset = store.get_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    metric_columns = dataset.metric_columns
    metric_count = len(metric_columns)
    default_weight = round(100.0 / metric_count, 2) if metric_count else 0.0

    return {
        "dataset_id": dataset_id,
        "source_filename": dataset.source_filename,
        "id_column": dataset.id_column,
        "metric_columns": metric_columns,
        "recommended_defaults": {
            "normalization": "minmax",
            "segmentation_algorithm": "kmeans",
            "n_clusters": 3,
            "metric_weights": [
                {"metric": metric, "weight": default_weight} for metric in metric_columns
            ],
        },
        "questions": [
            {
                "id": "selected_metrics",
                "prompt": "Which metrics should be included in scoring?",
                "type": "multi_select",
                "required": True,
                "options": metric_columns,
            },
            {
                "id": "metric_weights",
                "prompt": "What weight should each selected metric have? Total must equal 100.",
                "type": "weighted_list",
                "required": True,
            },
            {
                "id": "normalization",
                "prompt": "Which normalization method should be used?",
                "type": "single_select",
                "required": True,
                "options": ["minmax", "zscore"],
            },
            {
                "id": "segmentation_algorithm",
                "prompt": "Which segmentation algorithm should be used?",
                "type": "single_select",
                "required": True,
                "options": ["kmeans", "hierarchical", "rule_based"],
            },
            {
                "id": "n_clusters",
                "prompt": "How many clusters should be created (2-8)?",
                "type": "number",
                "required": False,
                "default": 3,
                "min": 2,
                "max": 8,
            },
            {
                "id": "compare_previous",
                "prompt": "Do you also want to compare this to a previous period file?",
                "type": "boolean",
                "required": False,
                "default": False,
            },
        ],
    }


def _run_analysis(request: AnalyzeRequest) -> Dict[str, Any]:
    current_record = store.get_dataset(request.current_dataset_id)
    current_df = current_record.dataframe
    id_column = current_record.id_column

    scored_df, corr_matrix, driver_strength, lorenz_curve, distributions, metric_summary = compute_scores_and_deciles(
        df=current_df,
        id_column=id_column,
        metric_weights=request.metric_weights,
        normalization=request.normalization,
    )

    metrics = [item.metric for item in request.metric_weights]
    segmented_df, explainability, segment_labels = segment_hcps(
        scored_df=scored_df,
        feature_columns=metrics + ["composite_score"],
        algorithm=request.segmentation_algorithm,
        n_clusters=request.n_clusters,
    )

    insight_payload = generate_insights(segmented_df, request.metric_weights, driver_strength)
    validation_notes = build_validation_notes(current_record.validation_notes, segmented_df)

    comparison_payload: Dict[str, Any] = {
        "movement_analysis": [],
        "new_vs_missing": {},
        "segment_shift_analysis": [],
        "comparison_summary": {},
        "comparison_context": {},
    }

    if request.previous_dataset_id:
        previous_record = store.get_dataset(request.previous_dataset_id)
        prev_df = previous_record.dataframe.copy()
        prev_id_column = previous_record.id_column
        if prev_id_column != id_column:
            prev_df = prev_df.rename(columns={prev_id_column: id_column})

        prev_scored, _, _, _, _, _ = compute_scores_and_deciles(
            df=prev_df,
            id_column=id_column,
            metric_weights=request.metric_weights,
            normalization=request.normalization,
        )
        prev_segmented, _, _ = segment_hcps(
            scored_df=prev_scored,
            feature_columns=metrics + ["composite_score"],
            algorithm=request.segmentation_algorithm,
            n_clusters=request.n_clusters,
        )

        comparison_payload = compare_current_vs_previous(
            current_df=segmented_df,
            previous_df=prev_segmented,
            id_column=id_column,
        )
        comparison_payload["comparison_context"] = {
            "previous_period": request.previous_period,
            "previous_algorithm": request.previous_algorithm,
        }

    response_payload: Dict[str, Any] = {
        "raw_with_scores": segmented_df.to_dict(orient="records"),
        "segmentation_results": segmented_df[[id_column, "composite_score", "decile", "segment_label"]].to_dict(
            orient="records"
        ),
        "correlation_matrix": corr_matrix.to_dict(),
        "lorenz_curve": lorenz_curve,
        "distributions": distributions,
        "metric_summary": metric_summary,
        "segment_explainability": explainability,
        "segment_labels": segment_labels,
        "validation_notes": validation_notes,
        **insight_payload,
        **comparison_payload,
    }

    analysis_id = store.put_analysis(response_payload)
    response_payload["analysis_id"] = analysis_id
    return response_payload


@router.post("/analyze")
async def analyze(request: AnalyzeRequest) -> Dict[str, Any]:
    try:
        return _run_analysis(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agent/analyze-and-export")
async def analyze_and_export(request: AnalyzeRequest) -> Dict[str, Any]:
    """Run full analysis and return an export URL for agent experiences."""
    try:
        result = _run_analysis(request)
        analysis_id = result["analysis_id"]
        return {
            "analysis_id": analysis_id,
            "export_url": f"/api/export/{analysis_id}",
            "summary_insights": result.get("summary_insights", []),
            "recommendations": result.get("recommendations", []),
            "validation_notes": result.get("validation_notes", []),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export/{analysis_id}")
async def export_analysis(analysis_id: str) -> StreamingResponse:
    try:
        analysis_payload = store.get_analysis(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    binary = build_excel_output(analysis_payload)

    return StreamingResponse(
        iter([binary]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=pharma_analytics_{analysis_id}.xlsx"},
    )


@router.post("/configurations")
async def save_configuration(request: SaveConfigurationRequest) -> Dict[str, str]:
    record = ConfigurationRecord(**request.model_dump())
    store.put_configuration(record.model_dump())
    return {"status": "saved", "name": request.name}


@router.get("/configurations")
async def list_configurations() -> List[Dict[str, Any]]:
    return list(store.list_configurations().values())
