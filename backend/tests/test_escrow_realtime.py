"""Tests for the escrow live-update channel (WS + SSE) — added 2026-09-12
after a real gap found live: an already-open escrow detail view had no
way to learn that a background auto-deploy had just linked a contract (or
any other server-side change — funding, a milestone's verdict landing,
an on-chain sync) short of a manual page reload.

No Redis is running in this test environment, so every test here
exercises the db-polling fallback path specifically — same reasoning
test_realtime_sse_ws.py's own module docstring gives for the identical
situation with dispute messages/consensus.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-escrow-realtime-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.routers.escrows as escrows_router  # noqa: E402
import app.services.genlayer_deploy as genlayer_deploy  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, Milestone, User  # noqa: E402

_FAKE_ADDRESS = "0xF00Dbabe00000000000000000000000000000042"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


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


async def _create_escrow(creator: str, counterparty: str) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Realtime test escrow",
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


# --- WS ----------------------------------------------------------------


def test_escrow_ws_sends_initial_snapshot(client):
    creator = Account.create()
    counterparty = Account.create()
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    with client.websocket_connect(f"/escrows/ws/{escrow_id}") as ws:
        init = ws.receive_json()
        assert init["type"] == "escrow"
        assert init["escrow"]["id"] == escrow_id
        assert init["escrow"]["contract_address"] is None


def test_escrow_ws_404_for_missing_escrow(client):
    with client.websocket_connect("/escrows/ws/999999") as ws:
        payload = ws.receive_json()
        assert payload.get("error") == "Escrow not found."


def test_escrow_ws_pushes_snapshot_after_auto_deploy(client, monkeypatch):
    """The exact bug reported live: a background auto-deploy setting
    contract_address had no way to reach an already-open detail view.
    Speeds the poll interval way down (no Redis in this test
    environment, so this exercises that db-polling fallback) rather than
    sitting through the real multi-second cadence."""
    monkeypatch.setattr(escrows_router, "ESCROW_POLL_INTERVAL_SECONDS", 0.05)

    creator = Account.create()
    counterparty = Account.create()
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    async def _fake_deploy_contract(file, args):
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    with client.websocket_connect(f"/escrows/ws/{escrow_id}") as ws:
        init = ws.receive_json()
        assert init["escrow"]["contract_address"] is None

        # Simulates routers/escrows.py::create_escrow's own
        # background_tasks.add_task(deploy_escrow_contract, escrow.id) —
        # this is the exact call the original bug report traced back to.
        asyncio.run(genlayer_deploy.deploy_escrow_contract(escrow_id))

        update = ws.receive_json()
        assert update["type"] == "escrow"
        assert update["escrow"]["contract_address"] == _FAKE_ADDRESS
        assert update["escrow"]["milestones"][0]["on_chain_index"] == 0


# --- SSE -----------------------------------------------------------------


class _FakeRequest:
    """Minimal stand-in for fastapi.Request — only is_disconnected() is
    ever called on it by _escrow_updates_sse_events. `connected`
    (mutable, checked by reference) lets a test flip it mid-stream to
    simulate a client going away."""

    def __init__(self, disconnected: bool = False):
        self.disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self.disconnected


def test_escrow_sse_events_initial_and_update(monkeypatch):
    monkeypatch.setattr(escrows_router, "ESCROW_POLL_INTERVAL_SECONDS", 0.05)

    creator = Account.create()
    counterparty = Account.create()
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    async def _run():
        agen = escrows_router._escrow_updates_sse_events(escrow_id, _FakeRequest())
        first = await agen.__anext__()
        assert "event: " not in first  # bare data: line for the init payload
        assert '"type": "escrow"' in first
        assert '"contract_address": null' in first

        async with AsyncSessionLocal() as db:
            escrow = await db.get(Escrow, escrow_id)
            escrow.funded_tx_hash = "0x" + "ab" * 32
            await db.commit()

        second = await asyncio.wait_for(agen.__anext__(), timeout=2.0)
        assert "ab" * 32 in second
        await agen.aclose()

    asyncio.run(_run())


def test_escrow_sse_events_error_for_missing_escrow():
    async def _run():
        agen = escrows_router._escrow_updates_sse_events(999999, _FakeRequest())
        first = await agen.__anext__()
        assert "event: " not in first
        assert "Escrow not found." in first
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()

    asyncio.run(_run())


def test_escrow_sse_events_stops_polling_once_client_disconnects(monkeypatch):
    """FIXED 2026-09-12 — found live, the hard way: a client killed
    abruptly (not a clean close) can leave the ASGI layer never
    delivering a disconnect signal on its own, so this loop kept polling
    the db forever — six abandoned connections were enough to make even
    GET /health stop responding on a real running server. This proves
    the fix: once request.is_disconnected() reports true, the generator
    must actually stop iterating, not keep querying the db tick after
    tick."""
    monkeypatch.setattr(escrows_router, "ESCROW_POLL_INTERVAL_SECONDS", 0.05)

    creator = Account.create()
    counterparty = Account.create()
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    async def _run():
        request = _FakeRequest(disconnected=False)
        agen = escrows_router._escrow_updates_sse_events(escrow_id, request)
        await agen.__anext__()  # the initial snapshot

        request.disconnected = True  # simulate the client vanishing
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(agen.__anext__(), timeout=2.0)

    asyncio.run(_run())


# --- Publish call sites --------------------------------------------------


def test_release_publishes_an_update(client, monkeypatch):
    """A lighter-weight check than a full WS round trip for every one of
    the ~7 call sites: monkeypatch _publish_escrow_snapshot itself and
    confirm it fires with the right escrow id. Covers the off-chain
    release_milestone endpoint specifically; the same helper is reused
    (not re-implemented) at every other call site, so this stands in for
    fund/cancel/submit acks too without duplicating a WS test per action.
    """
    creator = Account.create()
    counterparty = Account.create()
    escrow_id = asyncio.run(_create_escrow(creator.address.lower(), counterparty.address.lower()))

    async def _approve_milestone() -> None:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Milestone).where(Milestone.escrow_id == escrow_id))
            milestone = result.scalars().one()
            milestone.status_key = StatusKey.APPROVED
            await db.commit()

    asyncio.run(_approve_milestone())

    published_ids = []

    async def _fake_publish(escrow_id: int) -> None:
        published_ids.append(escrow_id)

    monkeypatch.setattr(escrows_router, "_publish_escrow_snapshot", _fake_publish)

    token = _get_token(client, creator)
    resp = client.post(f"/escrows/{escrow_id}/release", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert published_ids == [escrow_id]
