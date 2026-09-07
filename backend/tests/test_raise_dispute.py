"""Tests for POST /escrows/{id}/dispute — the previously-missing backend
half of escrow-detail-view.tsx's "Escalate to Internet Court" button.
ROADMAP.md 3.1 marked "GET/POST /disputes (implicit via escrow)" done, but
no such endpoint, implicit or otherwise, ever existed; this is that
endpoint.

Covers:
  1. Happy path with no `issue` override: pulls the milestone's most
     recent ConsensusJob reasoning into a default claim text, creates both
     the Dispute row and a matching first DisputeEvidence entry, and
     queues a DISPUTE ConsensusJob (the response carries stage 0, not a
     synchronously-run verdict — matches submit_evidence's own contract).
  2. A caller-supplied `issue` overrides the default text.
  3. Only a party to the escrow (creator or counterparty) may open one —
     403 for anyone else.
  4. A milestone that already has an open dispute rejects a second one
     (400) rather than creating a duplicate.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-raise-dispute-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Escrow, Milestone, User  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _get_token(client: TestClient, wallet: Account) -> str:
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    signed = wallet.sign_message(encode_defunct(text=message))
    resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": signed.signature.hex()},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _create_disputed_escrow(creator: str, counterparty: str, with_reasoning: bool) -> int:
    """A milestone already in the "AI rejected it" state — status_key
    DISPUTED, with (optionally) a completed ConsensusJob explaining why —
    exactly the state escrow-detail-view.tsx's "Escalate to Internet
    Court" button appears in."""
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Raise-dispute test escrow",
            total=Decimal("200.00"),
            status_key=StatusKey.DISPUTED,
        )
        milestone = Milestone(
            name="Milestone 1",
            amount=Decimal("200.00"),
            status_key=StatusKey.DISPUTED,
            criteria="Looks good.",
            order_index=0,
        )
        escrow.milestones.append(milestone)
        db.add(escrow)
        await db.flush()

        if with_reasoning:
            db.add(
                ConsensusJob(
                    subject_type=ConsensusSubjectType.MILESTONE,
                    subject_id=milestone.id,
                    stage=int(ConsensusStage.DONE),
                    verdict_approved=False,
                    verdict_reasoning="Deliverable link was unreachable during review.",
                )
            )

        await db.commit()
        return escrow.id


def test_raise_dispute_default_issue_from_reasoning(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    escrow_id = asyncio.run(
        _create_disputed_escrow(creator.address.lower(), counterparty.address.lower(), True)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/dispute",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["escrow_id"] == escrow_id
    assert body["opened_by_address"] == counterparty.address.lower()
    assert body["status_key"] == StatusKey.DISPUTED.value
    assert "unreachable during review" in body["issue"]
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["description"] == body["issue"]
    # The frontend's whole reason for needing this back synchronously:
    # resuming ConsensusPanel polling on the dispute-detail page without a
    # second round-trip to find the job — see DisputeCreateRead's docstring.
    assert isinstance(body["consensus_job_id"], int)


def test_raise_dispute_custom_issue(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    escrow_id = asyncio.run(
        _create_disputed_escrow(creator.address.lower(), counterparty.address.lower(), False)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/dispute",
        json={"issue": "The deliverable clearly meets every criterion listed."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["issue"] == "The deliverable clearly meets every criterion listed."


def test_raise_dispute_rejects_non_party(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    stranger = Account.create()
    _get_token(client, creator)
    _get_token(client, counterparty)
    stranger_token = _get_token(client, stranger)

    escrow_id = asyncio.run(
        _create_disputed_escrow(creator.address.lower(), counterparty.address.lower(), False)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/dispute",
        json={},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert resp.status_code == 403


def test_raise_dispute_rejects_duplicate_open_dispute(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    escrow_id = asyncio.run(
        _create_disputed_escrow(creator.address.lower(), counterparty.address.lower(), False)
    )

    first = client.post(
        f"/escrows/{escrow_id}/dispute", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/escrows/{escrow_id}/dispute", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    assert second.status_code == 400
