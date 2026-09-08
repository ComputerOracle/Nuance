"""Tests for POST /escrows/{id}/cancel/on-chain — the ack endpoint
components/app/genlayer-write-client.ts's cancelEscrowOnChain calls after
signing and sending a real NuanceEscrow.cancel_escrow transaction.

Covers:
  1. Happy path: the escrow creator cancelling a linked escrow flips
     status_key to CANCELLED and records the tx hash.
  2. Only the creator may call it (403 for the counterparty or anyone
     else) — mirrors the contract's own cancel_escrow restriction.
  3. Rejects an escrow not yet linked to a deployed contract (400).
  4. Rejects an already-cancelled escrow (400) — no double-cancel.
  5. Rejects a malformed tx_hash (422, from the schema itself).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-escrow-cancel-onchain-test-")
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

_FAKE_TX_HASH = "0x" + "22" * 32
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


async def _create_escrow(
    creator: str,
    counterparty: str,
    contract_address: str | None,
    status_key: StatusKey = StatusKey.IN_PROGRESS,
) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Cancel on-chain test escrow",
            total=Decimal("2.50"),
            status_key=status_key,
            contract_address=contract_address,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("2.50"),
                status_key=StatusKey.PENDING,
                criteria="Looks good.",
                order_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


def test_cancel_escrow_on_chain_happy_path(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(creator.address.lower(), counterparty.address.lower(), _BOOTSTRAP_CONTRACT_ADDRESS)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/cancel/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["cancelled_tx_hash"] == _FAKE_TX_HASH
    assert body["status_key"] == "cancelled"


def test_cancel_escrow_on_chain_requires_creator(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    counterparty_token = _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(creator.address.lower(), counterparty.address.lower(), _BOOTSTRAP_CONTRACT_ADDRESS)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/cancel/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {counterparty_token}"},
    )
    assert resp.status_code == 403


def test_cancel_escrow_on_chain_rejects_unlinked_escrow(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(creator.address.lower(), counterparty.address.lower(), None)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/cancel/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_cancel_escrow_on_chain_rejects_already_cancelled(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            _BOOTSTRAP_CONTRACT_ADDRESS,
            status_key=StatusKey.CANCELLED,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/cancel/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_cancel_escrow_on_chain_rejects_malformed_hash(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(creator.address.lower(), counterparty.address.lower(), _BOOTSTRAP_CONTRACT_ADDRESS)
    )

    resp = client.post(
        f"/escrows/{escrow_id}/cancel/on-chain",
        json={"tx_hash": "not-a-hash"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
