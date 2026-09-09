"""Tests for GET /agents/{wallet_address}/history — ROADMAP.md Part 4's
Real Agent Directory "transaction drill-down" (the aggregate trust score
in routers/agents.py::_agent_stats was already real, not seed data; what
was missing was any way to see the individual cases behind it).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-agent-history-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Dispute, Escrow, Milestone, User  # noqa: E402

_AGENT = "0xcccc000000000000000000000000000000cccc"
_CREATOR = "0xdddd000000000000000000000000000000dddd"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


async def _seed() -> tuple[int, int, int]:
    """Two milestone cases (won + lost) and one dispute case, all for
    _AGENT, at three distinct completed_at times so ordering is
    assertable. Returns (escrow1_id, escrow2_id, dispute_escrow_id)."""
    async with AsyncSessionLocal() as db:
        for addr in (_AGENT, _CREATOR):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))

        now = datetime.now(timezone.utc)

        escrow1 = Escrow(
            creator_address=_CREATOR,
            counterparty_address=_AGENT,
            title="Won milestone",
            total=Decimal("100.00"),
            status_key=StatusKey.APPROVED,
        )
        escrow1.milestones.append(
            Milestone(name="Ship the thing", amount=Decimal("100.00"), status_key=StatusKey.APPROVED,
                      criteria="x", order_index=0)
        )
        db.add(escrow1)
        await db.flush()
        db.add(
            ConsensusJob(
                subject_type=ConsensusSubjectType.MILESTONE,
                subject_id=escrow1.milestones[0].id,
                stage=int(ConsensusStage.DONE),
                verdict_label="approved",
                verdict_approved=True,
                verdict_confidence=80,
                verdict_reasoning="Looks complete.",
                completed_at=now - timedelta(hours=2),
            )
        )

        escrow2 = Escrow(
            creator_address=_CREATOR,
            counterparty_address=_AGENT,
            title="Lost milestone",
            total=Decimal("50.00"),
            status_key=StatusKey.DISPUTED,
        )
        escrow2.milestones.append(
            Milestone(name="Fix the bug", amount=Decimal("50.00"), status_key=StatusKey.DISPUTED,
                      criteria="x", order_index=0)
        )
        db.add(escrow2)
        await db.flush()
        db.add(
            ConsensusJob(
                subject_type=ConsensusSubjectType.MILESTONE,
                subject_id=escrow2.milestones[0].id,
                stage=int(ConsensusStage.DONE),
                verdict_label="disputed",
                verdict_approved=False,
                verdict_confidence=60,
                verdict_reasoning="Missing evidence.",
                completed_at=now - timedelta(hours=1),  # most recent
            )
        )

        dispute_escrow = Escrow(
            creator_address=_CREATOR,
            counterparty_address=_AGENT,
            title="Disputed escrow",
            total=Decimal("75.00"),
            status_key=StatusKey.DISPUTED,
        )
        db.add(dispute_escrow)
        await db.flush()
        dispute = Dispute(
            escrow_id=dispute_escrow.id,
            opened_by_address=_AGENT,
            issue="They never delivered.",
        )
        db.add(dispute)
        await db.flush()
        db.add(
            ConsensusJob(
                subject_type=ConsensusSubjectType.DISPUTE,
                subject_id=dispute.id,
                stage=int(ConsensusStage.DONE),
                verdict_label="approved",
                verdict_approved=True,
                verdict_confidence=70,
                verdict_reasoning="Claimant's evidence holds up.",
                completed_at=now - timedelta(hours=3),  # oldest
            )
        )

        await db.commit()
        return escrow1.id, escrow2.id, dispute_escrow.id


def test_agent_history_returns_all_cases_newest_first(client):
    escrow1_id, escrow2_id, dispute_escrow_id = asyncio.run(_seed())

    resp = client.get(f"/agents/{_AGENT}/history")
    assert resp.status_code == 200
    cases = resp.json()
    assert len(cases) == 3

    # Newest (lost milestone, -1h) -> won milestone (-2h) -> dispute (-3h).
    assert [c["title"] for c in cases] == ["Fix the bug", "Ship the thing", "They never delivered."]

    lost = cases[0]
    assert lost["subject_type"] == "milestone"
    assert lost["escrow_id"] == escrow2_id
    assert lost["dispute_id"] is None
    assert lost["verdict_approved"] is False

    won = cases[1]
    assert won["escrow_id"] == escrow1_id
    assert won["verdict_approved"] is True

    dispute_case = cases[2]
    assert dispute_case["subject_type"] == "dispute"
    assert dispute_case["escrow_id"] == dispute_escrow_id
    assert dispute_case["dispute_id"] is not None
    assert dispute_case["verdict_reasoning"] == "Claimant's evidence holds up."


def test_agent_history_case_insensitive_and_empty_for_unknown_wallet(client):
    # Depends on test_agent_history_returns_all_cases_newest_first having
    # already seeded _AGENT's 3 cases into this module's shared db — not
    # reseeding here (that would double-count them, since _seed() isn't
    # idempotent). Both lookups just need to agree with each other.
    lower = client.get(f"/agents/{_AGENT}/history")
    upper = client.get(f"/agents/{_AGENT.upper()}/history")
    assert upper.status_code == 200
    assert upper.json() == lower.json()
    assert len(upper.json()) > 0

    empty = client.get("/agents/0x1111111111111111111111111111111111111e/history")
    assert empty.status_code == 200
    assert empty.json() == []
