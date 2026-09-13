"""Tests for services/governance_generator.py — the governance equivalent
of test_market_generator.py, built after the identical feature was asked
for directly for Governance too ("build a real proposal generator (like
predictions have)"). Mocks google.genai.Client entirely (no real network
call). Covers the same shapes as test_market_generator.py where they
still apply, plus this file's own real divergences from that one — see
governance_generator.py's own module docstring, especially _process_
events' docstring on why `auto_publish=False` means something different
here than it does for market_generator.py.
"""

from __future__ import annotations

import itertools
import json
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal

# Same fix, same reasoning as test_market_generator.py's own 2026-09-13
# note: an isolated, throwaway sqlite file, set before any app.* import
# triggers app.config.get_settings()'s lru_cache to read the real one.
_TMP_DIR = tempfile.mkdtemp(prefix="nuance-governance-generator-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.services.governance_generator as governance_generator  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import GovernanceEventLog, Proposal, User  # noqa: E402
from app.services.governance_generator import ExtractedProposal, RawEvent, _process_events  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


_id_counter = itertools.count(1)


def _event(text: str, *, author: str = "genlayer", source: str = "twitter") -> RawEvent:
    n = next(_id_counter)
    return RawEvent(
        source_id=f"gov-test:{n}",
        source=source,
        author=author,
        text=text,
        url=f"https://x.com/{author}/status/gov-{n}",
        published_at=datetime.now(timezone.utc),
    )


# --- Fakes -----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)
        self.parsed = ExtractedProposal(**data)


class _FakeAsyncModels:
    """Returns an actionable-proposal verdict if the prompt contains
    "ACTIONABLE_MARKER", otherwise a non-actionable verdict — same trick
    test_market_generator.py's own _FakeAsyncModels uses."""

    async def generate_content(self, *, model: str, contents: str, config=None):
        if "ACTIONABLE_MARKER" in contents:
            return _FakeResponse(
                {
                    "is_actionable_proposal": True,
                    "title": "Fund a community GenVM tooling grants program",
                    "description": "Allocate treasury funds to a recurring grants program.",
                    "category": "Treasury",
                }
            )
        return _FakeResponse(
            {
                "is_actionable_proposal": False,
                "title": "",
                "description": "",
                "category": "",
            }
        )


class _FakeAio:
    def __init__(self):
        self.models = _FakeAsyncModels()


class _FakeGenaiClient:
    def __init__(self, *_args, **_kwargs):
        self.aio = _FakeAio()


# --- Relevance gate reuse (the real logic lives in, and is fully covered
# by, test_market_generator.py — this just confirms the same function is
# actually what's wired in here, not a silent fork of it) -------------


def test_relevance_gate_is_the_same_function_market_generator_uses():
    from app.services.market_generator import _is_relevant_candidate as market_gate

    assert governance_generator._is_relevant_candidate is market_gate


# --- End-to-end via _process_events (fake LLM), auto_publish=True ------


@pytest.mark.asyncio
async def test_actionable_event_creates_proposal():
    event = _event("ACTIONABLE_MARKER: should we fund this?")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )

    assert len(created) == 1
    proposal = created[0]
    assert proposal.id is not None
    assert proposal.title == "Fund a community GenVM tooling grants program"
    assert proposal.category == "Treasury"
    assert proposal.status == "active"
    assert proposal.proposer_address == get_settings().governance_generator_proposer_address.lower()

    async with AsyncSessionLocal() as db:
        log_row = await db.get(GovernanceEventLog, event.source_id)
    assert log_row is not None
    assert log_row.outcome == "created"
    assert log_row.proposal_id == proposal.id


@pytest.mark.asyncio
async def test_proposer_user_row_is_auto_provisioned():
    """Proposal.proposer_address is a real FK into users.wallet_address
    (unlike Prediction, which has none) — this must not blow up the first
    time the generator ever runs against a fresh database with no
    matching User row yet."""
    event = _event("ACTIONABLE_MARKER: auto-provision check")
    address = get_settings().governance_generator_proposer_address.lower()

    async with AsyncSessionLocal() as db:
        await db.execute(User.__table__.delete().where(User.wallet_address == address))
        await db.commit()

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(created) == 1

    async with AsyncSessionLocal() as db:
        user = await db.get(User, address)
    assert user is not None


