export type MetricWeight = {
  metric: string;
  weight: number;
};

export type UploadResponse = {
  dataset_id: string;
  row_count: number;
  id_column: string;
  metric_columns: string[];
  validation_notes: string[];
  data_preview: Record<string, unknown>[];
};

export type AnalyzeRequest = {
  current_dataset_id: string;
  metric_weights: MetricWeight[];
  normalization: "minmax" | "zscore";
  segmentation_algorithm: "kmeans" | "hierarchical" | "rule_based";
  n_clusters: number;
  previous_dataset_id?: string;
  previous_period?: string;
  previous_algorithm?: string;
};

export type AnalyzeResponse = {
  analysis_id: string;
  raw_with_scores: Record<string, unknown>[];
  segmentation_results: Record<string, unknown>[];
  correlation_matrix: Record<string, Record<string, number>>;
  lorenz_curve: {
    population_share: number[];
    value_share: number[];
  };
  distributions: Record<string, number[]>;
  metric_summary: Record<string, Record<string, number>>;
  segment_explainability: Record<string, Record<string, number>>;
  summary_insights: string[];
  recommendations: string[];
  validation_notes: string[];
  movement_analysis: Record<string, unknown>[];
  new_vs_missing: Record<string, unknown>;
  segment_shift_analysis: Record<string, unknown>[];
  comparison_summary: Record<string, unknown>;
};

export type SavedConfiguration = {
  name: string;
  metric_weights: MetricWeight[];
  normalization: "minmax" | "zscore";
  segmentation_algorithm: "kmeans" | "hierarchical" | "rule_based";
  n_clusters: number;
};
