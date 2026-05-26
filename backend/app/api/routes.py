from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas import (
    AnalyzeRequest,
    ConfigurationRecord,
    DatasetUploadResponse,
    SaveConfigurationRequest,
)
from app.services.analysis_engine import build_analysis_payload
from app.services.exporter import build_excel_output
from app.services.storage import store
from app.services.validation import load_excel_flexible, validate_dataframe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["hcp-targeting"])


def _read_uploaded_excel(file: UploadFile) -> pd.DataFrame:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")
    try:
        contents = file.file.read()
        return load_excel_flexible(io.BytesIO(contents))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read Excel: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to read Excel: {exc}") from exc


def _upload_dataset(dataset_type: str, file: UploadFile) -> DatasetUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File has no filename")
    df = _read_uploaded_excel(file)
    try:
        id_column, metric_columns, specialty_column, notes, validated_df = validate_dataframe(df)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dataset_id = store.put_dataset(
        dataset_type=dataset_type,
        dataframe=validated_df,
        source_filename=file.filename,
        id_column=id_column,
        metric_columns=metric_columns,
        validation_notes=notes,
        specialty_column=specialty_column,
    )
    return DatasetUploadResponse(
        dataset_id=dataset_id,
        row_count=len(validated_df),
        id_column=id_column,
        metric_columns=metric_columns,
        specialty_column=specialty_column,
        validation_notes=notes,
        data_preview=validated_df.head(10).to_dict(orient="records"),
    )


@router.post("/upload/current", response_model=DatasetUploadResponse)
async def upload_current(file: UploadFile = File(...)) -> DatasetUploadResponse:
    return _upload_dataset("current", file)


@router.post("/upload/previous", response_model=DatasetUploadResponse)
async def upload_previous(file: UploadFile = File(...)) -> DatasetUploadResponse:
    return _upload_dataset("previous", file)


def _serialize(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


def _run_analysis(request: AnalyzeRequest) -> Dict[str, Any]:
    current_record = store.get_dataset(request.current_dataset_id)
    previous_record = (
        store.get_dataset(request.previous_dataset_id) if request.previous_dataset_id else None
    )

    payload = build_analysis_payload(
        current_df=current_record.dataframe,
        id_column=current_record.id_column,
        metric_weights=request.metric_weights,
        bands=request.bands,
        specialty_column=current_record.specialty_column,
        previous_df=previous_record.dataframe if previous_record else None,
        previous_id_column=previous_record.id_column if previous_record else None,
        previous_specialty_column=previous_record.specialty_column if previous_record else None,
    )

    serializable = {k: _serialize(v) for k, v in payload.items()}
    analysis_id = store.put_analysis({**serializable, "_raw_payload": payload})
    serializable["analysis_id"] = analysis_id
    return serializable


@router.post("/analyze")
async def analyze(request: AnalyzeRequest) -> Dict[str, Any]:
    try:
        return _run_analysis(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export/{analysis_id}")
async def export_analysis(analysis_id: str) -> StreamingResponse:
    try:
        analysis = store.get_analysis(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    raw = analysis.get("_raw_payload", analysis)
    binary = build_excel_output(raw)
    return StreamingResponse(
        iter([binary]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=hcp_targeting_{analysis_id}.xlsx"},
    )


@router.post("/configurations")
async def save_configuration(request: SaveConfigurationRequest) -> Dict[str, str]:
    record = ConfigurationRecord(**request.model_dump())
    store.put_configuration(record.model_dump())
    return {"status": "saved", "name": request.name}


@router.get("/configurations")
async def list_configurations() -> List[Dict[str, Any]]:
    return list(store.list_configurations().values())
