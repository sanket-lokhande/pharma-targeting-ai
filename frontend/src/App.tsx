import { useMemo, useState } from "react";
import { MetricWeights } from "./components/MetricWeights";
import { ResultPanel } from "./components/ResultPanel";
import { StepHeader } from "./components/StepHeader";
import { analyze, exportAnalysis, listConfigurations, saveConfiguration, uploadCurrent, uploadPrevious } from "./services/api";
import type { AnalyzeResponse, MetricWeight, SavedConfiguration, UploadResponse } from "./types";

const initialWeights: MetricWeight[] = [];

export default function App() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [currentUpload, setCurrentUpload] = useState<UploadResponse | null>(null);
  const [previousUpload, setPreviousUpload] = useState<UploadResponse | null>(null);
  const [weights, setWeights] = useState<MetricWeight[]>(initialWeights);
  const [normalization, setNormalization] = useState<"minmax" | "zscore">("minmax");
  const [algorithm, setAlgorithm] = useState<"kmeans" | "hierarchical" | "rule_based">("kmeans");
  const [nClusters, setNClusters] = useState(3);
  const [previousPeriod, setPreviousPeriod] = useState("");
  const [previousAlgorithm, setPreviousAlgorithm] = useState("");

  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [configName, setConfigName] = useState("");
  const [configs, setConfigs] = useState<SavedConfiguration[]>([]);

  const totalWeight = useMemo(() => weights.reduce((acc, item) => acc + item.weight, 0), [weights]);

  const runCurrentUpload = async (file: File | null) => {
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      const data = await uploadCurrent(file);
      setCurrentUpload(data);
      setWeights(data.metric_columns.map((metric) => ({ metric, weight: 0 })));
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  const runPreviousUpload = async (file: File | null) => {
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      const data = await uploadPrevious(file);
      setPreviousUpload(data);
      setStep(Math.max(step, 5));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Previous upload failed");
    } finally {
      setLoading(false);
    }
  };

  const runAnalysis = async () => {
    if (!currentUpload) {
      setError("Upload current file first");
      return;
    }
    if (weights.filter((item) => item.weight > 0).length === 0) {
      setError("Select at least one metric with non-zero weight");
      return;
    }
    if (totalWeight !== 100) {
      setError("Total weight must be exactly 100%");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const selected = weights.filter((item) => item.weight > 0);
      const payload = {
        current_dataset_id: currentUpload.dataset_id,
        metric_weights: selected,
        normalization,
        segmentation_algorithm: algorithm,
        n_clusters: nClusters,
        ...(previousUpload
          ? {
              previous_dataset_id: previousUpload.dataset_id,
              previous_period: previousPeriod || "Unknown",
              previous_algorithm: previousAlgorithm || "Unknown"
            }
          : {})
      };

      const result = await analyze(payload);
      setAnalysis(result);
      setStep(6);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const onSaveConfiguration = async () => {
    if (!configName.trim()) {
      setError("Enter a configuration name");
      return;
    }

    try {
      await saveConfiguration({
        name: configName.trim(),
        metric_weights: weights.filter((item) => item.weight > 0),
        normalization,
        segmentation_algorithm: algorithm,
        n_clusters: nClusters
      });
      const fresh = await listConfigurations();
      setConfigs(fresh);
      setConfigName("");
    } catch {
      setError("Could not save configuration");
    }
  };

  const loadConfigurations = async () => {
    try {
      const result = await listConfigurations();
      setConfigs(result);
    } catch {
      setError("Could not load saved configurations");
    }
  };

  const applyConfig = (config: SavedConfiguration) => {
    setWeights(config.metric_weights);
    setNormalization(config.normalization);
    setAlgorithm(config.segmentation_algorithm);
    setNClusters(config.n_clusters);
  };

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <header className="mb-6 fade-in">
        <h1 className="font-display text-3xl font-bold text-ink md:text-4xl">Pharma Commercial AI Studio</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink/75 md:text-base">
          AI-powered targeting, segmentation, and movement diagnostics for HCP/account commercial planning.
        </p>
      </header>

      <StepHeader currentStep={step} />

      {error && (
        <div className="mb-4 rounded-xl bg-coral/20 px-4 py-3 text-sm text-coral">
          {error}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-white p-5 shadow-lg ring-1 ring-black/5">
          <h2 className="mb-3 font-display text-xl text-ink">1. Upload Current Data</h2>
          <input
            type="file"
            accept=".xlsx"
            onChange={(event) => runCurrentUpload(event.target.files?.[0] ?? null)}
            className="w-full rounded-lg border border-slate-300 p-2 text-sm"
          />
          {currentUpload && (
            <p className="mt-3 text-sm text-mint">
              Uploaded {currentUpload.row_count} rows | ID column: {currentUpload.id_column}
            </p>
          )}
        </div>

        <div className="rounded-2xl bg-white p-5 shadow-lg ring-1 ring-black/5">
          <h2 className="mb-3 font-display text-xl text-ink">5. Upload Previous (Optional)</h2>
          <input
            type="file"
            accept=".xlsx"
            onChange={(event) => runPreviousUpload(event.target.files?.[0] ?? null)}
            className="w-full rounded-lg border border-slate-300 p-2 text-sm"
          />
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <input
              placeholder="Previous period (e.g. Q1 2025)"
              value={previousPeriod}
              onChange={(event) => setPreviousPeriod(event.target.value)}
              className="rounded-lg border border-slate-300 p-2 text-sm"
            />
            <input
              placeholder="Previous algorithm"
              value={previousAlgorithm}
              onChange={(event) => setPreviousAlgorithm(event.target.value)}
              className="rounded-lg border border-slate-300 p-2 text-sm"
            />
          </div>
        </div>
      </section>

      {currentUpload && (
        <div className="mt-5 fade-in">
          <MetricWeights metrics={currentUpload.metric_columns} values={weights} onChange={setWeights} />

          <div className="mt-4 grid gap-4 rounded-2xl bg-white p-5 shadow-lg ring-1 ring-black/5 md:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs uppercase text-ink/70">Normalization</label>
              <select
                value={normalization}
                onChange={(event) => setNormalization(event.target.value as "minmax" | "zscore")}
                className="w-full rounded-lg border border-slate-300 p-2 text-sm"
              >
                <option value="minmax">Min-Max Scaling</option>
                <option value="zscore">Z-Score</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase text-ink/70">Segmentation Algorithm</label>
              <select
                value={algorithm}
                onChange={(event) => setAlgorithm(event.target.value as "kmeans" | "hierarchical" | "rule_based")}
                className="w-full rounded-lg border border-slate-300 p-2 text-sm"
              >
                <option value="kmeans">K-Means</option>
                <option value="hierarchical">Hierarchical</option>
                <option value="rule_based">Rule-Based</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase text-ink/70">Clusters</label>
              <input
                type="number"
                min={2}
                max={8}
                value={nClusters}
                onChange={(event) => setNClusters(Number(event.target.value))}
                className="w-full rounded-lg border border-slate-300 p-2 text-sm"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={runAnalysis}
                disabled={loading}
                className="w-full rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {loading ? "Running..." : "Generate Scores + Segments"}
              </button>
            </div>
          </div>

          <div className="mt-4 rounded-2xl bg-white p-5 shadow-lg ring-1 ring-black/5">
            <h3 className="mb-2 font-display text-lg text-ink">Bonus: Save / Reuse Configuration</h3>
            <div className="grid gap-2 md:grid-cols-4">
              <input
                value={configName}
                onChange={(event) => setConfigName(event.target.value)}
                placeholder="Configuration name"
                className="rounded-lg border border-slate-300 p-2 text-sm"
              />
              <button onClick={onSaveConfiguration} className="rounded-lg bg-mint px-4 py-2 text-sm font-semibold text-white">
                Save Config
              </button>
              <button onClick={loadConfigurations} className="rounded-lg bg-sun px-4 py-2 text-sm font-semibold text-ink">
                Load Configs
              </button>
            </div>
            {configs.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {configs.map((config) => (
                  <button
                    key={config.name}
                    onClick={() => applyConfig(config)}
                    className="rounded-full bg-surf px-3 py-1 text-xs font-semibold text-ink"
                  >
                    {config.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {analysis && (
        <section className="mt-6 fade-in">
          <div className="mb-4 flex flex-col gap-3 rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-ink/80">
              Analysis complete. Export full workbook with raw scores, segmentation, comparison, and insights.
            </p>
            <a
              href={exportAnalysis(analysis.analysis_id)}
              className="inline-flex w-full items-center justify-center rounded-lg bg-coral px-4 py-2 text-sm font-semibold text-white md:w-auto"
            >
              Download Excel Output
            </a>
          </div>

          <ResultPanel analysis={analysis} />
        </section>
      )}
    </div>
  );
}
