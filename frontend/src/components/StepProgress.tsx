import type { PipelineStep } from "../api/types";

const STEPS: { key: PipelineStep; label: string }[] = [
  { key: "downloading", label: "Download" },
  { key: "transcribing", label: "Transcribe" },
  { key: "enriching", label: "Enrich" },
  { key: "validating", label: "Validate" },
  { key: "compiling", label: "Compile" },
  { key: "pdf_generating", label: "PDF" },
  { key: "completed", label: "Done" },
];

const STEP_ORDER = STEPS.map((s) => s.key);

function stepIndex(step: PipelineStep): number {
  const idx = STEP_ORDER.indexOf(step);
  return idx === -1 ? -1 : idx;
}

export function StepProgress({
  currentStep,
  failed,
}: {
  currentStep: PipelineStep;
  failed?: boolean;
}) {
  const activeIdx = stepIndex(currentStep);

  return (
    <div className="flex items-center gap-1">
      {STEPS.map((step, i) => {
        const isCompleted = i < activeIdx;
        const isActive = i === activeIdx;
        const isFailed = isActive && failed;

        return (
          <div key={step.key} className="flex items-center">
            {i > 0 && (
              <div
                className={`mx-1 h-0.5 w-6 ${
                  isCompleted ? "bg-green-400" : "bg-gray-200"
                }`}
              />
            )}
            <div className="flex flex-col items-center">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                  isFailed
                    ? "bg-red-500 text-white"
                    : isCompleted
                      ? "bg-green-500 text-white"
                      : isActive
                        ? "bg-blue-500 text-white animate-pulse"
                        : "border border-gray-300 text-gray-400"
                }`}
              >
                {isCompleted ? "\u2713" : isFailed ? "\u2717" : i + 1}
              </div>
              <span
                className={`mt-1 text-[10px] ${
                  isActive || isCompleted ? "text-gray-700 font-medium" : "text-gray-400"
                }`}
              >
                {step.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
