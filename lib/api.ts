// Strongly-typed fetch wrapper around the Nuance FastAPI backend.
//
// Owns: the JWT (localStorage), attaching it to every request, reacting to
// a 401 by dropping it and notifying whoever registered as the
// "unauthorized" handler (see setUnauthorizedHandler — wired up by
// use-wallet-connection.ts so an expired/invalid session also disconnects
// the wallet), and the raw backend DTO shapes (snake_case, matching
// backend/app/schemas.py exactly). UI-shape mapping into this app's own
// Escrow/Dispute/Milestone types happens in nuance-app.tsx, not here.

import type { StatusKey } from "@/components/app/types";

// FOUND 2026-09-14, live on the first real Vercel/Render deploy: every
// path passed to apiFetch below already starts with "/" (see every
// call site in this file), and NEXT_PUBLIC_API_URL is exactly what a
// host's dashboard (Render's included) tends to hand you WITH a
// trailing slash when you copy it. `${API_BASE}${path}` then builds a
// real double-slash URL ("https://host.example//proposals") — FastAPI
// treats that as a different, nonexistent route and 404s it. That one
// stray trailing slash silently broke every single request the entire
// deployed app made, not just one page — replace() here so a trailing
// slash in the configured URL (or one added by a future host, or a
// stray edit) can never do that again.
const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010").replace(/\/+$/, "");

const TOKEN_STORAGE_KEY = "nuance_token";

// --- Token storage -----------------------------------------------------

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    // Private-browsing / storage-disabled contexts can throw on access.
    return null;
  }
}

function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Session just won't persist — not fatal.
  }
}

function clearStoredToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // see setToken
  }
}

/** True once a JWT has been stored by a successful verifySignature(). */
export function hasAuthToken(): boolean {
  return getToken() !== null;
}

/** Explicit drop — called on wallet disconnect so no stale session survives it. */
export function clearAuthToken(): void {
  clearStoredToken();
}

// --- Unauthorized handling ------------------------------------------------

type UnauthorizedListener = () => void;
let unauthorizedListener: UnauthorizedListener | null = null;

/** Registered once by useWalletConnection so a 401 from anywhere can drop
 * the wallet's connected state — this module has no React state of its own. */
export function setUnauthorizedHandler(listener: UnauthorizedListener | null): void {
  unauthorizedListener = listener;
}

// --- Core request wrapper --------------------------------------------------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// FastAPI error bodies are either {"detail": "message"} or, on a 422
// validation failure, {"detail": [{"msg": "...", ...}, ...]}.
function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) =>
          d && typeof d === "object" && "msg" in d
            ? String((d as { msg: unknown }).msg)
            : String(d)
        )
        .join("; ");
    }
  }
  return fallback;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    clearStoredToken();
    unauthorizedListener?.();
  }

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // Non-JSON error body (e.g. a proxy's HTML error page) — fall through.
    }
    throw new ApiError(
      res.status,
      errorMessage(body, res.statusText || `Request failed (${res.status})`)
    );
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- Backend DTOs (snake_case — mirrors backend/app/schemas.py) -----------

// Mirrors backend/app/enums.py's ChainStatus — see that enum's own
// docstring for why this vocabulary has to match lib/chain-status.ts's
// ChainStatus exactly rather than be re-derived here.
export type ApiChainStatus = "legacy_offchain" | "processing" | "decided" | "finalized" | "canceled";

