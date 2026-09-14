// Honest chain-status UI copy — the piece ROADMAP.md 4.5/4.6 calls out
// explicitly: GenLayer's real transaction lifecycle has an Accepted stage
// that is *not* settlement (there's an appeal window before Finalized), so
// nothing here is allowed to say something is done until it actually is.
//
// Every status name and helper below (DECIDED_STATES/isDecidedState,
// TransactionStatus, TransactionResult) is read straight from the
// installed genlayer-js package's own type definitions
// (node_modules/genlayer-js/dist/index-C3Ul1Rte.d.ts), not the docs site —
// an earlier draft of this file trusted a docs-page summary that turned
// out to describe a different/older API shape (a `fees`-based write call,
// a `lifecycle` field, `waitForFinalization`) than what's actually
// installed. Verified against genlayer-js@1.1.8 on 2026-09-04; genlayer-js
// is pre-mainnet and evolving, so re-check this against whatever version
// is installed before relying on it again.

import {
  TransactionStatus,
  TransactionResult,
  isDecidedState,
  transactionsStatusNameToNumber,
} from "genlayer-js/types";

// A pre-cutover (or simply not-yet-on-chain) escrow/dispute/prediction —
// the existing FastAPI + services/consensus.py path, nothing about it is
// GenLayer transaction state at all. Distinct from every TransactionStatus
// value so the UI can never accidentally render on-chain language for it.
export const LEGACY_OFFCHAIN = "legacy_offchain" as const;

// The four-bucket simplification this app's UI actually needs — genlayer-js
// itself has no such collapsed field (that was the earlier draft's
// mistake); this maps its real 14-value TransactionStatus enum down to
// what a bettor/counterparty needs to know at a glance.
export type ChainStatusBucket =
  | "processing" // UNINITIALIZED, PENDING, PROPOSING, COMMITTING, REVEALING
  | "decided"    // isDecidedState(status) — includes ACCEPTED and both APPEAL_* states: a
                  // decision exists but the appeal window (or finalization) hasn't closed
  | "finalized"  // FINALIZED
  | "canceled";  // CANCELED, VALIDATORS_TIMEOUT, LEADER_TIMEOUT

export type ChainStatus = ChainStatusBucket | typeof LEGACY_OFFCHAIN;

export interface ChainStatusMeta {
  label: string;
  detail: string;
  // Same three-way badge language the rest of the app already uses
  // (status.ts's StatusMeta) — positive/review/neutral, not a fourth palette.
  tone: "positive" | "review" | "neutral";
}

const CHAIN_STATUS_META: Record<ChainStatus, ChainStatusMeta> = {
  processing: {
    label: "Submitted",
    detail: "Sent to GenLayer validators — awaiting a decision.",
    tone: "review",
  },
  decided: {
    label: "Accepted, finalizing…",
    detail:
      "Validators reached a decision. Still inside the appeal window — not yet final.",
    tone: "review",
  },
  finalized: {
    label: "Finalized",
    detail: "Appeal window closed. This result is settled on-chain.",
    tone: "positive",
  },
  canceled: {
    label: "Canceled",
    detail: "This transaction did not complete (canceled, or a validator/leader timeout).",
    tone: "neutral",
  },
  [LEGACY_OFFCHAIN]: {
    label: "Off-chain",
    detail: "Ruled by Nuance's backend consensus engine, not a GenLayer contract.",
    tone: "neutral",
  },
};

export function chainStatusMeta(status: ChainStatus): ChainStatusMeta {
  return CHAIN_STATUS_META[status] ?? CHAIN_STATUS_META[LEGACY_OFFCHAIN];
}

// Buckets a real GenLayerTransaction's `statusName` — use
// isDecidedState(status), genlayer-js's own export, rather than
// hand-listing which of the 14 raw values counts as "decided"; that list
// is the SDK's to maintain, not ours to duplicate and let drift.
//
// FIXED 2026-09-14 — a real, live bug found verifying real GEN-staked
// governance voting end-to-end: a freshly created on-chain proposal's
// create_proposal tx reached ACCEPTED (5/5 validators AGREE — a genuine
// decision, still inside the appeal window) and sat there, never
// bucketed past "processing", so resolve_pending_proposal_ids (backend/
// app/services/genlayer_indexer.py) never got to resolve its
// on_chain_proposal_id until the tx reached FINALIZED outright — and the
// UI's "Accepted, finalizing…" badge above could never actually appear
// for ANY escrow/dispute/prediction/proposal transaction, on any of the
// four detail views that render it.
//
// Root cause, confirmed directly against the installed genlayer-js@1.1.8
// source (node_modules/genlayer-js/dist/chunk-EY35NPSE.js): despite its
// .d.ts declaring `isDecidedState(status: string)`, the real
// implementation is `DECIDED_STATES.some(state =>
// transactionsStatusNameToNumber[state] === status)` — it compares
// against the STRINGIFIED NUMERIC code ("5"), not the status NAME
// ("ACCEPTED") this file (correctly, per the .d.ts) was passing it.
// isDecidedState("ACCEPTED") is unconditionally false in this version;
// isDecidedState("5") is true. Re-verify this exact behavior before
// trusting it again if genlayer-js is ever upgraded — a fixed .d.ts/impl
// mismatch would make this translation step dead weight, not wrong.
function isDecidedStatusName(statusName: TransactionStatus): boolean {
  const numericCode = transactionsStatusNameToNumber[statusName];
  return numericCode !== undefined && isDecidedState(numericCode);
}

export function bucketFromStatusName(statusName: TransactionStatus): ChainStatusBucket {
  if (statusName === TransactionStatus.FINALIZED) return "finalized";
  if (
    statusName === TransactionStatus.CANCELED ||
    statusName === TransactionStatus.VALIDATORS_TIMEOUT ||
    statusName === TransactionStatus.LEADER_TIMEOUT
  ) {
    return "canceled";
  }
  if (isDecidedStatusName(statusName)) return "decided";
  return "processing"; // UNINITIALIZED, PENDING, PROPOSING, COMMITTING, REVEALING
}

// "Reached FINALIZED" doesn't by itself mean the contract call succeeded —
// check resultName too (TransactionResult.SUCCESS | FAILURE), set once the
// transaction has actually executed. Undefined until then.
export function isSuccessfulResult(resultName: TransactionResult | undefined): boolean {
  return resultName === TransactionResult.SUCCESS;
}
