import type { Prediction } from "@/components/app/types";

// REMOVED 2026-09-14, asked directly ("I do not want user to be able to
// create a Prediction Markets, I want it will be fetching data about
// genlayer using the API key"): the "+ New Market" button and its
// onOpenCreate/notice plumbing are gone along with routers/predictions.py's
// POST /predictions (see that router's own updated module docstring for
// the full account). Markets now only ever come from services/
// market_generator.py's real TwitterAPI.io + Gemini pipeline — this view
// is read-only by design now, not missing a feature.
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
        Real GEN staked on real outcomes, settled by GenVM&rsquo;s on-chain validator committee.
      </div>

      {predictions.length === 0 ? (
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-8 text-center text-[14px] text-fg-meta">
          No open markets yet — new ones are sourced automatically from real GenLayer activity.
        </div>
      ) : (
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
                  Resolves {p.resolveDate} · {(p.volume / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })} GEN volume
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
      )}
    </div>
  );
}