@pytest.mark.asyncio
async def test_on_chain_queuing_fields_set_when_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_create_proposals_on_chain", True)
    monkeypatch.setattr(get_settings(), "governance_contract_address", "0x" + "1" * 40)

    event = _event("ACTIONABLE_MARKER: on-chain queuing check")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(created) == 1
    proposal = created[0]
    assert proposal.deploy_attempted_at is not None
    assert proposal.quorum_threshold_gen == governance_generator.DEFAULT_ON_CHAIN_QUORUM_GEN


@pytest.mark.asyncio
async def test_no_on_chain_queuing_when_not_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_create_proposals_on_chain", False)

    event = _event("ACTIONABLE_MARKER: no on-chain queuing")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(created) == 1
    assert created[0].deploy_attempted_at is None
    assert created[0].quorum_threshold_gen is None


@pytest.mark.asyncio
async def test_non_actionable_event_creates_no_proposal_but_is_logged():
    event = _event("gm builders, just an announcement, nothing to vote on")
    async with AsyncSessionLocal() as db:
        before = (await db.execute(select(Proposal))).scalars().all()
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
        after = (await db.execute(select(Proposal))).scalars().all()

    assert created == []
    assert len(after) == len(before)

    async with AsyncSessionLocal() as db:
        log_row = await db.get(GovernanceEventLog, event.source_id)
    assert log_row is not None
    assert log_row.outcome == "skipped"
    assert log_row.proposal_id is None


@pytest.mark.asyncio
async def test_irrelevant_event_never_reaches_the_llm():
    event = _event("best coffee of my life today", author="rando")

    class _ExplodingClient:
        class aio:
            class models:
                @staticmethod
                async def generate_content(**_kwargs):
                    raise AssertionError("the LLM should never be called for an irrelevant event")

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_ExplodingClient(), trusted_accounts={"genlayer"}
        )
    assert created == []


@pytest.mark.asyncio
async def test_transient_extraction_failure_is_not_permanently_deduped():
    """Same fix, same reasoning as market_generator.py's own 2026-09-13
    note (test_market_generator.py::
    test_transient_extraction_failure_is_not_permanently_deduped) —
    ported here since _process_events' extraction try/except is its own
    copy, not a shared call, and deserves its own direct coverage."""

    class _FlakyThenWorkingClient:
        def __init__(self):
            self.calls = 0
            self.aio = self

        @property
        def models(self):
            return self

        async def generate_content(self, *, model: str, contents: str, config=None):
            self.calls += 1
            if self.calls <= 3:
                raise OSError("[Errno -3] Temporary failure in name resolution")
            return await _FakeAsyncModels().generate_content(model=model, contents=contents, config=config)

    event = _event("ACTIONABLE_MARKER: hit by a flaky DNS lookup")
    client = _FlakyThenWorkingClient()

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=client, trusted_accounts={"genlayer"}
        )
    assert created == []
    async with AsyncSessionLocal() as db:
        log_row = await db.get(GovernanceEventLog, event.source_id)
    assert log_row is None, "a transient extraction failure must not be permanently deduped"

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=client, trusted_accounts={"genlayer"}
        )
    assert len(created) == 1
    assert created[0].title == "Fund a community GenVM tooling grants program"


@pytest.mark.asyncio
async def test_duplicate_source_id_is_never_processed_twice():
    event = _event("ACTIONABLE_MARKER: only once please")

    async with AsyncSessionLocal() as db:
        first = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(first) == 1

    async with AsyncSessionLocal() as db:
        second = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert second == []

    event2 = _event("ACTIONABLE_MARKER: batch-internal duplicate")
    async with AsyncSessionLocal() as db:
        both = await _process_events(
            db, [event2, event2], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(both) == 1


# --- Offline (no API key) fallback — deliberately always None ----------


def test_offline_extractor_always_returns_none():
    """Deliberately NOT a mirror of market_generator.py's own offline
    fallback (which always fabricates a deterministic stand-in market) —
    see _extract_proposal_offline's own docstring for why guessing
    "actionable" from keywords alone is a real risk here that it isn't
    for a prediction market."""
    event = _event("ACTIONABLE_MARKER: even a strong keyword hit")
    assert governance_generator._extract_proposal_offline(event) is None


@pytest.mark.asyncio
async def test_offline_mode_creates_nothing_even_for_relevant_events():
    relevant = _event("ACTIONABLE_MARKER: genlayer testnet governance news")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [relevant], auto_publish=True, gemini_client=None, trusted_accounts={"genlayer"}
        )
    assert created == []
    async with AsyncSessionLocal() as db:
        log_row = await db.get(GovernanceEventLog, relevant.source_id)
    assert log_row is not None
    assert log_row.outcome == "skipped"


