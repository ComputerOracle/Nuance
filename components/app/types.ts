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
  counterparty: string;
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
  aiSummary: string;
}

export interface Position {
  side: "yes" | "no";
  amount: number;
}

export interface Dispute {
  id: number;
  agentA: string;
  agentB: string;
  issue: string;
  amount: number;
  statusKey: StatusKey;
}

export interface DisputeVerdict {
  label: string;
  color: string;
  panelBg: string;
  panelBorder: string;
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
