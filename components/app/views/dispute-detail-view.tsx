import { useEffect, useMemo, useRef, useState } from "react";
import type { Dispute, DisputeEvidence, DisputeMessage, DisputeVerdict } from "@/components/app/types";
import { ConsensusPanel, type ConsensusVerdict } from "@/components/app/consensus-panel";
import { ChainStatusBadge } from "@/components/app/chain-status-badge";
import { formatAddress } from "@/components/app/status";
import { useDisputeMessages } from "@/components/app/use-dispute-messages";
import { LEGACY_OFFCHAIN } from "@/lib/chain-status";
import * as api from "@/lib/api";

export function DisputeDetailView({
  dispute,
  stage,
  verdict,
  currentWalletAddress,
  onBack,
  evidenceDesc,
  evidenceLink,
  onEvidenceDescChange,
  onEvidenceLinkChange,
  onSubmitEvidence,
  submittingEvidence = false,
}: {
  dispute: Dispute;
  stage: number;
  verdict: DisputeVerdict | null;
  currentWalletAddress?: string | null;
  onBack: () => void;
  // Lifted up to nuance-app.tsx 2026-09-08 (matching escrows' own
  // deliverableText pattern) — this view used to own this form's state
  // AND call api.submitEvidence directly, which is exactly why
  // submitting evidence could never route on-chain: only the parent has
  // wallet/contract access to actually do that.
  evidenceDesc: string;
  evidenceLink: string;
  onEvidenceDescChange: (v: string) => void;
  onEvidenceLinkChange: (v: string) => void;
  onSubmitEvidence: () => void;
  submittingEvidence?: boolean;
}) {
  // WS -> SSE -> polling, replacing the old 3s setInterval — see
  // use-dispute-messages.ts's own docstring (ROADMAP.md Part 3 5.2).
  const { messages: apiMessages, addOptimistic } = useDisputeMessages(dispute.id);
  const messages: DisputeMessage[] = useMemo(
    () =>
      apiMessages.map((m) => ({
        id: m.id,
        disputeId: m.dispute_id,
        senderAddress: m.sender_address,
        content: m.content,
        createdAt: m.created_at,
      })),
    [apiMessages]
  );
  const [evidenceList, setEvidenceList] = useState<DisputeEvidence[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [sendingMsg, setSendingMsg] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  // Same fix as ChainStatusBadge's own contractLinked prop elsewhere —
  // an on-chain-filed dispute needs a real link for evidence (the
  // contract's add_evidence only takes a URL), even before its
  // onChainDisputeId has resolved.
  const isOnChainFiled = (dispute.chainStatus ?? LEGACY_OFFCHAIN) !== LEGACY_OFFCHAIN;

  // Poll evidence every 4s
  useEffect(() => {
    let cancelled = false;

    const fetchEvidence = async () => {
      try {
        const data = await api.getDisputeEvidence(dispute.id);
        if (!cancelled) {
          setEvidenceList(
            data.map((e) => ({
              id: e.id,
              disputeId: e.dispute_id,
              submitterAddress: e.submitter_address,
              description: e.description,
              link: e.link,
              createdAt: e.created_at,
            }))
          );
        }
      } catch {
        // Fallback silently during polling
      }
    };

    fetchEvidence();
    const interval = setInterval(fetchEvidence, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [dispute.id]);

  // Scroll chat on new messages
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || sendingMsg) return;
    setSendingMsg(true);
    setErrorBanner(null);
    try {
      const res = await api.sendDisputeMessage(dispute.id, chatInput.trim());
      // Immediate feedback rather than waiting on the realtime round trip —
      // the authoritative push that follows (routers/disputes.py's
      // send_message publishes right after commit) is deduped by id, so
      // this doesn't double up once it arrives.
      addOptimistic(res);
      setChatInput("");
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to send message. Connect your wallet."
      );
    } finally {
      setSendingMsg(false);
    }
  };


  const consensusVerdict: ConsensusVerdict | null = verdict
    ? {
        label: verdict.label,
        colorClass: verdict.approved ? "text-positive-text" : "text-negative-text",
        panelBgClass: verdict.approved ? "bg-positive/10" : "bg-negative/10",
        panelBorderClass: verdict.approved ? "border-positive/30" : "border-negative/30",
        reasoning: verdict.reasoning,
        // No "Enforce Ruling" button — removed 2026-09-08. It's not a
        // simplification, it was dead: services/consensus.py's
        // _apply_verdict_to_state already records the ruling and unlocks/
        // locks the linked milestone the instant a real verdict lands
        // (off-chain consensus job or on-chain adjudicate_dispute, same
        // function either way) — by the time a verdict is even visible
        // here, POST /disputes/{id}/enforce has nothing left to do and
        // always 400s ("already enforced"), confirmed directly against
        // its own test (test_idempotency.py seeds a dispute bypassing
        // the real flow specifically so a first enforce call has
        // anything to succeed against). This note replaces the button —
        // nothing to click, there was never really something to do.
        actions: (
          <div className="text-xs font-medium text-fg-meta">
            ✓ Ruling recorded automatically — no further action needed.
          </div>
        ),
      }
    : null;

  const normalizedCurrent = currentWalletAddress?.toLowerCase();
  const isParticipant =
    Boolean(normalizedCurrent) &&
    (normalizedCurrent === dispute.openedByAddress.toLowerCase() ||
      normalizedCurrent === dispute.counterpartyAddress.toLowerCase());
  const isTerminal =
    dispute.statusKey === "approved" || stage === 3 || verdict !== null;

  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div
        onClick={onBack}
        className="mb-4.5 inline-block cursor-pointer text-sm text-fg-meta transition-colors hover:text-fg"
      >
        ← Back to court
      </div>

      {isTerminal && (
        <div className="mb-4 rounded-xl border border-positive/30 bg-positive/10 px-4 py-3 text-xs font-medium text-positive-text flex items-center justify-between">
          <span>
            ✓ This dispute room has been adjudicated by AI Validator Consensus and is preserved as a historical record.
          </span>
          <span className="font-mono text-[11px] font-semibold uppercase tracking-wider">
            Settled
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="font-display text-2xl font-bold">
            {formatAddress(dispute.openedByAddress)}{" "}
            <span className="font-medium text-fg-meta">vs</span>{" "}
            {formatAddress(dispute.counterpartyAddress)}
          </div>
          <div className="mt-1 text-sm text-fg-dim-2">
            Dispute Room #{dispute.id} · Stake:{" "}
            <span className="font-semibold text-fg font-brand-mono">
              {dispute.amount.toLocaleString()} GEN
            </span>
          </div>
          <div className="mt-2">
            <ChainStatusBadge
              chainStatus={dispute.chainStatus ?? LEGACY_OFFCHAIN}
              txHash={dispute.onChainTxHash}
            />
          </div>
        </div>
        <div className="rounded-full border border-border-4 bg-surface-2 px-3 py-1 text-xs font-mono text-fg-meta">
          Status: {dispute.statusKey}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-border-1 bg-surface-1 p-4">
        <div className="text-xs uppercase tracking-wide text-fg-meta">
          Issue / Reason for Dispute
        </div>
        <div className="mt-1 text-sm text-fg">{dispute.issue}</div>
      </div>

      {errorBanner && (
        <div className="mt-4 rounded-lg border border-negative/35 bg-negative/12 px-3.5 py-2.5 text-xs text-negative-text">
          {errorBanner}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        {/* Left Column: Live Chat & Evidence Repository */}
        <div className="flex flex-col gap-6">
          {/* Dispute Chat Room */}
          <div className="rounded-xl border border-border-1 bg-surface-1 flex flex-col h-[400px]">
            <div className="border-b border-border-1 px-4 py-3 flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-fg-meta">
                Dispute Room Dialogue
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-fg-meta">
                <span className="inline-block h-2 w-2 rounded-full bg-positive animate-pulse" />
                Live Feed
              </div>
            </div>

            {/* Messages Stream */}
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
              {messages.length === 0 ? (
                <div className="m-auto text-center text-xs text-fg-meta py-8">
                  No messages yet. Counterparties can state their claims here.
                </div>
              ) : (
                messages.map((m) => {
                  const isMe = normalizedCurrent && m.senderAddress.toLowerCase() === normalizedCurrent;
                  const isClaimant = m.senderAddress.toLowerCase() === dispute.openedByAddress.toLowerCase();
                  return (
                    <div
                      key={m.id}
                      className={`flex flex-col max-w-[85%] ${
                        isMe ? "self-end items-end" : "self-start items-start"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 mb-1 text-[11px] text-fg-meta font-brand-mono">
                        <span>{formatAddress(m.senderAddress)}</span>
                        {isClaimant && (
                          <span className="rounded bg-chip-hover px-1 py-0.2 text-[9px] uppercase font-sans">
                            Claimant
                          </span>
                        )}
                        {isMe && (
                          <span className="text-[10px] text-fg-dim-2 font-sans font-semibold">
                            (You)
                          </span>
                        )}
                      </div>
                      <div
                        className={`rounded-xl px-3.5 py-2 text-sm leading-relaxed ${
                          isMe
                            ? "bg-accent-solid text-white"
                            : "bg-surface-2 border border-border-4 text-fg"
                        }`}
                      >
                        {m.content}
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={chatBottomRef} />
            </div>

            {/* Chat Input or Locked / Observer State */}
            {isTerminal ? (
              <div className="border-t border-border-1 p-3 text-center text-xs text-fg-meta font-medium bg-surface-2/50">
                🔒 Dialogue is closed. Ruling has been recorded by AI Consensus.
              </div>
            ) : !isParticipant ? (
              <div className="border-t border-border-1 p-3 text-center text-xs text-fg-meta font-medium bg-surface-2/50">
                👁 Viewing as observer. Only dispute counterparties can send messages.
              </div>
            ) : (
              <form
                onSubmit={handleSendMessage}
                className="border-t border-border-1 p-3 flex gap-2"
              >
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="State your case or respond to counterparty…"
                  className="flex-1 rounded-lg border border-border-4 bg-surface-2 px-3 py-2 text-sm text-fg placeholder:text-fg-faint-2 focus:outline-none focus:border-border-6"
                />
                <button
                  type="submit"
                  disabled={!chatInput.trim() || sendingMsg}
                  className="cursor-pointer rounded-lg border border-border-6 bg-chip-hover px-4 py-2 text-xs font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default disabled:opacity-50"
                >
                  {sendingMsg ? "Sending…" : "Send"}
                </button>
              </form>
            )}
          </div>

          {/* Evidence Repository & Submission */}
          <div className="rounded-xl border border-border-1 bg-surface-1 p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-fg-meta">
                Submitted Evidence ({evidenceList.length})
              </div>
            </div>

            {evidenceList.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border-4 p-4 text-center text-xs text-fg-meta">
                No formal evidence records attached yet.
              </div>
            ) : (
              <div className="flex flex-col gap-2.5 mb-5">
                {evidenceList.map((ev) => (
                  <div
                    key={ev.id}
                    className="rounded-lg border border-border-4 bg-surface-2 p-3.5"
                  >
                    <div className="flex items-center justify-between text-xs text-fg-meta mb-1 font-brand-mono">
                      <span>Submitted by {formatAddress(ev.submitterAddress)}</span>
                      <span>{new Date(ev.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                    </div>
                    <div className="text-sm text-fg">{ev.description}</div>
                    {ev.link && (
                      <a
                        href={ev.link}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-xs text-info hover:underline font-mono"
                      >
                        🔗 View Attached Link / Spec →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Evidence Submission Form or Closed / Observer Indicator */}
            <div className="mt-4 border-t border-border-1 pt-4">
              {isTerminal ? (
                <div className="rounded-lg border border-border-4 bg-surface-2/50 p-3 text-center text-xs text-fg-meta">
                  📁 Evidence submission is closed. Case evaluation has completed.
                </div>
              ) : !isParticipant ? (
                <div className="rounded-lg border border-border-4 bg-surface-2/50 p-3 text-center text-xs text-fg-meta">
                  👁 Viewing as observer. Only dispute counterparties can submit evidence.
                </div>
              ) : (
                <>
                  <div className="mb-2 text-xs font-medium text-fg-dim-2">
                    {isOnChainFiled
                      ? "Add Evidence — Real GenVM Validators Will Fetch This URL"
                      : "Submit New Evidence & Request AI Adjudication"}
                  </div>
                  {/* On-chain disputes: the contract's own add_evidence only
                      ever takes a URL (see that method's own docstring) —
                      a free-text description has nowhere to go on-chain and
                      would never actually reach a validator, so it's not
                      offered here at all rather than silently discarded. */}
                  {!isOnChainFiled && (
                    <textarea
                      value={evidenceDesc}
                      onChange={(e) => onEvidenceDescChange(e.target.value)}
                      placeholder="Describe transaction logs, bug diffs, contract specs, or deliverables…"
                      className="min-h-[80px] w-full resize-y rounded-lg border border-border-4 bg-surface-2 p-3 font-sans text-xs text-fg placeholder:text-fg-faint-2 focus:outline-none focus:border-border-6"
                    />
                  )}
                  <input
                    value={evidenceLink}
                    onChange={(e) => onEvidenceLinkChange(e.target.value)}
                    placeholder={
                      isOnChainFiled
                        ? "Evidence URL — required, this is what validators actually fetch"
                        : "Optional link (e.g. GitHub issue, PR, Figma URL, transaction hash)"
                    }
                    className={`w-full rounded-lg border border-border-4 bg-surface-2 px-3 py-2 font-mono text-xs text-fg placeholder:text-fg-faint-2 focus:outline-none focus:border-border-6 ${isOnChainFiled ? "" : "mt-2"}`}
                  />
                  <button
                    onClick={onSubmitEvidence}
                    disabled={
                      (isOnChainFiled ? !evidenceLink.trim() : !evidenceDesc.trim()) ||
                      submittingEvidence
                    }
                    className="mt-3 cursor-pointer rounded-lg border border-border-6 bg-chip-hover px-4 py-2.5 text-xs font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default disabled:opacity-50"
                  >
                    {submittingEvidence
                      ? isOnChainFiled
                        ? "Signing & Sending On-Chain…"
                        : "Submitting to Validators…"
                      : isOnChainFiled
                        ? "Add Evidence On-Chain"
                        : "Submit Evidence & Deliberate"}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: AI Validator Consensus Panel */}
        <div>
          <ConsensusPanel
            title={
              (dispute.chainStatus ?? LEGACY_OFFCHAIN) !== LEGACY_OFFCHAIN
                ? "Internet Court Ruling"
                : "Off-Chain Dispute Review"
            }
            subtitle={
              (dispute.chainStatus ?? LEGACY_OFFCHAIN) !== LEGACY_OFFCHAIN
                ? "3-of-3 real GenVM validators on Bradbury evaluate dialogue and evidence — on-chain."
                : "Nuance's own off-chain AI review evaluates dialogue and evidence — not GenVM's Internet Court."
            }
            stage={stage}
            analyzingLabel="Reviewing chat history & evidence…"
            doneLabel="Ruling recorded"
            idleText="Awaiting evidence submission to initiate deliberation…"
            verdict={consensusVerdict}
            sticky
          />
        </div>
      </div>
    </div>
  );
}
