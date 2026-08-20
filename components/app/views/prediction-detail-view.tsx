import type { Position, Prediction } from "@/components/app/types";

export function PredictionDetailView({
  prediction,
  betAmount,
  betSide,
  position,
  onBack,
  onSelectYes,
  onSelectNo,
  onBetAmountChange,
  onPlaceBet,
}: {
  prediction: Prediction;
  betAmount: string;
  betSide: "yes" | "no" | null;
  position: Position | null;
  onBack: () => void;
  onSelectYes: () => void;
  onSelectNo: () => void;
  onBetAmountChange: (v: string) => void;
  onPlaceBet: () => void;
}) {
  const noPrice = 100 - prediction.yesPrice;
  const betDisabled = !(betAmount && betSide);

  const sideClasses = (side: "yes" | "no") => {
    const active = betSide === side;
    if (side === "yes") {
      return active
        ? "border-positive/60 bg-positive/15 text-positive-text"
        : "border-border-4 bg-surface-3 text-fg-bright";
    }
    return active
      ? "border-negative/60 bg-negative/15 text-negative-text"
      : "border-border-4 bg-surface-3 text-fg-bright";
  };

  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div
        onClick={onBack}
        className="mb-4.5 inline-block cursor-pointer text-sm text-fg-meta transition-colors hover:text-fg"
      >
        ← Back to markets
      </div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-review-text">
        {prediction.category}
      </div>
      <div className="max-w-[640px] font-display text-2xl font-bold">
        {prediction.question}
      </div>
      <div className="mt-2 text-sm text-fg-dim-2">
        Resolves {prediction.resolveDate} · $
        {prediction.volume.toLocaleString()} volume
      </div>

      <div className="mt-7 grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-5">
          <div className="mb-3 font-display text-[15px] font-bold">
            AI Validator Read
          </div>
          <div className="text-[13px] leading-relaxed text-fg-bright">
            {prediction.aiSummary}
          </div>
          <div className="mt-4 flex gap-2">
            <div className="h-2.5 flex-1 overflow-hidden rounded-md bg-surface-3">
              <div
                className="h-full bg-dot-active"
                style={{ width: `${prediction.yesPrice}%` }}
              />
            </div>
          </div>
          <div className="mt-1.5 flex justify-between text-xs text-fg-meta">
            <span>YES {prediction.yesPrice}¢</span>
            <span>NO {noPrice}¢</span>
          </div>
        </div>

        <div className="h-fit rounded-2xl border border-border-2 bg-surface-2 p-5">
          <div className="mb-3.5 font-display text-[15px] font-bold">
            Place a Bet
          </div>
          <div className="mb-3.5 flex gap-2">
            <button
              onClick={onSelectYes}
              className={`flex-1 cursor-pointer rounded-lg border px-2 py-2.5 text-[13px] font-semibold ${sideClasses("yes")}`}
            >
              YES {prediction.yesPrice}¢
            </button>
            <button
              onClick={onSelectNo}
              className={`flex-1 cursor-pointer rounded-lg border px-2 py-2.5 text-[13px] font-semibold ${sideClasses("no")}`}
            >
              NO {noPrice}¢
            </button>
          </div>
          <input
            value={betAmount}
            onChange={(e) => onBetAmountChange(e.target.value)}
            placeholder="Amount (USDC)"
            className="w-full rounded-lg border border-border-4 bg-surface-3 px-3 py-2.5 font-brand-mono text-sm text-fg placeholder:text-fg-faint-2"
          />
          <button
            onClick={onPlaceBet}
            disabled={betDisabled}
            className="mt-3 w-full cursor-pointer rounded-lg border border-border-6 bg-chip-hover py-2.5 text-[13px] font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default"
            style={{ opacity: betDisabled ? 0.5 : 1 }}
          >
            Place Bet
          </button>
          {position && (
            <div
              className="mt-3.5 rounded-lg border border-positive/35 bg-positive/12 p-3 text-[13px] text-positive-text"
              style={{ animation: "fadeUp 0.3s ease" }}
            >
              Position opened: {position.amount} USDC on{" "}
              {position.side.toUpperCase()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