export interface ApiMilestone {
  id: number;
  name: string;
  amount: string; // Decimal, serialized as a string (e.g. "500.00")
  status_key: StatusKey;
  criteria: string;
  order_index: number;
  // Null until this milestone is linked to an index inside its escrow's
  // deployed NuanceEscrow contract — see lib/chain-config.ts's
  // milestoneIsOnChain(). Not the same number as `id`/`order_index`.
  on_chain_index: number | null;
  chain_status: ApiChainStatus;
  on_chain_tx_hash: string | null;
  // The validator committee's own stated reasoning for approving/
  // disputing this milestone — real GenVM validator text once linked
  // on-chain, or the off-chain ensemble's text otherwise. See
  // models/core.py's Milestone.reasoning for why this didn't exist
  // before (silently discarded for on-chain milestones specifically).
  reasoning: string | null;
  // Set once this milestone has actually been paid out via POST
  // /escrows/{id}/release — see models/core.py's Milestone.released_at.
  // Null means either not yet approved, or approved but not released.
  released_at: string | null;
}

// ROADMAP.md Part 4 6.2's multi-token collateral — the settlement
// currency an escrow's total/milestone amounts are denominated in. Every
// escrow has one (server_default points existing rows at native GEN, id
// 1 — see models/core.py::Asset's own docstring), so this is never null.
export interface ApiAsset {
  id: number;
  symbol: string;
  decimals: number;
  contract_address: string | null;
  is_native: boolean;
}

export interface ApiEscrow {
  id: number;
  creator_address: string;
  counterparty_address: string;
  title: string;
  total: string;
  asset: ApiAsset;
  status_key: StatusKey;
  created_at: string;
  milestones: ApiMilestone[];
  // Which deployed NuanceEscrow instance backs this escrow — null for
  // almost every escrow today (see lib/chain-config.ts's own header on
  // why there's no single global escrow address to fall back to).
  contract_address: string | null;
  // The tx hash of the creator's real, payable NuanceEscrow.fund_escrow
  // call, once sent — null means either not linked to a contract yet, or
  // linked but not funded yet. See models/core.py's Escrow.funded_tx_hash
  // for why this is only a UI convenience, not the source of truth for
  // whether the contract itself is actually funded.
  funded_tx_hash: string | null;
  // The contract's own real, chain-verified funded_amount (GEN, as a
  // decimal string) — see models/core.py's Escrow.funded_amount for why
  // this is the actually-trustworthy field (synced from a real
  // get_escrow read, not just "an ack endpoint recorded a hash").
  // Null for an off-chain escrow, or an on-chain one the indexer hasn't
  // synced yet — funded_tx_hash can be set while this is still null,
  // briefly, right after a fund transaction is sent but before the next
  // indexer poll cycle confirms it.
  funded_amount: string | null;
  // The contract's real native GEN balance (decimal string), read
  // directly via eth_getBalance — see models/core.py's
  // Escrow.contract_balance for why this exists separately from
  // funded_amount above: a confirmed, currently-open GenLayer platform
  // bug (genlayerlabs/genvm-manager#20) leaves emit_transfer's outbound
  // value stuck at the contract even after the contract's own bookkeeping
  // (funded_amount) says "refunded"/"paid out." Null until the indexer's
  // first balance read for this contract lands.
  contract_balance: string | null;
  // Set once a real cancel_escrow() transaction has been sent and
  // acknowledged — see models/core.py's Escrow.cancelled_tx_hash.
  cancelled_tx_hash: string | null;
}

export interface ApiDeliverableSubmission {
  id: number;
  milestone_id: number;
  wallet: string;
  text: string;
  submitted_at: string;
  consensus_job_id: number | null;
}

export interface ApiDisputeMessage {
  id: number;
  dispute_id: number;
  sender_address: string;
  content: string;
  created_at: string;
}

export interface ApiDisputeEvidence {
  id: number;
  dispute_id: number;
  submitter_address: string;
  description: string;
  link: string | null;
  created_at: string;
  consensus_job_id: number | null;
}

