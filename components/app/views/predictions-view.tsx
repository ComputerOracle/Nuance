import type { Prediction } from "@/components/app/types";

export function PredictionsView({
  predictions,
  onOpen,
}: {
  predictions: Prediction[];
  onOpen: (id: number) => void;
}) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="font-display text-[30px] font-bold">
        Prediction Markets
      </div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        Fuzzy, real-world outcomes settled by AI-validator consensus.
      </div>

      <div className="flex flex-col gap-2.5">
        {predictions.map((p) => (
          <div
            key={p.id}
            onClick={() => onOpen(p.id)}
            className="flex cursor-pointer items-center justify-between rounded-[14px] border border-border-1 bg-surface-1 p-5 transition-colors hover:border-border-6"
          >
            <div className="flex-1">
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-review-text">
                {p.category}
              </div>
              <div className="max-w-[480px] text-[15px] font-semibold">
                {p.question}
              </div>
              <div className="mt-1.5 text-[13px] text-fg-meta">
                Resolves {p.resolveDate} · ${p.volume.toLocaleString()} volume
              </div>
            </div>
            <div className="rounded-[10px] bg-surface-3 px-4.5 py-2.5 text-center">
              <div className="font-display text-xl font-bold text-positive-text">
                {p.yesPrice}¢
              </div>
              <div className="text-[11px] text-fg-meta">YES</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
