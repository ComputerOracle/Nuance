import type { Proposal } from "@/components/app/types";

const VOTE_LABEL: Record<"for" | "against" | "abstain", string> = {
  for: "For",
  against: "Against",
  abstain: "Abstain",
};

export function GovernanceView({
  proposals,
  walletConnected,
  pendingVoteId,
  onVote,
}: {
  proposals: Proposal[];
  walletConnected: boolean;
  pendingVoteId: number | null;
  onVote: (id: number, choice: "For" | "Against") => void;
}) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="font-display text-[30px] font-bold">Governance</div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        Plain-language proposals interpreted and enforced by AI consensus.
      </div>

      <div className="flex flex-col gap-3">
        {proposals.map((pr) => {
          const voted = pr.userVote;
          const isPending = pendingVoteId === pr.id;
          const canVote = pr.status === "Active" && !voted && walletConnected && !isPending;
          return (
            <div
              key={pr.id}
              className="rounded-[14px] border border-border-1 bg-surface-1 p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="max-w-[520px]">
                  <div className="text-[15px] font-semibold">{pr.title}</div>
                  <div className="mt-0.5 text-[11px] text-fg-meta">{pr.category}</div>
                </div>
                <div
                  className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                    pr.status === "Active"
                      ? "bg-review/18 text-review-text"
                      : "bg-neutral text-pending-text"
                  }`}
                >
                  {pr.status === "Active" ? "Active" : pr.rawStatus}
                </div>
              </div>
              <div className="mt-2 text-[13px] leading-relaxed text-fg-meta">
                {pr.summary}
              </div>
              <div className="mt-3.5 flex h-2 gap-1 overflow-hidden rounded-md">
                <div className="bg-positive" style={{ width: `${pr.forPct}%` }} />
                <div className="bg-negative" style={{ width: `${pr.againstPct}%` }} />
              </div>
              <div className="mt-1.5 flex justify-between text-xs text-fg-meta">
                <span>For {pr.forPct}%</span>
                <span>Against {pr.againstPct}%</span>
              </div>

              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-fg-meta">
                <span>
                  Turnout {pr.turnoutPct}% · needs {pr.quorumThreshold}% quorum
                  {" "}
                  {pr.quorumMet ? (
                    <span className="text-positive-text">(met)</span>
                  ) : (
                    <span>(not met)</span>
                  )}
                </span>
                <span>Needs {pr.passThreshold}% of decided votes to pass</span>
              </div>

              {canVote && (
                <div className="mt-3.5 flex gap-2.5">
                  <button
                    onClick={() => onVote(pr.id, "For")}
                    className="flex-1 cursor-pointer rounded-lg border border-positive/40 bg-positive/12 py-2.5 text-[13px] font-semibold text-positive-text"
                  >
                    Vote For
                  </button>
                  <button
                    onClick={() => onVote(pr.id, "Against")}
                    className="flex-1 cursor-pointer rounded-lg border border-negative/40 bg-negative/12 py-2.5 text-[13px] font-semibold text-negative-text"
                  >
                    Vote Against
                  </button>
                </div>
              )}
              {isPending && (
                <div className="mt-3 text-xs text-fg-meta">Submitting vote…</div>
              )}
              {voted && !isPending && (
                <div className="mt-3 text-xs text-fg-meta">✓ You voted {VOTE_LABEL[voted]}</div>
              )}
              {pr.status === "Active" && !voted && !walletConnected && !isPending && (
                <div className="mt-3 text-xs text-fg-meta">Connect a wallet to vote.</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