export interface ApiDispute {
  id: number;
  escrow_id: number;
  milestone_id: number | null;
  opened_by_address: string;
  issue: string;
  status_key: StatusKey;
  ruling: string | null;
  enforced_by: string | null;
  created_at: string;
  resolved_at: string | null;
  messages: ApiDisputeMessage[];
  evidence: ApiDisputeEvidence[];
  // Which entry in NuanceDisputeCourt's shared registry this dispute maps
  // to — null until services/genlayer_indexer.py's resolve_pending_
  // dispute_ids matches it (see lib/chain-config.ts's own header on why
  // there's no single global "the" dispute id to fall back to).
  on_chain_dispute_id: number | null;
  chain_status: ApiChainStatus;
  on_chain_tx_hash: string | null;
}

// The response shape POST /escrows/{id}/dispute specifically returns —
// ApiDispute plus the queued ConsensusJob's id, same reasoning
// ApiDeliverableSubmission/ApiDisputeEvidence already carry one: the
// frontend needs it back synchronously to start polling GET /consensus/{id}
// right away, not GET /disputes/{id} first to go find it.
export interface ApiDisputeCreateResponse extends ApiDispute {
  consensus_job_id: number | null;
}

export interface ApiValidatorResult {
  name: string;
  vote: "approve" | "dispute";
  confidence: number;
  reasoning: string;
}

export interface ApiConsensusVerdict {
  label: string;
  approved: boolean;
  confidence: number;
  reasoning: string;
}

export interface ApiConsensusStatus {
  stage: number;
  validator_results: ApiValidatorResult[] | null;
  verdict: ApiConsensusVerdict | null;
}

export interface ApiPredictionPosition {
  id: number;
  prediction_id: number;
  wallet_address: string;
  side: string;
  amount: number;
  payout?: number | null;
  status?: string;
  created_at: string;
}

export interface ApiPrediction {
  id: number;
  title: string;
  description: string;
  category: string;
  resolution_date: string;
  volume: number;
  status_key: string;
  outcome: string | null;
  resolution_reasoning?: string | null;
  created_at: string;
  resolved_at?: string | null;
  positions: ApiPredictionPosition[];
  // Which deployed NuancePredictionMarket instance backs this market —
  // null for almost every market today (see lib/chain-config.ts's own
  // header). Once set, betting/resolution route on-chain.
  contract_address: string | null;
  chain_status: ApiChainStatus;
  resolution_trigger_tx_hash?: string | null;
  // Present whenever this market has something to resolve against —
  // which per backend/app/schemas/core.py::PredictionCreate is every
  // market created going forward. A market with this set and
  // contract_address still null isn't "permanently off-chain" — see
  // routers/predictions.py::place_bet's 2026-09-13 fix note — it's mid
  // auto-deploy (services/genlayer_deploy.py's retry_undeployed_predictions
  // retries it indefinitely until it lands). The frontend uses this to
  // show "deploying" instead of offering a bet that the backend will now
  // refuse anyway.
  resolution_source_url?: string | null;
  // The contract's real native GEN balance (decimal string, GEN — NOT
  // milli-GEN like volume/positions above, matching ApiEscrow.
  // contract_balance's own serialization since both are the same backend
  // Decimal/AssetAmount column type), read via eth_getBalance and never
  // inferred from the contract's own self-reported state — see
  // backend/app/models/core.py's Prediction.contract_balance docstring on
  // why this exists: claim_winnings' payout leaves the contract via the
  // same emit_transfer() mechanism already confirmed to sometimes never
  // actually deliver despite a clean on-chain receipt
  // (genlayerlabs/genvm-manager#20). Null until the indexer's first
  // balance read for this contract lands.
  contract_balance?: string | null;
  // Snapshotted once, the instant this market first resolves (decimal
  // GEN string, same units as contract_balance above) — see
  // Prediction.contract_balance_at_resolution's own docstring. Comparing
  // contract_balance above against this tells you how much GEN has
  // actually left the contract since resolution, across every claimant.
  contract_balance_at_resolution?: string | null;
}

export type ApiVoteChoice = "for" | "against" | "abstain";
export type ApiProposalStatus = "active" | "passed" | "rejected" | "executed";

