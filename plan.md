# Backend Plan — Nuance API (Python)

Design doc for the Python backend, written before any backend code exists.
Scoped around three decisions already made:

- **AI-validator consensus is real** — actual LLM calls per validator, not
  keyword-matched mock logic.
- **Off-chain backend, on-chain-flavored** — a normal REST API with its own
  database implements the business logic; wallet connect stays real/cosmetic
  (proves identity + network) but no Intelligent Contracts get deployed.
- **Wallet-scoped accounts** — the connected wallet address is the user's
  identity, verified server-side, with real per-wallet persistence instead of
  one shared demo state.


Here are a few technical additions and edge cases worth incorporating into your plan before you start writing the backend logic:

1. LLM Reliability & Structured Outputs
Enforce JSON via Tool Use: Instead of relying strictly on prompt engineering to get Claude Haiku to return valid JSON, use Anthropic's Tool Use (Function Calling) API. Define your {vote, confidence, reasoning} schema as a required tool. This guarantees the LLM returns perfectly structured data and prevents your parsing logic from breaking.

Implement Retry Logic: Network hiccups and API rate limits happen. Wrap the concurrent Anthropic calls in a retry library (like tenacity) with exponential backoff to handle transient errors gracefully.

2. State Safety & Concurrency
Idempotency Keys: Prevent race conditions. If a user double-clicks the "Submit Deliverable" button, you don't want to spin up duplicate ConsensusJob rows and burn unnecessary LLM tokens. Lock the milestone state or use an idempotency key tied to the submission payload.

FastAPI Background Tasks: Instead of blocking the HTTP request while waiting for the LLM, use FastAPI's native BackgroundTasks. The POST request instantly returns 201 Created (moving the UI to Stage 1), while the background task handles the concurrent LLM calls and database updates.

3. Bridging the Gaps
Intelligent Oracle Simulation: For the missing prediction market resolution, you don't necessarily need a UI button. You could add a simple backend CRON job or an /admin/resolve-markets endpoint. This could trigger an LLM to simulate a live web search to verify real-world outcomes and settle the market data autonomously.

Audit Logging: Since this models a dispute court and governance system, consider adding a lightweight AuditLog table. Tracking exactly when a consensus job transitioned between stages provides great debugging telemetry
---

## 1. Stack

| Piece | Choice | Why |
|---|---|---|
| Framework | **FastAPI** (async) | Matches the staged/polling nature of consensus jobs; free OpenAPI docs; Pydantic schemas map cleanly onto `types.ts`. |
| DB | **SQLite via SQLAlchemy 2.0 (async)** + Alembic | Zero-setup for a demo-scale app; `DATABASE_URL` env var makes swapping to Postgres later a one-line change. |
| LLM | **Anthropic API** (Claude Haiku 4.5 per validator call) | Cheap/fast for 3 concurrent calls per submission; upgradeable to Sonnet if verdict quality needs it. |
| Auth | Signature verification via `eth_account` + JWT session token | Verifies the wallet's existing `personal_sign` flow server-side; no new wallet UX. |
| Sync | HTTP polling on a `consensus job` resource | Simplest thing that works for a 2–5s job; WebSockets are a clean later upgrade, not needed for v1. |

```
backend/
  app/
    main.py            # FastAPI app, CORS, router mounting
    config.py           # env vars (DATABASE_URL, ANTHROPIC_API_KEY, JWT_SECRET, CORS_ORIGINS)
    db.py                # async engine/session
    models/              # SQLAlchemy tables
    schemas/              # Pydantic request/response models
    routers/
      auth.py  escrows.py  predictions.py  disputes.py
      governance.py  validators.py  agents.py  settings.py
    services/
      auth.py            # nonce issuance + signature recovery
      consensus.py        # the AI-validator engine (core logic)
    seed.py               # inserts data.ts's exact rows on first run
  alembic/
  tests/
  requirements.txt
  .env.example
```

---

## 2. Data model (mirrors `types.ts`, adds ownership)

