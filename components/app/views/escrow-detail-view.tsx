import type { Escrow, EscrowVerdict } from "@/components/app/types";
import { StatusBadge } from "@/components/app/status-badge";
import { ChainStatusBadge } from "@/components/app/chain-status-badge";
import { activeMilestoneIndex, formatAddress } from "@/components/app/status";
import { ConsensusPanel, type ConsensusVerdict } from "@/components/app/consensus-panel";
import { LEGACY_OFFCHAIN } from "@/lib/chain-status";

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
  onFundEscrow,
  onCancelEscrow,
  submitDisabled = false,
  escalateDisabled = false,
  fundingDisabled = false,
  cancellingDisabled = false,
  releasingDisabled = false,
  connectedWalletAddress = null,
  milestoneReleased = false,
  existingDisputeId = null,
  onViewExistingDispute,
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
  // Only present once this escrow is linked to a deployed contract — see
  // the "Fund Escrow" card below.
  onFundEscrow?: () => void;
  // Same — only present once contract-linked. See the "Cancel Escrow"
  // button below for exactly when it's actually shown/usable.
  onCancelEscrow?: () => void;
  // True while an on-chain submit is mid-flight (waiting on the wallet's
  // own signing prompt / RPC round-trip) — a separate condition from
  // "text is empty," which the button already gates on its own.
  submitDisabled?: boolean;
  // True while POST /escrows/{id}/dispute is in flight.
  escalateDisabled?: boolean;
  // True while the real, payable fund_escrow transaction is mid-flight.
  fundingDisabled?: boolean;
  // True while the real cancel_escrow transaction is mid-flight.
  cancellingDisabled?: boolean;
  // True while the real release_milestone transaction is mid-flight
  // (on-chain escrows only — the legacy off-chain release has no wallet
  // round-trip to wait on).
  releasingDisabled?: boolean;
  // The currently connected wallet, or null if none — used ONLY to hide
  // Fund/Cancel from a wallet that obviously isn't the creator (both are
  // creator-gated contract-side). Added 2026-09-08 after a live test
  // showed "Fund Escrow" staying visible and signable from the
  // counterparty's own wallet — nuance-app.tsx's fundEscrow/cancelEscrow
  // handlers now also refuse this server-side-equivalent case
  // client-side before ever sending a transaction (critical for funding
  // specifically: GenVM doesn't refund a payable call's value on
  // revert), but hiding the button too avoids the confusing prompt
  // altogether rather than just rejecting it after the wallet popup.
  connectedWalletAddress?: string | null;
  // True once the active milestone's payout has actually happened — see
  // types.ts's Milestone.releasedAt. Found live, same session as the
  // wallet-check fix above: "Release Payment" kept showing (and kept
  // genuinely failing — see routers/escrows.py's _releasable_milestone
  // fix) after a real release had already gone through, since neither
  // the verdict nor the milestone's own statusKey change once released.
  milestoneReleased?: boolean;
  // Set once a Dispute already exists for this escrow (any status —
  // even a resolved one still means "already escalated once," not
  // "escalate again"). Found the same way: clicking "Escalate to
  // Internet Court" a second time for the same disagreement would file
  // a genuinely duplicate on-chain/off-chain dispute.
  existingDisputeId?: number | null;
  // Present whenever existingDisputeId is — jumps straight to that
  // dispute room instead of offering to file a new one.
  onViewExistingDispute?: () => void;
}) {
  const isConnectedAsCreator =
    connectedWalletAddress != null &&
    connectedWalletAddress.toLowerCase() === escrow.creatorAddress.toLowerCase();
  // FIXED 2026-09-12 — found live: this view offered an active-looking
  // deliverable submission form to ANY connected wallet, including a
  // total stranger to the escrow. The off-chain path's own equivalent
  // authorization gap is fixed server-side (routers/escrows.py::
  // submit_deliverable now checks this), but the on-chain path signs and
  // sends a real transaction BEFORE the contract's own identical check
  // (`gl.message.sender_address != self.counterparty`) can reject it —
  // real gas spent on a transaction that was always going to revert.
  // `null` (not connected at all) is deliberately NOT treated as "wrong
  // wallet" here: the off-chain path only needs a valid JWT, not a live
  // wallet connection, so a counterparty who's since disconnected their
  // injected wallet extension can still submit off-chain — the backend's
  // own check is what actually matters there.
  const isConnectedAsWrongWallet =
    connectedWalletAddress != null &&
    connectedWalletAddress.toLowerCase() !== escrow.counterpartyAddress.toLowerCase();
  const activeIdx = activeMilestoneIndex(escrow.milestones);
  const activeMilestone = escrow.milestones[activeIdx];
  // Same fix as ChainStatusBadge's own contractLinked prop: a submission
  // not yet made still routes on-chain if the milestone is actually
  // linked — chainStatus alone only reflects what's already happened.
  const activeMilestoneOnChain =
    (activeMilestone?.chainStatus ?? LEGACY_OFFCHAIN) !== LEGACY_OFFCHAIN ||
    (Boolean(escrow.contractAddress) && activeMilestone?.onChainIndex != null);

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
          milestoneReleased ? (
            <div className="text-xs font-medium text-fg-meta">✓ Payment already released.</div>
          ) : (
            <button
              onClick={onReleasePayment}
              disabled={releasingDisabled}
              className="cursor-pointer rounded-lg border-none bg-positive px-4 py-2.5 text-[13px] font-semibold text-positive-fg transition-[filter] hover:brightness-110 disabled:cursor-default disabled:opacity-60"
            >
              {releasingDisabled ? "Releasing…" : "Release Payment"}
            </button>
          )
        ) : existingDisputeId != null ? (
          <button
            onClick={onViewExistingDispute}
            className="cursor-pointer rounded-lg border-none bg-negative px-4 py-2.5 text-[13px] font-semibold text-white transition-[filter] hover:brightness-110"
          >
            View Dispute Room #{existingDisputeId}
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

  // Only a contract-linked, not-yet-funded escrow has anything to fund —
  // most escrows today are still off-chain (contractAddress null), and
  // once funded_tx_hash is set this app treats funding as already done
  // (see types.ts's Escrow.fundedTxHash for the caveat on what that
  // does/doesn't guarantee).
  // RE-ENABLED (2026-09-08) — the underlying bug is fixed and verified
  // against a real live Bradbury redeploy, not just code review:
  // NuanceEscrow's constructor now takes an explicit `creator` arg
  // (deploy_escrow_contract passes the real escrow.creator_address, not
  // gl.message.sender_address — see the contract's own __init__ docstring
  // for the full account of why that was wrong and cost real GEN), and a
  // fresh test deploy read back `creator` matching the real address
  // exactly, with milestone.amount correctly landing as real wei
  // (1000000000000000000, no JSON-bridge precision loss — see
  // genlayer_deploy.py's _gen_to_wei/_bigint_arg). Escrow #3 specifically
  // was redeployed under the corrected contract as part of this fix; its
  // original broken contract (and the 1 GEN stuck in it) stays abandoned.
  // isConnectedAsCreator added 2026-09-08 — see that flag's own comment
  // above for why (a live test found this staying visible/signable from
  // the wrong wallet).
  // statusKey !== "cancelled" added 2026-09-11 — fund_escrow() itself
  // already rejects a call once cancel_escrow() has run (its own guard is
  // `if self.status != "active"`, and cancel_escrow sets status to
  // "cancelled"), so this was never a fund-loss risk — just a button that
  // would stay visible and cleanly revert on submit for a cancelled
  // escrow's creator. Matches canCancel's own statusKey check below.
  const showFundCard =
    Boolean(escrow.contractAddress) &&
    !escrow.fundedTxHash &&
    escrow.statusKey !== "cancelled" &&
    isConnectedAsCreator;

  // FIXED 2026-09-12 — a real gap found live: a genuinely funded escrow
  // (5 GEN actually locked, confirmed directly against the deployed
  // contract) showed nothing at all once showFundCard above correctly
  // stopped rendering — the "Fund Escrow" card just vanished with no
  // confirmation left behind, reading as "funding silently failed"
  // rather than "funding succeeded." fundedAmount (models/core.py's
  // Escrow.funded_amount) is the one field in this app actually synced
  // from the contract's own get_escrow, not just "an ack endpoint
  // recorded a hash" — shown to everyone viewing, not creator-gated,
  // since the counterparty benefits from seeing real funds are locked
  // too.
  // FIXED 2026-09-12 (second pass) — the first fix here was itself wrong
  // in a way only a real on-chain balance check caught: it assumed a
  // cancelled escrow's funded_amount settling back to 0 meant "the real
  // refund landed." Reported live again — the creator's wallet never
  // actually received the GEN. A direct eth_getBalance against the
  // deployed contract (services/genlayer_indexer.py's contract_balance
  // sync) proved the money was still sitting at the contract's own
  // address: funded_amount is just in-contract bookkeeping that
  // cancel_escrow/release_milestone zero out unconditionally, whether or
  // not their paired emit_transfer() actually delivers the value — and it
  // currently doesn't, on any Bradbury/Asimov contract: a confirmed,
  // open GenLayer platform bug (genlayerlabs/genvm-manager#20) where
  // outbound async messages are recorded in the triggering transaction's
  // receipt but never actually executed on-chain. Not something more
  // app-level code can fix — see the "stuck" card below, which says so
  // honestly instead of repeating the contract's own optimistic
  // bookkeeping as if it were confirmed delivery.
  const isCancelledOnChain = escrow.statusKey === "cancelled" && Boolean(escrow.contractAddress);
  const isConfirmedFunded =
    Boolean(escrow.contractAddress) && !isCancelledOnChain && (escrow.fundedAmount ?? 0) > 0;
  // A fund transaction was sent (funded_tx_hash) but the indexer hasn't
  // yet confirmed the real amount against the contract — a real, if
  // usually brief, in-between state (one poll cycle, ~15s default) worth
  // its own honest label rather than silence.
  const isFundingPendingConfirmation =
    Boolean(escrow.contractAddress) &&
    !isCancelledOnChain &&
    Boolean(escrow.fundedTxHash) &&
    !isConfirmedFunded;

  // The one check in this view actually run against the chain's real
  // state instead of the contract's own self-report — see
  // Escrow.contract_balance's own docstring (models/core.py) for the full
  // account. `fundedAmount` is what the contract CLAIMS is left locked
  // right now (0 after a full cancel, or reduced by each released
  // milestone); `contractBalance` is what eth_getBalance says is
  // ACTUALLY there. A real gap between them — more sitting at the
  // contract than the contract itself thinks should be — only happens
  // when an emit_transfer the contract already recorded as done never
  // actually delivered. A tiny epsilon absorbs float rounding from the
  // Decimal->Number conversion upstream, not a real balance difference.
  const _STUCK_EPSILON = 1e-9;
  const isPayoutStuck =
    escrow.contractBalance != null &&
    escrow.fundedAmount != null &&
    escrow.contractBalance - escrow.fundedAmount > _STUCK_EPSILON;
  const hasEverBeenFunded = Boolean(escrow.fundedTxHash);
  const isRefundVerifying =
    isCancelledOnChain && hasEverBeenFunded && escrow.contractBalance == null;
  const isRefundConfirmed =
    isCancelledOnChain && hasEverBeenFunded && !isRefundVerifying && !isPayoutStuck;
  const isRefundStuck = isCancelledOnChain && hasEverBeenFunded && isPayoutStuck;

  // Client-side pre-check only, matching cancel_escrow's own on-chain
  // condition (see that method's docstring on why a deadline gate isn't
  // included: no on-chain clock exists for it to check) — hides a button
  // that would obviously fail rather than let someone pay gas to find
  // that out. The contract itself is the real enforcement either way.
  const canCancel =
    Boolean(escrow.contractAddress) &&
    escrow.statusKey !== "cancelled" &&
    !escrow.milestones.some((m) => m.statusKey === "approved") &&
    isConnectedAsCreator;

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
              {escrow.total.toLocaleString()} {escrow.asset.symbol}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <StatusBadge status={escrow.statusKey} />
          {canCancel && onCancelEscrow && (
            <button
              onClick={onCancelEscrow}
              disabled={cancellingDisabled}
              title="Refunds whatever's locked back to you — only possible before any milestone is approved."
              className="cursor-pointer rounded-lg border border-negative/30 bg-negative/10 px-3 py-1.5 text-xs font-semibold text-negative-text transition-colors hover:bg-negative/20 disabled:cursor-default disabled:opacity-60"
            >
              {cancellingDisabled ? "Cancelling…" : "Cancel & Refund"}
            </button>
          )}
        </div>
      </div>

      {showFundCard && (
        <div className="mt-5 rounded-xl border border-review/30 bg-review/10 p-4.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[13px] font-semibold text-review-text">
                Escrow contract deployed — awaiting funding
              </div>
              <div className="mt-1 text-xs text-fg-meta">
                Send {escrow.total.toLocaleString()} {escrow.asset.symbol} from your wallet into this
                escrow&rsquo;s contract before any milestone can be released.
              </div>
            </div>
            {onFundEscrow && (
              <button
                onClick={onFundEscrow}
                disabled={fundingDisabled}
                className="cursor-pointer rounded-lg border border-review/40 bg-review/20 px-4 py-2.5 text-[13px] font-semibold text-review-text transition-colors hover:bg-review/30 disabled:cursor-default disabled:opacity-60"
              >
                {fundingDisabled
                  ? "Waiting for wallet…"
                  : `Fund Escrow (${escrow.total.toLocaleString()} ${escrow.asset.symbol})`}
              </button>
            )}
          </div>
        </div>
      )}

      {isFundingPendingConfirmation && (
        <div className="mt-5 rounded-xl border border-review/30 bg-review/10 p-4.5">
          <div className="text-[13px] font-semibold text-review-text">
            Funding transaction sent — waiting for on-chain confirmation…
          </div>
          <div className="mt-1 text-xs text-fg-meta">
            This can take up to a minute. The amount shown here will update automatically once
            confirmed — no need to refresh.
          </div>
        </div>
      )}

      {isConfirmedFunded && (
        <div className="mt-5 rounded-xl border border-positive/30 bg-positive/10 p-4.5">
          <div className="text-[13px] font-semibold text-positive-text">
            ✓ Funded — {escrow.fundedAmount?.toLocaleString()} {escrow.asset.symbol} locked in the
            contract
          </div>
          <div className="mt-1 text-xs text-fg-meta">
            Verified directly against the deployed contract, not just a submitted transaction.
          </div>
        </div>
      )}

      {/* Same real-balance check as the cancel/refund cards below, applied
          to a released milestone's payout instead — release_milestone
          zeroes its own share of funded_amount and calls the identical
          emit_transfer() cancel_escrow does, so it's blocked by the same
          currently-open GenLayer platform bug (genlayerlabs/
          genvm-manager#20) whenever it fires. Shown regardless of overall
          escrow status since a milestone can be released mid-escrow. */}
      {!isCancelledOnChain && isPayoutStuck && (
        <div className="mt-5 rounded-xl border border-negative/30 bg-negative/10 p-4.5">
          <div className="text-[13px] font-semibold text-negative-text">
            ⚠ A milestone payout hasn&rsquo;t been delivered yet
          </div>
          <div className="mt-1 text-xs text-fg-meta">
            The contract recorded a release, but a currently-open GenLayer network issue is
            blocking outbound transfers from Intelligent Contracts (tracked publicly as
            genlayerlabs/genvm-manager#20) — the counterparty&rsquo;s GEN is still sitting at the
            contract&rsquo;s address for now, not lost.
          </div>
        </div>
      )}

      {/* Only shown when a fund transaction was actually sent — an escrow
          cancelled before ever being funded has nothing to refund, verify,
          or get stuck. Three real states, not one optimistic one — see
          isRefundVerifying/isRefundConfirmed/isRefundStuck above. */}
      {isRefundVerifying && (
        <div className="mt-5 rounded-xl border border-review/30 bg-review/10 p-4.5">
          <div className="text-[13px] font-semibold text-review-text">
            Cancelled on-chain — verifying refund…
          </div>
          <div className="mt-1 text-xs text-fg-meta">
            Checking the contract&rsquo;s real balance directly, not just its own status field.
          </div>
        </div>
      )}

      {isRefundConfirmed && (
        <div className="mt-5 rounded-xl border border-positive/30 bg-positive/10 p-4.5">
          <div className="text-[13px] font-semibold text-positive-text">
            ✓ Cancelled — {escrow.total.toLocaleString()} {escrow.asset.symbol} refunded to your
            wallet
          </div>
          <div className="mt-1 text-xs text-fg-meta">
            Verified against the contract&rsquo;s real on-chain balance (eth_getBalance), not just its
            own self-reported status.
          </div>
        </div>
      )}

      {/* FOUND 2026-09-12, investigating a live report that a "refunded"
          escrow's GEN never reached the wallet: this is a confirmed,
          currently-open GenLayer platform bug, not a Nuance bug —
          emit_transfer's outbound value is recorded in the transaction's
          receipt but never actually executed on-chain (see
          genlayerlabs/genvm-manager#20). The contract genuinely tried to
          send it back; the network hasn't delivered it. No app-level fix
          exists yet — this says so honestly instead of claiming the money
          moved. */}
      {isRefundStuck && (
        <div className="mt-5 rounded-xl border border-negative/30 bg-negative/10 p-4.5">
          <div className="text-[13px] font-semibold text-negative-text">
            ⚠ Cancelled on-chain — refund not yet delivered
          </div>
          <div className="mt-1 text-xs text-fg-meta">
            The contract recorded the cancellation and tried to send back{" "}
            {escrow.contractBalance?.toLocaleString()} {escrow.asset.symbol}, but a currently-open
            GenLayer network issue is blocking outbound transfers from Intelligent Contracts
            (tracked publicly as genlayerlabs/genvm-manager#20) — this isn&rsquo;t something Nuance
            can fix on its own. Your GEN is still provably at the escrow contract&rsquo;s address (
            <span className="font-brand-mono">{formatAddress(escrow.contractAddress ?? "")}</span>
            ) and will be re-checked automatically once the network delivers it.
          </div>
        </div>
      )}

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
                <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
                  <div className="font-brand-mono text-[13px] text-fg-bright">
                    {m.amount.toLocaleString()} GEN
                  </div>
                  <ChainStatusBadge
                    chainStatus={m.chainStatus ?? LEGACY_OFFCHAIN}
                    txHash={m.onChainTxHash}
                    contractLinked={Boolean(escrow.contractAddress) && m.onChainIndex != null}
                  />
                </div>

                {m.statusKey === "approved" && (
                  <div className="mt-3 rounded-lg border border-positive/30 bg-positive/10 px-3 py-2 text-xs font-medium text-positive-text">
                    <div>
                      ✓ Milestone deliverable approved by{" "}
                      {(m.chainStatus ?? LEGACY_OFFCHAIN) === LEGACY_OFFCHAIN
                        ? "Nuance's off-chain AI consensus"
                        : "real GenVM validator consensus on Bradbury"}
                      .
                    </div>
                    {/* Real validator reasoning — added 2026-09-08. Used
                        to be discarded entirely for on-chain milestones
                        (see models/core.py's Milestone.reasoning), so
                        this text was only ever visible by reading the
                        raw chain explorer directly. */}
                    {m.reasoning && (
                      <div className="mt-1.5 border-t border-positive/20 pt-1.5 font-normal text-fg-bright">
                        {m.reasoning}
                      </div>
                    )}
                  </div>
                )}

                {m.statusKey === "disputed" && (
                  <div className="mt-3 rounded-lg border border-negative/30 bg-negative/10 px-3 py-2 text-xs font-medium text-negative-text">
                    <div>
                      ⚠ Milestone deliverable disputed by{" "}
                      {(m.chainStatus ?? LEGACY_OFFCHAIN) === LEGACY_OFFCHAIN
                        ? "Nuance's off-chain AI consensus"
                        : "real GenVM validator consensus on Bradbury"}
                      .
                    </div>
                    {m.reasoning && (
                      <div className="mt-1.5 border-t border-negative/20 pt-1.5 font-normal text-fg-bright">
                        {m.reasoning}
                      </div>
                    )}
                  </div>
                )}

                {isActive &&
                  stage === 0 &&
                  (m.statusKey === "pending" || m.statusKey === "in_progress") &&
                  escrow.statusKey !== "approved" &&
                  escrow.statusKey !== "disputed" &&
                  // FIXED 2026-09-12 — a cancelled escrow's still-"pending"
                  // milestone (cancellation only ever touches the Escrow
                  // row's own statusKey, see types.ts) kept showing this as
                  // if the deal were still live. Both submission endpoints
                  // now reject this too (belt-and-suspenders, not
                  // duplicated trust) — this just stops the doomed attempt
                  // before it starts.
                  escrow.statusKey !== "cancelled" && (
                    <div className="mt-3.5 border-t border-border-1 pt-3.5">
                      {isConnectedAsWrongWallet ? (
                        <div className="text-xs text-fg-meta">
                          Connect the counterparty&rsquo;s wallet (
                          {formatAddress(escrow.counterpartyAddress)}) to submit a deliverable.
                        </div>
                      ) : (
                        <>
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
                        </>
                      )}
                    </div>
                  )}
              </div>
            );
          })}
        </div>

        <ConsensusPanel
          title={activeMilestoneOnChain ? "GenVM Validator Consensus" : "AI Validator Consensus"}
          subtitle={
            activeMilestoneOnChain
              ? "3-of-3 real GenVM validators on Bradbury adjudicate this milestone on-chain."
              : "Nuance's own off-chain AI review adjudicates this milestone — not GenVM."
          }
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