# --- Dry run (auto_publish=False) — the real divergence from
# market_generator.py's own dry-run behavior --------------------------


@pytest.mark.asyncio
async def test_dry_run_reports_but_never_persists_proposal_or_dedup():
    """See _process_events' own docstring: unlike market_generator.py
    (which persists a real "pending_review" draft AND marks dedup even
    when auto_publish=False), Proposal has no draft state to persist into
    — a dry run here must report what WOULD be created without writing
    anything to the database at all, so the exact same event can still be
    picked up for real by a later, real (auto_publish=True) run."""
    event = _event("ACTIONABLE_MARKER: dry run only")

    async with AsyncSessionLocal() as db:
        before = (await db.execute(select(Proposal))).scalars().all()
        created = await _process_events(
            db, [event], auto_publish=False, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
        after = (await db.execute(select(Proposal))).scalars().all()

    assert len(created) == 1
    assert created[0].id is None, "a dry-run proposal must stay transient, never flushed/committed"
    assert len(after) == len(before), "nothing should be persisted to the proposals table"

    async with AsyncSessionLocal() as db:
        log_row = await db.get(GovernanceEventLog, event.source_id)
    assert log_row is None, "a dry run must not consume the event's one real dedup chance"

    # And proof the event really is still available for a real run:
    async with AsyncSessionLocal() as db:
        real_created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(real_created) == 1
    assert real_created[0].id is not None


@pytest.mark.asyncio
async def test_dry_run_of_non_actionable_event_creates_nothing_and_logs_nothing():
    event = _event("gm builders, dry run noise")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=False, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert created == []
    async with AsyncSessionLocal() as db:
        log_row = await db.get(GovernanceEventLog, event.source_id)
    assert log_row is None


# --- process_latest_events: governance_gemini_api_key preference -----------
#
# FOUND 2026-09-13, diagnosing a live report that Governance only ever had
# one real proposal: process_latest_events used to always build its
# genai.Client from the same gemini_api_key market_generator.py's own
# weekly sweep already draws on — and that sweep runs hours earlier in the
# day and was confirmed live to exhaust the shared free-tier daily quota
# (RESOURCE_EXHAUSTED on every one of governance's own extraction calls)
# before governance's sweep ever got a turn. See config.py's own
# governance_gemini_api_key docstring for the full account.


class _RecordingGenaiClient:
    """Stands in for google.genai.Client — records the api_key it was
    constructed with instead of touching the network, so these tests can
    assert on *which* key process_latest_events actually chose without
    needing a real extraction call at all (paired with an empty event
    list below, so nothing past client construction ever runs)."""

    last_api_key: str | None = None

    def __init__(self, api_key: str | None = None):
        type(self).last_api_key = api_key


@pytest.mark.asyncio
async def test_process_latest_events_prefers_governance_specific_gemini_key(monkeypatch):
    monkeypatch.setattr(governance_generator, "genai", type("_M", (), {"Client": _RecordingGenaiClient}))

    async def _no_events(**kwargs):
        return []

    monkeypatch.setattr(governance_generator, "_ingest_events", _no_events)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "shared-key")
    monkeypatch.setattr(get_settings(), "governance_gemini_api_key", "governance-only-key")

    async with AsyncSessionLocal() as db:
        await governance_generator.process_latest_events(db, auto_publish=True)

    assert _RecordingGenaiClient.last_api_key == "governance-only-key"


@pytest.mark.asyncio
async def test_process_latest_events_falls_back_to_shared_gemini_key(monkeypatch):
    monkeypatch.setattr(governance_generator, "genai", type("_M", (), {"Client": _RecordingGenaiClient}))

    async def _no_events(**kwargs):
        return []

    monkeypatch.setattr(governance_generator, "_ingest_events", _no_events)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "shared-key")
    monkeypatch.setattr(get_settings(), "governance_gemini_api_key", None)

    async with AsyncSessionLocal() as db:
        await governance_generator.process_latest_events(db, auto_publish=True)

    assert _RecordingGenaiClient.last_api_key == "shared-key"
