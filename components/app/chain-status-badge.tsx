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
  className = "",
}: {
  chainStatus: ChainStatus;
  txHash?: string | null;
  className?: string;
}) {
  const meta = chainStatusMeta(chainStatus);
  const isOnChain = chainStatus !== LEGACY_OFFCHAIN;

  return (
    <div className={`inline-flex flex-col gap-1 ${className}`}>
      <div
        className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${TONE_CLASSES[meta.tone]}`}
        title={meta.detail}
      >
        <span>{isOnChain ? "⛓" : "🗄"}</span>
        <span>
          {isOnChain ? "On-Chain (GenLayer Bradbury)" : "Legacy Off-Chain (Demo/Cached)"}
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