export interface ApiVote {
  id: number;
  proposal_id: number;
  voter_address: string;
  choice: ApiVoteChoice;
  voting_power: number;
  created_at: string;
  updated_at: string;
  // --- On-chain linkage (2026-09-13) — see backend/app/models/
  // governance.py's Vote docstring. All null for a legacy off-chain
  // vote. stake_amount is a decimal GEN string (not milli-GEN), same
  // Decimal/AssetAmount serialization as ApiPrediction.contract_balance.
  stake_amount?: string | null;
  on_chain_tx_hash?: string | null;
  retracted_at?: string | null;
  retract_tx_hash?: string | null;
}

export interface ApiProposal {
  id: number;
  title: string;
  description: string;
  category: string;
  proposer_address: string;
  status: ApiProposalStatus;
  start_time: string;
  end_time: string;
  quorum_threshold: number;
  // Null for a LEGACY_OFFCHAIN proposal — see backend/app/models/
  // governance.py's Proposal.quorum_threshold_gen docstring for the real
  // bug this exists to fix: quorum_threshold above is a PERCENTAGE (of
  // "every wallet that's ever signed in"), meaningless on-chain; this is
  // the real, GEN-denominated quorum an on-chain proposal actually uses.
  // Decimal GEN string, same serialization as total_for/against/abstain.
  quorum_threshold_gen?: string | null;
  pass_threshold: number;
  // Decimal GEN strings since 2026-09-13 (not plain numbers) — see
  // backend/app/models/governance.py's Proposal.total_for docstring on
  // why this widening is value-compatible with every existing off-chain
  // proposal's small integer tallies too, not just new on-chain ones'.
  total_for: string;
  total_against: string;
  total_abstain: string;
  created_at: string;
  // Computed fresh by the backend on every read — see
  // backend/app/schemas/governance.py's ProposalRead docstring.
  turnout_pct: number;
  for_pct: number;
  against_pct: number;
  abstain_pct: number;
  quorum_met: boolean;
  // The requesting wallet's own vote, if any and if authenticated. Absent
  // (null) on an anonymous request — not the same as "voted abstain".
  user_vote: ApiVoteChoice | null;
  // The requesting wallet's own currently-staked GEN behind user_vote —
  // decimal string, only ever set alongside an on-chain vote. What a
  // real "Retract Vote" button shows before the user commits.
  user_vote_stake_amount?: string | null;
  // --- On-chain linkage (2026-09-13) — see backend/app/models/
  // governance.py's Proposal docstring. Null/"legacy_offchain" for every
  // proposal created before this update, by design (nothing
  // retroactively converts existing proposals).
  on_chain_proposal_id?: number | null;
  chain_status?: ApiChainStatus;
  on_chain_tx_hash?: string | null;
  // True once queued for on-chain creation but not linked yet — see
  // backend/app/schemas/governance.py's ProposalRead docstring. Mirrors
  // ApiPrediction.resolution_source_url's "deploying" purpose.
  is_queued_for_on_chain?: boolean;
  // The one shared NuanceGovernance registry address (same value on
  // every row) — see backend/app/schemas/governance.py's ProposalRead
  // docstring on why this isn't per-proposal.
  governance_contract_address?: string | null;
}

export interface ApiProposalDetail extends ApiProposal {
  votes: ApiVote[];
}

export interface CreateProposalPayload {
  title: string;
  description: string;
  category?: string;
  voting_period_days?: number;
  quorum_threshold?: number;
  pass_threshold?: number;
}

export interface ApiValidatorStat {
  name: string;
  cases_judged: number;
  accuracy_pct: number;
  is_active: boolean;
  last_active_at: string | null;
  last_provider: string | null;
}

export interface ApiAgentStat {
  wallet_address: string;
  category: string;
  cases_judged: number;
  trust_score: number;
}