- **User** — `wallet_address` (PK), `nonce`, `nonce_issued_at`
- **Escrow** — id, `owner_wallet` FK, title, counterparty, total, status_key
- **Milestone** — id, `escrow_id` FK, name, amount, status_key, criteria, order_index
- **DeliverableSubmission** — milestone_id FK, wallet FK, text, submitted_at
- **ConsensusJob** — id, `subject_type` (`milestone`|`dispute`), `subject_id`, stage (0–3), `validator_results` (JSON: 3× {name, vote, confidence, reasoning}), final verdict fields, timestamps — this is the one new concept not in the frontend today; it's what stage-polling reads.
- **Prediction** / **Position** (wallet FK, side, amount — upsert per wallet+market, same as today's `positions[predictionId]`)
- **Dispute** / **EvidenceSubmission** (verdicts also live in `ConsensusJob`)
- **Proposal** / **Vote** (wallet FK, choice, unique on `(proposal_id, wallet)`)
- **ValidatorDirectoryEntry** / **AgentDirectoryEntry** — seeded, static for v1
- **UserSettings** — wallet FK, notify_on, auto_escalate_on

---

## 3. Auth flow (the one real UX change)

Today the frontend generates its own sign-in nonce client-side — fine for
proving key control, useless for server-side replay protection. Fix:

1. `POST /auth/nonce {address}` → server issues & stores a nonce, returns the
   exact message string to sign.
2. Wallet signs it (same `personal_sign` step already in
   `use-wallet-connection.ts` — just swap the locally-built message for the
   server's).
3. `POST /auth/verify {address, message, signature}` → server recovers the
   signer (`eth_account.Account.recover_message`), checks it matches
   `address` and the nonce is fresh/unused, returns a JWT.
4. Frontend attaches `Authorization: Bearer <token>` to every write call.
   Token dropped on disconnect.

This is the only change to `use-wallet-connection.ts`'s actual logic —
everything else about wallet detection/connection stays untouched.

---

## 4. The consensus engine — the core mechanic, made real

`services/consensus.py::run_consensus(subject_type, subject_id, context)`:

1. Insert a `ConsensusJob` at stage 1 (queued) immediately on submit.
2. Fire 3 concurrent Anthropic calls, one per validator persona
   (**Validator-Alpha/Beta/Gamma** — matching `VALIDATOR_NAMES` exactly,
   since `consensus-panel.tsx` renders rows by that constant). Each prompt
   gets the milestone criteria (or dispute issue) + the submitted text, and
   must return structured JSON:
   `{vote: "approve"|"dispute", confidence: 0-100, reasoning: str}`.
   `temperature ≈ 0.5` gives genuine independent variance rather than 3
   identical outputs.
3. Move to stage 2 (analyzing) the instant calls are dispatched.
4. On all 3 resolving: majority vote decides the verdict direction;
   confidence = average of the majority's confidence scores; reasoning = the
   majority's own reasoning (skip a 4th "synthesis" call initially —
   cheaper, and still reads fine in the panel; easy to add later if verdicts
   read too raw).
5. Stage → 3, verdict persisted.
6. Enforce a floor (~1.2s) before allowing stage 3, so a fast LLM response
   doesn't make the UI flash instead of feeling like real deliberation.

`GET /consensus/{job_id}` returns `{stage, validator_results, verdict}` —
the frontend polls this every ~500ms after submit, replacing its current
local `after(ms, fn)` timer chain in `nuance-app.tsx` one-for-one.

---

## 5. REST surface (1:1 against what each view already calls)

| Resource | Endpoints |
|---|---|
| Auth | `POST /auth/nonce`, `POST /auth/verify` |
| Escrows | `GET /escrows`, `POST /escrows`, `GET /escrows/{id}`, `POST /escrows/{id}/deliverable`, `GET /consensus/{job_id}`, `POST /escrows/{id}/release` |
| Predictions | `GET /predictions`, `GET /predictions/{id}`, `POST /predictions/{id}/bet` |
| Disputes | `GET /disputes`, `GET /disputes/{id}`, `POST /disputes/{id}/evidence`, `POST /disputes/{id}/enforce` |
| Governance | `GET /proposals`, `POST /proposals/{id}/vote` |
| Directories | `GET /validators`, `GET /agents` |
| Settings | `GET /settings`, `PATCH /settings` |

All writes except `/auth/*` require the bearer token. `release`/`enforce`
port `activeMilestoneIndex` logic (`status.ts`) server-side unchanged.

---

## 6. Frontend changes needed

- New `lib/api.ts` — fetch wrapper with `NEXT_PUBLIC_API_URL` base + auth
  header injection.
- `nuance-app.tsx`'s handlers (`submitDeliverable`, `submitCreate`,
  `placeBet`, `submitEvidence`, `enforceRuling`, `vote`) become async: call
  the endpoint, then either use the response directly or start polling
  `/consensus/{job_id}`.
- `data.ts`'s static arrays get replaced by fetched data (loading states
  needed per view — currently none exist).
- `use-wallet-connection.ts` gains one extra round-trip: fetch nonce before
  signing.
- Governance vote changes from a flat "+4% nudge, no dedup" to a real
  per-wallet tally — a deliberate behavior change worth flagging, since it's
  more "real" but re-voting now flips your own prior vote instead of
  stacking.
- CORS on the backend allows `http://localhost:3000`.

---

## 7. Build order

1. Scaffold FastAPI + DB + Alembic + `seed.py` (ports `data.ts` verbatim) —
   nothing frontend-visible yet.
2. Auth: nonce/verify + frontend nonce round-trip + token storage.
3. Read-only GETs → swap `data.ts` imports for fetches (biggest visible
   milestone: app is now backend-driven).
4. Non-AI writes: create escrow, place bet, vote, enforce ruling, settings.
5. Consensus engine: LLM-backed deliverable/evidence submission + polling,
   replacing local stage timers.
6. Tests: consensus aggregation logic, signature verification, and one full
   escrow-lifecycle integration test via FastAPI's test client.

---

## 8. Gaps worth naming now (not solved by this plan alone)

- **No prediction-market resolution exists in the UI at all** — no "resolve
  this market" action anywhere in the frontend, so payouts aren't in scope
  unless you want that view added.
- Validator accuracy / agent scores stay static seed data for v1; making
  them compute from real dispute history is a natural v2, not required for
  "functional."
