type StepHeaderProps = {
  currentStep: number;
};

const steps = [
  "Upload Current",
  "Metric Weights",
  "Scoring + Deciles",
  "Segmentation",
  "Previous Comparison",
  "Insights + Export"
];

export function StepHeader({ currentStep }: StepHeaderProps) {
  return (
    <div className="mb-8 rounded-2xl bg-white/80 p-4 shadow-sm ring-1 ring-black/5">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        {steps.map((label, idx) => {
          const stepNumber = idx + 1;
          const active = stepNumber === currentStep;
          const complete = stepNumber < currentStep;

          return (
            <div
              key={label}
              className={`rounded-xl px-3 py-2 text-center text-xs font-semibold transition md:text-sm ${
                active
                  ? "bg-ink text-white"
                  : complete
                    ? "bg-mint text-white"
                    : "bg-surf text-ink"
              }`}
            >
              {stepNumber}. {label}
            </div>
          );
        })}
      </div>
    </div>
  );
}
