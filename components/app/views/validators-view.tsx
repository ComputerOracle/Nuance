import type { ValidatorDirectoryEntry } from "@/components/app/types";

function formatLastActive(iso: string | null): string {
  if (!iso) return "No cases yet";
  const date = new Date(iso);
  return `Active ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

// Display labels for services/consensus.py's provider identifiers. Falls
// back to the raw string for anything not listed here (e.g. a future
// provider added on the backend before this map is updated).
const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  anthropic: "Anthropic",
  openai: "OpenAI",
  heuristic: "Offline heuristic",
};

function formatProvider(provider: string | null): string | null {
  if (!provider) return null;
  return `via ${PROVIDER_LABELS[provider] ?? provider}`;
}

export function ValidatorsView({
  validators,
}: {
  validators: ValidatorDirectoryEntry[];
}) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="font-display text-[30px] font-bold">
        Validator Network
      </div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        GenVM nodes providing AI-consensus adjudication across Nuance.
      </div>

      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
        {validators.map((v) => (
          <div
            key={v.name}
            className="rounded-[14px] border border-border-1 bg-surface-1 p-4.5"
          >
            <div className="flex items-center justify-between">
              <div className="font-brand-mono text-[15px] font-semibold">
                {v.name}
              </div>
              <div
                className={`h-2 w-2 rounded-full ${v.isActive ? "bg-positive" : "bg-border-4"}`}
              />
            </div>
            {formatProvider(v.lastProvider) && (
              <div className="mt-0.5 text-[11px] text-fg-meta">
                {formatProvider(v.lastProvider)}
              </div>
            )}
            <div className="mt-3 flex gap-5">
              <div>
                <div className="text-[11px] text-fg-meta">Accuracy</div>
                <div className="mt-0.5 text-sm font-semibold">
                  {v.accuracyPct}%
                </div>
              </div>
              <div>
                <div className="text-[11px] text-fg-meta">Cases judged</div>
                <div className="mt-0.5 text-sm font-semibold">{v.casesJudged}</div>
              </div>
              <div>
                <div className="text-[11px] text-fg-meta">Status</div>
                <div className="mt-0.5 text-sm font-semibold">
                  {formatLastActive(v.lastActiveAt)}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
