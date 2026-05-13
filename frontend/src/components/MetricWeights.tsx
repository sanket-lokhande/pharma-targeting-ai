import type { MetricWeight } from "../types";

type MetricWeightsProps = {
  metrics: string[];
  values: MetricWeight[];
  onChange: (values: MetricWeight[]) => void;
};

export function MetricWeights({ metrics, values, onChange }: MetricWeightsProps) {
  const selectedMap = new Map(values.map((item) => [item.metric, item.weight]));

  const toggleMetric = (metric: string) => {
    if (selectedMap.has(metric)) {
      onChange(values.filter((item) => item.metric !== metric));
      return;
    }

    const next = [...values, { metric, weight: 0 }];
    onChange(next);
  };

  const setWeight = (metric: string, weight: number) => {
    onChange(values.map((item) => (item.metric === metric ? { ...item, weight } : item)));
  };

  const total = values.reduce((acc, item) => acc + item.weight, 0);

  return (
    <div className="rounded-2xl bg-white p-5 shadow-lg ring-1 ring-black/5">
      <h3 className="mb-3 font-display text-xl text-ink">Select Metrics and Weights</h3>
      <p className="mb-4 text-sm text-ink/70">Select only relevant metrics. Total weight must equal 100%.</p>

      <div className="space-y-3">
        {metrics.map((metric) => {
          const checked = selectedMap.has(metric);
          const value = selectedMap.get(metric) ?? 0;
          return (
            <div key={metric} className="rounded-xl border border-slate-200 p-3">
              <div className="flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm font-medium text-ink">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleMetric(metric)}
                    className="h-4 w-4 accent-mint"
                  />
                  {metric}
                </label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  disabled={!checked}
                  value={value}
                  onChange={(event) => setWeight(metric, Number(event.target.value))}
                  className="w-24 rounded-lg border border-slate-300 px-2 py-1 text-right text-sm"
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className={`mt-4 rounded-lg px-3 py-2 text-sm font-semibold ${total === 100 ? "bg-mint/20 text-mint" : "bg-coral/20 text-coral"}`}>
        Total Weight: {total}%
      </div>
    </div>
  );
}
