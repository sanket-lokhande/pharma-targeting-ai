from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


SegmentationAlgorithm = Literal["kmeans", "hierarchical", "rule_based"]
NormalizationMethod = Literal["minmax", "zscore"]


class MetricWeight(BaseModel):
    metric: str
    weight: float = Field(gt=0, le=100)


class AnalyzeRequest(BaseModel):
    current_dataset_id: str
    metric_weights: List[MetricWeight]
    normalization: NormalizationMethod = "minmax"
    segmentation_algorithm: SegmentationAlgorithm = "kmeans"
    n_clusters: int = Field(default=3, ge=2, le=8)
    previous_dataset_id: Optional[str] = None
    previous_period: Optional[str] = None
    previous_algorithm: Optional[str] = None

    @model_validator(mode="after")
    def validate_weights(self) -> "AnalyzeRequest":
        total = sum(item.weight for item in self.metric_weights)
        if abs(total - 100.0) > 1e-6:
            raise ValueError("Sum of metric weights must equal 100")
        if self.previous_dataset_id and not self.previous_period:
            raise ValueError("previous_period is required when previous_dataset_id is provided")
        if self.previous_dataset_id and not self.previous_algorithm:
            raise ValueError("previous_algorithm is required when previous_dataset_id is provided")
        return self


class SaveConfigurationRequest(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    metric_weights: List[MetricWeight]
    normalization: NormalizationMethod
    segmentation_algorithm: SegmentationAlgorithm
    n_clusters: int = Field(default=3, ge=2, le=8)

    @model_validator(mode="after")
    def validate_weights(self) -> "SaveConfigurationRequest":
        total = sum(item.weight for item in self.metric_weights)
        if abs(total - 100.0) > 1e-6:
            raise ValueError("Sum of metric weights must equal 100")
        return self


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    row_count: int
    id_column: str
    metric_columns: List[str]
    validation_notes: List[str]
    data_preview: List[Dict[str, object]]


class ConfigurationRecord(BaseModel):
    name: str
    metric_weights: List[MetricWeight]
    normalization: NormalizationMethod
    segmentation_algorithm: SegmentationAlgorithm
    n_clusters: int
