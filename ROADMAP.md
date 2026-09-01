# 🧭 Nuance — Engineering Roadmap

> Contracts that understand nuance, not just logic.
> AI-validator consensus for claims traditional smart contracts can't settle — was the work actually good, did the campaign really mislead, who broke the deal.

![Status](https://img.shields.io/badge/status-active--development-blue)
![Frontend](https://img.shields.io/badge/frontend-Next.js%2016%20%7C%20React%2019-black)
![Backend](https://img.shields.io/badge/backend-FastAPI%20%7C%20SQLAlchemy%20async-009688)
![Tests](https://img.shields.io/badge/backend%20tests-24%2F24%20passing-brightgreen)
![Network](https://img.shields.io/badge/network-GenLayer%20Bradbury%20Testnet-8a2be2)
![License](https://img.shields.io/badge/license-TBD-lightgrey)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Phase 0 — Current State & Baseline Audit](#2-phase-0--current-state--baseline-audit)
3. [Part 1 — Backend Completion & Full Feature Parity](#3-part-1--backend-completion--full-feature-parity-immediate-sprint)
4. [Part 2 — GenLayer On-Chain Transition (GenVM)](#4-part-2--genlayer-on-chain-transition--intelligent-contracts-genvm-integration)
5. [Part 3 — Production Hardening, Realtime UX & Security](#5-part-3--production-hardening-security-real-time-ux--analytics)
6. [Part 4 — Ecosystem Expansion & Mainnet Readiness](#6-part-4--ecosystem-expansion-autonomous-agents--mainnet-readiness)
7. [Appendix](#7-appendix)

---

## 1. System Overview

### 1.1 Mission

Nuance lets two parties commit to an agreement whose fulfillment is *subjective* — quality of work, truthfulness of a claim, fairness of a dispute — and settles it with a panel of independent AI validators reaching **consensus** instead of a human arbitrator or a rigid on-chain condition. It is built for **GenLayer's Testnet Bradbury**, the first blockchain purpose-built to let smart contracts (there, "Intelligent Contracts") reason in natural language via LLMs, with disagreement between validator nodes resolved by GenVM's **Optimistic Democracy** / equivalence-principle consensus.

### 1.2 Core Modules

| Module | What it does | Primary backend surface |
|---|---|---|
| **Intelligent Escrows** | Two-party milestone-based payments; a milestone releases only once AI validators agree the submitted deliverable meets its stated criteria. | `routers/escrows.py`, `services/consensus.py` |
| **Dispute Resolution Court** | Either party escalates a milestone/escrow disagreement; both sides submit evidence, an AI validator jury rules, a ruling gets enforced. | `routers/disputes.py`, `services/consensus.py` |
| **Prediction Markets** | Wallet-scoped YES/NO positions on real-world claims; an autonomous oracle resolves the market and computes payouts. | `routers/predictions.py`, `services/prediction_oracle.py` |
| **Autonomous Governance** | Plain-language proposals voted on by the wallet-holding community, executed automatically once passed. | *Not yet built — see [Part 1](#31-governance-engine)* |

### 1.3 Architecture — Today

```mermaid
flowchart TB
    subgraph Client["Client Layer"]
        direction TB
        WALLET["EIP-6963 Wallet\n(MetaMask / Rabby / Phantom / etc.)"]
        FE["Next.js App Router\nReact 19 · TypeScript · Tailwind v4\nnuance-app.tsx"]
    end

    subgraph Backend["Backend Layer — FastAPI (async)"]
        direction TB
        AUTHR["auth router\nnonce -> verify -> JWT"]
        ESCROWR["escrows router"]
        DISPR["disputes router"]
        PREDR["predictions router"]
        CONSR["consensus router\n(status polling)"]
        CONSENGINE["Consensus Engine\nservices/consensus.py\nBackgroundTask"]
        ORACLE["Prediction Oracle\nservices/prediction_oracle.py"]
    end

    subgraph Data["Data Layer"]
        DB[("SQLite\nSQLAlchemy 2.0 async\n-> PostgreSQL, see Part 3")]
    end

    subgraph AI["AI Provider(s)"]
        GEMINI["Google Gemini\n(gemini-3.5-flash, 3x per job)"]
    end

    subgraph Chain["GenLayer Bradbury Testnet"]
        RPC["JSON-RPC\nrpc-bradbury.genlayer.com\nchainId 4221 / 0x107d"]
    end

    WALLET -->|"eth_requestAccounts · personal_sign\neth_chainId · eth_getBalance"| FE
    FE -->|"wallet_switchEthereumChain"| RPC
    FE -->|"fetch() + Authorization: Bearer JWT"| AUTHR
    FE --> ESCROWR
    FE --> DISPR
    FE --> PREDR
    FE -->|"poll every 500ms"| CONSR

    AUTHR --> DB
    ESCROWR --> DB
    DISPR --> DB
    PREDR --> DB
    CONSR --> DB

    ESCROWR -.->|"schedule on submit"| CONSENGINE
    DISPR -.->|"schedule on submit"| CONSENGINE
    CONSENGINE --> DB
    CONSENGINE -->|"structured tool-call JSON"| GEMINI

    PREDR -.->|"schedule on resolve"| ORACLE
    ORACLE --> DB

    RPC -.->|"Part 2: GenVM Intelligent Contracts\nreplace off-chain consensus"| CONSENGINE
```

> [!NOTE]
> Today's consensus engine is **off-chain, on-chain-flavored** by design (see `plan.md`): wallet connection and network identity are real, but the validator deliberation itself runs as a FastAPI background task calling Gemini directly, not as a GenVM Intelligent Contract. [Part 2](#4-part-2--genlayer-on-chain-transition--intelligent-contracts-genvm-integration) is the plan to close that gap.

### 1.4 Consensus Lifecycle — Today

```mermaid
sequenceDiagram
    participant U as User (wallet)
    participant FE as Next.js Frontend
    participant API as FastAPI Router
    participant BG as BackgroundTask (consensus.py)
    participant LLM as 3x Gemini calls
    participant DB as Database

    U->>FE: Submit deliverable / evidence
    FE->>API: POST /escrows/{id}/deliverable
    API->>DB: INSERT ConsensusJob(stage=QUEUED)
    API-->>FE: 201 Created { consensus_job_id }
    API->>BG: schedule run_consensus(job_id)
    FE->>API: GET /consensus/{job_id}  (every 500ms)

    par Validator-Alpha
        BG->>LLM: generate_content(prompt, tool=verdict_schema)
    and Validator-Beta
        BG->>LLM: generate_content(prompt, tool=verdict_schema)
    and Validator-Gamma
        BG->>LLM: generate_content(prompt, tool=verdict_schema)
    end

    LLM-->>BG: {vote, confidence, reasoning} x3
    BG->>DB: UPDATE stage=ANALYZING, validator_results=[...]
    BG->>BG: majority vote + avg confidence + 1.5s deliberation floor
    BG->>DB: UPDATE stage=DONE, verdict_label/approved/confidence/reasoning

    API-->>FE: GET /consensus/{job_id} -> stage=DONE, verdict
    FE-->>U: ConsensusPanel renders final verdict
```

---

## 2. Phase 0 — Current State & Baseline Audit

Everything in this section is **built and verified working today** (24/24 backend pytest tests pass; `npx tsc --noEmit` is clean).

### 2.1 What's Working

- [x] **Frontend core** — `nuance-app.tsx` app-shell with view routing (`dashboard`, `detail`, `create`, `predictions`, `predictionDetail`, `disputes`, `disputeDetail`, `governance`, `validators`, `agents`, `settings`); clean TS compilation.
- [x] **Web3 auth & session**
  - [x] EIP-6963 multi-wallet discovery (`use-wallet-detection.ts`, `wallet-catalog.tsx`) + legacy `window.ethereum` fallback.
  - [x] Real connection flow: `eth_requestAccounts` → `personal_sign` → `eth_chainId` → `eth_getBalance`, live `accountsChanged`/`chainChanged` subscriptions (`use-wallet-connection.ts`).
  - [x] GenLayer Bradbury network params sourced from the official `genlayer-js` SDK (`genlayer-chain.ts`) driving `wallet_switchEthereumChain` / `wallet_addEthereumChain`.
  - [x] Server-side SIWE-style auth: `POST /auth/nonce` → sign → `POST /auth/verify` (`eth_account.Account.recover_message`) → JWT, attached as `Authorization: Bearer` by `lib/api.ts`.
  - [x] Automatic 401 handling: `ApiError` + `setUnauthorizedHandler` drops the stored token and disconnects the wallet UI in lockstep.
- [x] **Backend foundation** — FastAPI (async), SQLAlchemy 2.0 async models, SQLite via `init_db()`, CORS, `/health`. 24/24 pytest passing (`test_auth_flow.py`, `test_consensus.py`, `test_predictions.py`).
- [x] **Escrows vertical** — `GET/POST /escrows`, `GET /escrows/{id}`, `POST /escrows/{id}/deliverable` (schedules a `ConsensusJob`), `POST /escrows/{id}/release`.
- [x] **Dispute Court vertical** — `GET/POST /disputes` (implicit via escrow), dispute messages (`GET/POST /disputes/{id}/messages`), evidence (`GET/POST /disputes/{id}/evidence`, schedules a `ConsensusJob`), `POST /disputes/{id}/enforce`.
- [x] **Prediction Markets vertical** — `GET /predictions`, `GET /predictions/{id}`, `POST /predictions/{id}/bet`, and an **autonomous resolution oracle** — `POST /predictions/{id}/resolve` (`services/prediction_oracle.py`) — this was flagged as an open gap in the original `plan.md` and has since shipped ahead of schedule.
- [x] **AI Consensus Engine** — `services/consensus.py`: 3 concurrent Gemini calls (`Validator-Alpha/Beta/Gamma`, matching `VALIDATOR_NAMES` in `consensus-panel.tsx` exactly), structured output via a Pydantic tool schema (`vote`/`confidence`/`reasoning`), `tenacity` retry with exponential backoff, majority-vote aggregation, a 1.5s minimum deliberation floor, staged (`IDLE→QUEUED→ANALYZING→DONE`) so the frontend can poll instead of guessing timing.
- [x] **Frontend↔backend wiring** — `lib/api.ts` (typed fetch wrapper, DTOs mirroring `schemas.py`) and `use-consensus-polling.ts` (500ms polling, stops at `DONE`) fully replace the old local `setTimeout` stage-chain simulation.
- [x] **User settings** — `GET/PATCH /auth/me`, `PATCH /auth/settings` wired to `SettingsView`.

### 2.2 Known Gaps (tracked, not yet started)

| Gap | Impact | Tracked in |
|---|---|---|
| Governance (`Proposal`/`Vote`) is local `useState` in `nuance-app.tsx`, seeded from `data.ts` | Votes aren't persisted, per-wallet, or tallied server-side | [Part 1 §3.1](#31-governance-engine) |
| Validator/Agent directories are static seed arrays, no reputation math | Trust signals shown in the UI (`accuracy`, `score`) aren't real | [Part 1 §3.2](#32-validator--agent-directory) |
| No Alembic — `init_db()` just calls `create_all` | Any schema change requires a fresh DB; no migration history | [Part 3 §5.1](#51-postgresql-migration-with-alembic) |
| Single LLM provider (Gemini only), no fallback | A Gemini outage or rate-limit event stalls every consensus job | [Part 1 §3.3](#33-consensus--oracle-hardening) |
| Consensus updates via 500ms polling | Wastes requests, ~250ms average added latency vs. push | [Part 1 §3.3](#33-consensus--oracle-hardening) |
| Off-chain, single-backend consensus | Doesn't yet use GenVM's actual equivalence-principle validator consensus — the product's own namesake mechanic isn't on-chain yet | [Part 2](#4-part-2--genlayer-on-chain-transition--intelligent-contracts-genvm-integration) |
| `data.ts`'s doc comment is stale (still claims predictions are mock) | Documentation drift, not a functional bug | Cleanup, below |

### 2.3 Tech Debt & Cleanup Tasks

- [x] `backend/.gitignore` already excludes `venv/`, `__pycache__/`, `*.db`, `.env`, `.pytest_cache/` — verified clean with `git status --ignored`. **No action needed**, just don't `git add -f` those paths when `backend/` is first committed.
- [ ] Update `components/app/data.ts`'s header comment — it still says predictions "stay local mock data," which is no longer true.
- [ ] Add root-level `backend/README.md` documenting local setup (`venv`, `requirements.txt`, `uvicorn app.main:app --port 8010`, `.env` keys) — currently only inferable from `plan.md`.
- [ ] Pin `MODEL = "gemini-3.5-flash"` and the two-provider list (below) to a config value (`GEMINI_MODEL` in `.env`) instead of a source constant, so model upgrades don't require a redeploy.
- [ ] Add `alembic` (see Part 3) before the schema grows further — every additional vertical below (governance, validator stats) adds tables that currently only exist via `create_all` on a fresh DB.

> [!TIP]
> Treat Phase 0 as the contract the rest of this roadmap builds on. Nothing here should regress — every part below is additive or hardens what's already shipped.

---

## 3. Part 1 — Backend Completion & Full Feature Parity (Immediate Sprint)

**Goal:** every view in the frontend is backed by a real, tested, persisted backend surface — no `data.ts` mock arrays left except pure copy/marketing content.

### 3.1 Governance Engine

> [!NOTE]
> **Backend shipped (2026-09-01).** `Proposal`/`Vote` models, all four endpoints, and the quorum/pass-threshold finalize logic are live — `backend/app/models/governance.py`, `backend/app/schemas/governance.py`, `backend/app/routers/governance.py`, mounted in `main.py`. Re-voting flips as designed (verified live: a wallet voting FOR then AGAINST moves `total_for` back to 0, not to -1). 14 new pytest tests in `backend/tests/test_governance.py`, all passing alongside the existing 24. Frozen response shapes captured live in `lib/fixtures/proposals.json` / `proposal-detail.json` (the Sync Point below) — the frontend wiring bullets underneath are still open.

#### Data model

```python
# backend/app/models.py — additions

class ProposalStatus(StrEnum):
    ACTIVE = "active"
    PASSED = "passed"
    REJECTED = "rejected"
    EXECUTED = "executed"

class VoteChoice(StrEnum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"

class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposer_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    title: Mapped[str]
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[ProposalStatus] = mapped_column(default=ProposalStatus.ACTIVE)
    quorum_pct: Mapped[int] = mapped_column(default=20)       # % of eligible voting power that must vote
    pass_threshold_pct: Mapped[int] = mapped_column(default=50)  # % FOR (of FOR+AGAINST) required to pass
    voting_ends_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)

    votes: Mapped[list["Vote"]] = relationship(back_populates="proposal", cascade="all, delete-orphan")

class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("proposal_id", "wallet_address"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    wallet_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    choice: Mapped[VoteChoice]
    weight: Mapped[int] = mapped_column(default=1)   # 1 today; GEN-stake-weighted in a later pass
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    proposal: Mapped["Proposal"] = relationship(back_populates="votes")
```

> [!NOTE]
> Re-voting **updates** the existing `Vote` row (unique on `proposal_id, wallet_address`) rather than inserting a duplicate — this is the deliberate behavior change `plan.md` already flagged: governance moves from "+4% nudge, no dedup" to a real per-wallet tally, so casting a second vote *flips* your prior vote instead of stacking.

#### Endpoints

| Method | Path | Auth | Behavior |
|---|---|---|---|
| `GET` | `/proposals` | — | List all proposals with live `for_pct`/`against_pct`/`quorum_met` computed from `votes`. |
| `GET` | `/proposals/{id}` | — | One proposal + full vote tally + the caller's own prior vote if a token is present. |
| `POST` | `/proposals` | JWT | Create a proposal (`title`, `summary`, `voting_period_days`, optional `quorum_pct`/`pass_threshold_pct` overrides). |
| `POST` | `/proposals/{id}/vote` | JWT | Body `{choice: "for"\|"against"\|"abstain"}`; upserts the caller's `Vote`. |
| `POST` | `/proposals/{id}/finalize` | JWT (or cron) | Idempotent: if `now >= voting_ends_at` and status is still `ACTIVE`, compute quorum + threshold, transition to `PASSED`/`REJECTED`, and — if passed — call `execute_proposal()`. |

#### Quorum & execution state machine

```mermaid
stateDiagram-v2
    [*] --> Active: POST /proposals
    Active --> Passed: voting_ends_at reached\nAND turnout >= quorum_pct\nAND for_pct >= pass_threshold_pct
    Active --> Rejected: voting_ends_at reached\nAND (turnout < quorum_pct OR for_pct < pass_threshold_pct)
    Passed --> Executed: execute_proposal() applies the encoded action
    Rejected --> [*]
    Executed --> [*]
```

- **Turnout** = `count(distinct votes.wallet_address)` ÷ `count(distinct users)` at finalize-time (a rough v1 proxy for "eligible voting power" until GEN staking exists).
- `finalize()` runs both (a) lazily — any `GET /proposals/{id}` past `voting_ends_at` triggers a finalize check — and (b) via a cron sweep (`services/governance.py::sweep_expired_proposals()`) so proposals close even with zero traffic, matching the "Audit Logging" and "CRON job" pattern `plan.md` already called out for prediction resolution.
- `execute_proposal()` starts as a no-op logger (`AuditLog` entry: "proposal #N executed") for text/sentiment proposals; parameter-change proposals (e.g. "raise validator stake requirement") get a typed `action_key`/`action_payload` column so execution can dispatch to real config mutations later without a schema change.

#### Frontend wiring

- [ ] `lib/api.ts`: `getProposals()`, `getProposal(id)`, `createProposal(payload)`, `castVote(id, choice)`.
- [ ] `nuance-app.tsx`: replace `INITIAL_PROPOSALS` + local `vote()` with a `loadProposals()` fetch (same pattern as escrows/disputes/predictions) and an async `vote()` that calls `castVote` then reconciles from the response instead of hand-rolling the `forPct`/`againstPct` nudge.
- [ ] `GovernanceView`: add a disabled state + optimistic UI while a vote is in flight; surface `quorum_met`/turnout, not just the for/against bar.

### 3.2 Validator & Agent Directory

> [!NOTE]
> **Backend shipped (2026-09-01), simplified from the design below.** `GET /validators` and `GET /agents` are live (`backend/app/routers/validators.py`, `routers/agents.py`) — computed **on read**, straight from `ConsensusJob` history, rather than the persisted `ValidatorStat`/`AgentProfile` tables sketched below. No new tables, no incremental-recompute hooks to keep in sync: an agent's `trust_score` is win-rate across every `ConsensusJob` where that wallet was the milestone submitter or dispute claimant, and a validator's `accuracy_pct` is how often its own vote matched the final verdict. Deliberately **not** included: a `stake` figure — there's no real GEN staking data yet, and a fabricated number would be worse than omitting the field. Both endpoints correctly return `[]` on a history-free database rather than seed rows. If read load ever makes the on-the-fly aggregation too slow, revisit the persisted-table design below then — not before.

Today `ValidatorDirectoryEntry`/`AgentDirectoryEntry` are static arrays. The fix is to derive both from data the system already produces — `ConsensusJob.validator_results` and escrow/dispute outcomes — rather than hand-maintaining numbers.

```python
class ValidatorStat(Base):
    """One row per named validator persona (Validator-Alpha/Beta/Gamma/...).
    Recomputed incrementally every time a ConsensusJob reaches DONE."""
    __tablename__ = "validator_stats"

    name: Mapped[str] = mapped_column(primary_key=True)
    cases_judged: Mapped[int] = mapped_column(default=0)
    cases_matched_majority: Mapped[int] = mapped_column(default=0)  # this validator's vote == final verdict
    stake: Mapped[Decimal] = mapped_column(Money, default=0)         # seeded for now; real once staking lands
    status: Mapped[str] = mapped_column(default="active")            # active | slashed | offline
    last_active_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def accuracy_pct(self) -> float:
        return 100.0 * self.cases_matched_majority / self.cases_judged if self.cases_judged else 0.0


class AgentProfile(Base):
    """One row per wallet that has *acted as a counterparty* (an "agent" in
    the UI's sense: an economic actor being scored, human or autonomous)."""
    __tablename__ = "agent_profiles"

    wallet_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"), primary_key=True)
    category: Mapped[str] = mapped_column(default="Uncategorized")
    txn_count: Mapped[int] = mapped_column(default=0)          # escrows + bets + disputes touched
    disputes_lost: Mapped[int] = mapped_column(default=0)
    milestones_completed: Mapped[int] = mapped_column(default=0)

    @property
    def trust_score(self) -> int:
        # Illustrative v1 formula — completion rate minus a dispute-loss
        # penalty, clamped to [0, 100]. Tune once real usage data exists.
        base = 100 * self.milestones_completed / max(self.txn_count, 1)
        penalty = 15 * self.disputes_lost
        return max(0, min(100, round(base - penalty)))
```

- `recompute_validator_stat(name, matched_majority)` is called once per validator, once per `ConsensusJob` transition to `DONE`, from inside `services/consensus.py` — no separate batch job needed since it's an O(1) update at the exact moment the ground truth (`verdict_approved`) is known.
- `recompute_agent_profile(wallet_address)` is called from `routers/escrows.py::release_milestone` and `routers/disputes.py::enforce` — the two places an outcome for a wallet becomes final.

#### New endpoints

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/validators` | List `ValidatorStat` rows sorted by `accuracy_pct` desc. |
| `GET` | `/validators/{name}` | One validator + recent `ConsensusJob` history (for a future drill-down view). |
| `GET` | `/agents` | List `AgentProfile` rows sorted by `trust_score` desc, joined to `users.display_name`. |
| `GET` | `/agents/{wallet_address}` | One agent's full transaction/dispute history. |

- [ ] `lib/api.ts` + `nuance-app.tsx`: fetch both on mount (same loading/error pattern as escrows), feed `ValidatorsView`/`AgentsView` real data instead of `VALIDATOR_DIRECTORY`/`AGENT_DIRECTORY`.
- [ ] Seed migration: backfill `ValidatorStat` rows for the three existing `VALIDATOR_NAMES` at zero, and `AgentProfile` rows for every distinct wallet already referenced by an `Escrow`/`Dispute`, so the directories aren't empty on first deploy.

### 3.3 Consensus & Oracle Hardening

#### Multi-model redundancy — heterogeneous validators, not just failover

Rather than treating Claude/OpenAI as a mere fallback for Gemini, assign **one provider per validator persona**. This is strictly better for a product whose entire pitch is *independent* consensus: three prompts to the same model is prompt-diversity only, three different frontier models is genuine architectural diversity, and it means a single vendor's outage or systematic bias can't silently produce a false "3-0 consensus."

```python
# backend/app/services/llm_providers.py (new)

class LLMProvider(Protocol):
    async def get_verdict(self, prompt: str) -> ValidatorVerdict: ...

class GeminiProvider(LLMProvider): ...   # existing google-genai call, extracted as-is
class ClaudeProvider(LLMProvider): ...   # anthropic SDK, tool_use for the same {vote,confidence,reasoning} schema
class OpenAIProvider(LLMProvider): ...   # openai SDK, response_format=json_schema

VALIDATOR_PROVIDERS: dict[str, LLMProvider] = {
    "Validator-Alpha": GeminiProvider(model="gemini-3.5-flash"),
    "Validator-Beta":  ClaudeProvider(model="claude-haiku-4-5"),
    "Validator-Gamma": OpenAIProvider(model="gpt-5-mini"),
}
```

- Each provider keeps its own `tenacity` retry policy (already in place for Gemini — generalize it into the `LLMProvider` base rather than duplicating per class).
- **Fallback chain**: if a persona's primary provider exhausts retries, fall back to a secondary (`Validator-Beta` → Claude, then Gemini as understudy) so a single provider outage degrades to "prompt diversity on 2 models" instead of stalling the whole job — log an `AuditLog` entry either way so degraded-consensus jobs are auditable, not silently masked as normal.
- Config additions: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` alongside the existing `GEMINI_API_KEY` in `backend/.env` / `config.py`.

#### Rate limiting

- [ ] Per-wallet write-endpoint limiting (`slowapi` or a Redis token bucket) on `POST /escrows/{id}/deliverable`, `POST /disputes/{id}/evidence`, `POST /predictions/{id}/bet` — these are the ones that either burn LLM tokens or move funds, and are the ones `plan.md`'s idempotency-key note already flagged for double-submit protection.
- [ ] Idempotency keys: accept an `Idempotency-Key` header (or hash the payload) on the same endpoints; a repeat within a short TTL returns the original `ConsensusJob`/response instead of spinning up a duplicate job.

#### Push instead of poll

Replace 500ms HTTP polling with a WebSocket push, keeping polling as an automatic fallback:

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant WS as /ws/consensus/{job_id}
    participant BG as run_consensus()

    FE->>WS: connect
    BG->>WS: stage=QUEUED
    WS-->>FE: {stage:1}
    BG->>WS: stage=ANALYZING, validator_results=[...]
    WS-->>FE: {stage:2, validator_results}
    BG->>WS: stage=DONE, verdict
    WS-->>FE: {stage:3, verdict}
    WS-->>FE: close
```

- [ ] `backend/app/routers/consensus.py`: add `@router.websocket("/ws/consensus/{job_id}")`, backed by an in-process `asyncio.Queue` per job (or Redis pub/sub once multi-worker — see Part 3) that `run_consensus()` publishes stage transitions to.
- [ ] `use-consensus-polling.ts` → `use-consensus-socket.ts`: open a `WebSocket`, but **retain the existing polling loop as a fallback** on connection failure/timeout so nothing regresses behind a proxy that strips upgrade headers.

**Definition of done for Part 1:** `data.ts` contains no data that a real wallet action can invalidate — governance, validators, and agents all round-trip through the backend; a Gemini outage degrades consensus quality instead of failing every submission; the consensus panel updates without a visible 500ms step.

---

## 4. Part 2 — GenLayer On-Chain Transition & Intelligent Contracts (GenVM Integration)

### 4.1 The architectural shift

Today, "consensus" is a FastAPI background task calling one or more centralized LLM APIs and writing the result to a database **Nuance controls**. GenLayer's actual value proposition is that this deliberation happens **inside Intelligent Contracts run by GenVM**, where independent validator *nodes* (not just independent prompts) execute the same non-deterministic block and reach on-chain consensus on the output via the **equivalence principle** — GenLayer's mechanism for validators to agree an LLM-produced result is "close enough" to be accepted, rather than requiring bit-for-bit determinism.

```mermaid
flowchart LR
    subgraph Before["Today — off-chain consensus"]
        A1[FastAPI backend] -->|"direct API call"| A2[LLM provider]
        A2 --> A3[(Nuance DB is\nsole source of truth)]
    end

    subgraph After["Part 2 — on-chain consensus"]
        B1[Next.js frontend] -->|"signed tx via genlayer-js"| B2["GenVM Intelligent Contract\n(Python)"]
        B2 -->|"gl.nondet.ai"| B3["LLM call, executed\nindependently by each\nGenLayer validator node"]
        B3 -->|"equivalence principle"| B4["On-chain consensus\non the LLM output"]
        B4 --> B5["Contract state\n(the verdict) is canonical"]
        B5 -.->|"indexed for fast reads"| B6[(Nuance backend DB\nas a read cache)]
    end
```

> [!IMPORTANT]
> GenLayer's SDK and `gl.*` API surface are actively evolving pre-mainnet. Treat every code sample in this section as **illustrating the intended pattern**, not a pinned API — verify method names/signatures against the `genlayer` Python package and official docs actually installed at build time before implementing.

### 4.2 Target contract layout

```
contracts/
  nuance_escrow.py            # milestone lifecycle + gl.nondet.ai deliverable review
  nuance_dispute_court.py     # evidence intake + gl.nondet.ai jury ruling
  nuance_prediction_market.py # bet intake + gl.nondet.web outcome verification
  common/
    validator_prompts.py      # shared prompt templates (mirrors services/consensus.py's prompts)
    schemas.py                 # shared {vote, confidence, reasoning} result type
  deploy.py                    # deployment script, see 4.4
  gltest/
    test_escrow_contract.py    # GenLayer's contract-simulator test harness
```

### 4.3 Illustrative contract skeleton

```python
# contracts/nuance_escrow.py — illustrative; validate gl.* signatures against
# the installed genlayer SDK before shipping.

from genlayer import *

class NuanceEscrow(gl.Contract):
    milestones: TreeMap[u256, Milestone]
    creator: Address
    counterparty: Address

    def __init__(self, counterparty: Address):
        self.creator = gl.message.sender_address
        self.counterparty = counterparty

    @gl.public.write
    def submit_deliverable(self, milestone_id: u256, criteria: str, deliverable_text: str) -> None:
        milestone = self.milestones[milestone_id]

        # Non-deterministic block: every validator node runs this
        # independently and GenVM's equivalence principle reconciles the
        # (necessarily slightly-varying) LLM outputs into one agreed result
        # before it's allowed to mutate contract state.
        def review() -> dict:
            prompt = (
                f"Milestone criteria: {criteria}\n"
                f"Submitted deliverable: {deliverable_text}\n"
                "Return {vote: approve|dispute, confidence: 0-100, reasoning: str}."
            )
            return gl.nondet.ai.exec_prompt(prompt, response_format="json")

        result = gl.eq_principle.strict_eq(review)  # or a looser comparator for free-text reasoning

        milestone.status = "approved" if result["vote"] == "approve" else "disputed"
        milestone.verdict_confidence = result["confidence"]
        milestone.verdict_reasoning = result["reasoning"]

        if milestone.status == "approved":
            self._release_funds(milestone_id)

    @gl.public.write
    def verify_external_claim(self, url: str, claim: str) -> bool:
        # gl.nondet.web is the oracle primitive: validators independently
        # fetch/scrape a live URL as part of the non-deterministic block,
        # used by the dispute court (verifying a linked evidence URL still
        # says what it was submitted as saying) and the prediction market
        # (checking a real-world outcome at resolution time).
        def check() -> bool:
            page = gl.nondet.web.render(url)
            return gl.nondet.ai.exec_prompt(
                f"Does this page support the claim '{claim}'? Page:\n{page}\nAnswer true or false."
            )
        return gl.eq_principle.majority_vote(check, rounds=3)
```

### 4.4 Deployment

```python
# contracts/deploy.py
from genlayer_py import create_client, create_account
from pathlib import Path

client = create_client(chain="genlayer-bradbury")   # rpc-bradbury.genlayer.com, chainId 4221
account = create_account(private_key=DEPLOYER_PRIVATE_KEY)

tx = client.deploy_contract(
    account=account,
    code=Path("contracts/nuance_escrow.py").read_text(),
    args=[],
)
receipt = client.wait_for_transaction_receipt(tx)
print("NuanceEscrow deployed at", receipt.contract_address)
```

- [ ] `deploy.py` writes deployed addresses to `backend/.env` (`ESCROW_CONTRACT_ADDRESS`, `DISPUTE_COURT_CONTRACT_ADDRESS`, `PREDICTION_MARKET_CONTRACT_ADDRESS`) and `.env.local` (`NEXT_PUBLIC_*` equivalents) so both layers point at the same deployment without hand-editing.
- [ ] A `contracts/CHANGELOG.md` tracking address history per redeploy — GenVM contracts are immutable once deployed, so upgrades mean a new address, and every consumer (indexer, frontend) needs a coordinated cutover.

### 4.5 Hybrid state — the indexer

GenLayer transactions move through **Proposed → Accepted → Finalized** (there's an appeal window between Accepted and Finalized under Optimistic Democracy). Reading contract state directly from the RPC on every page load would be slow and would surface "Accepted-but-not-yet-Finalized" data as if it were settled. The fix already implied by `plan.md`'s "off-chain, on-chain-flavored" framing generalizes cleanly here: keep Nuance's Postgres/SQLite database as a **read-optimized mirror**, populated by an indexer, while writes go straight from the frontend to the contract.

```
backend/app/services/genlayer_indexer.py
  - poll_new_transactions()   # gen_getTransactionReceipt / block range scan since last cursor
  - sync_escrow_state(addr)   # read contract storage, upsert into Escrow/Milestone tables
  - sync_dispute_state(addr)
  - track_finality(tx_hash)   # Accepted -> Finalized -> update a `chain_status` column read by the UI
```

- [ ] `ConsensusJob`/`Escrow`/`Dispute` rows gain a `chain_status: accepted | finalized | appealed` column and (once Part 2 ships) an `on_chain_tx_hash`, so the frontend can show "optimistically approved, finalizing…" — an honest UX for GenLayer's actual consensus timing, instead of implying instant finality.
- [ ] Writes: evaluate whether the frontend signs and sends transactions directly via `genlayer-js` (most decentralized, but means gas/GEN costs land on end users) vs. a backend relayer service account (smoother UX, reintroduces a centralization point) — **default recommendation: direct frontend signing**, consistent with how wallet connection already works, with the backend indexer purely a read cache.
- [ ] Migration path: escrows/disputes created *before* the cutover stay served by the existing off-chain `services/consensus.py` path (mark them `chain_status: legacy_offchain`); only new escrows target the deployed contract. No forced migration of historical data onto GenVM.

**Definition of done for Part 2:** a new escrow's milestone-approval consensus is computed by validator nodes executing `NuanceEscrow.submit_deliverable` on Bradbury testnet, not by the FastAPI backend calling an LLM directly; the frontend reflects Accepted vs. Finalized state truthfully.

---

## 5. Part 3 — Production Hardening, Security, Real-Time UX & Analytics

### 5.1 PostgreSQL Migration with Alembic

- [ ] `alembic init backend/alembic`; point `env.py` at `Base.metadata` from `app.db` for autogenerate.
- [ ] Generate an initial "baseline" revision against the **current** SQLite schema (`alembic revision --autogenerate -m "baseline"`) before changing anything else, so history starts from what's actually deployed today.
- [ ] `docker-compose.yml` adding a local `postgres:16` service; `DATABASE_URL` becomes `postgresql+asyncpg://...` (already a one-line change per `plan.md`'s original design goal).
- [ ] One-off `scripts/migrate_sqlite_to_postgres.py` for any existing demo data worth preserving.
- [ ] CI gate: `alembic upgrade head --sql` (dry-run) on every PR that touches `models.py`, plus a check that a new model change always ships with a matching revision file (`alembic check`).

### 5.2 Real-Time Architecture

- [ ] Land the WebSocket consensus channel from [§3.3](#33-consensus--oracle-hardening) behind a Redis pub/sub backbone (not just an in-process `asyncio.Queue`) so it survives multi-worker `uvicorn --workers N` deployment.
- [ ] Extend the same channel to dispute-message live updates (`/ws/disputes/{id}/messages`) — today `sendDisputeMessage` requires a manual refetch.
- [ ] SSE as the documented fallback transport for environments that block WebSocket upgrades (some corporate proxies), sharing the same publish call as the WS path.

### 5.3 Test Suite Expansion

| Layer | Tooling | New coverage |
|---|---|---|
| GenVM contracts | `gltest` (GenLayer's simulator harness) | `submit_deliverable` approve/dispute paths, `verify_external_claim` against a mocked page |
| Backend load | `locust` or `k6` | Concurrent `POST /escrows/{id}/deliverable` under load — validates rate limiting & idempotency keys from §3.3 actually hold |
| Backend integration | `pytest` (extend existing suite) | Governance quorum/finalize edge cases, validator/agent stat recomputation correctness |
| E2E | Playwright (Cypress is also fine — pick one, don't run both) | Full escrow lifecycle: connect a mocked injected wallet → create escrow → submit deliverable → watch consensus resolve → release funds |

- [ ] CI: run the existing 24 pytest tests + new suites on every PR; block merge on failure (none of this exists as CI today — only local `pytest` runs).

### 5.4 Security Hardening

- [ ] **Prompt injection guards** — deliverable text and dispute evidence are user-controlled strings interpolated directly into validator prompts. Harden with: explicit delimiter fencing (already partially achieved by the structured tool-call schema, which constrains *output* but not input); a pre-flight classifier pass or regex/heuristic scan for instruction-like content ("ignore previous instructions", role-play framing) that flags a submission for review rather than silently feeding it in verbatim; logging the raw prompt+response pair per `ConsensusJob` for audit.
- [ ] **Sybil defense on governance** — 1-wallet-1-vote as built is trivially sybil-able with disposable wallets. Mitigate with `weight` tied to wallet age/tx-history heuristics initially, moving to real GEN-stake-weighted voting once Part 2's on-chain balances are readable by the indexer.
- [ ] **Escrow lock safety** — ensure `release_milestone`/`enforce` can't double-fire: DB-level row locking (`SELECT ... FOR UPDATE` once on Postgres) or a `status_key` guard clause checked inside the same transaction as the mutation, plus the idempotency keys from §3.3 covering the HTTP layer above that.
- [ ] Dependency/secret scanning (`pip-audit`, `npm audit`, gitleaks) in CI given real API keys (`GEMINI_API_KEY`, `JWT_SECRET`, future `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`) now live in `backend/.env`.

### 5.5 Analytics Foundation

- [ ] New `routers/analytics.py`: `GET /analytics/overview` (TVL in open escrows, dispute resolution median time, validator accuracy leaderboard, prediction market volume) backing a new `AnalyticsView`.
- [ ] Materialized/aggregated tables refreshed on a cron (reuse the sweep pattern from governance finalize) rather than computing aggregates on every request.

**Definition of done for Part 3:** the app runs on Postgres with a real migration history, consensus and dispute updates push instead of poll, CI blocks regressions across contract/load/integration/E2E layers, and the three security items above have shipped mitigations, not just a written acknowledgment.

---

## 6. Part 4 — Ecosystem Expansion, Autonomous Agents & Mainnet Readiness

### 6.1 Autonomous Agent Participation

Nuance's own "Agent Directory" concept implies non-human counterparties should be able to act without a browser wallet flow.

- [ ] `POST /auth/api-keys` (JWT-authed) issues a scoped API key per wallet: `{key_id, secret, scopes: ["escrow:create","bet:place","evidence:submit"]}`.
- [ ] `apiFetch` in `lib/api.ts`-equivalent server SDKs authenticate via `X-Api-Key` instead of a bearer JWT, verified the same way (maps back to a `wallet_address`, same permission checks).
- [ ] Webhooks: `POST /webhooks` registers a callback URL invoked on `consensus.completed`/`dispute.resolved`/`prediction.resolved` — so an autonomous agent doesn't need to poll `use-consensus-polling.ts`'s equivalent itself.
- [ ] Per-key rate limits distinct from per-wallet UI limits (agents are expected to be higher-throughput but more automatable-abuse-prone).

### 6.2 Multi-Token Collateral

- [ ] Generalize `Escrow.total: Decimal` into an `(amount: Decimal, asset_id: FK)` pair:

```python
class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str]              # "GEN", "USDC", ...
    decimals: Mapped[int]
    contract_address: Mapped[str | None]   # null for native GEN
    is_native: Mapped[bool] = mapped_column(default=False)
```

- [ ] Support native `GEN` (Bradbury testnet's currency, already known to `genlayer-chain.ts`) plus a testnet ERC-20 stablecoin (e.g. testnet USDC) for predictable-value escrows.
- [ ] Prediction market payouts and escrow releases both read `Asset.decimals` rather than assuming 2-decimal USD-like amounts (today's `Numeric(12,2)` `Money` type is USD-shaped and won't hold an 18-decimal GEN amount correctly).

### 6.3 Mainnet Readiness Checklist

- [ ] Independent security audit of both the FastAPI backend and the GenVM contracts (Part 2) — non-negotiable before any non-testnet fund custody.
- [ ] Gas/GEN cost modeling for contract calls under realistic load (validator equivalence-principle calls are inherently more expensive than a plain state write — budget for it).
- [ ] Governance-controlled treasury via a multi-sig (or the governance contract itself once `execute_proposal` handles real fund movement, see §3.1).
- [ ] Monitoring/alerting: Sentry (backend errors + frontend), Grafana/Prometheus (API latency, consensus job queue depth, LLM provider error rates from §3.3's fallback chain).
- [ ] Incident-response runbook: what happens when a `ConsensusJob` hangs, when a GenVM appeal overturns a Finalized state the indexer already mirrored, when an LLM provider is fully down.
- [ ] Public developer SDK: an OpenAPI-generated TypeScript client (`@nuance/sdk`) and Python client (`nuance-sdk` on PyPI) wrapping the same REST surface `lib/api.ts` already defines, so external integrators (including the autonomous agents from §6.1) don't hand-roll `fetch` calls.
- [ ] Public docs site (versioned API reference + contract addresses per network) ahead of any mainnet announcement.

**Definition of done for Part 4:** an external, non-Nuance-authored agent can create an escrow, get judged by consensus, and receive a payout entirely through the API/SDK with no browser involved; the app supports more than one settlement asset; a named security firm has signed off before mainnet.

---

## 7. Appendix

### 7.1 Target Directory Structure (post–Part 2)

```
Nuance/
├── app/                          # Next.js App Router
├── components/app/               # Frontend feature code (views, hooks, wallet flow)
├── lib/api.ts                    # Backend REST client
├── contracts/                    # GenVM Intelligent Contracts (Part 2)
│   ├── nuance_escrow.py
│   ├── nuance_dispute_court.py
│   ├── nuance_prediction_market.py
│   ├── deploy.py
│   └── gltest/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py             # + Proposal, Vote, ValidatorStat, AgentProfile, Asset
│   │   ├── schemas.py
│   │   ├── enums.py
│   │   ├── routers/              # + governance.py, validators.py, agents.py, analytics.py
│   │   └── services/
│   │       ├── consensus.py
│   │       ├── llm_providers.py  # Part 1 multi-model abstraction
│   │       ├── prediction_oracle.py
│   │       ├── governance.py     # Part 1
│   │       └── genlayer_indexer.py  # Part 2
│   ├── alembic/                  # Part 3
│   └── tests/
├── docker-compose.yml            # Part 3 — Postgres
├── plan.md                       # original backend design doc (superseded in scope by this file)
└── ROADMAP.md                    # this file
```

### 7.2 Glossary

| Term | Meaning |
|---|---|
| **GenVM** | GenLayer's virtual machine executing Python-based Intelligent Contracts. |
| **Equivalence Principle** | GenVM's mechanism for validator nodes to agree a non-deterministic (LLM) result is consistent enough to accept, without requiring byte-identical outputs. |
| **Optimistic Democracy** | GenLayer's consensus model: a leader proposes, validators vote, state is Accepted then Finalized after an appeal window. |
| **`gl.nondet.ai`** | GenVM primitive for an LLM call inside a non-deterministic contract block. |
| **`gl.nondet.web`** | GenVM primitive for live web access (scraping/oracle data) inside a non-deterministic contract block. |
| **`ConsensusJob`** | Nuance backend's own staged record (`IDLE→QUEUED→ANALYZING→DONE`) of one off-chain validator run; the on-chain equivalent post–Part 2 is a contract's own transaction receipt. |

### 7.3 References

- `plan.md` — the original backend design doc this roadmap builds on and, in places, supersedes (multi-model consensus, WebSocket upgrade, and the GenVM transition are new relative to it).
- [GenLayer docs](https://docs.genlayer.com) and `genlayer-js` (`github.com/genlayerlabs/genlayer-js`) — source of truth for `gl.*` API signatures; re-verify before implementing Part 2.
- `README.md` — current frontend structure and what's demo data vs. real (wallet connection, GenLayer network params).

---

> [!TIP]
> This roadmap is a living document. As each checkbox above ships, update it in the same PR — a roadmap that drifts from reality is worse than no roadmap.
