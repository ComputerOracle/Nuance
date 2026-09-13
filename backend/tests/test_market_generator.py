"""Tests for services/market_generator.py.

Mocks google.genai.Client entirely (no real network call, no dependence on
Gemini's free-tier quota) and verifies:
  1. The account/keyword relevance gate.
  2. A verifiable milestone becomes a Prediction with the right fields.
  3. Noise (per the LLM) creates no Prediction but is still logged, so it's
     never re-extracted.
  4. The exact same source_id is never processed twice (dedup).
  5. auto_publish controls status_key ("open" vs "pending_review").
  6. The offline (no API key) fallback is deterministic and still respects
     the relevance gate.
"""

from __future__ import annotations

import itertools
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

# FIXED 2026-09-13 — a real, serious gap found live: this file had no
# DATABASE_URL override at all, unlike every sibling test file (see e.g.
# test_chain_unavailable_guard.py/test_prediction_contract_balance.py's
# identical preamble) — `from app.db import AsyncSessionLocal` below used
# to pick up whatever DATABASE_URL was already active, which with no
# override is backend/.env's own `sqlite+aiosqlite:///./nuance.db`: the
# real, live, production database this repo's actual running backend
# serves to real users. Caught in the act: running this file repeatedly
# today left 11 fake "MILESTONE_MARKER"/test:N predictions sitting in the
# live db (ids 23-30, plus three from 2026-09-07's own
# "auto-deploy-test:N" rows, ids 20-22) — two of which (20, 22) then got
# picked up by services/genlayer_deploy.py's own legitimate auto-deploy
# retry sweep and had REAL testnet GEN spent deploying real contracts for
# fake test data. Same fix as every other test file: an isolated, throwaway
# sqlite file, set before any app.* import triggers app.config.get_settings()'s
# lru_cache to read the real one.
_TMP_DIR = tempfile.mkdtemp(prefix="nuance-market-generator-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.services.market_generator as market_generator  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import MarketEventLog, Prediction  # noqa: E402
from app.services.market_generator import ExtractedMarket, RawEvent, _process_events  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


_id_counter = itertools.count(1)


def _event(text: str, *, author: str = "genlayer", source: str = "twitter") -> RawEvent:
    n = next(_id_counter)
    return RawEvent(
        source_id=f"test:{n}",
        source=source,
        author=author,
        text=text,
        url=f"https://x.com/{author}/status/{n}",
        published_at=datetime.now(timezone.utc),
    )


# --- Fakes -----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)
        self.parsed = ExtractedMarket(**data)


class _FakeAsyncModels:
    """Returns a milestone verdict if the prompt contains "MILESTONE_MARKER",
    otherwise a noise verdict — lets each test pick the outcome via the
    mock event's own text, same trick test_consensus.py uses keyed on
    validator persona name."""

    async def generate_content(self, *, model: str, contents: str, config=None):
        if "MILESTONE_MARKER" in contents:
            future = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
            return _FakeResponse(
                {
                    "is_verifiable_milestone": True,
                    "title": "Will GenLayer ship the marked milestone?",
                    "resolution_rules": "Resolves YES if the milestone ships as described.",
                    "end_time": future,
                }
            )
        return _FakeResponse(
            {
                "is_verifiable_milestone": False,
                "title": "",
                "resolution_rules": "",
                "end_time": "",
            }
        )


class _FakeAio:
    def __init__(self):
        self.models = _FakeAsyncModels()


class _FakeGenaiClient:
    def __init__(self, *_args, **_kwargs):
        self.aio = _FakeAio()


# --- Relevance gate ----------------------------------------------------


def test_relevant_trusted_account_bypasses_keyword_requirement():
    event = _event("gm builders, nothing keyword-y here", author="genlayer")
    assert market_generator._is_relevant_candidate(event, {"genlayer"}) is True


def test_relevant_keyword_match_from_untrusted_account():
    event = _event("Heads up: GenLayer testnet numbers looking great", author="rando")
    assert market_generator._is_relevant_candidate(event, {"genlayer"}) is True


def test_irrelevant_untrusted_no_keyword():
    event = _event("best coffee of my life today", author="rando")
    assert market_generator._is_relevant_candidate(event, {"genlayer"}) is False


# --- End-to-end via _process_events (fake LLM) --------------------------


@pytest.mark.asyncio
async def test_milestone_event_creates_prediction():
    event = _event("MILESTONE_MARKER: mainnet consensus release date set")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )

    assert len(created) == 1
    prediction = created[0]
    assert prediction.title == "Will GenLayer ship the marked milestone?"
    assert prediction.category == "GenLayer Ecosystem"
    assert prediction.status_key == "open"
    assert prediction.resolution_source_url == event.url
    # The fake extractor said 14 days out — confirms resolution_date comes
    # from the extractor's own end_time, not a hardcoded default horizon.
    # (SQLite round-trips datetimes as naive; re-attach UTC before diffing.)
    resolution_date = prediction.resolution_date
    if resolution_date.tzinfo is None:
        resolution_date = resolution_date.replace(tzinfo=timezone.utc)
    days_out = (resolution_date - datetime.now(timezone.utc)).days
    assert 12 <= days_out <= 14

    async with AsyncSessionLocal() as db:
        log_row = await db.get(MarketEventLog, event.source_id)
    assert log_row is not None
    assert log_row.outcome == "created"
    assert log_row.prediction_id == prediction.id


