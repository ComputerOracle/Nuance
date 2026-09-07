import { useEffect, useState } from "react";
import type { Position, Prediction } from "@/components/app/types";

export function PredictionDetailView({
  prediction,
  betAmount,
  betSide,
  position,
  isBetting,
  isResolving,
  bettingError,
  onBack,
  onSelectYes,
  onSelectNo,
  onBetAmountChange,
  onPlaceBet,
  onResolveMarket,
}: {
  prediction: Prediction;
  betAmount: string;
  betSide: "yes" | "no" | null;
  position: Position | null;
  isBetting?: boolean;
  isResolving?: boolean;
  bettingError?: string | null;
  onBack: () => void;
  onSelectYes: () => void;
  onSelectNo: () => void;
  onBetAmountChange: (v: string) => void;
  onPlaceBet: () => void;
  onResolveMarket?: () => void;
}) {
  const isResolved =
    prediction.statusKey?.toUpperCase() === "RESOLVED" ||
    Boolean(prediction.outcome);

  // Date.now() can't be called directly during render — an impure read
  // (React's purity rule: two renders with the same props/state must
  // produce the same output). Tracked as state instead, refreshed every
  // 30s — "matures" up to 30s late is an acceptable cutoff-precision
  // tradeoff for disabling betting, not a value rendered to the user.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(interval);
  }, []);

  const resTimestamp = prediction.resolutionDate
    ? new Date(prediction.resolutionDate).getTime()
    : 0;
  const isMatured = resTimestamp > 0 && now >= resTimestamp;

  const noPrice = 100 - prediction.yesPrice;
  const betDisabled =
    !(betAmount && betSide) || isBetting || isResolved || isMatured;

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

  const isWinner =
    position &&
    (position.status === "WON" ||
      (position.payout != null && position.payout > 0) ||
      (isResolved &&
        prediction.outcome &&
        position.side.toUpperCase() === prediction.outcome.toUpperCase()));

  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div
        onClick={onBack}
        className="mb-4.5 inline-block cursor-pointer text-sm text-fg-meta transition-colors hover:text-fg"
      >
        ← Back to markets
      </div>

      {isResolved && (
        <div className="mb-6 rounded-2xl border border-positive/40 bg-positive/10 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-positive/25 font-bold text-sm text-positive-text">
                ✓
              </span>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-positive-text">
                  Market Settled by GenLayer Intelligent Oracle
                </div>
                <div className="font-display text-xl font-bold">
                  Official Outcome:{" "}
                  <span
                    className={
                      prediction.outcome === "YES"
                        ? "text-positive-text"
                        : "text-negative-text"
                    }
                  >
                    {prediction.outcome}
                  </span>
                </div>
              </div>
            </div>
            <span className="rounded-lg border border-positive/30 bg-positive/20 px-3 py-1 font-mono text-xs font-bold uppercase tracking-wider text-positive-text">
              Resolved
            </span>
          </div>
          {prediction.resolutionReasoning && (
            <div className="mt-3.5 border-t border-positive/20 pt-3 text-xs leading-relaxed text-fg-bright">
              {prediction.resolutionReasoning}
            </div>
          )}
        </div>
      )}

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
          <div className="mb-3 flex items-center justify-between">
            <div className="font-display text-[15px] font-bold">
              GenLayer Intelligent Oracle Read
            </div>
            <span className="rounded-md border border-review/30 bg-review/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-review-text">
              Intelligent Oracle
            </span>
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
          <div className="mt-4 border-t border-border-2 pt-3 text-[11px] text-fg-meta">
            ⚡ Market resolution criteria evaluated and finalized by GenLayer Intelligent Oracle consensus nodes.
          </div>
        </div>

        <div className="h-fit rounded-2xl border border-border-2 bg-surface-2 p-5">
          <div className="mb-3.5 flex items-center justify-between font-display text-[15px] font-bold">
            <span>{isResolved ? "Market Settlement" : "Place a Bet"}</span>
            {isResolved ? (
              <span className="text-xs font-mono text-fg-meta uppercase">Closed</span>
            ) : isMatured ? (
              <span className="text-xs font-mono text-review-text uppercase">Matured</span>
            ) : (
              <span className="text-xs font-mono text-positive-text uppercase">Open</span>
            )}
          </div>

          {isResolved ? (
            <div className="space-y-4">
              {position ? (
                isWinner ? (
                  <div className="rounded-xl border border-positive/50 bg-positive/15 p-4 text-center">
                    <div className="text-2xl mb-1">🎉</div>
                    <div className="font-display text-lg font-bold text-positive-text">
                      Won {Number(position.payout ?? 0).toFixed(2)} USDC
                    </div>
                    <div className="mt-1 text-xs text-fg-meta">
                      Position: {position.amount} USDC on {position.side.toUpperCase()}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-border-4 bg-surface-3 p-4 text-center">
                    <div className="font-display text-sm font-semibold text-fg-meta">
                      Outcome Resolved — Position Closed
                    </div>
                    <div className="mt-1 text-xs text-fg-faint-2">
                      Stake: {position.amount} USDC on {position.side.toUpperCase()} · Payout: 0.00 USDC
                    </div>
                  </div>
                )
              ) : (
                <div className="rounded-xl border border-border-4 bg-surface-3 p-4 text-center text-xs text-fg-meta">
                  This market has been resolved by the GenLayer Intelligent Oracle. No open positions for current wallet.
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="mb-3.5 flex gap-2">
                <button
                  onClick={onSelectYes}
                  disabled={isBetting || isMatured}
                  className={`flex-1 cursor-pointer rounded-lg border px-2 py-2.5 text-[13px] font-semibold ${sideClasses("yes")}`}
                >
                  YES {prediction.yesPrice}¢
                </button>
                <button
                  onClick={onSelectNo}
                  disabled={isBetting || isMatured}
                  className={`flex-1 cursor-pointer rounded-lg border px-2 py-2.5 text-[13px] font-semibold ${sideClasses("no")}`}
                >
                  NO {noPrice}¢
                </button>
              </div>
              <input
                value={betAmount}
                onChange={(e) => onBetAmountChange(e.target.value)}
                disabled={isBetting || isMatured}
                placeholder={isMatured ? "Betting closed" : "Amount (USDC)"}
                className="w-full rounded-lg border border-border-4 bg-surface-3 px-3 py-2.5 font-brand-mono text-sm text-fg placeholder:text-fg-faint-2 focus:outline-none focus:border-border-6 disabled:opacity-50"
              />
              {bettingError && (
                <div className="mt-2.5 rounded-lg border border-negative/35 bg-negative/12 p-2.5 text-xs text-negative-text">
                  {bettingError}
                </div>
              )}
              <button
                onClick={onPlaceBet}
                disabled={betDisabled}
                className="mt-3 w-full cursor-pointer rounded-lg border border-border-6 bg-chip-hover py-2.5 text-[13px] font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default"
                style={{ opacity: betDisabled ? 0.5 : 1 }}
              >
                {isBetting ? "Placing Bet…" : isMatured ? "Betting Closed" : "Place Bet"}
              </button>

              {position && (
                <div
                  className="mt-3.5 rounded-lg border border-positive/35 bg-positive/12 p-3 text-[13px] text-positive-text"
                  style={{ animation: "fadeUp 0.3s ease" }}
                >
                  Active position: {position.amount} USDC on{" "}
                  {position.side.toUpperCase()}
                </div>
              )}

              {/* Task 2: Conditional resolution badge vs button */}
              <div className="mt-5 border-t border-border-2 pt-4">
                {isMatured ? (
                  onResolveMarket && (
                    <button
                      onClick={onResolveMarket}
                      disabled={isResolving}
                      className="w-full cursor-pointer rounded-lg border border-review/40 bg-review/15 py-2.5 text-xs font-semibold text-review-text transition-colors hover:bg-review/25 disabled:cursor-default"
                    >
                      {isResolving
                        ? "Resolving via Oracle Consensus…"
                        : "⚡ Trigger GenLayer Oracle Resolution"}
                    </button>
                  )
                ) : (
                  <div className="flex items-center justify-center gap-1.5 rounded-lg border border-border-4 bg-surface-3 px-3 py-2 text-center text-xs text-fg-meta">
                    <span>⏳ Awaiting Resolution Date (resolves on {prediction.resolveDate})</span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}



