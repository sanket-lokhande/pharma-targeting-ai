from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


NormalizationMethod = Literal["minmax", "zscore"]

ALL_DECILES: List[str] = [f"D{i}" for i in range(1, 11)]


class MetricWeight(BaseModel):
    metric: str
    weight: float = Field(ge=0, le=100)


class DecileBand(BaseModel):
    """User-defined band mapping a name (e.g. 'High Value') to a list of deciles."""

    name: str = Field(min_length=1, max_length=60)
    deciles: List[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_deciles(self) -> "DecileBand":
        invalid = [d for d in self.deciles if d not in ALL_DECILES]
        if invalid:
            raise ValueError(f"Band '{self.name}' contains invalid deciles: {invalid}")
        return self


DEFAULT_BANDS: List[DecileBand] = [
    DecileBand(name="High Value", deciles=["D8", "D9", "D10"]),
    DecileBand(name="Medium", deciles=["D4", "D5", "D6", "D7"]),
    DecileBand(name="Low", deciles=["D1", "D2", "D3"]),
]


class BandConfig(BaseModel):
    bands: List[DecileBand]

    @model_validator(mode="after")
    def _validate_no_overlap(self) -> "BandConfig":
        seen: Dict[str, str] = {}
        for band in self.bands:
            for d in band.deciles:
                if d in seen:
                    raise ValueError(
                        f"Decile {d} appears in multiple bands ('{seen[d]}' and '{band.name}')"
                    )
                seen[d] = band.name
        return self


class AnalyzeRequest(BaseModel):
    current_dataset_id: str
    metric_weights: List[MetricWeight]
    bands: List[DecileBand] = Field(default_factory=lambda: list(DEFAULT_BANDS))
    normalization: NormalizationMethod = "minmax"
    previous_dataset_id: Optional[str] = None
    previous_period: Optional[str] = None

    @model_validator(mode="after")
    def _validate(self) -> "AnalyzeRequest":
        active = [m for m in self.metric_weights if m.weight > 0]
        if not active:
            raise ValueError("At least one metric must have weight > 0")
        total = sum(item.weight for item in active)
        if abs(total - 100.0) > 1e-6:
            raise ValueError("Sum of metric weights must equal 100")
        BandConfig(bands=self.bands)
        return self


class SaveConfigurationRequest(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    metric_weights: List[MetricWeight]
    bands: List[DecileBand] = Field(default_factory=lambda: list(DEFAULT_BANDS))
    normalization: NormalizationMethod = "minmax"

    @model_validator(mode="after")
    def _validate(self) -> "SaveConfigurationRequest":
        total = sum(item.weight for item in self.metric_weights if item.weight > 0)
        if abs(total - 100.0) > 1e-6:
            raise ValueError("Sum of metric weights must equal 100")
        return self


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    row_count: int
    id_column: str
    metric_columns: List[str]
    specialty_column: Optional[str] = None
    validation_notes: List[str]
    data_preview: List[Dict[str, object]]


class ConfigurationRecord(BaseModel):
    name: str
    metric_weights: List[MetricWeight]
    bands: List[DecileBand]
    normalization: NormalizationMethod
