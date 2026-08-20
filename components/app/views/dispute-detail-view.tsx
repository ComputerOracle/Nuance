import type { Dispute, DisputeVerdict } from "@/components/app/types";
import { ConsensusPanel, type ConsensusVerdict } from "@/components/app/consensus-panel";

export function DisputeDetailView({
  dispute,
  stage,
  evidenceText,
  verdict,
  onBack,
  onEvidenceChange,
  onSubmitEvidence,
  onEnforceRuling,
}: {
  dispute: Dispute;
  stage: number;
  evidenceText: string;
  verdict: DisputeVerdict | null;
  onBack: () => void;
  onEvidenceChange: (v: string) => void;
  onSubmitEvidence: () => void;
  onEnforceRuling: () => void;
}) {
  const consensusVerdict: ConsensusVerdict | null = verdict
    ? {
        label: verdict.label,
        colorClass: "text-positive-text",
        panelBgClass: "bg-positive/10",
        panelBorderClass: "border-positive/30",
        reasoning: verdict.reasoning,
        actions: (
          <button
            onClick={onEnforceRuling}
            className="cursor-pointer rounded-lg border-none bg-positive px-4 py-2.5 text-[13px] font-semibold text-positive-fg transition-[filter] hover:brightness-110"
          >
            Enforce Ruling On-Chain
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
        ← Back to court
      </div>
      <div className="font-display text-2xl font-bold">
        {dispute.agentA}{" "}
        <span className="font-medium text-fg-meta">vs</span> {dispute.agentB}
      </div>
      <div className="mt-2 max-w-[640px] text-sm text-fg-dim-2">
        {dispute.issue}
      </div>

      <div className="mt-7 grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <div className="mb-2.5 text-xs uppercase tracking-wide text-fg-meta">
            Evidence
          </div>
          {stage === 0 && (
            <>
              <textarea
                value={evidenceText}
                onChange={(e) => onEvidenceChange(e.target.value)}
                placeholder="Submit transaction logs, message transcripts, or a plain-language account of what happened…"
                className="min-h-[120px] w-full resize-y rounded-lg border border-border-4 bg-surface-1 p-3 font-sans text-[13px] text-fg placeholder:text-fg-faint-2"
              />
              <button
                onClick={onSubmitEvidence}
                disabled={!evidenceText.trim()}
                className="mt-2.5 cursor-pointer rounded-lg border border-border-6 bg-chip-hover px-4.5 py-2.5 text-[13px] font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default"
                style={{ opacity: evidenceText.trim() ? 1 : 0.5 }}
              >
                Submit to Validators
              </button>
            </>
          )}
        </div>

        <ConsensusPanel
          title="Internet Court Ruling"
          subtitle="3-of-3 GenVM validators review evidence and rule."
          stage={stage}
          analyzingLabel="Reviewing evidence…"
          doneLabel="Ruling recorded"
          idleText="Awaiting evidence submission…"
          verdict={consensusVerdict}
        />
      </div>
    </div>
  );
}
