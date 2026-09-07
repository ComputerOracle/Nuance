"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/app/sidebar";
import { WalletModal } from "@/components/app/wallet-modal";
import { DashboardView } from "@/components/app/views/dashboard-view";
import { EscrowDetailView } from "@/components/app/views/escrow-detail-view";
import { CreateEscrowView } from "@/components/app/views/create-escrow-view";
import { PredictionsView } from "@/components/app/views/predictions-view";
import { PredictionDetailView } from "@/components/app/views/prediction-detail-view";
import { DisputesView } from "@/components/app/views/disputes-view";
import { DisputeDetailView } from "@/components/app/views/dispute-detail-view";
import { GovernanceView } from "@/components/app/views/governance-view";
import { ValidatorsView } from "@/components/app/views/validators-view";
import { AgentsView } from "@/components/app/views/agents-view";
import { SettingsView } from "@/components/app/views/settings-view";
import { useWalletConnection } from "@/components/app/use-wallet-connection";
import { useConsensusPolling } from "@/components/app/use-consensus-polling";
import { formatAddress } from "@/components/app/status";
import type { Eip1193Provider } from "@/components/app/eip1193";
import {
  escrowContractAddress,
  milestoneIsOnChain,
  disputeCourtContractAddress,
} from "@/lib/chain-config";
import {
  submitDeliverableOnChain,
  fileDisputeOnChain,
  describeWriteError,
} from "@/components/app/genlayer-write-client";
import * as api from "@/lib/api";
import type { ApiDispute, ApiEscrow, ApiMilestone } from "@/lib/api";
import type {
  AgentDirectoryEntry,
  Dispute,
  DisputeVerdict,
  Escrow,
  EscrowVerdict,
  Milestone,
  Position,
  Prediction,
  Proposal,
  ValidatorDirectoryEntry,
  View,
} from "@/components/app/types";

// --- Backend DTO -> UI-shape mapping ---------------------------------
// Backend amounts are Decimal, serialized as strings ("500.00") — convert
// once here rather than scattering Number(...) calls through the views.

function mapMilestone(m: ApiMilestone): Milestone {
  return {
    name: m.name,
    amount: Number(m.amount),
    statusKey: m.status_key,
    criteria: m.criteria,
  };
}

function mapEscrow(e: ApiEscrow): Escrow {
  return {
    id: e.id,
    title: e.title,
    creatorAddress: e.creator_address,
    counterpartyAddress: e.counterparty_address,
    total: Number(e.total),
    statusKey: e.status_key,
    milestones: e.milestones.map(mapMilestone),
  };
}

function mapDispute(d: ApiDispute, escrows: Escrow[]): Dispute {
  const linkedEscrow = escrows.find((e) => e.id === d.escrow_id);
  const counterparty = linkedEscrow
    ? d.opened_by_address.toLowerCase() === linkedEscrow.creatorAddress.toLowerCase()
      ? linkedEscrow.counterpartyAddress
      : linkedEscrow.creatorAddress
    : "0x0000000000000000000000000000000000000000";
  return {
    id: d.id,
    escrowId: d.escrow_id,
    openedByAddress: d.opened_by_address,
    counterpartyAddress: counterparty,
    issue: d.issue,
    amount: linkedEscrow?.total ?? 0,
    statusKey: d.status_key,
    messages: d.messages?.map((m) => ({
      id: m.id,
      disputeId: m.dispute_id,
      senderAddress: m.sender_address,
      content: m.content,
      createdAt: m.created_at,
    })),
    evidence: d.evidence?.map((e) => ({
      id: e.id,
      disputeId: e.dispute_id,
      submitterAddress: e.submitter_address,
      description: e.description,
      link: e.link,
      createdAt: e.created_at,
    })),
  };
}

function mapPrediction(p: api.ApiPrediction): Prediction {
  const dateObj = new Date(p.resolution_date);
  const formattedDate = dateObj.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  const yesPositions = p.positions?.filter((pos) => pos.side.toUpperCase() === "YES") || [];
  const totalPosAmount = p.positions?.reduce((sum, pos) => sum + pos.amount, 0) || 0;
  const yesPosAmount = yesPositions.reduce((sum, pos) => sum + pos.amount, 0);
  const yesPrice = totalPosAmount > 0 ? Math.round((yesPosAmount / totalPosAmount) * 100) : 50;

  return {
    id: p.id,
    question: p.title,
    category: p.category,
    yesPrice: Math.max(1, Math.min(99, yesPrice)),
    volume: p.volume,
    resolveDate: formattedDate,
    resolutionDate: p.resolution_date,
    aiSummary: p.description,
    statusKey: p.status_key,
    outcome: p.outcome,
    resolutionReasoning: p.resolution_reasoning,
    resolvedAt: p.resolved_at,
    positions: p.positions?.map((pos) => ({
      id: pos.id,
      side: pos.side.toLowerCase() as "yes" | "no",
      amount: pos.amount,
      payout: pos.payout,
      status: pos.status,
    })) || [],
  };
}

