import type {
  AgentDirectoryEntry,
  Prediction,
  Proposal,
  ValidatorDirectoryEntry,
} from "@/components/app/types";

// Escrows and disputes are no longer seeded from static mock data — see
// nuance-app.tsx, which fetches both from the backend (GET /escrows,
// GET /disputes) on mount instead. Predictions/governance/directories
// below stay local mock data until those backend surfaces exist.

export const INITIAL_PREDICTIONS: Prediction[] = [
  {
    id: 1,
    question:
      "Will Company X win its trademark dispute against Company Y by Q3?",
    category: "Legal",
    yesPrice: 64,
    volume: 128000,
    resolveDate: "Aug 30, 2026",
    aiSummary:
      "Validators crawled filed court briefs and press coverage. Recent motion outcomes lean in favor of Company X, but appeal risk keeps this from certainty.",
  },
  {
    id: 2,
    question:
      "Will the downtown stadium construction be completed on schedule?",
    category: "Infrastructure",
    yesPrice: 38,
    volume: 54200,
    resolveDate: "Dec 1, 2026",
    aiSummary:
      "Permit filings and contractor reports show a six-week delay from steel supply issues. On-time completion now looks unlikely absent a schedule change.",
  },
  {
    id: 3,
    question:
      "Will the viral marketing campaign be judged as misleading by regulators?",
    category: "Marketing",
    yesPrice: 22,
    volume: 76300,
    resolveDate: "Sep 15, 2026",
    aiSummary:
      "Ad language was compared against advertising-standards guidance. Claims are aggressive but validators found adequate disclosures in most placements.",
  },
];

export const INITIAL_PROPOSALS: Proposal[] = [
  {
    id: 1,
    title: "Increase validator staking requirement to 5,000 NUAI",
    summary:
      "Plain-language proposal to raise the minimum stake to reduce spam validators.",
    forPct: 72,
    againstPct: 28,
    status: "Active",
  },
  {
    id: 2,
    title: "Fund a public GenVM debugging toolkit",
    summary:
      "Allocate treasury funds toward open-source developer tooling for Python-based Intelligent Contracts.",
    forPct: 88,
    againstPct: 12,
    status: "Active",
  },
  {
    id: 3,
    title:
      "Adopt plain-English constitution amendment on dispute appeals",
    summary:
      "Allow a second round of AI review before Internet Court rulings finalize.",
    forPct: 54,
    againstPct: 46,
    status: "Closed",
  },
];

export const VALIDATOR_DIRECTORY: ValidatorDirectoryEntry[] = [
  { name: "Validator-Alpha", accuracy: 98.6, cases: 4210, stake: "82,000 NUAI" },
  { name: "Validator-Beta", accuracy: 97.9, cases: 3890, stake: "76,500 NUAI" },
  { name: "Validator-Gamma", accuracy: 98.2, cases: 4032, stake: "79,200 NUAI" },
  { name: "Validator-Delta", accuracy: 96.4, cases: 2210, stake: "54,000 NUAI" },
];

export const AGENT_DIRECTORY: AgentDirectoryEntry[] = [
  {
    name: "Agent-7f3c (Logistics Bot)",
    category: "Supply chain",
    txns: 1284,
    score: 91,
  },
  {
    name: "Agent-91ab (Payments Bot)",
    category: "Finance",
    txns: 3021,
    score: 87,
  },
  { name: "Agent-Vega (Pricing Bot)", category: "Retail", txns: 654, score: 62 },
  {
    name: "Agent-Nova (Inventory Bot)",
    category: "Retail",
    txns: 902,
    score: 74,
  },
  {
    name: "Agent-Kilo (Scheduling Bot)",
    category: "Fulfillment",
    txns: 445,
    score: 40,
  },
];

export const VALIDATOR_NAMES = [
  "Validator-Alpha",
  "Validator-Beta",
  "Validator-Gamma",
] as const;