@pytest.mark.asyncio
async def test_auto_publish_false_creates_pending_review_not_open():
    event = _event("MILESTONE_MARKER: another real milestone")
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=False, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert created[0].status_key == "pending_review"


@pytest.mark.asyncio
async def test_noise_event_creates_no_prediction_but_is_logged():
    event = _event("gm builders, just vibing, no milestone here")
    async with AsyncSessionLocal() as db:
        before = (await db.execute(select(Prediction))).scalars().all()
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
        after = (await db.execute(select(Prediction))).scalars().all()

    assert created == []
    assert len(after) == len(before)  # nothing new persisted

    async with AsyncSessionLocal() as db:
        log_row = await db.get(MarketEventLog, event.source_id)
    assert log_row is not None
    assert log_row.outcome == "skipped"
    assert log_row.prediction_id is None


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
    """FIXED 2026-09-13 — a real gap found live, not hypothesized: running
    a real ingestion pass right after GEMINI_API_KEY was configured hit a
    transient `[Errno -3] Temporary failure in name resolution` calling
    Gemini for every one of 20 freshly-fetched, real tweets (confirmed
    separately as genuinely transient — a bare retry of the same DNS
    lookup succeeded 2 of 3 times, not a bad key). The old code called
    _mark_processed(outcome="error") in that branch — exactly as
    permanent as "skipped"/"created" per _already_processed — which would
    have silently and permanently lost all 20 tweets, on every future
    run, over one passing network blip. This is the exact scenario that
    would have caused: an event whose extraction call raises must NOT be
    logged at all, so a later run (this same event, offered again) gets a
    real second chance once the transient failure has cleared — contrast
    with test_noise_event_creates_no_prediction_but_is_logged, where the
    LLM DID successfully judge the event (as noise) and that real verdict
    is correctly permanent."""

    class _FlakyThenWorkingClient:
        """Raises on every call within _call_extractor's own retry budget
        (stop_after_attempt(3) — see _RETRYABLE_ERRORS' 2026-09-13 fix
        note, which now retries OSError there too) so the first
        _process_events run below still genuinely exhausts its retries and
        reaches the except block, exactly like the live incident this
        guards against; the 4th call — a separate, later run, exactly what
        a real subsequent scheduled ingestion does — succeeds normally."""

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

    event = _event("MILESTONE_MARKER: a real milestone hit by a flaky DNS lookup")
    client = _FlakyThenWorkingClient()

    # First run: the extraction call raises. Nothing created, and —
    # unlike the noise case — nothing logged either.
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=client, trusted_accounts={"genlayer"}
        )
    assert created == []
    async with AsyncSessionLocal() as db:
        log_row = await db.get(MarketEventLog, event.source_id)
    assert log_row is None, "a transient extraction failure must not be permanently deduped"

    # Second run: same event offered again (exactly what the next
    # scheduled ingestion run does) — this time extraction succeeds, and
    # since it was never logged, _already_processed doesn't skip it.
    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [event], auto_publish=True, gemini_client=client, trusted_accounts={"genlayer"}
        )
    assert len(created) == 1
    assert created[0].title == "Will GenLayer ship the marked milestone?"


