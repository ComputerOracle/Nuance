"""Tests for POST /escrows/{id}/dispute/on-chain — the ack endpoint
components/app/genlayer-write-client.ts calls after signing and sending a
real NuanceDisputeCourt.file_dispute transaction. Unlike the off-chain
POST /escrows/{id}/dispute (test_raise_dispute.py), this one creates the
Dispute with on_chain_dispute_id left null (see that field's own
docstring — services/genlayer_indexer.py's resolve_pending_dispute_ids
fills it in asynchronously) and queues no ConsensusJob.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-raise-dispute-onchain-test-")
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

_FAKE_TX_HASH = "0x" + "cd" * 32
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


async def _create_linked_escrow(creator: str, counterparty: str) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Raise-dispute-on-chain test escrow",
            total=Decimal("100.00"),
            status_key=StatusKey.DISPUTED,
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("100.00"),
                status_key=StatusKey.DISPUTED,
                criteria="Looks good.",
                order_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


async def _consensus_job_count_for_escrow_milestones(escrow_id: int) -> int:
    async with AsyncSessionLocal() as db:
        milestone_ids = (
            (await db.execute(select(Milestone.id).where(Milestone.escrow_id == escrow_id)))
            .scalars()
            .all()
        )
        result = await db.execute(
            select(func.count()).select_from(ConsensusJob).where(ConsensusJob.subject_id.in_(milestone_ids))
        )
        return result.scalar_one()


def test_raise_dispute_on_chain_happy_path(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    escrow_id = asyncio.run(_create_linked_escrow(creator.address.lower(), counterparty.address.lower()))

    resp = client.post(
        f"/escrows/{escrow_id}/dispute/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "issue": "The work clearly satisfies the brief."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["issue"] == "The work clearly satisfies the brief."
    assert body["on_chain_tx_hash"] == _FAKE_TX_HASH
    assert body["chain_status"] == ChainStatus.PROCESSING.value
    assert body["on_chain_dispute_id"] is None

    # No ConsensusJob queued — GenVM's own committee is the jury once
    # adjudicate_dispute is called against the contract, not our backend's LLMs.
    job_count = asyncio.run(_consensus_job_count_for_escrow_milestones(escrow_id))
    assert job_count == 0


def test_raise_dispute_on_chain_rejects_unlinked_escrow(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    token = _get_token(client, counterparty)

    async def _create_unlinked() -> int:
        async with AsyncSessionLocal() as db:
            for addr in (creator.address.lower(), counterparty.address.lower()):
                if await db.get(User, addr) is None:
                    db.add(User(wallet_address=addr))
            escrow = Escrow(
                creator_address=creator.address.lower(),
                counterparty_address=counterparty.address.lower(),
                title="Legacy escrow",
                total=Decimal("50.00"),
                status_key=StatusKey.DISPUTED,
            )
            escrow.milestones.append(
                Milestone(
                    name="Milestone 1",
                    amount=Decimal("50.00"),
                    status_key=StatusKey.DISPUTED,
                    criteria="Looks good.",
                    order_index=0,
                )
            )
            db.add(escrow)
            await db.commit()
            await db.refresh(escrow)
            return escrow.id

    escrow_id = asyncio.run(_create_unlinked())

    resp = client.post(
        f"/escrows/{escrow_id}/dispute/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_raise_dispute_on_chain_requires_party(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    stranger = Account.create()
    _get_token(client, creator)
    _get_token(client, counterparty)
    stranger_token = _get_token(client, stranger)

    escrow_id = asyncio.run(_create_linked_escrow(creator.address.lower(), counterparty.address.lower()))

    resp = client.post(
        f"/escrows/{escrow_id}/dispute/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert resp.status_code == 403
