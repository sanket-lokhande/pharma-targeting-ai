import Plot from "react-plotly.js";
import type { AnalyzeResponse } from "../types";

type ResultPanelProps = {
  analysis: AnalyzeResponse;
};

function buildCorrelationHeatmap(correlation: Record<string, Record<string, number>>) {
  const labels = Object.keys(correlation);
  const z = labels.map((row) => labels.map((col) => correlation[row][col] ?? 0));
  return { labels, z };
}

export function ResultPanel({ analysis }: ResultPanelProps) {
  const corr = buildCorrelationHeatmap(analysis.correlation_matrix);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5">
          <h3 className="mb-3 font-display text-lg text-ink">Concentration Curve</h3>
          <Plot
            data={[
              {
                x: analysis.lorenz_curve.population_share,
                y: analysis.lorenz_curve.value_share,
                type: "scatter",
                mode: "lines",
                line: { color: "#2f8f83", width: 3 },
                name: "Lorenz"
              },
              {
                x: [0, 1],
                y: [0, 1],
                type: "scatter",
                mode: "lines",
                line: { color: "#e76f51", dash: "dash" },
                name: "Parity"
              }
            ]}
            layout={{
              autosize: true,
              margin: { l: 40, r: 10, t: 20, b: 40 },
              xaxis: { title: "Population Share" },
              yaxis: { title: "Value Share" }
            }}
            config={{ responsive: true, displaylogo: false }}
            style={{ width: "100%", height: "300px" }}
          />
        </div>

        <div className="rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5">
          <h3 className="mb-3 font-display text-lg text-ink">Composite Score Distribution</h3>
          <Plot
            data={[
              {
                x: analysis.distributions.composite_score_bins,
                y: analysis.distributions.composite_score_counts,
                type: "bar",
                marker: { color: "#f4a259" }
              }
            ]}
            layout={{ autosize: true, margin: { l: 40, r: 10, t: 20, b: 40 } }}
            config={{ responsive: true, displaylogo: false }}
            style={{ width: "100%", height: "300px" }}
          />
        </div>
      </div>

      <div className="rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5">
        <h3 className="mb-3 font-display text-lg text-ink">Correlation Matrix</h3>
        <Plot
          data={[
            {
              z: corr.z,
              x: corr.labels,
              y: corr.labels,
              type: "heatmap",
              colorscale: "Teal",
              zmin: -1,
              zmax: 1
            }
          ]}
          layout={{ autosize: true, margin: { l: 80, r: 10, t: 20, b: 80 } }}
          config={{ responsive: true, displaylogo: false }}
          style={{ width: "100%", height: "380px" }}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5">
          <h4 className="mb-2 font-display text-base text-ink">Summary Insights</h4>
          <ul className="space-y-2 text-sm text-ink/80">
            {analysis.summary_insights.slice(0, 8).map((item, idx) => (
              <li key={`${item}-${idx}`}>- {item}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5">
          <h4 className="mb-2 font-display text-base text-ink">Recommendations</h4>
          <ul className="space-y-2 text-sm text-ink/80">
            {analysis.recommendations.map((item, idx) => (
              <li key={`${item}-${idx}`}>- {item}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl bg-white p-4 shadow-lg ring-1 ring-black/5">
          <h4 className="mb-2 font-display text-base text-ink">Validation Notes</h4>
          <ul className="space-y-2 text-sm text-ink/80">
            {analysis.validation_notes.map((item, idx) => (
              <li key={`${item}-${idx}`}>- {item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
