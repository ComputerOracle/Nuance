// Makes the on-chain/off-chain distinction visible everywhere a
// milestone/dispute/prediction is shown — previously nowhere in the UI,
// despite lib/chain-status.ts's own honest vocabulary already existing
// for exactly this (built, never wired in). Every escrow/dispute/
// prediction still defaults to LEGACY_OFFCHAIN (Nuance's own backend
// consensus engine deciding it) unless it's actually linked to a
// deployed GenVM contract and a real transaction has actually been sent
// against it — this badge is the one place that distinction is now
// unambiguous rather than conflated under one "AI Validator Consensus"
// label regardless of which path actually judged it.
import { chainStatusMeta, LEGACY_OFFCHAIN, type ChainStatus } from "@/lib/chain-status";
import { blockExplorerTxUrl } from "@/components/app/genlayer-chain";

const TONE_CLASSES: Record<"positive" | "review" | "neutral", string> = {
  positive: "bg-positive/16 text-positive-text border-positive/30",
  review: "bg-review/18 text-review-text border-review/30",
  neutral: "bg-neutral text-pending-text border-border-4",
};

function truncateHash(hash: string): string {
  return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
}

export function ChainStatusBadge({
  chainStatus,
  txHash,
  // Real bug fixed 2026-09-08, caught live: chainStatus alone conflates
  // two different things. "legacy_offchain" means BOTH "never linked to
  // a contract at all" AND "linked, but nothing's been submitted to it
  // yet" (chain_status only updates once a real transaction lands — see
  // services/genlayer_indexer.py). Without this flag, a milestone/
  // dispute/prediction that's fully wired for the real thing but simply
  // hasn't been tried yet got told to the user as "off-chain," which is
  // actively wrong: submitting it WILL go through GenVM. Pass true
  // whenever the underlying contract_address/on_chain_index (or
  // equivalent) is actually set, regardless of chainStatus.
  contractLinked = false,
  className = "",
}: {
  chainStatus: ChainStatus;
  txHash?: string | null;
  contractLinked?: boolean;
  className?: string;
}) {
  const meta = chainStatusMeta(chainStatus);
  const isOnChain = chainStatus !== LEGACY_OFFCHAIN;
  const isReadyButUntried = !isOnChain && contractLinked;

  return (
    <div className={`inline-flex flex-col gap-1 ${className}`}>
      <div
        className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
          isReadyButUntried ? TONE_CLASSES.review : TONE_CLASSES[meta.tone]
        }`}
        title={
          isReadyButUntried
            ? "Linked to a real deployed contract — the next action here will be a real on-chain transaction, judged by real GenVM validators. Nothing's been submitted to it yet."
            : meta.detail
        }
      >
        <span>{isOnChain || isReadyButUntried ? "⛓" : "🗄"}</span>
        <span>
          {isOnChain
            ? "On-Chain (GenLayer Bradbury)"
            : isReadyButUntried
              ? "On-Chain Ready (not yet submitted)"
              : "Legacy Off-Chain (Demo/Cached)"}
        </span>
        {isOnChain && <span className="opacity-70">· {meta.label}</span>}
      </div>
      {isOnChain && txHash && (
        <a
          href={blockExplorerTxUrl(txHash)}
          target="_blank"
          rel="noreferrer"
          className="w-fit font-mono text-[10px] text-info hover:underline"
        >
          {truncateHash(txHash)} ↗
        </a>
      )}
    </div>
  );
}
