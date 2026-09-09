import type { AgentCase, AgentDirectoryEntry } from "@/components/app/types";
import { formatAddress } from "@/components/app/status";

function scoreColorClass(score: number): string {
  if (score >= 70) return "text-positive-text";
  if (score >= 50) return "text-warn-text";
  return "text-negative-text";
}

function addressTag(address: string): string {
  return address.replace(/^0x/i, "").slice(0, 2).toUpperCase();
}

function formatCaseDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/**
 * ROADMAP.md Part 4's Real Agent Directory "transaction drill-down" —
 * AgentsView's own list only ever showed the aggregate trust_score;
 * clicking a row had nowhere to go. Backs onto GET /agents/{wallet}/
 * history (routers/agents.py), which is itself real ConsensusJob
 * history, not seed data — same as the aggregate stat it explains.
 */
export function AgentDetailView({
  agent,
  cases,
  casesLoading,
  casesError,
  onBack,
  onOpenEscrow,
  onOpenDispute,
}: {
  agent: AgentDirectoryEntry;
  cases: AgentCase[];
  casesLoading: boolean;
  casesError: string | null;
  onBack: () => void;
  onOpenEscrow: (escrowId: number) => void;
  onOpenDispute: (disputeId: number) => void;
}) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div
        onClick={onBack}
        className="mb-4.5 inline-block cursor-pointer text-sm text-fg-meta transition-colors hover:text-fg"
      >
        ← Back to Agent Directory
      </div>

      <div className="mb-7 flex items-center justify-between rounded-[14px] border border-border-1 bg-surface-1 p-5">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] border border-border-6 bg-chip-hover text-sm font-bold">
            {addressTag(agent.walletAddress)}
          </div>
          <div>
            <div className="font-brand-mono text-base font-semibold" title={agent.walletAddress}>
              {formatAddress(agent.walletAddress)}
            </div>
            <div className="mt-0.5 text-xs text-fg-meta">
              {agent.category} · {agent.casesJudged} case{agent.casesJudged === 1 ? "" : "s"} judged
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className={`font-display text-2xl font-bold ${scoreColorClass(agent.trustScore)}`}>
            {agent.trustScore}
          </div>
          <div className="text-[11px] text-fg-meta">trust score</div>
        </div>
      </div>

      <div className="mb-3 text-lg font-semibold">Case History</div>

      {casesLoading ? (
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-6 text-center text-sm text-fg-meta">
          Loading case history…
        </div>
      ) : casesError ? (
        <div className="rounded-[14px] border border-negative/30 bg-negative/10 p-4 text-sm text-negative-text">
          {casesError}
        </div>
      ) : cases.length === 0 ? (
        <div className="rounded-[14px] border border-dashed border-border-4 bg-surface-1/50 p-6 text-center text-sm text-fg-meta">
          No judged cases yet for this wallet.
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {cases.map((c) => (
            <div
              key={c.consensusJobId}
              className="rounded-[14px] border border-border-1 bg-surface-1 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-fg-meta">
                    <span className="rounded bg-chip-hover px-1.5 py-0.5 font-sans">
                      {c.subjectType === "milestone" ? "Milestone" : "Dispute"}
                    </span>
                    {c.completedAt && <span>{formatCaseDate(c.completedAt)}</span>}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-fg">{c.title}</div>
                  {c.verdictReasoning && (
                    <div className="mt-1.5 text-xs leading-relaxed text-fg-dim-2">{c.verdictReasoning}</div>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <div
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      c.verdictApproved
                        ? "bg-positive/16 text-positive-text"
                        : "bg-negative/16 text-negative-text"
                    }`}
                  >
                    {c.verdictApproved ? "Approved" : "Disputed"}
                    {c.verdictConfidence != null ? ` · ${c.verdictConfidence}%` : ""}
                  </div>
                  <button
                    onClick={() =>
                      c.subjectType === "dispute" && c.disputeId != null
                        ? onOpenDispute(c.disputeId)
                        : onOpenEscrow(c.escrowId)
                    }
                    className="cursor-pointer text-[11px] font-medium text-fg-meta underline underline-offset-2 transition-colors hover:text-fg"
                  >
                    View {c.subjectType === "dispute" ? "dispute" : "escrow"} →
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
