from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

import pandas as pd


@dataclass
class DatasetRecord:
    dataset_type: str
    dataframe: pd.DataFrame
    source_filename: str
    id_column: str
    metric_columns: list[str]
    validation_notes: list[str]
    specialty_column: Optional[str] = None


class InMemoryStore:
    def __init__(self) -> None:
        self._datasets: Dict[str, DatasetRecord] = {}
        self._analyses: Dict[str, Dict[str, Any]] = {}
        self._configurations: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def put_dataset(
        self,
        dataset_type: str,
        dataframe: pd.DataFrame,
        source_filename: str,
        id_column: str,
        metric_columns: list[str],
        validation_notes: list[str],
        specialty_column: Optional[str] = None,
    ) -> str:
        dataset_id = str(uuid4())
        with self._lock:
            self._datasets[dataset_id] = DatasetRecord(
                dataset_type=dataset_type,
                dataframe=dataframe.copy(),
                source_filename=source_filename,
                id_column=id_column,
                metric_columns=metric_columns,
                validation_notes=validation_notes,
                specialty_column=specialty_column,
            )
        return dataset_id

    def get_dataset(self, dataset_id: str) -> DatasetRecord:
        record = self._datasets.get(dataset_id)
        if record is None:
            raise KeyError(f"Dataset {dataset_id} was not found")
        return record

    def put_analysis(self, payload: Dict[str, Any]) -> str:
        analysis_id = str(uuid4())
        with self._lock:
            self._analyses[analysis_id] = payload
        return analysis_id

    def get_analysis(self, analysis_id: str) -> Dict[str, Any]:
        analysis = self._analyses.get(analysis_id)
        if analysis is None:
            raise KeyError(f"Analysis {analysis_id} was not found")
        return analysis

    def put_configuration(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._configurations[payload["name"]] = payload

    def list_configurations(self) -> Dict[str, Dict[str, Any]]:
        return self._configurations.copy()


store = InMemoryStore()
