"""Autonomous GenLayer-ecosystem governance proposal generator — the
governance equivalent of services/market_generator.py, asked for directly
("build a real proposal generator (like predictions have)") after that
file's own weekly refresh proved out live.

Reuses services/market_generator.py's own ingestion machinery directly
(_ingest_events, RawEvent, _is_relevant_candidate, KEYWORDS) rather than
re-implementing it — the event SOURCE (GenLayer's own accounts/RSS/web) is
identical; only what this file does with an event once it's relevant
differs. Dedup is a genuinely separate table (GovernanceEventLog, not
MarketEventLog) — see that model's own docstring for why sharing one
dedup log between the two generators would let whichever one processes an
event first permanently starve the other of the exact same source
content.

Deliberately far more conservative than market_generator's own
extraction: "is this a real, checkable future milestone" (predictions'
bar) is a much lower bar than "does this source content actually present
a concrete decision the community could vote FOR or AGAINST" (this file's
bar). Most GenLayer announcements are exactly that — announcements, with
nothing to decide — so this pipeline is expected to produce proposals far
less often than predictions produces markets from the same event stream.
That's the honest, correct behavior, not a bug: a real governance
proposal represents real GEN staked on a real community decision, and
fabricating a decision that was never actually presented as one would be
strictly worse than producing nothing that week.

Offline (no GEMINI_API_KEY) fallback is deliberately just "skip
everything" — see _extract_proposal_offline's own docstring for why
market_generator's own keyword-heuristic fallback isn't responsible to
mirror here.

Run as a one-off dry run (pulls real events if a live ingestion source is
configured, otherwise falls back to mock events; works without a Gemini
key too, in which case it always reports "no live ingestion source" is
irrelevant to the outcome — see _extract_proposal_offline):

    cd backend && venv/bin/python -m app.services.governance_generator
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.models import GovernanceEventLog, Proposal, User
from app.services.market_generator import (
    KEYWORDS,  # noqa: F401 — re-exported for anyone importing this module's own KEYWORDS
    RawEvent,
    _ingest_events,
    _is_relevant_candidate,
)

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "gemini-3.5-flash"
DEFAULT_VOTING_PERIOD_DAYS = 7
# See routers/governance.py's own _DEFAULT_ON_CHAIN_QUORUM_GEN — a
# separate constant here on purpose (this file lives independently of
# that router, same reasoning services/genlayer_indexer.py's own copy
# gives), not a cross-module reach into a router-private name.
DEFAULT_ON_CHAIN_QUORUM_GEN = Decimal("1")

_RETRYABLE_ERRORS = (errors.APIError, OSError)  # same shape as market_generator.py's own


class ExtractedProposal(BaseModel):
    is_actionable_proposal: bool = Field(
        description=(
            "True ONLY if this source content presents a genuine, "
            "concrete decision the GenLayer community could actually vote "
            "FOR or AGAINST — e.g. whether to fund/support a specific "
            "initiative it names, whether to adopt a specific policy or "
            "process change it announces, or whether to formally endorse "
            "a specific partnership/direction it reveals. False for pure "
            "announcements, feature launches, hype, memes, recaps, "
            "opinion, or anything already a done deal with no real "
            "choice left for a vote to make. When in doubt, false — "
            "fabricating a decision that was never actually presented as "
            "one is worse than producing nothing."
        )
    )
    title: str = Field(
        default="",
        description=(
            "A concise governance proposal title, phrased as a concrete "
            "action for the DAO to vote on — e.g. 'Allocate treasury "
            "funds to support the Agent Tank hackathon winners' or "
            "'Formally endorse GenLayer's new validator onboarding "
            "process'. Grounded only in what the source actually says — "
            "never invent a specific amount, recipient, or scope the "
            "source didn't mention. Empty if is_actionable_proposal is "
            "false."
        ),
    )
    description: str = Field(
        default="",
        description=(
            "2-4 sentences: what exactly is being proposed and why, "
            "grounded only in the source content. Empty if "
            "is_actionable_proposal is false."
        ),
    )
    category: str = Field(
        default="",
        description=(
            "One of: Treasury, Policy, Partnerships, Technical, "
            "Community. Empty if is_actionable_proposal is false."
        ),
    )


_EXTRACTOR_SYSTEM_PROMPT = (
    "You are a governance-proposal analyst for Nuance, a GenLayer-"
    "ecosystem DAO platform. You are given one raw social post or "
    "announcement, most often from GenLayer's own official account. Your "
    "job is NOT to summarize it — it is to decide whether it presents a "
    "genuine, concrete decision the community could vote FOR or AGAINST, "
    "and if so, phrase that decision as a real governance proposal. "
    "Reject pure announcements, feature launches, hype, memes, recaps, "
    "and opinion — these are the large majority of real GenLayer posts, "
    "and correctly rejecting them is the normal, expected outcome, not a "
    "failure. Never invent specifics (amounts, recipients, scope) the "
    "source didn't actually state. Respond with the required structured "
    "JSON only."
)


def _extractor_user_prompt(event: RawEvent) -> str:
    return (
        f"Source: {event.source}\n"
        f"Author: {event.author}\n"
        f"Published: {event.published_at.isoformat()}\n"
        f"URL: {event.url}\n\n"
        f"Content:\n{event.text}"
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_extractor(client: genai.Client, event: RawEvent) -> ExtractedProposal:
    config = types.GenerateContentConfig(
        system_instruction=_EXTRACTOR_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ExtractedProposal,
        temperature=0.2,
    )
    response = await client.aio.models.generate_content(
        model=EXTRACTION_MODEL,
        contents=_extractor_user_prompt(event),
        config=config,
    )

    if response.parsed and isinstance(response.parsed, ExtractedProposal):
        return response.parsed
    if response.text:
        import json

        return ExtractedProposal(**json.loads(response.text))
    raise ValueError("Empty response from the extraction model.")


async def _extract_proposal(client: genai.Client, event: RawEvent) -> ExtractedProposal | None:
    result = await _call_extractor(client, event)
    if not result.is_actionable_proposal or not result.title.strip():
        return None
    return result


def _extract_proposal_offline(event: RawEvent) -> ExtractedProposal | None:
    """No GEMINI_API_KEY configured. Deliberately NOT the same shape as
    market_generator.py's own _extract_market_offline (which always
    fabricates a deterministic stand-in market from any keyword-relevant
    event) — a real governance proposal represents real GEN a real wallet
    will stake on a real community decision. Guessing "yes, this is an
    actionable proposal" from keyword matching alone, with no actual
    judgment of whether the source presents a real decision, would be
    exactly the kind of fabricated-decision risk this module's own header
    already commits to avoiding. Always returns None; the caller logs
    once, up front, that this degraded mode means zero output by design.
    """
    return None


async def _already_processed(db: AsyncSession, source_id: str) -> bool:
    return await db.get(GovernanceEventLog, source_id) is not None


async def _mark_processed(
    db: AsyncSession, event: RawEvent, outcome: str, proposal_id: int | None = None
) -> None:
    db.add(
        GovernanceEventLog(
            source_id=event.source_id,
            source=event.source,
            source_url=event.url,
            outcome=outcome,
            proposal_id=proposal_id,
        )
    )


async def _ensure_proposer_user(db: AsyncSession, wallet_address: str) -> None:
    """Proposal.proposer_address is a real FK into users.wallet_address
    (unlike Prediction, which has no creator/proposer column at all —
    see that model's own definition) — a bare `Proposal(proposer_address=
    ...)` insert for a wallet nobody has ever signed in with would fail
    the FK constraint on Postgres (and, per this codebase's own
    established SQLite-is-lenient-about-constraints caveat elsewhere,
    might silently "work" there while breaking on the exact same code in
    production). Get-or-create rather than requiring an operator to
    pre-seed this row by hand — see config.py's own
    governance_generator_proposer_address docstring for why this address
    specifically."""
    if await db.get(User, wallet_address) is None:
        db.add(User(wallet_address=wallet_address, display_name="Nuance Governance Generator"))
        await db.flush()


async def _process_events(
    db: AsyncSession,
    events: Iterable[RawEvent],
    *,
    auto_publish: bool,
    gemini_client: genai.Client | None,
    trusted_accounts: set[str],
) -> list[Proposal]:
    """Mirrors services/market_generator.py::_process_events's own dedup-
    then-relevance-then-extract shape and its "an extraction call
    throwing is never marked processed" fix (see that function's own
    2026-09-13 note for the live incident that motivated it), but
    deliberately diverges from it on what `auto_publish=False` means.

    Prediction has a real, meaningful draft state (status_key=
    "pending_review") a human could someday review and publish, so
    market_generator's own dry run persists drafts AND marks dedup for
    real. Proposal has no equivalent state at all (ProposalStatus is
    ACTIVE/PASSED/REJECTED/EXECUTED — ADDING a pending/draft value just
    for this generator would mean auditing every other place that
    branches on ProposalStatus, e.g. _progress and _finalize_if_due in
    routers/governance.py, to make sure a half-reviewed governance
    decision can never leak into a live listing or a real vote — a much
    bigger, riskier change than what was actually asked for here).
    Instead, `auto_publish=False` here means a true dry run: relevance
    and extraction still run for real against real (or mock) events, but
    NOTHING is written to the database — not the Proposal, and not the
    GovernanceEventLog dedup entry either, since marking a genuinely
    creatable event "processed" from a run that never actually created
    anything would permanently suppress it from a future real run. The
    returned Proposal objects are therefore transient (never added to
    `db`, `.id` stays None) — fine for _dry_run's own reporting, which
    only reads their in-memory fields.
    """
    settings = get_settings()
    created: list[Proposal] = []
    seen_this_batch: set[str] = set()
    now = datetime.now(timezone.utc)
    proposer_address = settings.governance_generator_proposer_address.lower()

    for event in events:
        if event.source_id in seen_this_batch:
            continue
        seen_this_batch.add(event.source_id)

        if await _already_processed(db, event.source_id):
            continue

        if not _is_relevant_candidate(event, trusted_accounts):
            if auto_publish:
                await _mark_processed(db, event, outcome="skipped")
            continue

        try:
            extracted = (
                await _extract_proposal(gemini_client, event)
                if gemini_client is not None
                else _extract_proposal_offline(event)
            )
        except Exception as exc:  # noqa: BLE001 — one bad extraction shouldn't kill the batch
            # Same fix, same reasoning as market_generator.py::
            # _process_events' own 2026-09-13 note: never permanently
            # dedupe a transient failure, or a real network blip
            # silently, permanently loses that event's chance at ever
            # becoming a proposal.
            logger.warning(
                "Extraction failed for %s (will retry on the next run, not "
                "marked processed): %s",
                event.source_id,
                exc,
            )
            continue

        if extracted is None:
            if auto_publish:
                await _mark_processed(db, event, outcome="skipped")
            continue

        proposal = Proposal(
            title=extracted.title.strip(),
            description=extracted.description.strip(),
            category=extracted.category.strip() or "General",
            proposer_address=proposer_address,
            status="active",
            start_time=now,
            end_time=now + timedelta(days=DEFAULT_VOTING_PERIOD_DAYS),
            quorum_threshold=20,
            pass_threshold=50,
        )

        if not auto_publish:
            # True dry run — see this function's own docstring above.
            # Nothing persisted; proposal.id stays None.
            created.append(proposal)
            continue

        await _ensure_proposer_user(db, proposer_address)
        # Same on-chain-queuing shape as routers/governance.py::
        # create_proposal — see that endpoint's own 2026-09-13 fix note on
        # why deploy_attempted_at is set synchronously here, not only
        # inside create_proposal_on_chain's own background task: closes
        # the identical race routers/predictions.py::place_bet's fix
        # found live (a vote cast in the gap before the first real write
        # lands would otherwise sail through the off-chain endpoint).
        if settings.auto_create_proposals_on_chain and settings.governance_contract_address:
            proposal.deploy_attempted_at = now
            proposal.quorum_threshold_gen = DEFAULT_ON_CHAIN_QUORUM_GEN

        db.add(proposal)
        await db.flush()  # assign proposal.id before logging it below
        await _mark_processed(db, event, outcome="created", proposal_id=proposal.id)
        created.append(proposal)

    if auto_publish:
        await db.commit()
        for proposal in created:
            await db.refresh(proposal)

        if created:
            from app.services.genlayer_indexer import create_proposal_on_chain

            await asyncio.gather(
                *(
                    create_proposal_on_chain(p.id)
                    for p in created
                    if p.deploy_attempted_at is not None
                ),
                return_exceptions=True,
            )

    return created


async def process_latest_events(db: AsyncSession, auto_publish: bool = True) -> list[Proposal]:
    """The real entrypoint — services/governance_ingestion_scheduler.py's
    own weekly sweep calls this directly, same shape as services/
    market_generator.py::process_latest_events."""
    await _ensure_schema()
    settings = get_settings()
    events = await _ingest_events(
        accounts=settings.market_generator_accounts_list,
        twitterapi_io_key=settings.twitterapi_io_key,
        bearer_token=settings.twitter_bearer_token,
        rss_feeds=settings.market_generator_rss_feeds_list,
        web_pages=settings.market_generator_web_pages_list,
    )

    # FOUND 2026-09-13 — see config.py's own governance_gemini_api_key
    # docstring for the full account: sharing gemini_api_key with
    # market_generator.py meant both weekly sweeps drew on one Google-side
    # free-tier daily quota, and market_generator's own scheduler runs
    # hours earlier in the day and was confirmed live to exhaust it
    # completely before this generator ever got a turn — every extraction
    # call failing RESOURCE_EXHAUSTED, silently, every single week.
    # governance_gemini_api_key (from a genuinely separate Google Cloud/AI
    # Studio project) is preferred when set; None falls back to the shared
    # key, i.e. today's exact starved behavior for anyone who hasn't
    # configured it yet.
    effective_gemini_key = settings.governance_gemini_api_key or settings.gemini_api_key
    gemini_client = genai.Client(api_key=effective_gemini_key) if effective_gemini_key else None
    if gemini_client is None:
        logger.warning(
            "GEMINI_API_KEY not set — governance_generator has no responsible offline "
            "fallback (see _extract_proposal_offline's own docstring) and will produce "
            "zero proposals this run, by design."
        )

    trusted = {handle.lower() for handle in settings.market_generator_accounts_list}
    return await _process_events(
        db, events, auto_publish=auto_publish, gemini_client=gemini_client, trusted_accounts=trusted
    )


async def _ensure_schema() -> None:
    """Same reasoning as market_generator.py's own — this can run as its
    own standalone process (the dry run below), separate from FastAPI's
    lifespan, and needs the schema to exist before touching it."""
    await init_db()


# --- Dry run / CLI ----------------------------------------------------------

_MOCK_EVENTS: list[RawEvent] = [
    RawEvent(
        source_id="mock:governance-actionable",
        source="twitter",
        author="genlayer",
        text=(
            "We're considering allocating a portion of the ecosystem "
            "treasury to a recurring grants program for community-built "
            "GenVM tooling. What do you think?"
        ),
        url="https://x.com/GenLayer/status/mock-actionable",
        published_at=datetime.now(timezone.utc),
    ),
    RawEvent(
        source_id="mock:governance-announcement",
        source="twitter",
        author="genlayer",
        text="Mochi is live! Check out the new docs site.",
        url="https://x.com/GenLayer/status/mock-announcement",
        published_at=datetime.now(timezone.utc),
    ),
]


async def _dry_run() -> None:
    """Pulls real events (and/or RSS/web) when a real ingestion source is
    configured; otherwise exercises the whole pipeline against the mock
    events above, network-free. Either way, `auto_publish=False` — this
    is still a dry run, so anything created lands as a `pending_review`
    draft, not a live, on-chain-queued proposal."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    await _ensure_schema()

    settings = get_settings()
    gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
    trusted = {handle.lower() for handle in settings.market_generator_accounts_list}

    live_source_configured = bool(
        settings.twitterapi_io_key
        or settings.twitter_bearer_token
        or settings.market_generator_rss_feeds_list
        or settings.market_generator_web_pages_list
    )

    if live_source_configured:
        events = await _ingest_events(
            accounts=settings.market_generator_accounts_list,
            twitterapi_io_key=settings.twitterapi_io_key,
            bearer_token=settings.twitter_bearer_token,
            rss_feeds=settings.market_generator_rss_feeds_list,
            web_pages=settings.market_generator_web_pages_list,
        )
        mode = f"LIVE ingestion — {len(events)} raw event(s) fetched"
    else:
        events = _MOCK_EVENTS
        mode = f"no live ingestion source configured — {len(events)} mock event(s)"

    print(
        f"--- governance_generator dry run "
        f"({'Gemini' if gemini_client else 'offline (always empty, see module docstring)'} "
        f"extraction, {mode}, auto_publish=False so nothing is persisted — see "
        f"_process_events' own docstring on why this diverges from market_generator.py's "
        f"own dry run) ---\n"
    )

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, events, auto_publish=False, gemini_client=gemini_client, trusted_accounts=trusted
        )

    if not created:
        print(
            "No proposals created — everything was noise, irrelevant, not a real "
            "decision to vote on, or already processed on a prior run against this "
            "same database. This is the expected, normal outcome most runs — see this "
            "module's own header on why the bar here is deliberately much higher than "
            "market_generator.py's."
        )
    for proposal in created:
        print(f"[would create — not persisted] {proposal.title}")
        print(f"  category: {proposal.category}")
        print(f"  description: {proposal.description}\n")


if __name__ == "__main__":
    asyncio.run(_dry_run())
