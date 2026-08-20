import type {
  AgentDirectoryEntry,
  Dispute,
  Escrow,
  Prediction,
  Proposal,
  ValidatorDirectoryEntry,
} from "@/components/app/types";

export const INITIAL_ESCROWS: Escrow[] = [
  {
    id: 1,
    title: "Marketplace mobile app",
    counterparty: "@arjun.dev",
    total: 4200,
    statusKey: "in_review",
    milestones: [
      {
        name: "Wireframes & IA",
        amount: 800,
        statusKey: "approved",
        criteria: "Covers all core user flows, approved by design lead.",
      },
      {
        name: "UI build — checkout flow",
        amount: 1400,
        statusKey: "in_review",
        criteria: "Matches Figma spec, passes Lighthouse a11y ≥ 90.",
      },
      {
        name: "QA & handoff",
        amount: 2000,
        statusKey: "pending",
        criteria: "Zero P1 bugs across iOS/Android, docs delivered.",
      },
    ],
  },
  {
    id: 2,
    title: "Brand identity for Solace Labs",
    counterparty: "@studio_kae",
    total: 2600,
    statusKey: "in_progress",
    milestones: [
      {
        name: "Logo concepts",
        amount: 900,
        statusKey: "approved",
        criteria: "3 distinct directions, vector source files.",
      },
      {
        name: "Full brand guide",
        amount: 1700,
        statusKey: "in_progress",
        criteria: 'Guide reads as "professional" per brand brief tone.',
      },
    ],
  },
  {
    id: 3,
    title: "Smart contract audit — vault module",
    counterparty: "0x9b1...44Ac",
    total: 5000,
    statusKey: "disputed",
    milestones: [
      {
        name: "Static analysis report",
        amount: 1500,
        statusKey: "disputed",
        criteria: "No critical/high findings unresolved.",
      },
      {
        name: "Manual review + writeup",
        amount: 3500,
        statusKey: "pending",
        criteria: "Report covers reentrancy, access control, oracle risk.",
      },
    ],
  },
  {
    id: 4,
    title: "API documentation rewrite",
    counterparty: "@lena_writes",
    total: 900,
    statusKey: "approved",
    milestones: [
      {
        name: "Full docs pass",
        amount: 900,
        statusKey: "approved",
        criteria: "All endpoints documented with working examples.",
      },
    ],
  },
];

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

export const INITIAL_DISPUTES: Dispute[] = [
  {
    id: 1,
    agentA: "Agent-7f3c (Logistics Bot)",
    agentB: "Agent-91ab (Payments Bot)",
    issue: "Payment released before shipment confirmation was received.",
    amount: 3200,
    statusKey: "in_review",
  },
  {
    id: 2,
    agentA: "Agent-Vega (Pricing Bot)",
    agentB: "Agent-Nova (Inventory Bot)",
    issue:
      "Disagreement over dynamic pricing allegedly violating inventory contract terms.",
    amount: 890,
    statusKey: "disputed",
  },
  {
    id: 3,
    agentA: "Agent-Kilo (Scheduling Bot)",
    agentB: "Agent-Rho (Fulfillment Bot)",
    issue: "Missed SLA window disputed as force majeure.",
    amount: 1500,
    statusKey: "approved",
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
