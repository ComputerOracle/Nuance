"""Unit tests for the AI-validator consensus engine (Gemini).

Mocks google.genai.Client entirely (no real network call happens) and verifies:
  1. Stage transitions land at DONE with a completed_at timestamp.
  2. Majority-vote aggregation math (direction, averaged confidence,
     concatenated majority reasoning) is correct.
  3. A missing ConsensusJob is a no-op, not a crash.
  4. No API key configured means no client is even constructed.
  5. API call errors gracefully degrade to 0-confidence Disputed state.
"""

from __future__ import annotations

import itertools
import json
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-consensus-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from google.genai.errors import APIError  # noqa: E402

import app.services.consensus as consensus  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Dispute, DisputeEvidence, DisputeMessage, Escrow, Milestone, User  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


# --- Fakes -------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)
        self.parsed = consensus.ValidatorVerdict(**data)


_CANNED_VERDICTS = {
    "Validator-Alpha": {"vote": "approve", "confidence": 90, "reasoning": "Alpha: meets the brief."},
    "Validator-Beta": {"vote": "approve", "confidence": 70, "reasoning": "Beta: looks solid."},
    "Validator-Gamma": {"vote": "dispute", "confidence": 60, "reasoning": "Gamma: missing tests."},
}


class _FakeAsyncModels:
    async def generate_content(self, *, model: str, contents: str, config=None):
        system_instruction = getattr(config, "system_instruction", "") or ""
        for name, verdict in _CANNED_VERDICTS.items():
            if name in system_instruction:
                return _FakeResponse(verdict)
        return _FakeResponse({"vote": "dispute", "confidence": 50, "reasoning": "Default dispute."})


class _FakeAio:
    def __init__(self):
        self.models = _FakeAsyncModels()


class _FakeGenaiClient:
    def __init__(self, api_key: str | None = None, *_args, **_kwargs):
        self.api_key = api_key
        self.aio = _FakeAio()


class _FailingAsyncModels:
    async def generate_content(self, **_kwargs):
        raise APIError(code=500, message="Gemini service unavailable")


class _FailingAio:
    def __init__(self):
        self.models = _FailingAsyncModels()


class _FailingGenaiClient:
    def __init__(self, *_args, **_kwargs):
        self.aio = _FailingAio()


# --- DB helpers ----------------------------------------------------------


_wallet_counter = itertools.count(1)


async def _seed_milestone() -> Milestone:
    suffix1 = format(next(_wallet_counter), "040x")
    suffix2 = format(next(_wallet_counter), "040x")
    async with AsyncSessionLocal() as db:
        user1 = User(wallet_address="0x" + suffix1)
        user2 = User(wallet_address="0x" + suffix2)
        escrow = Escrow(
            creator_address=user1.wallet_address,
            counterparty_address=user2.wallet_address,
            title="Test escrow",
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


# --- Tests -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_consensus_transitions_stages_and_computes_majority(monkeypatch):
    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    monkeypatch.setattr(consensus.genai, "Client", _FakeGenaiClient)
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-key")

    await consensus.run_consensus(
        ConsensusSubjectType.MILESTONE,
        milestone.id,
        "Here is the finished prototype.",
    )

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)
        refreshed_milestone = await db.get(Milestone, milestone.id)
        refreshed_escrow = await db.get(Escrow, milestone.escrow_id)

    assert refreshed.stage == int(ConsensusStage.DONE)
    assert refreshed.completed_at is not None

    # Verify state mutation occurred on Milestone and Escrow
    assert refreshed_milestone.status_key == StatusKey.APPROVED
    assert refreshed_escrow.status_key == StatusKey.APPROVED

    names = [r["name"] for r in refreshed.validator_results]
    assert names == list(consensus.VALIDATOR_NAMES)

    # Majority: Alpha + Beta approve, Gamma disputes -> approved, confidence
    # averaged over just the majority: (90 + 70) / 2 = 80.
    assert refreshed.verdict_approved is True
    assert refreshed.verdict_label == "approve"
    assert refreshed.verdict_confidence == 80
    assert "Alpha" in refreshed.verdict_reasoning
    assert "Beta" in refreshed.verdict_reasoning
    assert "Gamma" not in refreshed.verdict_reasoning


