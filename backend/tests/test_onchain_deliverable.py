"""Tests for POST /escrows/{id}/deliverable/on-chain — the ack endpoint
components/app/genlayer-write-client.ts calls after it has already signed
and sent a real NuanceEscrow.submit_deliverable transaction itself.

Covers:
  1. Happy path: an escrow linked to a contract (contract_address +
     milestone.on_chain_index set) accepts a valid tx hash from the
     counterparty, sets chain_status/status_key, and — the important
     negative check — does NOT queue a ConsensusJob the way the off-chain
     POST /escrows/{id}/deliverable does, since GenVM's own validator
     committee is doing that job instead.
  2. An escrow with no contract_address (the normal/legacy state) rejects
     this endpoint with 400 — it isn't the right path for it.
  3. Only the escrow counterparty may call it (403 otherwise), mirroring
     the on-chain contract's own `submit_deliverable` guard.
  4. A malformed tx_hash is rejected by the schema itself (422), before
     any of the above logic runs.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-onchain-deliverable-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ChainStatus, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Escrow, Milestone, User  # noqa: E402

_FAKE_TX_HASH = "0x" + "ab" * 32
_BOOTSTRAP_CONTRACT_ADDRESS = "0xDB6939bD12775e5F77e48138F0DE103D804268f7"


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


async def _create_linked_escrow(creator: str, counterparty: str) -> tuple[int, int]:
    """A real escrow + milestone, linked as if a per-escrow contract
    deploy had already happened (that flow itself doesn't exist yet — see
    ROADMAP.md 4.4.1's bootstrap-instance caveat — so tests link directly,
    same as genlayer_indexer.py's own --link-demo does by hand)."""
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="On-chain deliverable test escrow",
            total=Decimal("100.00"),
            status_key=StatusKey.IN_PROGRESS,
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("100.00"),
                status_key=StatusKey.PENDING,
                criteria="Looks good.",
                order_index=0,
                on_chain_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow, attribute_names=["milestones"])
        return escrow.id, escrow.milestones[0].id


async def _create_unlinked_escrow(creator: str, counterparty: str) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Legacy off-chain escrow",
            total=Decimal("50.00"),
            status_key=StatusKey.IN_PROGRESS,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("50.00"),
                status_key=StatusKey.PENDING,
                criteria="Looks good.",
                order_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


async def _consensus_job_count(milestone_id: int) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count()).select_from(ConsensusJob).where(ConsensusJob.subject_id == milestone_id)
        )
        return result.scalar_one()


def test_onchain_ack_happy_path(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)  # ensures the creator User row exists via auth
    token = _get_token(client, counterparty)

    escrow_id, milestone_id = asyncio.run(
        _create_linked_escrow(creator.address.lower(), counterparty.address.lower())
    )

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["chain_status"] == ChainStatus.PROCESSING.value
    assert body["on_chain_tx_hash"] == _FAKE_TX_HASH
    assert body["status_key"] == StatusKey.IN_REVIEW.value

    # The important negative check: this path must NOT queue an off-chain
    # consensus job — GenVM's own validator committee already handles the
    # equivalent judgment on the deployed contract.
    job_count = asyncio.run(_consensus_job_count(milestone_id))
    assert job_count == 0


def test_onchain_ack_rejects_unlinked_escrow(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    escrow_id = asyncio.run(
        _create_unlinked_escrow(creator.address.lower(), counterparty.address.lower())
    )

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_onchain_ack_requires_counterparty(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    creator_token = _get_token(client, creator)
    _get_token(client, counterparty)

    escrow_id, _ = asyncio.run(
        _create_linked_escrow(creator.address.lower(), counterparty.address.lower())
    )

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert resp.status_code == 403


def test_onchain_ack_rejects_malformed_hash(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    escrow_id, _ = asyncio.run(
        _create_linked_escrow(creator.address.lower(), counterparty.address.lower())
    )

    resp = client.post(
        f"/escrows/{escrow_id}/deliverable/on-chain",
        json={"tx_hash": "not-a-real-hash"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