// GET /agents/{wallet_address}/history (ROADMAP.md Part 4's Real Agent
// Directory "transaction drill-down") — one entry per judged case behind
// an agent's aggregate trust_score above.
export interface ApiAgentCase {
  consensus_job_id: number;
  subject_type: "milestone" | "dispute";
  subject_id: number;
  escrow_id: number;
  dispute_id: number | null;
  title: string;
  verdict_label: string | null;
  verdict_approved: boolean | null;
  verdict_confidence: number | null;
  verdict_reasoning: string | null;
  completed_at: string | null;
}

// GET /analytics/overview (ROADMAP.md Part 3 5.5) — every *_gen field
// arrives as a JSON string (FastAPI serializes Decimal that way), not a
// number, same reasoning callers already handle for Escrow.total/
// Prediction amounts elsewhere in this file.
export interface ApiAnalyticsOverview {
  tvl_open_escrows_gen: string;
  open_escrow_count: number;
  dispute_resolution_median_hours: number | null;
  resolved_dispute_count: number;
  prediction_market_volume_gen: string;
  prediction_market_count: number;
  validator_leaderboard: ApiValidatorStat[];
  generated_at: string;
}

export interface ApiNonceResponse {
  nonce: string;
  message: string;
}

export interface ApiTokenResponse {
  access_token: string;
  token_type: string;
  wallet_address: string;
}

export interface ApiUserSettings {
  notify_on: boolean;
  auto_escalate_on: boolean;
}

export interface ApiUser {
  wallet_address: string;
  display_name: string | null;
  created_at: string;
  settings?: ApiUserSettings | null;
}

export interface CreateEscrowPayload {
  title: string;
  counterparty_address: string;
  total: number;
  criteria?: string | null;
}

export interface EnforceDisputePayload {
  approved: boolean;
  ruling?: string | null;
}

// --- Auth -----------------------------------------------------------------

export async function requestNonce(walletAddress: string): Promise<ApiNonceResponse> {
  return apiFetch<ApiNonceResponse>("/auth/nonce", {
    method: "POST",
    body: JSON.stringify({ wallet_address: walletAddress }),
  });
}

/** Verifies the signed nonce message and stores the returned JWT on success. */
export async function verifySignature(
  walletAddress: string,
  message: string,
  signature: string
): Promise<ApiTokenResponse> {
  const result = await apiFetch<ApiTokenResponse>("/auth/verify", {
    method: "POST",
    body: JSON.stringify({ wallet_address: walletAddress, message, signature }),
  });
  setToken(result.access_token);
  return result;
}

export async function getMe(): Promise<ApiUser> {
  return apiFetch<ApiUser>("/auth/me");
}

