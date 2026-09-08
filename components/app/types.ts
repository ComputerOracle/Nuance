export type StatusKey =
  | "approved"
  | "in_review"
  | "in_progress"
  | "pending"
  | "disputed"
  // A dispute whose claim was rejected by consensus — only ever set on a
  // Dispute, never a Milestone/Escrow. Distinct from "disputed" (still open).
  | "rejected";

export type View =
  | "dashboard"
  | "detail"
  | "create"
  | "predictions"
  | "predictionDetail"
  | "disputes"
  | "disputeDetail"
  | "governance"
  | "validators"
  | "agents"
  | "settings";

export interface Milestone {
  name: string;
  amount: number;
  statusKey: StatusKey;
  criteria: string;
}

export interface Escrow {
  id: number;
  title: string;
  creatorAddress: string;
  counterpartyAddress: string;
  total: number;
  statusKey: StatusKey;
  milestones: Milestone[];
  // Which deployed NuanceEscrow instance backs this escrow, if any — only
  // an escrow with this set has a real fund_escrow()/release_milestone()
  // to call; most escrows today are still off-chain (null).
  contractAddress?: string | null;
  // Set once the creator's real fund_escrow transaction has been sent —
  // hides the "Fund Escrow" action once present. See lib/api.ts's
  // ApiEscrow.funded_tx_hash for the full caveat on what this does and
  // doesn't guarantee.
  fundedTxHash?: string | null;
}

export interface Prediction {
  id: number;
  question: string;
  category: string;
  yesPrice: number;
  volume: number;
  resolveDate: string;
  resolutionDate?: string;
  aiSummary: string;
  statusKey?: string;
  outcome?: string | null;
  resolutionReasoning?: string | null;
  resolvedAt?: string | null;
  positions?: Position[];
  // Which deployed NuancePredictionMarket instance backs this market, if
  // any — null for almost every market today. Only markets with this set
  // have a real claim_winnings() to call (an off-chain "Won $X" figure is
  // notional bookkeeping, not a real stake to pull out).
  contractAddress?: string | null;
}

export interface Position {
  id?: number;
  side: "yes" | "no";
  amount: number;
  payout?: number | null;
  status?: string;
}

export interface DisputeMessage {
  id: number;
  disputeId: number;
  senderAddress: string;
  content: string;
  createdAt: string;
}

export interface DisputeEvidence {
  id: number;
  disputeId: number;
  submitterAddress: string;
  description: string;
  link?: string | null;
  createdAt: string;
}

export interface Dispute {
  id: number;
  escrowId: number;
  openedByAddress: string;
  counterpartyAddress: string;
  issue: string;
  amount: number;
  statusKey: StatusKey;
  messages?: DisputeMessage[];
  evidence?: DisputeEvidence[];
}

export interface DisputeVerdict {
  label: string;
  approved: boolean;
  reasoning: string;
}

export interface Proposal {
  id: number;
  title: string;
  summary: string;
  category: string;
  status: "Active" | "Closed";
  rawStatus: "active" | "passed" | "rejected" | "executed";
  totalFor: number;
  totalAgainst: number;
  totalAbstain: number;
  // For/against as a share of decided ballots (abstains excluded); abstain
  // as a share of turnout. Mirrors backend/app/routers/governance.py::_progress.
  forPct: number;
  againstPct: number;
  abstainPct: number;
  turnoutPct: number;
  quorumThreshold: number;
  passThreshold: number;
  quorumMet: boolean;
  endTime: string;
  // The connected wallet's own vote, if any — null if not voted or not
  // authenticated (not the same as having voted "abstain").
  userVote: "for" | "against" | "abstain" | null;
}

export interface ValidatorDirectoryEntry {
  name: string;
  accuracyPct: number;
  casesJudged: number;
  isActive: boolean;
  lastActiveAt: string | null;
  // Which provider ("gemini" | "anthropic" | "openai" | "heuristic")
  // answered this validator's most recent case. Null if it has none yet,
  // or the case predates this field.
  lastProvider: string | null;
}

export interface AgentDirectoryEntry {
  walletAddress: string;
  category: string;
  casesJudged: number;
  trustScore: number;
}

export interface EscrowVerdict {
  approved: boolean;
  disputed: boolean;
  label: string;
  confidence: number;
  reasoning: string;
}

export type WalletStatus = "idle" | "connecting" | "connected";