@pytest.mark.asyncio
async def test_run_consensus_missing_job_is_a_noop(monkeypatch):
    monkeypatch.setattr(consensus.genai, "Client", _FakeGenaiClient)
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-key")

    # No ConsensusJob exists for this subject_id — should log and return, not raise.
    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, 999_999, "irrelevant")


@pytest.mark.asyncio
async def test_run_consensus_skips_network_without_api_key(monkeypatch):
    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    def _boom(*_a, **_k):
        raise AssertionError("genai.Client should not be constructed without an API key")

    monkeypatch.setattr(consensus.genai, "Client", _boom)
    monkeypatch.setattr(consensus.settings, "gemini_api_key", None)
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)

    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, milestone.id, "text")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)
        refreshed_milestone = await db.get(Milestone, milestone.id)
        refreshed_escrow = await db.get(Escrow, milestone.escrow_id)

    assert refreshed.stage == int(ConsensusStage.DONE)
    assert all(r["confidence"] == 0 for r in refreshed.validator_results)
    assert refreshed.verdict_approved is False

    # State mutation to disputed
    assert refreshed_milestone.status_key == StatusKey.DISPUTED
    assert refreshed_escrow.status_key == StatusKey.DISPUTED


@pytest.mark.asyncio
async def test_run_consensus_api_error_returns_clean_fallback(monkeypatch):
    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    monkeypatch.setattr(consensus.genai, "Client", _FailingGenaiClient)
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-key")

    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, milestone.id, "text")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)
        refreshed_milestone = await db.get(Milestone, milestone.id)
        refreshed_escrow = await db.get(Escrow, milestone.escrow_id)

    assert refreshed.verdict_approved is False
    assert refreshed.verdict_confidence == 0
    assert refreshed_milestone.status_key == StatusKey.DISPUTED
    assert refreshed_escrow.status_key == StatusKey.DISPUTED


@pytest.mark.asyncio
async def test_run_consensus_dispute_with_messages_and_evidence(monkeypatch):
    suffix1 = format(next(_wallet_counter), "040x")
    suffix2 = format(next(_wallet_counter), "040x")
    async with AsyncSessionLocal() as db:
        user1 = User(wallet_address="0x" + suffix1)
        user2 = User(wallet_address="0x" + suffix2)
        escrow = Escrow(
            creator_address=user1.wallet_address,
            counterparty_address=user2.wallet_address,
            title="Design QA Escrow",
            total=500,
            status_key=StatusKey.IN_PROGRESS,
        )
        milestone = Milestone(
            name="Milestone 1",
            amount=500,
            status_key=StatusKey.IN_REVIEW,
            criteria="Pixel-perfect Figma match.",
            order_index=0,
        )
        escrow.milestones.append(milestone)
        db.add(user1)
        db.add(user2)
        db.add(escrow)
        await db.flush()
        await db.refresh(milestone)

        dispute = Dispute(
            escrow_id=escrow.id,
            milestone_id=milestone.id,
            opened_by_address=user1.wallet_address,
            issue="Figma specs not met on button padding and fonts.",
            status_key=StatusKey.DISPUTED,
        )
        db.add(dispute)
        await db.flush()
        await db.refresh(dispute)

        msg1 = DisputeMessage(
            dispute_id=dispute.id,
            sender_address=user1.wallet_address,
            content="Buttons are 12px instead of 16px.",
        )
        msg2 = DisputeMessage(
            dispute_id=dispute.id,
            sender_address=user2.wallet_address,
            content="Fixed in commit 3ab4f.",
        )
        ev1 = DisputeEvidence(
            dispute_id=dispute.id,
            submitter_address=user1.wallet_address,
            description="Screenshot diff showing font mismatch.",
            link="https://example.com/diff.png",
        )
        db.add_all([msg1, msg2, ev1])

        job = ConsensusJob(
            subject_type=ConsensusSubjectType.DISPUTE,
            subject_id=dispute.id,
            stage=int(ConsensusStage.IDLE),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        dispute_id = dispute.id
        job_id = job.id

    monkeypatch.setattr(consensus.genai, "Client", _FakeGenaiClient)
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-key")

    await consensus.run_consensus(
        ConsensusSubjectType.DISPUTE,
        dispute_id,
        "Submitting final screenshot comparisons and CSS inspect metrics.",
    )

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job_id)
        refreshed_dispute = await db.get(Dispute, dispute_id)
        refreshed_escrow = await db.get(Escrow, refreshed_dispute.escrow_id)
        refreshed_milestone = await db.get(Milestone, refreshed_dispute.milestone_id)

    assert refreshed.stage == int(ConsensusStage.DONE)
    assert refreshed.verdict_approved is True
    assert refreshed.verdict_confidence == 80

    # Dispute upheld -> dispute resolved with ruling, milestone and escrow marked disputed
    assert refreshed_dispute.status_key == StatusKey.APPROVED
    assert refreshed_dispute.ruling is not None
    assert refreshed_milestone.status_key == StatusKey.DISPUTED
    assert refreshed_escrow.status_key == StatusKey.DISPUTED