function mapProposal(p: api.ApiProposal): Proposal {
  return {
    id: p.id,
    title: p.title,
    summary: p.description,
    category: p.category,
    status: p.status === "active" ? "Active" : "Closed",
    rawStatus: p.status,
    totalFor: p.total_for,
    totalAgainst: p.total_against,
    totalAbstain: p.total_abstain,
    forPct: p.for_pct,
    againstPct: p.against_pct,
    abstainPct: p.abstain_pct,
    turnoutPct: p.turnout_pct,
    quorumThreshold: p.quorum_threshold,
    passThreshold: p.pass_threshold,
    quorumMet: p.quorum_met,
    endTime: p.end_time,
    userVote: p.user_vote,
  };
}

function mapValidator(v: api.ApiValidatorStat): ValidatorDirectoryEntry {
  return {
    name: v.name,
    accuracyPct: v.accuracy_pct,
    casesJudged: v.cases_judged,
    isActive: v.is_active,
    lastActiveAt: v.last_active_at,
    lastProvider: v.last_provider,
  };
}

function mapAgent(a: api.ApiAgentStat): AgentDirectoryEntry {
  return {
    walletAddress: a.wallet_address,
    category: a.category,
    casesJudged: a.cases_judged,
    trustScore: a.trust_score,
  };
}

// Mirrors the backend's own re-vote rule (routers/governance.py::
// _adjust_tally): back the previous choice's weight out of the running
// totals before adding the new one in, rather than stacking a second
// ballot on top. turnoutPct/quorumMet aren't recomputed here — they depend
// on the total eligible-voter count, which the frontend doesn't have — so
// they're left at their last server-known value until castVote() resolves
// and mapProposal() overwrites this whole object with the real thing.
function applyOptimisticVote(proposal: Proposal, choice: "For" | "Against"): Proposal {
  const newChoice = choice === "For" ? "for" : "against";
  let totalFor = proposal.totalFor;
  let totalAgainst = proposal.totalAgainst;
  const totalAbstain = proposal.totalAbstain;

  if (proposal.userVote === "for") totalFor -= 1;
  else if (proposal.userVote === "against") totalAgainst -= 1;
  if (newChoice === "for") totalFor += 1;
  else totalAgainst += 1;

  const decided = totalFor + totalAgainst;
  const round1 = (n: number) => Math.round(n * 10) / 10;

  return {
    ...proposal,
    totalFor,
    totalAgainst,
    userVote: newChoice,
    forPct: decided ? round1((100 * totalFor) / decided) : 0,
    againstPct: decided ? round1((100 * totalAgainst) / decided) : 0,
    abstainPct: totalFor + totalAgainst + totalAbstain
      ? round1((100 * totalAbstain) / (totalFor + totalAgainst + totalAbstain))
      : 0,
  };
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 rounded-lg border border-negative/35 bg-negative/12 px-3 py-2 text-xs text-negative-text">
      {message}
    </div>
  );
}

// Same shape as ErrorBanner, "info" tone (status.ts's in_progress badge
// already uses this exact pairing) — for a successful, non-final notice
// like an on-chain submission, not a failure.
function InfoBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 rounded-lg border border-info/35 bg-info/12 px-3 py-2 text-xs text-info-text">
      {message}
    </div>
  );
}

function ErrorCard({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-[14px] border border-negative/35 bg-negative/10 p-6 text-center">
      <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-negative/20 text-negative-text font-bold">
        !
      </div>
      <div className="font-semibold text-negative-text text-[15px]">Failed to fetch backend data</div>
      <p className="mt-1 text-xs text-fg-meta max-w-md mx-auto">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 cursor-pointer rounded-lg border border-border-6 bg-chip-hover px-4 py-2 text-xs font-semibold transition-colors hover:bg-chip-hover-2"
        >
          ↻ Retry Connection
        </button>
      )}
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-4 py-4 animate-pulse">
      <div className="h-9 w-48 rounded-lg bg-surface-2" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="h-24 rounded-[14px] bg-surface-2" />
        <div className="h-24 rounded-[14px] bg-surface-2" />
        <div className="h-24 rounded-[14px] bg-surface-2" />
      </div>
      <div className="py-8 text-center text-xs text-fg-meta">{label}</div>
    </div>
  );
}

function WalletAuthGuard({ onConnect }: { onConnect: () => void }) {
  return (
    <div
      style={{ animation: "fadeUp 0.3s ease" }}
      className="flex flex-col items-center justify-center rounded-[20px] border border-border-2 bg-surface-1 px-8 py-20 text-center shadow-lg"
    >
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-border-4 bg-surface-2 text-3xl">
        🔒
      </div>
      <div className="font-display text-2xl font-bold text-fg">
        Authentication Required
      </div>
      <p className="mt-2.5 max-w-md text-sm text-fg-dim-2">
        🔒 Connect your wallet to view your secure dashboard and disputes.
      </p>
      <button
        onClick={onConnect}
        className="mt-6 cursor-pointer rounded-xl border border-border-6 bg-chip-hover px-6 py-3 text-sm font-semibold transition-all hover:bg-chip-hover-2 hover:border-border-7"
      >
        Connect Wallet
      </button>
    </div>
  );
}

