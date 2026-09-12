"""Tests for POST /escrows/{id}/deliverable's authorization — a real gap
found live (2026-09-12): this endpoint never checked who was calling it.
Any signed-in wallet — not the counterparty, not even a party to the
escrow at all — could submit a "deliverable" for someone else's escrow,
trigger real AI consensus, and move the milestone straight to APPROVED
(payout-eligible). The on-chain contract's own submit_deliverable has
always enforced both checks added here (`gl.message.sender_address !=
self.counterparty` and `self.status != "active"` — contracts/
nuance_escrow.py); this off-chain sibling exists specifically to give an
off-chain escrow equivalent behavior, and had neither.

Covers:
  1. The real counterparty can submit (happy path, unaffected).
  2. The escrow's own creator — the exact wallet the original live bug
     was found with — is rejected (403), not silently accepted.
  3. A completely unrelated third wallet is rejected (403).
  4. A cancelled escrow rejects a submission even from the real
     counterparty (400) — matches the contract's own `self.status !=
     "active"` guard.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-submit-deliverable-auth-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, Milestone, User  # noqa: E402


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


async def _create_escrow(
    creator: str, counterparty: str, status_key: StatusKey = StatusKey.IN_PROGRESS
) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Submit-deliverable authorization test escrow",
            total=Decimal("10.00"),
            status_key=status_key,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("10.00"),
                status_key=StatusKey.PENDING,
                criteria="Looks good.",
                order_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


def test_counterparty_can_submit(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    counterparty_token = _get_token(client, counterparty)
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable",
        json={"text": "Here is the finished work."},
        headers={"Authorization": f"Bearer {counterparty_token}"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["wallet"] == counterparty.address.lower()


def test_creator_cannot_submit_as_the_counterparty(client: TestClient):
    """The exact bug found live: the escrow's own creator submitting a
    deliverable for their own escrow — completely bypassing the point of
    having a separate counterparty do the work — used to be silently
    accepted."""
    creator = Account.create()
    counterparty = Account.create()
    creator_token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable",
        json={"text": "I'll just approve my own work."},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert resp.status_code == 403


def test_unrelated_wallet_cannot_submit(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    stranger = Account.create()
    _get_token(client, creator)
    _get_token(client, counterparty)
    stranger_token = _get_token(client, stranger)
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable",
        json={"text": "Total stranger's submission."},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert resp.status_code == 403


def test_cancelled_escrow_rejects_submission_even_from_counterparty(client: TestClient):
    """Matches contracts/nuance_escrow.py's own `self.status != "active"`
    guard — a cancelled deal has nothing left to submit against, even for
    the real counterparty."""
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    counterparty_token = _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(creator.address.lower(), counterparty.address.lower(), StatusKey.CANCELLED)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable",
        json={"text": "Trying to submit after cancellation."},
        headers={"Authorization": f"Bearer {counterparty_token}"},
    )
    assert resp.status_code == 400