@pytest.mark.asyncio
async def test_duplicate_source_id_is_never_processed_twice():
    event = _event("MILESTONE_MARKER: only once please")

    async with AsyncSessionLocal() as db:
        first = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(first) == 1

    # Same event object, brand-new call — simulates the next scheduled run
    # re-ingesting the same tweet.
    async with AsyncSessionLocal() as db:
        second = await _process_events(
            db, [event], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert second == []

    # And within a single batch (e.g. the same tweet surfaced by two
    # ingestion sources at once):
    event2 = _event("MILESTONE_MARKER: batch-internal duplicate")
    async with AsyncSessionLocal() as db:
        both = await _process_events(
            db, [event2, event2], auto_publish=True, gemini_client=_FakeGenaiClient(), trusted_accounts={"genlayer"}
        )
    assert len(both) == 1


# --- Offline (no API key) fallback --------------------------------------


def test_offline_extractor_is_deterministic_and_labeled():
    event = _event("MILESTONE_MARKER: mainnet date announced")
    result = market_generator._extract_market_offline(event)
    assert result is not None
    assert result.is_verifiable_milestone is True
    assert "GEMINI_API_KEY not configured" in result.resolution_rules
    assert event.url in result.resolution_rules


@pytest.mark.asyncio
async def test_offline_mode_still_respects_relevance_gate():
    relevant = _event("MILESTONE_MARKER: genlayer testnet news")
    irrelevant = _event("best coffee of my life today", author="rando")

    async with AsyncSessionLocal() as db:
        created = await _process_events(
            db, [relevant, irrelevant], auto_publish=True, gemini_client=None, trusted_accounts={"genlayer"}
        )
    assert len(created) == 1
    assert created[0].resolution_source_url == relevant.url


# --- _parse_end_time (never trust the extractor's timestamp blindly) ---


def test_parse_end_time_valid_future_iso():
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    parsed = market_generator._parse_end_time(future)
    days_out = (parsed - datetime.now(timezone.utc)).days
    assert 9 <= days_out <= 10


def test_parse_end_time_accepts_z_suffix():
    future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    parsed = market_generator._parse_end_time(future)
    assert parsed.tzinfo is not None
    assert 3 <= (parsed - datetime.now(timezone.utc)).days <= 5


def test_parse_end_time_empty_falls_back_to_default_horizon():
    parsed = market_generator._parse_end_time("")
    days_out = (parsed - datetime.now(timezone.utc)).days
    assert days_out == pytest.approx(market_generator.DEFAULT_HORIZON_DAYS, abs=1)


def test_parse_end_time_malformed_falls_back_to_default_horizon():
    parsed = market_generator._parse_end_time("not a date at all")
    days_out = (parsed - datetime.now(timezone.utc)).days
    assert days_out == pytest.approx(market_generator.DEFAULT_HORIZON_DAYS, abs=1)


def test_parse_end_time_in_the_past_falls_back_to_default_horizon():
    past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    parsed = market_generator._parse_end_time(past)
    days_out = (parsed - datetime.now(timezone.utc)).days
    assert days_out == pytest.approx(market_generator.DEFAULT_HORIZON_DAYS, abs=1)


def test_parse_end_time_implausibly_far_out_is_clamped():
    way_out = (datetime.now(timezone.utc) + timedelta(days=10_000)).isoformat()
    parsed = market_generator._parse_end_time(way_out)
    days_out = (parsed - datetime.now(timezone.utc)).days
    assert days_out == pytest.approx(market_generator.MAX_HORIZON_DAYS, abs=1)


# --- _ingest_from_twitter (TwitterAPI.io) -------------------------------


_SAMPLE_TWITTERAPI_IO_PAYLOAD = {
    "status": "success",
    "code": 0,
    "msg": "success",
    "data": {
        "pin_tweet": None,
        "tweets": [
            {
                "id": "2094454210943148524",
                "url": "https://x.com/GenLayer/status/2094454210943148524",
                "text": "Three days until the hackathon opens!",
                "createdAt": "Mon Aug 31 15:56:11 +0000 2026",
                "author": {"userName": "GenLayer"},
            }
        ],
    },
}


def _fake_httpx_client_factory(responses: dict):
    """responses: {handle: payload_dict | Exception}"""

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, _url, params=None, headers=None):
            handle = (params or {})["userName"]
            result = responses[handle]
            if isinstance(result, Exception):
                raise result
            return _FakeResp(result)

    return _FakeClient


@pytest.mark.asyncio
async def test_ingest_from_twitter_no_key_returns_none():
    result = await market_generator._ingest_from_twitter(["genlayer"], None)
    assert result is None


@pytest.mark.asyncio
async def test_ingest_from_twitter_parses_verified_response_shape(monkeypatch):
    monkeypatch.setattr(
        market_generator.httpx,
        "AsyncClient",
        _fake_httpx_client_factory({"genlayer": _SAMPLE_TWITTERAPI_IO_PAYLOAD}),
    )

    result = await market_generator._ingest_from_twitter(["genlayer"], "fake-key")

    assert result is not None
    assert len(result) == 1
    event = result[0]
    assert event.source_id == "twitter_2094454210943148524"
    assert event.source == "twitter"
    assert event.author == "GenLayer"
    assert event.url == "https://x.com/GenLayer/status/2094454210943148524"
    assert event.text == "Three days until the hackathon opens!"
    assert event.published_at.year == 2026
    assert event.published_at.month == 8
    assert event.published_at.day == 31


@pytest.mark.asyncio
async def test_ingest_from_twitter_all_accounts_failing_returns_none(monkeypatch):
    monkeypatch.setattr(
        market_generator.httpx,
        "AsyncClient",
        _fake_httpx_client_factory({"genlayer": httpx.ConnectError("boom")}),
    )
    result = await market_generator._ingest_from_twitter(["genlayer"], "fake-key")
    assert result is None


@pytest.mark.asyncio
async def test_ingest_from_twitter_partial_failure_keeps_successful_accounts(monkeypatch):
    monkeypatch.setattr(
        market_generator.httpx,
        "AsyncClient",
        _fake_httpx_client_factory(
            {
                "genlayer": _SAMPLE_TWITTERAPI_IO_PAYLOAD,
                "genlayerfdn": httpx.ConnectError("boom"),
            }
        ),
    )
    result = await market_generator._ingest_from_twitter(["genlayer", "genlayerfdn"], "fake-key")
    assert result is not None  # at least one account succeeded -> real (if partial) result
    assert len(result) == 1


def test_parse_twitter_created_at_malformed_falls_back_to_now():
    before = datetime.now(timezone.utc)
    parsed = market_generator._parse_twitter_created_at("not a twitter date")
    assert parsed >= before