export function NuanceApp() {
  // Navigation ------------------------------------------------------------
  const [view, setView] = useState<View>("dashboard");

  // Escrows -----------------------------------------------------------------
  const [escrows, setEscrows] = useState<Escrow[]>([]);
  const [escrowsLoading, setEscrowsLoading] = useState(true);
  const [escrowsError, setEscrowsError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [deliverableText, setDeliverableText] = useState("");
  // escrow id -> its most recently submitted consensus job id, so
  // reopening an escrow resumes polling that job instead of losing it.
  const [escrowJobIds, setEscrowJobIds] = useState<Record<number, string>>({});
  const [activeEscrowJobId, setActiveEscrowJobId] = useState<string | null>(null);
  const [escrowActionError, setEscrowActionError] = useState<string | null>(null);
  // Set once a deliverable has actually been signed and sent on-chain
  // (see submitDeliverable below) — distinct from escrowActionError:
  // this is a successful, informational notice, not a failure. Cleared
  // whenever a different escrow is opened.
  const [onChainSubmitNotice, setOnChainSubmitNotice] = useState<string | null>(null);
  const [onChainSubmitPending, setOnChainSubmitPending] = useState(false);
  const [escalatePending, setEscalatePending] = useState(false);

  const [formTitle, setFormTitle] = useState("");
  const [formCounterparty, setFormCounterparty] = useState("");
  const [formAmount, setFormAmount] = useState("");
  const [formCriteria, setFormCriteria] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  // Prediction markets ------------------------------------------------------
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [predictionsLoading, setPredictionsLoading] = useState(true);
  const [predictionsError, setPredictionsError] = useState<string | null>(null);
  const [selectedPredictionId, setSelectedPredictionId] = useState<
    number | null
  >(null);
  const [betAmount, setBetAmount] = useState("");
  const [betSide, setBetSide] = useState<"yes" | "no" | null>(null);
  const [positions, setPositions] = useState<Record<number, Position>>({});
  const [isBetting, setIsBetting] = useState(false);
  const [isResolving, setIsResolving] = useState(false);
  const [bettingError, setBettingError] = useState<string | null>(null);

  // Disputes ------------------------------------------------------------
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [disputesLoading, setDisputesLoading] = useState(true);
  const [disputesError, setDisputesError] = useState<string | null>(null);

  const [selectedDisputeId, setSelectedDisputeId] = useState<number | null>(
    null
  );
  const [evidenceText, setEvidenceText] = useState("");
  const [disputeJobIds, setDisputeJobIds] = useState<Record<number, string>>(
    {}
  );
  const [activeDisputeJobId, setActiveDisputeJobId] = useState<string | null>(
    null
  );
  const [disputeActionError, setDisputeActionError] = useState<string | null>(
    null
  );

  // Governance --------------------------------------------------------------
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [proposalsLoading, setProposalsLoading] = useState(true);
  const [proposalsError, setProposalsError] = useState<string | null>(null);
  const [voteError, setVoteError] = useState<string | null>(null);
  const [pendingVoteId, setPendingVoteId] = useState<number | null>(null);

  const [validators, setValidators] = useState<ValidatorDirectoryEntry[]>([]);
  const [validatorsLoading, setValidatorsLoading] = useState(true);
  const [validatorsError, setValidatorsError] = useState<string | null>(null);

  const [agents, setAgents] = useState<AgentDirectoryEntry[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  // Settings ------------------------------------------------------------
  const [notifyOn, setNotifyOn] = useState(true);
  const [autoEscalateOn, setAutoEscalateOn] = useState(false);

  // Wallet ------------------------------------------------------------
  const wallet = useWalletConnection();
  const [showWalletModal, setShowWalletModal] = useState(false);

  // Live consensus polling — stage/verdict now come exclusively from the
  // backend rather than a local timer chain.
  const escrowConsensus = useConsensusPolling(activeEscrowJobId);
  const disputeConsensus = useConsensusPolling(activeDisputeJobId);

  // Initial data load — loads escrows, disputes, and predictions from backend.
  const loadData = async () => {
    setEscrowsLoading(true);
    setEscrowsError(null);
    setDisputesLoading(true);
    setDisputesError(null);
    setPredictionsLoading(true);
    setPredictionsError(null);
    setProposalsLoading(true);
    setProposalsError(null);
    setValidatorsLoading(true);
    setValidatorsError(null);
    setAgentsLoading(true);
    setAgentsError(null);

    let loadedEscrows: Escrow[] = [];
    try {
      const apiEscrows = await api.getEscrows();
      loadedEscrows = apiEscrows.map(mapEscrow);
      setEscrows(loadedEscrows);
    } catch (err) {
      setEscrowsError(errorText(err, "Failed to load escrows from backend."));
    } finally {
      setEscrowsLoading(false);
    }

    try {
      const apiDisputes = await api.getDisputes();
      setDisputes(apiDisputes.map((d) => mapDispute(d, loadedEscrows)));
    } catch (err) {
      setDisputesError(errorText(err, "Failed to load disputes from backend."));
    } finally {
      setDisputesLoading(false);
    }

    try {
      const apiPreds = await api.getPredictions();
      const mappedPreds = apiPreds.map(mapPrediction);
      setPredictions(mappedPreds);

      // Restore user positions if wallet is already connected
      if (wallet.address) {
        const userAddr = wallet.address.toLowerCase();
        const userPositions: Record<number, Position> = {};
        apiPreds.forEach((pred) => {
          const userPos = pred.positions?.filter(
            (pos) => pos.wallet_address.toLowerCase() === userAddr
          );
          if (userPos && userPos.length > 0) {
            const lastPos = userPos[userPos.length - 1];
            userPositions[pred.id] = {
              id: lastPos.id,
              side: lastPos.side.toLowerCase() as "yes" | "no",
              amount: userPos.reduce((sum, p) => sum + p.amount, 0),
              payout: userPos.reduce((sum, p) => sum + (p.payout || 0), 0),
              status: lastPos.status,
            };
          }
        });
        setPositions(userPositions);
      }
    } catch (err) {
      setPredictionsError(errorText(err, "Failed to load predictions from backend."));
    } finally {
      setPredictionsLoading(false);
    }

    try {
      const apiProposals = await api.getProposals();
      setProposals(apiProposals.map(mapProposal));
    } catch (err) {
      setProposalsError(errorText(err, "Failed to load proposals from backend."));
    } finally {
      setProposalsLoading(false);
    }

    try {
      const apiValidators = await api.getValidators();
      setValidators(apiValidators.map(mapValidator));
    } catch (err) {
      setValidatorsError(errorText(err, "Failed to load validators from backend."));
    } finally {
      setValidatorsLoading(false);
    }

    try {
      const apiAgents = await api.getAgents();
      setAgents(apiAgents.map(mapAgent));
    } catch (err) {
      setAgentsError(errorText(err, "Failed to load agents from backend."));
    } finally {
      setAgentsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (wallet.status === "connected") {
      api.getMe()
        .then((u) => {
          if (u.settings) {
            setNotifyOn(u.settings.notify_on);
            setAutoEscalateOn(u.settings.auto_escalate_on);
          }
        })
        .catch(() => {});
      loadData();
    } else {
      setPositions({});
    }
  }, [wallet.status]);

  const handleToggleNotify = () => {
    const next = !notifyOn;
    setNotifyOn(next);
    if (wallet.status === "connected") {
      api.updateSettings({ notify_on: next }).catch(() => {});
    }
  };

  const handleToggleAutoEscalate = () => {
    const next = !autoEscalateOn;
    setAutoEscalateOn(next);
    if (wallet.status === "connected") {
      api.updateSettings({ auto_escalate_on: next }).catch(() => {});
    }
  };

  // Escrow handlers -----------------------------------------------------
  function goDashboard() {
    setView("dashboard");
    setSelectedId(null);
    setDeliverableText("");
    setActiveEscrowJobId(null);
    setEscrowActionError(null);
  }
  function openEscrow(id: number) {
    setView("detail");
    setSelectedId(id);
    setDeliverableText("");
    setEscrowActionError(null);
    setOnChainSubmitNotice(null);
    setActiveEscrowJobId(escrowJobIds[id] ?? null);
  }
  async function submitDeliverable() {
    if (!deliverableText.trim() || selectedId == null) return;
    const escrowId = selectedId;
    setEscrowActionError(null);
    setOnChainSubmitNotice(null);

    // A fresh, authoritative read rather than trusting the already-mapped
    // `escrows` state — that UI-shape mapping (mapEscrow/mapMilestone,
    // above) deliberately drops contract_address/on_chain_index, and this
    // decision (on-chain vs. legacy path) has to be made against real,
    // current linkage, not a stale/simplified copy of it.
    let escrowData: api.ApiEscrow;
    try {
      escrowData = await api.getEscrow(escrowId);
    } catch (err) {
      setEscrowActionError(errorText(err, "Failed to submit deliverable."));
      return;
    }
    const activeMilestone = escrowData.milestones.find((m) => m.status_key !== "approved");
    const contractAddress = escrowContractAddress(escrowData);

    if (
      contractAddress &&
      activeMilestone &&
      milestoneIsOnChain(escrowData, activeMilestone) &&
      wallet.status === "connected" &&
      wallet.provider
    ) {
      // On-chain path: sign and send NuanceEscrow.submit_deliverable
      // directly from this browser via the connected wallet — no LLM call
      // from our own backend, GenVM's validator committee does that
      // judgment on the deployed contract instead (ROADMAP.md 4's whole
      // point). This app never waits for that verdict itself; services/
      // genlayer_indexer.py polls it server-side once the tx hash below
      // is handed to the backend.
      setOnChainSubmitPending(true);
      try {
        const txHash = await submitDeliverableOnChain({
          walletAddress: wallet.address,
          provider: wallet.provider,
          contractAddress,
          milestoneIndex: activeMilestone.on_chain_index as number,
          deliverableText,
          deliverableUrl: "",
        });
        await api.submitDeliverableOnChainAck(escrowId, txHash);
        setDeliverableText("");
        setOnChainSubmitNotice(
          `Submitted on-chain — tx ${txHash.slice(0, 10)}…${txHash.slice(-6)}. ` +
            "GenLayer validators are reviewing it now; this can take a few minutes."
        );
      } catch (err) {
        setEscrowActionError(describeWriteError(err));
      } finally {
        setOnChainSubmitPending(false);
      }
      return;
    }

    // Legacy off-chain path — unchanged: the backend's own LLM-validator
    // consensus (services/consensus.py) judges the submission.
    try {
      const submission = await api.submitDeliverable(escrowId, deliverableText);
      setDeliverableText("");
      if (submission.consensus_job_id != null) {
        const jobId = String(submission.consensus_job_id);
        setEscrowJobIds((prev) => ({ ...prev, [escrowId]: jobId }));
        setActiveEscrowJobId(jobId);
      }
    } catch (err) {
      setEscrowActionError(errorText(err, "Failed to submit deliverable."));
    }
  }
  // The "Escalate to Internet Court" button (escrow-detail-view.tsx) —
  // was rendered with no handler at all until POST /escrows/{id}/dispute
  // existed to call. Fires with no form of its own; a default claim gets
  // built from the milestone's AI verdict reasoning (server-side for the
  // off-chain path below; here, client-side, since the on-chain call
  // needs real claim text before any backend round-trip happens at all).
  async function escalateToDisputeCourt() {
    if (selectedId == null) return;
    const escrowId = selectedId;
    setEscrowActionError(null);
    setEscalatePending(true);

    let escrowData: api.ApiEscrow;
    try {
      escrowData = await api.getEscrow(escrowId);
    } catch (err) {
      setEscrowActionError(errorText(err, "Failed to raise a dispute."));
      setEscalatePending(false);
      return;
    }

    // NuanceDisputeCourt is the one global shared registry (lib/
    // chain-config.ts's own header) — its address alone doesn't make a
    // dispute "on-chain capable"; the specific escrow being disputed also
    // needs its own NuanceEscrow instance, since that address is what
    // file_dispute records as escrow_address and what services/
    // genlayer_indexer.py later matches against.
    const disputeCourtAddress = disputeCourtContractAddress();
    const escrowAddress = escrowContractAddress(escrowData);

    if (disputeCourtAddress && escrowAddress && wallet.status === "connected" && wallet.provider) {
      // On-chain path: sign and send NuanceDisputeCourt.file_dispute
      // directly from this browser. No ConsensusJob, no run_consensus —
      // GenVM's own validator committee is the jury once adjudicate_dispute
      // is called against the contract (separate action, not wired here).
      const respondent =
        wallet.address.toLowerCase() === escrowData.creator_address.toLowerCase()
          ? escrowData.counterparty_address
          : escrowData.creator_address;
      const claimStatement = escrowConsensus.verdict?.reasoning
        ? `Escalating AI Consensus verdict: ${escrowConsensus.verdict.reasoning}`
        : `Escalating escrow #${escrowId} to Dispute Court review.`;

      try {
        const txHash = await fileDisputeOnChain({
          walletAddress: wallet.address,
          provider: wallet.provider,
          disputeCourtAddress,
          escrowAddress,
          respondentAddress: respondent,
          claimStatement,
          evidenceUrl: "",
        });
        const created = await api.raiseDisputeOnChainAck(escrowId, txHash, claimStatement);
        const mapped = mapDispute(created, escrows);
        setDisputes((prev) => [mapped, ...prev]);
        openDispute(created.id);
      } catch (err) {
        setEscrowActionError(describeWriteError(err));
      } finally {
        setEscalatePending(false);
      }
      return;
    }

    // Legacy off-chain path — unchanged: the backend judges via its own
    // AI-validator consensus, same as an escalated dispute always has.
    try {
      const created = await api.raiseDispute(escrowId);
      const mapped = mapDispute(created, escrows);
      setDisputes((prev) => [mapped, ...prev]);
      if (created.consensus_job_id != null) {
        setDisputeJobIds((prev) => ({ ...prev, [created.id]: String(created.consensus_job_id) }));
      }
      openDispute(created.id);
    } catch (err) {
      setEscrowActionError(errorText(err, "Failed to raise a dispute."));
    } finally {
      setEscalatePending(false);
    }
  }
  async function releasePayment() {
    if (selectedId == null) return;
    const escrowId = selectedId;
    setEscrowActionError(null);
    try {
      const updated = mapEscrow(await api.releaseMilestone(escrowId));
      setEscrows((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setActiveEscrowJobId(null);
      setDeliverableText("");
    } catch (err) {
      setEscrowActionError(errorText(err, "Failed to release payment."));
    }
  }
  async function submitCreate() {
    if (!formTitle.trim() || !formCounterparty.trim() || !formAmount) return;
    setCreateError(null);
    try {
      const created = mapEscrow(
        await api.createEscrow({
          title: formTitle,
          counterparty_address: formCounterparty,
          total: Number(formAmount) || 0,
          criteria: formCriteria || null,
        })
      );
      setEscrows((prev) => [...prev, created]);
      setView("detail");
      setSelectedId(created.id);
      setActiveEscrowJobId(null);
      setFormTitle("");
      setFormCounterparty("");
      setFormAmount("");
      setFormCriteria("");
      setDeliverableText("");
    } catch (err) {
      setCreateError(errorText(err, "Failed to create escrow."));
    }
  }

  // Prediction market handlers --------------------------------------------
  function goPredictions() {
    setView("predictions");
    setSelectedPredictionId(null);
    setBetAmount("");
    setBetSide(null);
    setBettingError(null);
  }
  function openPrediction(id: number) {
    setView("predictionDetail");
    setSelectedPredictionId(id);
    setBetAmount("");
    setBetSide(null);
    setBettingError(null);
  }
  async function placeBet() {
    if (!betAmount || !betSide || selectedPredictionId == null || isBetting) return;
    const parsedAmount = parseInt(betAmount, 10);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setBettingError("Enter a valid bet amount.");
      return;
    }

    setIsBetting(true);
    setBettingError(null);
    try {
      const updatedApi = await api.placeBet(selectedPredictionId, betSide, parsedAmount);
      const updatedPred = mapPrediction(updatedApi);
      setPredictions((prev) => prev.map((p) => (p.id === updatedPred.id ? updatedPred : p)));
      setPositions((prev) => ({
        ...prev,
        [selectedPredictionId]: {
          side: betSide,
          amount: (prev[selectedPredictionId]?.amount || 0) + parsedAmount,
        },
      }));
      setBetAmount("");
    } catch (err) {
      setBettingError(errorText(err, "Failed to place bet. Ensure wallet is connected."));
    } finally {
      setIsBetting(false);
    }
  }

  async function resolveMarket() {
    if (selectedPredictionId == null || isResolving) return;
    setIsResolving(true);
    setBettingError(null);
    try {
      const updatedApi = await api.resolvePrediction(selectedPredictionId);
      const updatedPred = mapPrediction(updatedApi);
      setPredictions((prev) => prev.map((p) => (p.id === updatedPred.id ? updatedPred : p)));

      if (wallet.address) {
        const userAddr = wallet.address.toLowerCase();
        const userPos = updatedApi.positions?.filter(
          (pos) => pos.wallet_address.toLowerCase() === userAddr
        );
        if (userPos && userPos.length > 0) {
          const lastPos = userPos[userPos.length - 1];
          setPositions((prev) => ({
            ...prev,
            [selectedPredictionId]: {
              id: lastPos.id,
              side: lastPos.side.toLowerCase() as "yes" | "no",
              amount: userPos.reduce((sum, p) => sum + p.amount, 0),
              payout: userPos.reduce((sum, p) => sum + (p.payout || 0), 0),
              status: lastPos.status,
            },
          }));
        }
      }
    } catch (err) {
      setBettingError(errorText(err, "Failed to resolve prediction market."));
    } finally {
      setIsResolving(false);
    }
  }

  // Dispute handlers --------------------------------------------------------
  function goDisputes() {
    setView("disputes");
    setSelectedDisputeId(null);
    setEvidenceText("");
    setActiveDisputeJobId(null);
    setDisputeActionError(null);
  }
  function openDispute(id: number) {
    setView("disputeDetail");
    setSelectedDisputeId(id);
    setEvidenceText("");
    setDisputeActionError(null);
    setActiveDisputeJobId(disputeJobIds[id] ?? null);
  }
  async function submitEvidence() {
    if (!evidenceText.trim() || selectedDisputeId == null) return;
    const disputeId = selectedDisputeId;
    setDisputeActionError(null);
    try {
      const submission = await api.submitEvidence(disputeId, evidenceText);
      setEvidenceText("");
      if (submission.consensus_job_id != null) {
        const jobId = String(submission.consensus_job_id);
        setDisputeJobIds((prev) => ({ ...prev, [disputeId]: jobId }));
        setActiveDisputeJobId(jobId);
      }
    } catch (err) {
      setDisputeActionError(errorText(err, "Failed to submit evidence."));
    }
  }
  async function enforceRuling() {
    if (selectedDisputeId == null || !disputeConsensus.verdict) return;
    const disputeId = selectedDisputeId;
    setDisputeActionError(null);
    try {
      const updated = mapDispute(
        await api.enforceRuling(disputeId, {
          approved: disputeConsensus.verdict.approved,
          ruling: disputeConsensus.verdict.reasoning,
        }),
        escrows
      );
      setDisputes((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
    } catch (err) {
      setDisputeActionError(errorText(err, "Failed to enforce ruling."));
    }
  }

  // Governance handlers -----------------------------------------------------
  async function vote(id: number, choice: "For" | "Against") {
    const target = proposals.find((p) => p.id === id);
    if (!target || target.status !== "Active" || pendingVoteId != null) return;

    setVoteError(null);
    setPendingVoteId(id);
    const previous = target;
    // Optimistic update — reflected immediately, reconciled with the
    // server's authoritative tally below (or rolled back on failure).
    setProposals((prev) => prev.map((p) => (p.id === id ? applyOptimisticVote(p, choice) : p)));

    try {
      const updated = await api.castVote(id, choice);
      setProposals((prev) => prev.map((p) => (p.id === id ? mapProposal(updated) : p)));
    } catch (err) {
      setProposals((prev) => prev.map((p) => (p.id === id ? previous : p)));
      setVoteError(errorText(err, "Failed to cast vote."));
    } finally {
      setPendingVoteId(null);
    }
  }

  // Wallet handlers -----------------------------------------------------
  async function selectWallet(provider: Eip1193Provider, name: string) {
    const connected = await wallet.connect(provider, name);
    // Close only on success — a rejection/error should leave the modal open
    // with the error message visible, not silently vanish.
    if (connected) setShowWalletModal(false);
  }

  // Derived view data -----------------------------------------------------
  const selectedEscrow = escrows.find((e) => e.id === selectedId) ?? null;
  const selectedPrediction =
    predictions.find((p) => p.id === selectedPredictionId) ?? null;
  const selectedDispute =
    disputes.find((d) => d.id === selectedDisputeId) ?? null;

  const escrowVerdict: EscrowVerdict | null = escrowConsensus.verdict
    ? {
        approved: escrowConsensus.verdict.approved,
        disputed: !escrowConsensus.verdict.approved,
        label: escrowConsensus.verdict.approved
          ? "Consensus: Approved"
          : "Consensus: Disputed",
        confidence: escrowConsensus.verdict.confidence,
        reasoning: escrowConsensus.verdict.reasoning,
      }
    : null;

  const disputeVerdict: DisputeVerdict | null = disputeConsensus.verdict
    ? {
        label: disputeConsensus.verdict.approved
          ? `Ruling: In favor of ${formatAddress(selectedDispute?.openedByAddress)}`
          : `Ruling: In favor of ${formatAddress(selectedDispute?.counterpartyAddress)}`,
        approved: disputeConsensus.verdict.approved,
        reasoning: disputeConsensus.verdict.reasoning,
      }
    : null;

  return (
    <div className="flex min-h-screen">
      <Sidebar
        view={view}
        onNavigate={(key) => {
          if (key === "dashboard") goDashboard();
          else if (key === "predictions") goPredictions();
          else if (key === "disputes") goDisputes();
          else setView(key as View);
        }}
        walletStatus={wallet.status}
        walletAddress={wallet.addressShort}
        walletBalance={wallet.balance}
        isWrongNetwork={wallet.isWrongNetwork}
        walletError={showWalletModal ? null : wallet.error}
        onOpenWalletModal={() => setShowWalletModal(true)}
        onDisconnect={wallet.disconnect}
        onSwitchNetwork={wallet.switchNetwork}
      />

      {showWalletModal && (
        <WalletModal
          onClose={() => setShowWalletModal(false)}
          onSelect={selectWallet}
          connecting={wallet.status === "connecting"}
          error={wallet.error}
        />
      )}

      <div className="max-w-[1200px] flex-1 p-10 py-10 sm:px-14">
        {view === "dashboard" &&
          (wallet.status !== "connected" ? (
            <WalletAuthGuard onConnect={() => setShowWalletModal(true)} />
          ) : escrowsLoading ? (
            <LoadingState label="Loading escrows from backend…" />
          ) : escrowsError ? (
            <ErrorCard message={escrowsError} onRetry={loadData} />
          ) : (
            <DashboardView
              escrows={escrows}
              onOpenCreate={() => setView("create")}
              onOpenEscrow={openEscrow}
            />
          ))}

        {view === "detail" &&
          (wallet.status !== "connected" ? (
            <WalletAuthGuard onConnect={() => setShowWalletModal(true)} />
          ) : selectedEscrow ? (
            <>
              {escrowActionError && <ErrorBanner message={escrowActionError} />}
              {onChainSubmitNotice && <InfoBanner message={onChainSubmitNotice} />}
              <EscrowDetailView
                escrow={selectedEscrow}
                stage={escrowConsensus.stage}
                deliverableText={deliverableText}
                verdict={escrowVerdict}
                onBack={goDashboard}
                onDeliverableChange={setDeliverableText}
                onSubmitDeliverable={submitDeliverable}
                onReleasePayment={releasePayment}
                onEscalate={escalateToDisputeCourt}
                submitDisabled={onChainSubmitPending}
                escalateDisabled={escalatePending}
              />
            </>
          ) : null)}

        {view === "create" &&
          (wallet.status !== "connected" ? (
            <WalletAuthGuard onConnect={() => setShowWalletModal(true)} />
          ) : (
            <>
              {createError && <ErrorBanner message={createError} />}
              <CreateEscrowView
                formTitle={formTitle}
                formCounterparty={formCounterparty}
                formAmount={formAmount}
                formCriteria={formCriteria}
                onTitleChange={setFormTitle}
                onCounterpartyChange={setFormCounterparty}
                onAmountChange={setFormAmount}
                onCriteriaChange={setFormCriteria}
                onCancel={goDashboard}
                onSubmit={submitCreate}
              />
            </>
          ))}

        {view === "predictions" &&
          (predictionsLoading ? (
            <LoadingState label="Loading prediction markets from backend…" />
          ) : predictionsError ? (
            <ErrorCard message={predictionsError} onRetry={loadData} />
          ) : (
            <PredictionsView predictions={predictions} onOpen={openPrediction} />
          ))}

        {view === "predictionDetail" && selectedPrediction && (
          <PredictionDetailView
            prediction={selectedPrediction}
            betAmount={betAmount}
            betSide={betSide}
            position={positions[selectedPrediction.id] ?? null}
            isBetting={isBetting}
            isResolving={isResolving}
            bettingError={bettingError}
            onBack={goPredictions}
            onSelectYes={() => setBetSide("yes")}
            onSelectNo={() => setBetSide("no")}
            onBetAmountChange={setBetAmount}
            onPlaceBet={placeBet}
            onResolveMarket={resolveMarket}
          />
        )}

        {view === "disputes" &&
          (wallet.status !== "connected" ? (
            <WalletAuthGuard onConnect={() => setShowWalletModal(true)} />
          ) : disputesLoading ? (
            <LoadingState label="Loading disputes from backend…" />
          ) : disputesError ? (
            <ErrorCard message={disputesError} onRetry={loadData} />
          ) : (
            <DisputesView disputes={disputes} onOpen={openDispute} />
          ))}

        {view === "disputeDetail" &&
          (wallet.status !== "connected" ? (
            <WalletAuthGuard onConnect={() => setShowWalletModal(true)} />
          ) : selectedDispute ? (
            <>
              {disputeActionError && <ErrorBanner message={disputeActionError} />}
              <DisputeDetailView
                dispute={selectedDispute}
                stage={disputeConsensus.stage}
                verdict={disputeVerdict}
                currentWalletAddress={wallet.address}
                onBack={goDisputes}
                onEvidenceSubmitted={(jobId) => {
                  if (selectedDisputeId != null) {
                    setDisputeJobIds((prev) => ({ ...prev, [selectedDisputeId]: jobId }));
                  }
                  setActiveDisputeJobId(jobId);
                }}
                onEnforceRuling={enforceRuling}
              />
            </>
          ) : null)}

        {view === "governance" &&
          (proposalsLoading ? (
            <LoadingState label="Loading proposals from backend…" />
          ) : proposalsError ? (
            <ErrorCard message={proposalsError} onRetry={loadData} />
          ) : (
            <>
              {voteError && <ErrorBanner message={voteError} />}
              <GovernanceView
                proposals={proposals}
                walletConnected={wallet.status === "connected"}
                pendingVoteId={pendingVoteId}
                onVote={vote}
              />
            </>
          ))}

        {view === "validators" &&
          (validatorsLoading ? (
            <LoadingState label="Loading validator network from backend…" />
          ) : validatorsError ? (
            <ErrorCard message={validatorsError} onRetry={loadData} />
          ) : (
            <ValidatorsView validators={validators} />
          ))}

        {view === "agents" &&
          (agentsLoading ? (
            <LoadingState label="Loading agent directory from backend…" />
          ) : agentsError ? (
            <ErrorCard message={agentsError} onRetry={loadData} />
          ) : (
            <AgentsView agents={agents} />
          ))}

        {view === "settings" && (
          <SettingsView
            notifyOn={notifyOn}
            autoEscalateOn={autoEscalateOn}
            onToggleNotify={handleToggleNotify}
            onToggleAutoEscalate={handleToggleAutoEscalate}
          />
        )}
      </div>
    </div>
  );
}
