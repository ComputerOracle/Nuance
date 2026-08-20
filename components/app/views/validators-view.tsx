import type { ValidatorDirectoryEntry } from "@/components/app/types";

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
              <div className="h-2 w-2 rounded-full bg-positive" />
            </div>
            <div className="mt-3 flex gap-5">
              <div>
                <div className="text-[11px] text-fg-meta">Accuracy</div>
                <div className="mt-0.5 text-sm font-semibold">
                  {v.accuracy}%
                </div>
              </div>
              <div>
                <div className="text-[11px] text-fg-meta">Cases</div>
                <div className="mt-0.5 text-sm font-semibold">{v.cases}</div>
              </div>
              <div>
                <div className="text-[11px] text-fg-meta">Stake</div>
                <div className="mt-0.5 text-sm font-semibold">{v.stake}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
