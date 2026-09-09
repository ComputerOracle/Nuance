# Nuance — Incident Response Runbook

ROADMAP.md Part 4 §6.3's mainnet-readiness checklist item: "Incident-response
runbook: what happens when a `ConsensusJob` hangs, when a GenVM appeal
overturns a Finalized state the indexer already mirrored, when an LLM
provider is fully down." Each section below covers one real failure mode
this codebase already has to tolerate — grounded in what the code actually
does today (file:line references throughout), not generic incident-response
boilerplate. Written from Emma's "coordinate the mainnet checklist" item on
the Part 4 build plan; this is the document that item produces.

**Scope**: this is for whoever is on call for Nuance in production — today
that's Chibuikem and Emma; update this line once the team grows. Every
playbook below assumes you have shell access to the backend host and can
read its logs; none require GenVM/Bradbury-specific tooling beyond what's
already in this repo (`scripts/genlayer-read.ts`, `alembic`, `psql`/`sqlite3`).

## Before you start: how to tell something's actually wrong

Nuance has no dashboards yet (§6.3's other checklist items —
Grafana/Prometheus, and Sentry's frontend half — are still open; see the
bottom of this doc). Until those exist, the signal is **structured log
lines this codebase already emits on purpose** — every optional/degradable
integration logs a clear warning the moment it falls back, by design (see
each service's own docstring). `grep` these in whatever log aggregation you
have (`backend/logs/dev-server.log` locally, your platform's log stream in
prod):

| Grep for | Means |
|---|---|
| `falling back to DB polling for the rest of this process's life` | Redis is unreachable — see [Redis outage](#redis-outage) |
| `will use the deterministic offline heuristic for every validator` | No LLM provider is configured/reachable — see [LLM providers down](#llm-providers-fully-down) |
| `genlayer_indexer: poll cycle failed` | The chain indexer hit an exception this cycle — see [Chain indexer](#chain-indexer-stuck-or-crashing) |
| `provider 'X' failed` (repeated, all three) | A specific consensus job fell all the way through the provider chain — see [Consensus job stuck](#a-consensusjob-never-reaches-done) |
| `Dropped malformed pub/sub message` | A Redis payload didn't deserialize — usually transient, page if repeated |

## A `ConsensusJob` never reaches DONE

**Symptom**: a milestone/dispute stays stuck at "Analyzing" in the UI
indefinitely; `GET /consensus/{job_id}` keeps returning `stage < 3`.

**What's actually running**: `services/consensus.py::run_consensus` is a
single `BackgroundTasks` call fired from the request that created the job
(`routers/escrows.py::submit_deliverable`, `routers/disputes.py::
submit_evidence`) — it is **not** a durable queue with retries. If the
*process* that handled that original request dies mid-run (OOM, deploy,
crash) before `run_consensus` finishes, the job is orphaned permanently:
nothing will ever pick it back up. This is the single biggest operational
gap in the consensus pipeline as of this writing — flagged, not fixed, by
this runbook.

**Diagnose**:
1. `GET /consensus/{job_id}` — note `stage`. `0`/`1` (IDLE/QUEUED) stuck
   for more than a few seconds past creation means the background task
   likely never started or died before its first commit.
2. Check logs for that job id / the milestone's deliverable text. Every
   validator's fallback attempt logs its own line (`_run_validator_with_
   fallback`) — if you see all three land on `every configured provider
   failed ... using the deterministic offline heuristic`, the job should
   still complete in ~`MIN_DELIBERATION_SECONDS` (1.5s) — if it's been
   longer than that and `stage` hasn't moved, the process crashed mid-run.
3. `grep` for `run_consensus: no ConsensusJob for subject_type=...` — a
   distinct bug (the job row itself never got created), not this one.

**Recover**: there is no automatic retry. Manually re-trigger by re-calling
the mutation that started it — for a milestone, the deliverable's already
recorded (`DeliverableSubmission`), so re-POSTing `/escrows/{id}/
deliverable` with the same text creates a second `ConsensusJob` and a
second submission row (idempotent in effect, not byte-identical state, but
functionally fine — the milestone's `status_key` gets re-set to
`IN_REVIEW` either way). For a dispute, same idea via `/disputes/{id}/
evidence`.

**Prevent** (not yet built): the honest fix is a durable job queue (Celery/
arq/a simple `SELECT ... FOR UPDATE SKIP LOCKED` sweep like governance's own
finalize pattern) that a separate worker polls, instead of a
`BackgroundTasks` call tied to the lifetime of the request process that
created it. Track this against ROADMAP.md §5.3's still-open load-testing
item — a queue is also what makes rate-limited concurrent submission
actually safe under real load.

## LLM providers fully down

**Symptom**: `will use the deterministic offline heuristic for every
validator` in the logs for every job; verdicts still arrive (fast — no
network round trip) but every reasoning string reads `"Offline heuristic
fallback: no LLM provider was reachable for <name>. Matched N positive vs M
negative signal keyword(s)..."` instead of real model output.

**This is a designed degradation, not an outage** — `services/
consensus.py::_deterministic_heuristic_verdict` (keyword-matched,
deterministic, zero network calls) is what every validator falls back to
once its whole provider chain (Gemini → Anthropic → OpenAI, persona-
dependent order) is exhausted. **The system keeps functioning** — it just
stops being a real AI judgment. This is *worse* than a hard failure in one
specific way: nothing blocks a user from continuing to submit deliverables
and get "verdicts" that are keyword-matching, not adjudication.

**Diagnose which providers are actually down**: `provider 'gemini' failed
(...)` / `has no API key configured — skipping` lines name the specific
provider and error (rate limit, invalid key, credit balance, timeout — see
this exact scenario already hit live: a real "Your credit balance is too
low to access the Anthropic API" 400 during this repo's own Playwright E2E
work, see git history around 2026-09-08).

**Recover**: fix whichever provider(s) failed (top up credits, rotate a
revoked key, wait out a rate limit) — no restart needed, `_build_provider_
clients` re-reads `settings` (itself `lru_cache`d — a **key rotation
requires a process restart**, an env var change alone won't be picked up
under the running process).

**Escalate if**: this persists for more than a few minutes during business
hours — every verdict issued in that window is a keyword-match, not a real
judgment, and any escrow/dispute resolved under it should be considered for
manual review once providers recover.

## Redis outage

**Symptom**: `Redis publish failed for consensus job ... — falling back to
DB polling for the rest of this process's life` / same for `subscribe`.

**This is also a designed degradation** — `services/realtime.py`'s own
module docstring: an unreachable Redis on first use marks the pub/sub layer
unavailable **for that process's remaining lifetime** (not re-checked per
call) and every WS/SSE endpoint (consensus, dispute messages) falls back to
the original per-connection DB-polling loop, unchanged. Users see slightly
higher latency on live updates (polling cadence, not instant push) and, if
you're running `uvicorn --workers N > 1`, updates from one worker no longer
reach a WS connection accepted by a different worker — see that file's own
header for why.

**Diagnose**: `redis-cli -u $REDIS_URL ping` from the backend host.

**Recover**: fix Redis (restart the container/service, check
`REDIS_URL`), then **restart the backend process** — `_get_client`'s
"unavailable for this process's life" flag does not self-heal without a
restart, by design (a working system shouldn't hammer a downed Redis on
every request trying to reconnect).

## Chain indexer stuck or crashing

**Symptom**: `genlayer_indexer: poll cycle failed` in logs, repeated;
on-chain-linked escrows/disputes/predictions stop reflecting real chain
state (status badges go stale).

**What's running**: `services/genlayer_indexer.py::run_forever`, a
background task inside the same process as the API server (`main.py`'s
lifespan, gated by `ENABLE_CHAIN_INDEXER`). Its own `except Exception`
around each cycle means **one bad cycle logs and moves on** — it does not
crash the server, and does not stop trying on the next cycle
(`genlayer_indexer_poll_seconds`, default 15s).

**Diagnose**: read the actual traceback in `poll cycle failed` — the RPC
leg shells out to `npx tsx scripts/genlayer-read.ts` as a subprocess per
cycle; a hung or leaked subprocess is the most likely repeat-failure mode
(check `ps aux | grep genlayer-read` for orphans). A single cycle timing
out against a slow Bradbury RPC is expected occasionally and self-heals
next cycle — only escalate if failures are **consecutive and repeated**.

**Recover**: restart the backend process (clears any leaked subprocess
state). If Bradbury's own RPC is down, there's nothing to do but wait — the
indexer will resume once it's reachable again, no data is lost (every
sync is a fresh read against current chain state, not an event log that
can gap).

## A GenVM appeal overturns a Finalized state the indexer already mirrored

**Current understanding** (see `lib/chain-status.ts`'s own header): GenVM's
`isDecidedState()` — which this app's `chain-status.ts` uses verbatim, not
a hand-rolled copy — already buckets `ACCEPTED` and both `APPEAL_*` states
under `"decided"`, distinct from `"finalized"`. That implies `FINALIZED`
is only reached *after* the appeal window has already closed, which would
make this scenario impossible by construction. **This has not been proven
against a real live appeal** (Bradbury testnet's appeal flow has not
actually been exercised end-to-end by this codebase's own live-testing —
see ROADMAP.md's own "confirmed live" standard for everything else in Part
2). Treat this section as a contingency plan for something that
*shouldn't* happen, not confirmation that it can't.

**If it ever does happen**: the indexer's own sync (`genlayer_indexer.py::
run_once`) always reads current chain state fresh, every cycle — there is
no cached/derived "finalized, so stop checking" shortcut in the poll loop
itself. A reversed on-chain verdict **will** get picked up and overwrite
the mirrored DB row on the very next poll cycle. The actual risk is
downstream, not in the indexer: any payout, dispute enforcement, or UI
state a user already acted on *before* the reversal was caught needs
manual reconciliation — this app has no automatic "undo a payout" path
(GenVM contracts are the source of truth for funds; the backend DB is a
read cache of them, not the other way around, so a real fund movement
based on stale state can't be silently rolled back in the DB alone).

**Recover**: (1) confirm the reversal by reading the contract directly
(`client.getContractSchema`/a manual `get_dispute`/`get_milestone` call —
don't trust only the mirrored DB row once you suspect this), (2) if funds
already moved on the old (wrong) verdict, this becomes a manual
reconciliation with the affected parties — there is no code path for it
today.

## Auto-deploy background task failing silently

**Symptom**: an escrow/prediction market is created but `contract_address`
stays `null` indefinitely (never gets linked on-chain) even though
`AUTO_DEPLOY_ESCROW_CONTRACTS`/`AUTO_DEPLOY_PREDICTION_CONTRACTS` is `true`.

**What's running**: `services/genlayer_deploy.py::deploy_escrow_contract`/
`deploy_prediction_contract`, fired as a `BackgroundTasks` call from
`create_escrow`/the market-generator's own publish path — same "tied to
the creating request's process lifetime" caveat as
[ConsensusJob](#a-consensusjob-never-reaches-done) above, and the same
missing-durable-queue gap.

**Diagnose**: check logs around the escrow/market's creation time for a
deploy failure (a real Bradbury deploy takes real time — budget a few
minutes before treating this as stuck, not seconds). A `GENLAYER_PRIVATE_
KEY` with insufficient GEN balance for gas is the most likely real-world
cause — deploys are backend-signed from one service wallet, so its balance
is a shared resource across every auto-deploy in flight.

**Recover**: no automatic retry exists. The row stays on the legacy
off-chain path indefinitely (this is safe — see nuance-app.tsx's own
`activeMilestoneOnChain`/`contractAddress` checks throughout, every write
path already branches to the off-chain fallback when `contract_address` is
null) — an on-chain cutover for that specific row would need a manual
re-trigger of the deploy call, not currently exposed as an endpoint.

## Database outage / migration failure

**Postgres down**: standard Postgres incident response applies — this app
adds nothing exotic here. `app/db.py::init_db()` does nothing on Postgres
(Alembic is the real source of truth, see that function's own docstring) —
a fresh deploy against an unmigrated Postgres will fail loudly on first
query, not silently create tables. Run `alembic upgrade head` before
starting the app against a new Postgres instance.

**A migration fails partway (`alembic upgrade head`)**: Alembic wraps each
revision in a transaction on Postgres — a failed revision rolls back
cleanly, the db stays on the previous good revision, `alembic current`
tells you exactly where. Fix the migration file, re-run. **Never** hand-
edit `alembic_version` to skip past a failure — CI's `migrations` job
(`.github/workflows/ci.yml`) exists specifically to catch a broken
migration before it ever reaches a real environment; if one gets through,
find why CI didn't fail first.

**`alembic check` fails in CI** (model/migration drift): someone changed a
model without a matching revision file. `alembic revision --autogenerate`
against a locally migrated db, review the generated diff by hand (it can
be wrong about server-side defaults/enum changes — every existing
migration in this repo was hand-reviewed after autogenerate, not committed
blind), commit it.

## A wrong-sender payable call permanently loses GEN

**This already happened once** (see `contracts/nuance_escrow.py`'s own
`fund_escrow` docstring and ROADMAP.md's Part 2 account): GenVM does
**not** refund a payable call's attached value when the contract then
raises an error. A wrong-sender (not the real `creator`) calling
`fund_escrow` loses that GEN into the contract permanently, with no
withdrawal path — this cost 1 real GEN before the root cause (the
contract's `creator` defaulting to the deploy signer, not the real escrow
creator) was found and fixed.

**Prevention already shipped**: `nuance-app.tsx`'s `fundEscrow`/
`cancelEscrow` handlers check `wallet.address === escrow.creatorAddress`
**client-side, before ever sending a transaction** — this is a UX
guardrail, not a security boundary (the contract's own `creator`-only
check is the real enforcement; client-side is just "don't let someone
sign a transaction guaranteed to fail and lose funds").

**If it happens again anyway** (a client bypass, a future contract with
the same class of bug): there is no recovery path — the GEN is gone from
the app's perspective. This is a hard argument for **never shipping a new
payable entry point without first asking "what happens to `msg.value` if
this reverts partway"** — treat that question as mandatory review for any
new contract method before it goes anywhere near mainnet.

---

## What's still missing (tracked, not done)

This runbook can only describe what the *code* already does under
failure — it can't invent monitoring/alerting that doesn't exist yet.
ROADMAP.md Part 4 §6.3's remaining open items, in the order they'd most
reduce time-to-detect for the scenarios above:

- [ ] **Sentry, frontend half.** Backend error tracking now exists
  (`app/observability.py::init_sentry` — set `SENTRY_DSN` to turn it on,
  no code changes needed; see `backend/.env.example`). The frontend half
  (`@sentry/nextjs`) is not wired — it needs its own config file
  generation (`sentry.client.config.ts`/`sentry.server.config.ts`/`next.
  config.ts` wrapping) that wasn't done in this pass since it can't be
  meaningfully verified without a real Sentry project to point it at.
- [ ] **Grafana/Prometheus** — API latency, `ConsensusJob` queue depth (a
  real metric: `COUNT(*) WHERE stage < 3 AND created_at < now() - '2m'`
  would directly surface the [stuck-job](#a-consensusjob-never-reaches-done)
  scenario above before a user has to report it), LLM provider error
  rates. Not started.
- [ ] **A durable job queue** for `ConsensusJob`/contract-deploy background
  work — the actual fix for the two "orphaned on process death" scenarios
  above, not just a runbook entry for living with them.
- [ ] **Gas/GEN cost modeling** under realistic load (ROADMAP.md §6.3).
- [ ] **A `contracts/CHANGELOG.md`** tracking deployed-address history per
  redeploy (ROADMAP.md §4.4's own still-open item) — without it, "which
  address is the current `NuanceGovernance`" has exactly one source of
  truth (ROADMAP.md's own deployment table), with no history if it's ever
  redeployed.
