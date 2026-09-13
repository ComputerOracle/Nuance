import type { Proposal } from "@/components/app/types";

const VOTE_LABEL: Record<"for" | "against" | "abstain", string> = {
  for: "For",
  against: "Against",
  abstain: "Abstain",
};

// Quick-pick GEN amounts for an on-chain vote — informational presets
// only (unlike prediction bets' fixed BET_AMOUNTS_MILLI_GEN, the backend
// accepts any positive amount), so a free-text input still exists
// alongside these for anything else.
const VOTE_AMOUNT_PRESETS = ["0.5", "1", "2", "5"];

export function GovernanceView({
  proposals,
  walletConnected,
  pendingVoteId,
  onVote,
  voteAmounts,
  onVoteAmountChange,
  pendingRetractId,
  onRetractVote,
  pendingExecuteId,
  onExecute,
}: {
  proposals: Proposal[];
  walletConnected: boolean;
  pendingVoteId: number | null;
  onVote: (id: number, choice: "For" | "Against" | "Abstain") => void;
  // Per-proposal GEN amount input — see nuance-app.tsx's own comment on
  // why this is a Record, not a single shared value.
  voteAmounts: Record<number, string>;
  onVoteAmountChange: (id: number, value: string) => void;
  pendingRetractId: number | null;
  onRetractVote: (id: number) => void;
  pendingExecuteId: number | null;
  onExecute: (id: number) => void;
}) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="font-display text-[30px] font-bold">Governance</div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        Plain-language proposals interpreted and enforced by AI consensus.
      </div>

      <div className="flex flex-col gap-3">
        {proposals.map((pr) => {
          // FIXED 2026-09-13 — real, GEN-staked on-chain voting (asked
          // directly: "any user that vote and unvote you will have to
          // use Gen token ... like a real Governance"). A proposal
          // linked to (or queued to link to) the shared NuanceGovernance
          // registry routes through a different flow than the legacy
          // off-chain one below — see nuance-app.tsx::vote's own guard,
          // which mirrors backend/app/routers/governance.py::cast_vote's
          // server-side rejection of the off-chain endpoint for either
          // state.
          // FIXED 2026-09-13 — a real bug found live: on_chain_proposal_id
          // is a real on-chain index starting at 0, and Boolean(0) is
          // false — the very first linked proposal (id 0) rendered as if
          // it were still off-chain (plain Vote For/Against buttons, no
          // GEN amount input), and clicking them then hit nuance-app.tsx's
          // off-chain guard, which correctly 503'd against a UI state
          // that should never have been shown. != null leaves 0 alone.
          const isOnChain = pr.onChainProposalId != null;
          const isDeploying = Boolean(pr.isDeployingOnChain) && !isOnChain;
          const voted = pr.userVote;
          const isPending = pendingVoteId === pr.id;
          const isRetracting = pendingRetractId === pr.id;
          const amount = voteAmounts[pr.id] ?? "";
          const canVoteOffChain =
            !isOnChain &&
            !isDeploying &&
            pr.status === "Active" &&
            !voted &&
            walletConnected &&
            !isPending;
          const canVoteOnChain =
            isOnChain &&
            pr.status === "Active" &&
            !voted &&
            walletConnected &&
            !isPending &&
            !isRetracting;
          const canRetract = isOnChain && voted && walletConnected && !isRetracting && !isPending;
          const isExecuting = pendingExecuteId === pr.id;
          const canExecute = pr.rawStatus === "passed" && walletConnected && !isExecuting;
          return (
            <div
              key={pr.id}
              className="rounded-[14px] border border-border-1 bg-surface-1 p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="max-w-[520px]">
                  <div className="text-[15px] font-semibold">{pr.title}</div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-fg-meta">
                    <span>{pr.category}</span>
                    {(isOnChain || isDeploying) && (
                      <span className="rounded-md border border-review/30 bg-review/10 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-review-text">
                        {isOnChain ? "On-Chain" : "Deploying"}
                      </span>
                    )}
                  </div>
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
                <span>For {pr.forPct}%{isOnChain ? ` (${pr.totalFor} GEN)` : ""}</span>
                <span>Against {pr.againstPct}%{isOnChain ? ` (${pr.totalAgainst} GEN)` : ""}</span>
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

              {isDeploying && (
                <div className="mt-3.5 rounded-lg border border-review/30 bg-review/10 p-2.5 text-xs text-review-text">
                  ⏳ Deploying on-chain — voting opens automatically once the real
                  governance contract is live (usually within a few minutes).
                </div>
              )}

              {canVoteOnChain && (
                <div className="mt-3.5">
                  <div className="mb-2 text-[11px] uppercase tracking-wide text-fg-meta">
                    Stake GEN to vote
                  </div>
                  <div className="mb-2 flex flex-wrap gap-2">
                    {VOTE_AMOUNT_PRESETS.map((preset) => (
                      <button
                        key={preset}
                        onClick={() => onVoteAmountChange(pr.id, preset)}
                        className={`cursor-pointer rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                          amount === preset
                            ? "border-positive/60 bg-positive/15 text-positive-text"
                            : "border-border-4 bg-surface-3 text-fg-bright hover:bg-chip-hover"
                        }`}
                      >
                        {preset} GEN
                      </button>
                    ))}
                    <input
                      type="number"
                      min="0"
                      step="0.001"
                      value={amount}
                      onChange={(e) => onVoteAmountChange(pr.id, e.target.value)}
                      placeholder="Custom GEN"
                      className="w-28 rounded-lg border border-border-4 bg-surface-3 px-2.5 py-1.5 text-xs text-fg-bright placeholder:text-fg-faint-2 focus:outline-none focus:border-border-6"
                    />
                  </div>
                  <div className="flex gap-2.5">
                    <button
                      onClick={() => onVote(pr.id, "For")}
                      className="flex-1 cursor-pointer rounded-lg border border-positive/40 bg-positive/12 py-2.5 text-[13px] font-semibold text-positive-text disabled:cursor-default disabled:opacity-50"
                      disabled={!amount || Number(amount) <= 0}
                    >
                      Vote For
                    </button>
                    <button
                      onClick={() => onVote(pr.id, "Against")}
                      className="flex-1 cursor-pointer rounded-lg border border-negative/40 bg-negative/12 py-2.5 text-[13px] font-semibold text-negative-text disabled:cursor-default disabled:opacity-50"
                      disabled={!amount || Number(amount) <= 0}
                    >
                      Vote Against
                    </button>
                    <button
                      onClick={() => onVote(pr.id, "Abstain")}
                      className="flex-1 cursor-pointer rounded-lg border border-border-6 bg-surface-2 py-2.5 text-[13px] font-semibold text-fg disabled:cursor-default disabled:opacity-50"
                      disabled={!amount || Number(amount) <= 0}
                    >
                      Abstain
                    </button>
                  </div>
                </div>
              )}
              {canVoteOffChain && (
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
                <div className="mt-3 text-xs text-fg-meta">
                  {isOnChain ? "Signing and sending your vote…" : "Submitting vote…"}
                </div>
              )}
              {voted && !isPending && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-positive/30 bg-positive/10 px-3 py-2 text-xs text-positive-text">
                  <span>
                    ✓ You voted {VOTE_LABEL[voted]}
                    {isOnChain && pr.userVoteStakeGen != null
                      ? ` — ${pr.userVoteStakeGen} GEN staked`
                      : ""}
                  </span>
                  {canRetract && (
                    <button
                      onClick={() => onRetractVote(pr.id)}
                      className="cursor-pointer rounded-md border border-border-6 bg-surface-2 px-2.5 py-1 font-semibold text-fg hover:bg-chip-hover"
                    >
                      Retract Vote
                    </button>
                  )}
                  {isRetracting && <span>Retracting…</span>}
                </div>
              )}
              {pr.status === "Active" && !voted && !walletConnected && !isPending && !isDeploying && (
                <div className="mt-3 text-xs text-fg-meta">Connect a wallet to vote.</div>
              )}

              {canExecute && (
                <button
                  onClick={() => onExecute(pr.id)}
                  className="mt-3.5 w-full cursor-pointer rounded-lg border border-border-6 bg-surface-2 py-2.5 text-[13px] font-semibold text-fg"
                >
                  Execute Proposal
                </button>
              )}
              {isExecuting && (
                <div className="mt-3 text-xs text-fg-meta">Executing…</div>
              )}
              {pr.rawStatus === "passed" && !walletConnected && !isExecuting && (
                <div className="mt-3 text-xs text-fg-meta">Connect a wallet to execute.</div>
              )}
              {pr.rawStatus === "executed" && (
                <div className="mt-3 text-xs text-fg-meta">✓ Executed</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
