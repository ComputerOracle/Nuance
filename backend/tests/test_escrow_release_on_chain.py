"""Tests for POST /escrows/{id}/release/on-chain and its two companion
fixes — a real fund-safety gap found tracing the escrow lifecycle end to
end (see backend/app/schemas/core.py's OnChainReleaseAck for the full
incident): nothing anywhere in this app ever called the deployed
NuanceEscrow.release_milestone, so an approved milestone on a real, funded
on-chain escrow had its payout permanently stuck.

Covers:
  1. Happy path: the escrow creator releasing an approved, on-chain-linked,
     unreleased milestone records the tx hash + PROCESSING chain_status —
     NOT released_at (that's the indexer's job once it reads the real
     `released: true` back off the contract, tested separately below).
  2. Only the creator may call it (403) — mirrors release_milestone's own
     on-chain sender restriction.
  3. Rejects an escrow not yet linked to a deployed contract (400).
  4. Rejects when there's no approved, unreleased milestone (400) — not
     yet approved, or already released.
  5. Rejects a malformed tx_hash (422, from the schema itself).
  6. The companion guard: the LEGACY off-chain POST /escrows/{id}/release
     now rejects (400) once an escrow is linked to a deployed contract,
     instead of silently marking a real on-chain milestone "released" in
     this DB with zero on-chain effect.
  7. genlayer_indexer._apply_milestone_view mirrors the contract's own
     `released: true` back into Milestone.released_at — the other half of
     this fix; without it, even a real, confirmed on-chain release
     transaction would never be reflected anywhere in this app.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-escrow-release-onchain-test-")
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
from app.services import genlayer_indexer  # noqa: E402

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
    *,
    contract_address: str | None,
    milestone_status: StatusKey,
    on_chain_index: int | None,
    released_at=None,
) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Release on-chain test escrow",
            total=Decimal("2.50"),
            status_key=StatusKey.IN_PROGRESS,
            contract_address=contract_address,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("2.50"),
                status_key=milestone_status,
                criteria="Looks good.",
                order_index=0,
                on_chain_index=on_chain_index,
                released_at=released_at,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


def test_release_on_chain_happy_path(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=0,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    milestone = resp.json()["milestones"][0]
    assert milestone["on_chain_tx_hash"] == _FAKE_TX_HASH
    assert milestone["chain_status"] == "processing"
    # NOT released yet — that's the indexer's job once it reads the real
    # on-chain confirmation, never this ack endpoint (see its own docstring).
    assert milestone["released_at"] is None


def test_release_on_chain_requires_creator(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    _get_token(client, creator)
    counterparty_token = _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=0,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {counterparty_token}"},
    )
    assert resp.status_code == 403


def test_release_on_chain_rejects_unlinked_escrow(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=None,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=None,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_release_on_chain_rejects_not_yet_approved(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.IN_REVIEW,
            on_chain_index=0,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_release_on_chain_rejects_already_released(client: TestClient):
    import datetime as dt

    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=0,
            released_at=dt.datetime.now(dt.timezone.utc),
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_release_on_chain_rejects_malformed_hash(client: TestClient):
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=0,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release/on-chain",
        json={"tx_hash": "not-a-hash"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_legacy_release_rejects_contract_linked_escrow(client: TestClient):
    """The companion fix: the OFF-chain release endpoint used to have no
    idea a real deployed contract even existed — it would happily mark a
    real on-chain escrow's milestone "released" in this DB with zero
    on-chain effect, which is exactly how this whole gap first surfaced
    (the frontend's "Release Payment" button called only this endpoint,
    unconditionally). It must now refuse and point at the on-chain path
    instead."""
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=0,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "on-chain" in resp.json()["detail"]


def test_legacy_release_still_works_for_offchain_escrow(client: TestClient):
    """The legacy path must keep working unchanged for an escrow that was
    never linked to a deployed contract in the first place — nothing
    on-chain to move, so the pure-DB write is correct here."""
    creator = Account.create()
    counterparty = Account.create()
    token = _get_token(client, creator)
    _get_token(client, counterparty)
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=None,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=None,
        )
    )

    resp = client.post(
        f"/escrows/{escrow_id}/release",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["milestones"][0]["released_at"] is not None


def test_indexer_mirrors_on_chain_released_flag(client: TestClient):
    """The other half of this fix: _apply_milestone_view used to read
    every field get_milestone returns EXCEPT `released` — so even a real,
    confirmed on-chain release_milestone transaction would never have
    updated Milestone.released_at at all. Calls the sync function
    directly with a fake ReadResult, same style as this repo's other
    direct service-layer tests (no real RPC involved)."""
    creator = Account.create()
    counterparty = Account.create()
    escrow_id = asyncio.run(
        _create_escrow(
            creator.address.lower(),
            counterparty.address.lower(),
            contract_address=_BOOTSTRAP_CONTRACT_ADDRESS,
            milestone_status=StatusKey.APPROVED,
            on_chain_index=0,
        )
    )

    async def _run():
        async with AsyncSessionLocal() as db:
            escrow = await db.get(Escrow, escrow_id)
            milestone = (await db.execute(
                Milestone.__table__.select().where(Milestone.escrow_id == escrow_id)
            )).first()
            milestone_row = await db.get(Milestone, milestone.id)
            assert milestone_row.released_at is None

            await genlayer_indexer._apply_milestone_view(
                db,
                milestone_row,
                escrow,
                {
                    "ok": True,
                    "result": {
                        "name": "Milestone 1",
                        "amount": 2.5,
                        "criteria": "Looks good.",
                        "status": "approved",
                        "released": True,
                        "deliverable_text": "",
                        "deliverable_url": "",
                        "reasoning": "Approved by GenVM validators.",
                    },
                },
            )
            await db.commit()
            await db.refresh(milestone_row)
            assert milestone_row.released_at is not None

    asyncio.run(_run())