export async function updateMe(payload: { display_name?: string | null }): Promise<ApiUser> {
  return apiFetch<ApiUser>("/auth/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function updateSettings(payload: {
  notify_on?: boolean;
  auto_escalate_on?: boolean;
}): Promise<ApiUserSettings> {
  return apiFetch<ApiUserSettings>("/auth/settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// --- Escrows ----------------------------------------------------------

export async function getEscrows(): Promise<ApiEscrow[]> {
  return apiFetch<ApiEscrow[]>("/escrows");
}

export async function getEscrow(id: number): Promise<ApiEscrow> {
  return apiFetch<ApiEscrow>(`/escrows/${id}`);
}

export async function createEscrow(payload: CreateEscrowPayload): Promise<ApiEscrow> {
  return apiFetch<ApiEscrow>("/escrows", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function submitDeliverable(
  escrowId: number,
  text: string
): Promise<ApiDeliverableSubmission> {
  return apiFetch<ApiDeliverableSubmission>(`/escrows/${escrowId}/deliverable`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts has already signed and sent a real
// NuanceEscrow.submit_deliverable transaction directly to the chain —
// this just hands the resulting tx hash to the backend so services/
// genlayer_indexer.py has something to poll. No `text` here; the
// deliverable text already lives on-chain (the contract's own storage),
// not in this request.
export async function submitDeliverableOnChainAck(
  escrowId: number,
  txHash: string
): Promise<ApiMilestone> {
  return apiFetch<ApiMilestone>(`/escrows/${escrowId}/deliverable/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash }),
  });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts's fundEscrowOnChain has already signed and sent
// a real, payable NuanceEscrow.fund_escrow transaction — real GEN has
// already left the creator's wallet by the time this fires. This call
// only records the tx hash for the UI (hide the "Fund Escrow" action once
// set); it does not itself move any funds. Only the escrow's own creator
// may call this (enforced server-side, matching fund_escrow's own
// contract-side restriction).
export async function fundEscrowOnChainAck(
  escrowId: number,
  txHash: string
): Promise<ApiEscrow> {
  return apiFetch<ApiEscrow>(`/escrows/${escrowId}/fund/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash }),
  });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts's cancelEscrowOnChain has already signed and
// sent a real NuanceEscrow.cancel_escrow transaction — the contract has
// already refunded whatever was locked back to the creator's wallet by
// the time this fires. This call flips status_key to "cancelled" locally
// (see OnChainCancelAck's own docstring on why that's safe to trust
// immediately, unlike fund/deliverable acks). Only the escrow's own
// creator may call this (enforced server-side, matching cancel_escrow's
// own contract-side restriction).
export async function cancelEscrowOnChainAck(
  escrowId: number,
  txHash: string
): Promise<ApiEscrow> {
  return apiFetch<ApiEscrow>(`/escrows/${escrowId}/cancel/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash }),
  });
}

export async function releaseMilestone(escrowId: number): Promise<ApiEscrow> {
  return apiFetch<ApiEscrow>(`/escrows/${escrowId}/release`, { method: "POST" });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts's releaseMilestoneOnChain has already signed
// and sent the real, fund-moving transaction. See backend/app/schemas/
// core.py's OnChainReleaseAck for why this exists — added 2026-09-11 to
// close a real gap where an on-chain escrow's approved milestone payout
// had no way to ever actually be released.
export async function releaseMilestoneOnChainAck(
  escrowId: number,
  txHash: string
): Promise<ApiEscrow> {
  return apiFetch<ApiEscrow>(`/escrows/${escrowId}/release/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash }),
  });
}

// Escalates the escrow's active milestone to a formal Dispute Court
// review — the "Escalate to Internet Court" button (escrow-detail-view.tsx)
// fires this with no `issue` of its own; the backend fills in a default
// from the milestone's AI verdict reasoning when omitted.
export async function raiseDispute(
  escrowId: number,
  issue?: string
): Promise<ApiDisputeCreateResponse> {
  return apiFetch<ApiDisputeCreateResponse>(`/escrows/${escrowId}/dispute`, {
    method: "POST",
    body: JSON.stringify(issue ? { issue } : {}),
  });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts's fileDisputeOnChain has already signed and
// sent a real NuanceDisputeCourt.file_dispute transaction. `issue` here
// MUST be the exact same text passed as that call's claimStatement — the
// backend stores it verbatim, and services/genlayer_indexer.py's
// resolve_pending_dispute_ids matches on exact string equality, not
// fuzzy matching.
export async function raiseDisputeOnChainAck(
  escrowId: number,
  txHash: string,
  issue: string
): Promise<ApiDispute> {
  return apiFetch<ApiDispute>(`/escrows/${escrowId}/dispute/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash, issue }),
  });
}

// --- Disputes ---------------------------------------------------------

export async function getDisputes(): Promise<ApiDispute[]> {
  return apiFetch<ApiDispute[]>("/disputes");
}

export async function getDispute(id: number): Promise<ApiDispute> {
  return apiFetch<ApiDispute>(`/disputes/${id}`);
}

export async function getDisputeMessages(disputeId: number): Promise<ApiDisputeMessage[]> {
  return apiFetch<ApiDisputeMessage[]>(`/disputes/${disputeId}/messages`);
}

export async function sendDisputeMessage(
  disputeId: number,
  content: string
): Promise<ApiDisputeMessage> {
  return apiFetch<ApiDisputeMessage>(`/disputes/${disputeId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function getDisputeEvidence(disputeId: number): Promise<ApiDisputeEvidence[]> {
  return apiFetch<ApiDisputeEvidence[]>(`/disputes/${disputeId}/evidence`);
}

export async function submitEvidence(
  disputeId: number,
  description: string,
  link?: string | null
): Promise<ApiDisputeEvidence> {
  return apiFetch<ApiDisputeEvidence>(`/disputes/${disputeId}/evidence`, {
    method: "POST",
    body: JSON.stringify({ description, link: link || null }),
  });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts's addEvidenceOnChain has already signed and
// sent a real NuanceDisputeCourt.add_evidence transaction. Records a
// local DisputeEvidence row for the UI's evidence list — the real
// judgment happens via adjudicate_dispute on the contract itself, not
// anything queued by this call (unlike submitEvidence above).
export async function submitEvidenceOnChainAck(
  disputeId: number,
  txHash: string,
  evidenceUrl: string
): Promise<ApiDisputeEvidence> {
  return apiFetch<ApiDisputeEvidence>(`/disputes/${disputeId}/evidence/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash, evidence_url: evidenceUrl }),
  });
}

export async function enforceRuling(
  disputeId: number,
  payload: EnforceDisputePayload
): Promise<ApiDispute> {
  return apiFetch<ApiDispute>(`/disputes/${disputeId}/enforce`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// --- Consensus --------------------------------------------------------

export async function getConsensusStatus(jobId: number): Promise<ApiConsensusStatus> {
  return apiFetch<ApiConsensusStatus>(`/consensus/${jobId}`);
}

// --- Predictions ------------------------------------------------------

// 2026-09-12 rebrand — backend/app/schemas/core.py's PredictionCreate.
export async function getPredictions(): Promise<ApiPrediction[]> {
  return apiFetch<ApiPrediction[]>("/predictions");
}

// createPrediction/CreatePredictionPayload REMOVED 2026-09-14, asked
// directly ("I do not want user to be able to create a Prediction
// Markets, I want it will be fetching data about genlayer using the API
// key") — POST /predictions is gone server-side too (see backend/app/
// routers/predictions.py's own updated module docstring). Markets now
// only ever come from services/market_generator.py's real TwitterAPI.io
// + Gemini pipeline.

export async function getPrediction(id: number): Promise<ApiPrediction> {
  return apiFetch<ApiPrediction>(`/predictions/${id}`);
}

export async function placeBet(
  predictionId: number,
  side: "YES" | "NO" | "yes" | "no",
  amount: number
): Promise<ApiPrediction> {
  return apiFetch<ApiPrediction>(`/predictions/${predictionId}/bet`, {
    method: "POST",
    body: JSON.stringify({ side: side.toUpperCase(), amount }),
  });
}

// The on-chain counterpart: called after components/app/
// genlayer-write-client.ts's betOnChain has already signed and sent a
// real NuancePredictionMarket.bet transaction. side/amount here mirror
// the stake into a PredictionPosition row (the indexer's view-sync
// doesn't track individual bettors' on-chain stakes, only the market's
// own state as a whole — see that endpoint's own docstring).
export async function placeBetOnChainAck(
  predictionId: number,
  txHash: string,
  side: "YES" | "NO" | "yes" | "no",
  amount: number
): Promise<ApiPrediction> {
  return apiFetch<ApiPrediction>(`/predictions/${predictionId}/bet/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash, side: side.toUpperCase(), amount }),
  });
}

export async function resolvePrediction(predictionId: number): Promise<ApiPrediction> {
  return apiFetch<ApiPrediction>(`/predictions/${predictionId}/resolve`, {
    method: "POST",
  });
}

// --- Governance ---------------------------------------------------------

export async function getProposals(): Promise<ApiProposal[]> {
  return apiFetch<ApiProposal[]>("/proposals");
}

export async function getProposal(id: number): Promise<ApiProposalDetail> {
  return apiFetch<ApiProposalDetail>(`/proposals/${id}`);
}

export async function createProposal(payload: CreateProposalPayload): Promise<ApiProposal> {
  return apiFetch<ApiProposal>("/proposals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// `choice` is case-insensitive on the backend (VoteCreate._normalize_choice
// lowercases before validating), so callers can pass "For"/"Against" as-is.
// FIXED 2026-09-13 — this off-chain endpoint now 503s (ChainUnavailableError)
// for any proposal that's linked to, or even just queued to link to, the
// on-chain governance registry (deploy_attempted_at set) — see backend/
// app/routers/governance.py::cast_vote's own docstring. Use castVoteOnChainAck
// below for those; the caller decides which based on ApiProposal.
// on_chain_proposal_id/governance_contract_address.
export async function castVote(
  proposalId: number,
  choice: ApiVoteChoice | "For" | "Against" | "Abstain"
): Promise<ApiProposal> {
  return apiFetch<ApiProposal>(`/proposals/${proposalId}/vote`, {
    method: "POST",
    body: JSON.stringify({ choice }),
  });
}

// The on-chain counterpart to castVote above — reached once components/
// app/genlayer-write-client.ts's castVoteOnChain has already signed and
// sent a real, payable NuanceGovernance.cast_vote transaction. Mirrors
// the stake into a Vote row so "my votes" keeps working — see backend/
// app/routers/governance.py::cast_vote_on_chain's own docstring.
// `amountGen` is a plain string/number GEN amount (not milli-GEN) —
// whatever the connected wallet actually staked.
export async function castVoteOnChainAck(
  proposalId: number,
  txHash: string,
  choice: ApiVoteChoice | "For" | "Against" | "Abstain",
  amountGen: number | string
): Promise<ApiProposal> {
  return apiFetch<ApiProposal>(`/proposals/${proposalId}/vote/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash, choice, stake_amount: amountGen }),
  });
}

// The new unvote's ack — reached once genlayer-write-client.ts's
// retractVoteOnChain has already signed and sent a real
// NuanceGovernance.retract_vote transaction, refunding the caller's
// exact staked GEN. See that router endpoint's own docstring.
export async function retractVoteOnChainAck(
  proposalId: number,
  txHash: string
): Promise<ApiProposal> {
  return apiFetch<ApiProposal>(`/proposals/${proposalId}/retract-vote/on-chain`, {
    method: "POST",
    body: JSON.stringify({ tx_hash: txHash }),
  });
}

// Marks a PASSED proposal EXECUTED — see backend/app/routers/governance.py::
// execute_proposal's own docstring: no real on-chain effect yet (no treasury
// transfer, no parameter change), just the formal "this decision has been
// enacted" status transition + an audit trail (executed_by/executed_at).
// 400s if the proposal isn't PASSED, or is already EXECUTED.
export async function executeProposal(proposalId: number): Promise<ApiProposal> {
  return apiFetch<ApiProposal>(`/proposals/${proposalId}/execute`, {
    method: "POST",
  });
}

// --- Validators & agents --------------------------------------------------

export async function getValidators(): Promise<ApiValidatorStat[]> {
  return apiFetch<ApiValidatorStat[]>("/validators");
}

export async function getAgents(): Promise<ApiAgentStat[]> {
  return apiFetch<ApiAgentStat[]>("/agents");
}

export async function getAgentHistory(walletAddress: string): Promise<ApiAgentCase[]> {
  return apiFetch<ApiAgentCase[]>(`/agents/${walletAddress}/history`);
}

export async function getAnalyticsOverview(): Promise<ApiAnalyticsOverview> {
  return apiFetch<ApiAnalyticsOverview>("/analytics/overview");
}


