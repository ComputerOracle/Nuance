import type { Escrow, EscrowVerdict } from "@/components/app/types";
import { StatusBadge } from "@/components/app/status-badge";
import { activeMilestoneIndex, formatAddress } from "@/components/app/status";
import { ConsensusPanel, type ConsensusVerdict } from "@/components/app/consensus-panel";

export function EscrowDetailView({
  escrow,
  stage,
  deliverableText,
  verdict,
  onBack,
  onDeliverableChange,
  onSubmitDeliverable,
  onReleasePayment,
  onEscalate,
  submitDisabled = false,
  escalateDisabled = false,
}: {
  escrow: Escrow;
  stage: number;
  deliverableText: string;
  verdict: EscrowVerdict | null;
  onBack: () => void;
  onDeliverableChange: (text: string) => void;
  onSubmitDeliverable: () => void;
  onReleasePayment: () => void;
  onEscalate: () => void;
  // True while an on-chain submit is mid-flight (waiting on the wallet's
  // own signing prompt / RPC round-trip) — a separate condition from
  // "text is empty," which the button already gates on its own.
  submitDisabled?: boolean;
  // True while POST /escrows/{id}/dispute is in flight.
  escalateDisabled?: boolean;
}) {
  const activeIdx = activeMilestoneIndex(escrow.milestones);

  const consensusVerdict: ConsensusVerdict | null = verdict
    ? {
        label: verdict.label,
        colorClass: verdict.approved ? "text-positive-text" : "text-negative-text",
        panelBgClass: verdict.approved ? "bg-positive/10" : "bg-negative/10",
        panelBorderClass: verdict.approved
          ? "border-positive/30"
          : "border-negative/30",
        confidence: verdict.confidence,
        reasoning: verdict.reasoning,
        actions: verdict.approved ? (
          <button
            onClick={onReleasePayment}
            className="cursor-pointer rounded-lg border-none bg-positive px-4 py-2.5 text-[13px] font-semibold text-positive-fg transition-[filter] hover:brightness-110"
          >
            Release Payment
          </button>
        ) : (
          <button
            onClick={onEscalate}
            disabled={escalateDisabled}
            className="cursor-pointer rounded-lg border-none bg-negative px-4 py-2.5 text-[13px] font-semibold text-white transition-[filter] hover:brightness-110 disabled:cursor-default disabled:opacity-60"
          >
            {escalateDisabled ? "Filing dispute…" : "Escalate to Internet Court"}
          </button>
        ),
      }
    : null;

  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div
        onClick={onBack}
        className="mb-4.5 inline-block cursor-pointer text-sm text-fg-meta transition-colors hover:text-fg"
      >
        ← Back to escrows
      </div>

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-display text-2xl font-bold">{escrow.title}</div>
          <div className="mt-1.5 text-sm text-fg-dim-2">
            Counterparty{" "}
            <span className="font-brand-mono text-fg-bright">
              {formatAddress(escrow.counterpartyAddress)}
            </span>{" "}
            · Creator{" "}
            <span className="font-brand-mono text-fg-bright">
              {formatAddress(escrow.creatorAddress)}
            </span>{" "}
            · Total{" "}
            <span className="font-semibold text-fg">
              {escrow.total.toLocaleString()} USDC
            </span>
          </div>
        </div>
        <StatusBadge status={escrow.statusKey} />
      </div>

      <div className="mt-7 grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="flex flex-col gap-3">
          <div className="mb-0.5 text-xs uppercase tracking-wide text-fg-meta">
            Milestones
          </div>
          {escrow.milestones.map((m, i) => {
            const isActive =
              i === activeIdx &&
              (m.statusKey === "pending" ||
                m.statusKey === "in_review" ||
                m.statusKey === "in_progress" ||
                m.statusKey === "disputed");
            return (
              <div
                key={m.name}
                className="rounded-xl border border-border-1 bg-surface-1 p-4.5"
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold">{m.name}</div>
                  <StatusBadge status={m.statusKey} />
                </div>
                <div className="mt-1.5 text-[13px] text-fg-meta">
                  {m.criteria}
                </div>
                <div className="mt-2.5 font-brand-mono text-[13px] text-fg-bright">
                  {m.amount.toLocaleString()} USDC
                </div>

                {m.statusKey === "approved" && (
                  <div className="mt-3 rounded-lg border border-positive/30 bg-positive/10 px-3 py-2 text-xs font-medium text-positive-text">
                    ✓ Milestone deliverable approved by AI Consensus.
                  </div>
                )}

                {m.statusKey === "disputed" && (
                  <div className="mt-3 rounded-lg border border-negative/30 bg-negative/10 px-3 py-2 text-xs font-medium text-negative-text">
                    ⚠ Milestone deliverable disputed by AI Consensus.
                  </div>
                )}

                {isActive &&
                  stage === 0 &&
                  (m.statusKey === "pending" || m.statusKey === "in_progress") &&
                  escrow.statusKey !== "approved" &&
                  escrow.statusKey !== "disputed" && (
                    <div className="mt-3.5 border-t border-border-1 pt-3.5">
                      <textarea
                        value={deliverableText}
                        onChange={(e) => onDeliverableChange(e.target.value)}
                        placeholder="Paste deliverable URL, PR link, or describe the completed work for AI review…"
                        className="min-h-[78px] w-full resize-y rounded-lg border border-border-4 bg-surface-3 px-3 py-2.5 font-sans text-[13px] text-fg placeholder:text-fg-faint-2"
                      />
                      <button
                        onClick={onSubmitDeliverable}
                        disabled={!deliverableText.trim() || submitDisabled}
                        className="mt-2.5 cursor-pointer rounded-lg border border-border-6 bg-chip-hover px-4.5 py-2.5 text-[13px] font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default"
                        style={{ opacity: deliverableText.trim() && !submitDisabled ? 1 : 0.5 }}
                      >
                        {submitDisabled ? "Waiting for wallet…" : "Submit for AI Review"}
                      </button>
                    </div>
                  )}
              </div>
            );
          })}
        </div>

        <ConsensusPanel
          title="AI Validator Consensus"
          subtitle="3-of-3 GenVM validators adjudicate this milestone."
          stage={stage}
          analyzingLabel="Analyzing deliverable…"
          doneLabel="Consensus recorded"
          idleText="Awaiting deliverable submission…"
          verdict={consensusVerdict}
          sticky
        />
      </div>
    </div>
  );
}
