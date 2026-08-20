"use client";

import { useEffect, useRef, useState } from "react";
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
import { activeMilestoneIndex } from "@/components/app/status";
import { useWalletConnection } from "@/components/app/use-wallet-connection";
import type { Eip1193Provider } from "@/components/app/eip1193";
import {
  AGENT_DIRECTORY,
  INITIAL_DISPUTES,
  INITIAL_ESCROWS,
  INITIAL_PREDICTIONS,
  INITIAL_PROPOSALS,
  VALIDATOR_DIRECTORY,
} from "@/components/app/data";
import type {
  Dispute,
  DisputeVerdict,
  Escrow,
  EscrowVerdict,
  Position,
  Prediction,
  Proposal,
  View,
} from "@/components/app/types";

export function NuanceApp() {
  // Navigation ------------------------------------------------------------
  const [view, setView] = useState<View>("dashboard");

  // Escrows -----------------------------------------------------------------
  const [escrows, setEscrows] = useState<Escrow[]>(INITIAL_ESCROWS);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [deliverableText, setDeliverableText] = useState("");
  const [stage, setStage] = useState(0);
  const [verdictByMilestone, setVerdictByMilestone] = useState<
    Record<number, EscrowVerdict>
  >({});
  const [formTitle, setFormTitle] = useState("");
  const [formCounterparty, setFormCounterparty] = useState("");
  const [formAmount, setFormAmount] = useState("");
  const [formCriteria, setFormCriteria] = useState("");
  const [nextId, setNextId] = useState(5);

  // Prediction markets ------------------------------------------------------
  const [predictions] = useState<Prediction[]>(INITIAL_PREDICTIONS);
  const [selectedPredictionId, setSelectedPredictionId] = useState<
    number | null
  >(null);
  const [betAmount, setBetAmount] = useState("");
  const [betSide, setBetSide] = useState<"yes" | "no" | null>(null);
  const [positions, setPositions] = useState<Record<number, Position>>({});

  // Disputes ------------------------------------------------------------
  const [disputes, setDisputes] = useState<Dispute[]>(INITIAL_DISPUTES);
  const [selectedDisputeId, setSelectedDisputeId] = useState<number | null>(
    null
  );
  const [evidenceText, setEvidenceText] = useState("");
  const [disputeStage, setDisputeStage] = useState(0);
  const [disputeVerdictById, setDisputeVerdictById] = useState<
    Record<number, DisputeVerdict>
  >({});

  // Governance --------------------------------------------------------------
  const [proposals, setProposals] = useState<Proposal[]>(INITIAL_PROPOSALS);
  const [votes, setVotes] = useState<Record<number, "For" | "Against">>({});

  // Settings ------------------------------------------------------------
  const [notifyOn, setNotifyOn] = useState(true);
  const [autoEscalateOn, setAutoEscalateOn] = useState(false);

  // Wallet ------------------------------------------------------------
  const wallet = useWalletConnection();
  const [showWalletModal, setShowWalletModal] = useState(false);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
    };
  }, []);
  function after(ms: number, fn: () => void) {
    timers.current.push(setTimeout(fn, ms));
  }

  // Escrow handlers -----------------------------------------------------
  function goDashboard() {
    setView("dashboard");
    setSelectedId(null);
    setDeliverableText("");
    setStage(0);
  }
  function openEscrow(id: number) {
    setView("detail");
    setSelectedId(id);
    setDeliverableText("");
    setStage(0);
  }
  function submitDeliverable() {
    if (!deliverableText.trim() || selectedId == null) return;
    const key = selectedId;
    const text = deliverableText.toLowerCase();
    setStage(1);
    after(900, () => setStage(2));
    after(2000, () => {
      const disputed =
        text.includes("bug") || text.includes("broken") || text.trim().length < 12;
      const verdict: EscrowVerdict = disputed
        ? {
            approved: false,
            disputed: true,
            label: "Consensus: Disputed",
            confidence: 91,
            reasoning:
              "Validators found the submitted deliverable does not satisfy the stated milestone criteria. Flagged discrepancies were cross-checked against the linked artifact before consensus.",
          }
        : {
            approved: true,
            disputed: false,
            label: "Consensus: Approved",
            confidence: 96,
            reasoning:
              "All three validators independently confirmed the deliverable satisfies the milestone criteria. Escrowed funds are cleared for release.",
          };
      setStage(3);
      setVerdictByMilestone((prev) => ({ ...prev, [key]: verdict }));
    });
  }
  function releasePayment() {
    if (selectedId == null) return;
    const id = selectedId;
    setEscrows((prev) =>
      prev.map((e) => {
        if (e.id !== id) return e;
        const idx = activeMilestoneIndex(e.milestones);
        const milestones = e.milestones.map((m, i) =>
          i === idx ? { ...m, statusKey: "approved" as const } : m
        );
        const nextIdx = milestones.findIndex((m) => m.statusKey === "pending");
        if (nextIdx !== -1) {
          milestones[nextIdx] = {
            ...milestones[nextIdx],
            statusKey: "in_progress",
          };
        }
        const overall = milestones.every((m) => m.statusKey === "approved")
          ? "approved"
          : "in_progress";
        return { ...e, milestones, statusKey: overall };
      })
    );
    setStage(0);
    setDeliverableText("");
  }
  function submitCreate() {
    if (!formTitle.trim() || !formCounterparty.trim() || !formAmount) return;
    const amount = Number(formAmount) || 0;
    const escrow: Escrow = {
      id: nextId,
      title: formTitle,
      counterparty: formCounterparty,
      total: amount,
      statusKey: "in_progress",
      milestones: [
        {
          name: "Milestone 1",
          amount,
          statusKey: "in_progress",
          criteria: formCriteria || "Deliverable meets the agreed brief.",
        },
      ],
    };
    setEscrows((prev) => [...prev, escrow]);
    setNextId((n) => n + 1);
    setView("detail");
    setSelectedId(escrow.id);
    setFormTitle("");
    setFormCounterparty("");
    setFormAmount("");
    setFormCriteria("");
    setStage(0);
    setDeliverableText("");
  }

  // Prediction market handlers --------------------------------------------
  function goPredictions() {
    setView("predictions");
    setSelectedPredictionId(null);
    setBetAmount("");
    setBetSide(null);
  }
  function openPrediction(id: number) {
    setView("predictionDetail");
    setSelectedPredictionId(id);
    setBetAmount("");
    setBetSide(null);
  }
  function placeBet() {
    if (!betAmount || !betSide || selectedPredictionId == null) return;
    setPositions((prev) => ({
      ...prev,
      [selectedPredictionId]: { side: betSide, amount: Number(betAmount) },
    }));
  }

  // Dispute handlers --------------------------------------------------------
  function goDisputes() {
    setView("disputes");
    setSelectedDisputeId(null);
    setEvidenceText("");
    setDisputeStage(0);
  }
  function openDispute(id: number) {
    setView("disputeDetail");
    setSelectedDisputeId(id);
    setEvidenceText("");
    setDisputeStage(0);
  }
  function submitEvidence() {
    if (!evidenceText.trim() || selectedDisputeId == null) return;
    const id = selectedDisputeId;
    setDisputeStage(1);
    after(900, () => setDisputeStage(2));
    after(2000, () => {
      const d = disputes.find((x) => x.id === id);
      if (!d) return;
      const verdict: DisputeVerdict = {
        label: `Ruling: In favor of ${d.agentB}`,
        color: "positive",
        panelBg: "positive",
        panelBorder: "positive",
        reasoning: `Validators cross-referenced submitted transaction logs against the service agreement. ${d.agentA} released funds ahead of the confirmed trigger condition, breaching the agreed sequence.`,
      };
      setDisputeStage(3);
      setDisputeVerdictById((prev) => ({ ...prev, [id]: verdict }));
    });
  }
  function enforceRuling() {
    if (selectedDisputeId == null) return;
    const id = selectedDisputeId;
    setDisputes((prev) =>
      prev.map((d) => (d.id === id ? { ...d, statusKey: "approved" } : d))
    );
  }

  // Governance handlers -----------------------------------------------------
  function vote(id: number, choice: "For" | "Against") {
    setProposals((prev) =>
      prev.map((p) => {
        if (p.id !== id) return p;
        const bump = 4;
        const forPct =
          choice === "For"
            ? Math.min(100, p.forPct + bump)
            : Math.max(0, p.forPct - bump);
        return { ...p, forPct, againstPct: 100 - forPct };
      })
    );
    setVotes((prev) => ({ ...prev, [id]: choice }));
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
        {view === "dashboard" && (
          <DashboardView
            escrows={escrows}
            onOpenCreate={() => setView("create")}
            onOpenEscrow={openEscrow}
          />
        )}

        {view === "detail" && selectedEscrow && (
          <EscrowDetailView
            escrow={selectedEscrow}
            stage={stage}
            deliverableText={deliverableText}
            verdict={verdictByMilestone[selectedEscrow.id] ?? null}
            onBack={goDashboard}
            onDeliverableChange={setDeliverableText}
            onSubmitDeliverable={submitDeliverable}
            onReleasePayment={releasePayment}
          />
        )}

        {view === "create" && (
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
        )}

        {view === "predictions" && (
          <PredictionsView predictions={predictions} onOpen={openPrediction} />
        )}

        {view === "predictionDetail" && selectedPrediction && (
          <PredictionDetailView
            prediction={selectedPrediction}
            betAmount={betAmount}
            betSide={betSide}
            position={positions[selectedPrediction.id] ?? null}
            onBack={goPredictions}
            onSelectYes={() => setBetSide("yes")}
            onSelectNo={() => setBetSide("no")}
            onBetAmountChange={setBetAmount}
            onPlaceBet={placeBet}
          />
        )}

        {view === "disputes" && (
          <DisputesView disputes={disputes} onOpen={openDispute} />
        )}

        {view === "disputeDetail" && selectedDispute && (
          <DisputeDetailView
            dispute={selectedDispute}
            stage={disputeStage}
            evidenceText={evidenceText}
            verdict={disputeVerdictById[selectedDispute.id] ?? null}
            onBack={goDisputes}
            onEvidenceChange={setEvidenceText}
            onSubmitEvidence={submitEvidence}
            onEnforceRuling={enforceRuling}
          />
        )}

        {view === "governance" && (
          <GovernanceView proposals={proposals} votes={votes} onVote={vote} />
        )}

        {view === "validators" && (
          <ValidatorsView validators={VALIDATOR_DIRECTORY} />
        )}

        {view === "agents" && <AgentsView agents={AGENT_DIRECTORY} />}

        {view === "settings" && (
          <SettingsView
            notifyOn={notifyOn}
            autoEscalateOn={autoEscalateOn}
            onToggleNotify={() => setNotifyOn((v) => !v)}
            onToggleAutoEscalate={() => setAutoEscalateOn((v) => !v)}
          />
        )}
      </div>
    </div>
  );
}
