export type StatusKey =
  | "approved"
  | "in_review"
  | "in_progress"
  | "pending"
  | "disputed";

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
  forPct: number;
  againstPct: number;
  status: "Active" | "Closed";
}

export interface ValidatorDirectoryEntry {
  name: string;
  accuracy: number;
  cases: number;
  stake: string;
}

export interface AgentDirectoryEntry {
  name: string;
  category: string;
  txns: number;
  score: number;
}

export interface EscrowVerdict {
  approved: boolean;
  disputed: boolean;
  label: string;
  confidence: number;
  reasoning: string;
}

export type WalletStatus = "idle" | "connecting" | "connected";