@pytest.mark.asyncio
async def test_run_consensus_dispute_rejected_sets_rejected_not_approved(monkeypatch):
    """Regression test for the bug where every resolved dispute — upheld or
    not — got stamped StatusKey.APPROVED. No API key -> every validator
    abstains as "dispute" -> verdict_approved is False -> the claim was
    rejected, so the dispute itself must land on REJECTED, not APPROVED."""
    suffix1 = format(next(_wallet_counter), "040x")
    suffix2 = format(next(_wallet_counter), "040x")
    async with AsyncSessionLocal() as db:
        user1 = User(wallet_address="0x" + suffix1)
        user2 = User(wallet_address="0x" + suffix2)
        escrow = Escrow(
            creator_address=user1.wallet_address,
            counterparty_address=user2.wallet_address,
            title="Rejected-dispute Escrow",
            total=500,
            status_key=StatusKey.IN_PROGRESS,
        )
        milestone = Milestone(
            name="Milestone 1",
            amount=500,
            status_key=StatusKey.APPROVED,
            criteria="Ship the landing page.",
            order_index=0,
        )
        escrow.milestones.append(milestone)
        db.add(user1)
        db.add(user2)
        db.add(escrow)
        await db.flush()
        await db.refresh(milestone)

        dispute = Dispute(
            escrow_id=escrow.id,
            milestone_id=milestone.id,
            opened_by_address=user1.wallet_address,
            issue="Claiming the delivery was late.",
            status_key=StatusKey.DISPUTED,
        )
        db.add(dispute)
        await db.flush()
        await db.refresh(dispute)

        job = ConsensusJob(
            subject_type=ConsensusSubjectType.DISPUTE,
            subject_id=dispute.id,
            stage=int(ConsensusStage.IDLE),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        dispute_id = dispute.id
        job_id = job.id

    monkeypatch.setattr(consensus.settings, "gemini_api_key", None)
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)

    await consensus.run_consensus(
        ConsensusSubjectType.DISPUTE, dispute_id, "No real evidence to support the claim."
    )

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job_id)
        refreshed_dispute = await db.get(Dispute, dispute_id)
        refreshed_milestone = await db.get(Milestone, milestone.id)
        refreshed_escrow = await db.get(Escrow, escrow.id)

    assert refreshed.verdict_approved is False

    # The claim was rejected -> the dispute itself is REJECTED, not APPROVED,
    # and the underlying delivery stands (milestone/escrow stay APPROVED).
    assert refreshed_dispute.status_key == StatusKey.REJECTED
    assert refreshed_dispute.resolved_at is not None
    assert refreshed_milestone.status_key == StatusKey.APPROVED
    assert refreshed_escrow.status_key == StatusKey.APPROVED

