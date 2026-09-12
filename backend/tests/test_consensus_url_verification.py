"""Tests for services/consensus.py's live URL verification — a real gap
found live: the off-chain consensus path judged only the submitter's own
typed text, with no way to check whether a claimed link even existed, let
alone supported the claim. escrow-detail-view.tsx's own deliverable
placeholder ("Paste deliverable URL, PR link, or describe the completed
work for AI review…") already implied a pasted URL would be reviewed —
nothing ever fetched one. contracts/nuance_escrow.py's submit_deliverable
and contracts/nuance_dispute_court.py's adjudicate_dispute both already do
this on-chain (gl.nondet.web.render / gl.nondet.web.get); this closes the
same gap off-chain.

Covers:
  1. _extract_first_url: finds a URL, returns None when absent, picks the
     first of several.
  2. _fetch_url_for_verification: extracts readable text from an HTML
     response, returns an honest note (never raises) when the URL is
     unreachable, truncates an oversized page.
  3. End to end via run_consensus: a submission whose own text has no
     judgeable signal words but whose linked page's real content does
     actually changes the deterministic heuristic's verdict — proof the
     fetched content really reaches the judgment, not just decoration.
  4. run_consensus never attempts a fetch at all when the submission has
     no URL (monkeypatched to raise if called).
"""

from __future__ import annotations

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-consensus-url-verification-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import secrets  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.consensus as consensus  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Escrow, Milestone, User  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture(autouse=True)
def _fast_deliberation(monkeypatch):
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)


@pytest.fixture(autouse=True)
def _no_provider_keys(monkeypatch):
    # Every test here exercises the deterministic offline heuristic
    # specifically — simplest way to observe whether fetched content
    # actually reached the text the judgment ran against.
    monkeypatch.setattr(consensus.settings, "gemini_api_key", None)
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", None)
    monkeypatch.setattr(consensus.settings, "openai_api_key", None)


def _random_wallet_address() -> str:
    return "0x" + secrets.token_hex(20)


async def _seed_milestone() -> Milestone:
    async with AsyncSessionLocal() as db:
        user1 = User(wallet_address=_random_wallet_address())
        user2 = User(wallet_address=_random_wallet_address())
        escrow = Escrow(
            creator_address=user1.wallet_address,
            counterparty_address=user2.wallet_address,
            title="URL verification test escrow",
            total=100,
            status_key=StatusKey.IN_PROGRESS,
        )
        milestone = Milestone(
            name="Milestone 1",
            amount=100,
            status_key=StatusKey.IN_REVIEW,
            criteria="Ships a working prototype.",
            order_index=0,
        )
        escrow.milestones.append(milestone)
        db.add(user1)
        db.add(user2)
        db.add(escrow)
        await db.commit()
        await db.refresh(milestone)
        return milestone


async def _create_job(subject_id: int) -> ConsensusJob:
    async with AsyncSessionLocal() as db:
        job = ConsensusJob(
            subject_type=ConsensusSubjectType.MILESTONE,
            subject_id=subject_id,
            stage=int(ConsensusStage.IDLE),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


async def _get_milestone(milestone_id: int) -> Milestone:
    async with AsyncSessionLocal() as db:
        milestone = await db.get(Milestone, milestone_id)
        assert milestone is not None
        return milestone


# --- 1. _extract_first_url ---------------------------------------------


def test_extract_first_url_finds_a_clean_url():
    url = consensus._extract_first_url("Proof here: https://example.com/proof see it")
    assert url == "https://example.com/proof"


def test_extract_first_url_returns_none_when_absent():
    assert consensus._extract_first_url("Finished the work, no links needed.") is None


def test_extract_first_url_picks_first_of_multiple():
    url = consensus._extract_first_url(
        "See https://first.example.com/a and also https://second.example.com/b"
    )
    assert url == "https://first.example.com/a"


# --- 2. _fetch_url_for_verification --------------------------------------


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html", status: int = 200):
        self.text = text
        self.headers = {"content-type": content_type}
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


class _FakeAsyncClient:
    _next_response: object = None  # class-level, set per-test before use

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, _url):
        result = _FakeAsyncClient._next_response
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_fetch_url_for_verification_extracts_html_text(monkeypatch):
    _FakeAsyncClient._next_response = _FakeResponse(
        "<html><body><h1>Real Page</h1><p>This work was completed and verified.</p></body></html>"
    )
    monkeypatch.setattr(consensus.httpx, "AsyncClient", _FakeAsyncClient)

    result = await consensus._fetch_url_for_verification("https://example.com/proof")
    assert "Real Page" in result
    assert "completed and verified" in result
    assert "<html>" not in result  # tags stripped, not dumped raw


@pytest.mark.asyncio
async def test_fetch_url_for_verification_handles_unreachable_url(monkeypatch):
    _FakeAsyncClient._next_response = httpx.ConnectError("boom")
    monkeypatch.setattr(consensus.httpx, "AsyncClient", _FakeAsyncClient)

    result = await consensus._fetch_url_for_verification("https://example.com/dead")
    assert "unreachable" in result.lower() or "timed out" in result.lower()


@pytest.mark.asyncio
async def test_fetch_url_for_verification_truncates_long_content(monkeypatch):
    _FakeAsyncClient._next_response = _FakeResponse("word " * 10_000, content_type="text/plain")
    monkeypatch.setattr(consensus.httpx, "AsyncClient", _FakeAsyncClient)

    result = await consensus._fetch_url_for_verification("https://example.com/huge")
    assert len(result) <= consensus._MAX_FETCHED_CHARS


# --- 3/4. End to end via run_consensus -----------------------------------


@pytest.mark.asyncio
async def test_fetched_content_changes_the_heuristic_verdict(monkeypatch):
    """The submission text alone ("see the link") has zero positive/
    negative heuristic signal words — a tie, which the heuristic resolves
    to `dispute` (`positive_hits > negative_hits` is False at 0-0). The
    linked page's real content has clear positive signals. If the fetch
    genuinely reaches the judgment, the verdict flips to approve; if this
    regresses back to "never fetch anything," it won't."""
    milestone = await _seed_milestone()
    await _create_job(milestone.id)

    _FakeAsyncClient._next_response = _FakeResponse(
        "<html><body>Confirmed: this deliverable was completed, verified, and "
        "delivered exactly as specified in the milestone criteria.</body></html>"
    )
    monkeypatch.setattr(consensus.httpx, "AsyncClient", _FakeAsyncClient)

    await consensus.run_consensus(
        ConsensusSubjectType.MILESTONE, milestone.id, "See the link: https://example.com/proof"
    )

    updated = await _get_milestone(milestone.id)
    assert updated.status_key == StatusKey.APPROVED


@pytest.mark.asyncio
async def test_no_url_in_submission_never_attempts_a_fetch(monkeypatch):
    milestone = await _seed_milestone()
    await _create_job(milestone.id)

    async def _boom(_url):
        raise AssertionError("_fetch_url_for_verification should never be called with no URL present")

    monkeypatch.setattr(consensus, "_fetch_url_for_verification", _boom)

    # Should complete without the monkeypatched fetch ever firing.
    await consensus.run_consensus(
        ConsensusSubjectType.MILESTONE, milestone.id, "Finished the work, no links needed."
    )
    updated = await _get_milestone(milestone.id)
    assert updated.status_key in (StatusKey.APPROVED, StatusKey.DISPUTED)
