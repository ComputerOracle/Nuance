"""Tests for services/genlayer_indexer.py::quick_sync_escrow — a real
latency gap found live: after funding a real escrow, confirmation took
as long as the general indexer's own poll interval (15s by default) to
show up in the UI. Real dapps don't make a user wait for a generic
background sweep to notice their own transaction; this is a short-lived,
fast-cadence poll of ONE escrow, queued right after routers/escrows.py's
fund/cancel/submit/release-on-chain acks (the exact moments a user is
watching for confirmation).

Mocks app.services.genlayer_rpc.read_and_check entirely (no subprocess,
no real network, no real testnet GEN spent).

Covers:
  1. Stops (and publishes) as soon as a poll actually changes something —
     doesn't burn through every attempt once it has an answer.
  2. Gives up cleanly after max_attempts if nothing ever changes.
  3. A missing/failed read on one attempt doesn't crash the loop or
     count as "changed" — it just tries again next tick.
  4. Exits immediately for an escrow with no contract_address (nothing
     on-chain to poll) or that no longer exists.
  5. Wiring: fund_escrow_on_chain actually queues it as a background
     task (TestClient runs queued tasks before returning, so this is a
     real, not mocked, end-to-end check of the call site itself).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-escrow-quick-sync-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_indexer as genlayer_indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, Milestone, User  # noqa: E402

_CONTRACT_ADDRESS = "0xF00Dbabe00000000000000000000000000000042"


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


async def _create_escrow(contract_address: str | None = _CONTRACT_ADDRESS) -> int:
    async with AsyncSessionLocal() as db:
        creator = "0x" + "1" * 40
        counterparty = "0x" + "2" * 40
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Quick-sync test escrow",
            total=Decimal("5.00"),
            status_key=StatusKey.IN_PROGRESS,
            contract_address=contract_address,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal("5.00"),
                status_key=StatusKey.PENDING,
                criteria="Looks good.",
                order_index=0,
                on_chain_index=0 if contract_address else None,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


async def _get_escrow(escrow_id: int) -> Escrow:
    async with AsyncSessionLocal() as db:
        escrow = await db.get(Escrow, escrow_id)
        assert escrow is not None
        return escrow


def _fake_read_and_check(escrow_results: list[dict]):
    """Returns a fake genlayer_rpc.read_and_check that yields each dict
    in `escrow_results` in turn (one per call), matching the shape
    _build_read_batch's escrow: id key expects. Exhausting the list
    means "still no answer" on every subsequent call, matching a real
    RPC that keeps saying "pending" until it doesn't."""
    calls = {"n": 0}

    async def _fake(reads, tx_hashes):
        idx = min(calls["n"], len(escrow_results) - 1)
        calls["n"] += 1
        result = escrow_results[idx]
        read_results = {r["id"]: result for r in reads if r["functionName"] == "get_escrow"}
        return read_results, {}

    return _fake, calls


def test_quick_sync_stops_as_soon_as_something_changes(monkeypatch):
    monkeypatch.setattr(genlayer_indexer, "_QUICK_SYNC_INTERVAL_SECONDS", 0.01)
    escrow_id = asyncio.run(_create_escrow())

    fake, calls = _fake_read_and_check(
        [
            {"ok": True, "result": {"funded_amount": "0", "status": "active"}},
            {"ok": True, "result": {"funded_amount": "5000000000000000000", "status": "active"}},
        ]
    )
    monkeypatch.setattr(genlayer_indexer.genlayer_rpc, "read_and_check", fake)

    asyncio.run(genlayer_indexer.quick_sync_escrow(escrow_id, max_attempts=10, interval_seconds=0.01))

    # Stopped at attempt 2, not all 10 — the real point of "quick" sync.
    assert calls["n"] == 2
    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.funded_amount == Decimal("5")


def test_quick_sync_gives_up_after_max_attempts_if_nothing_changes(monkeypatch):
    monkeypatch.setattr(genlayer_indexer, "_QUICK_SYNC_INTERVAL_SECONDS", 0.01)
    escrow_id = asyncio.run(_create_escrow())

    # Always reports unfunded — nothing ever changes.
    fake, calls = _fake_read_and_check([{"ok": True, "result": {"funded_amount": "0", "status": "active"}}])
    monkeypatch.setattr(genlayer_indexer.genlayer_rpc, "read_and_check", fake)

    asyncio.run(genlayer_indexer.quick_sync_escrow(escrow_id, max_attempts=5, interval_seconds=0.01))

    assert calls["n"] == 5
    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.funded_amount == Decimal("0")


def test_quick_sync_survives_a_failed_read_and_keeps_trying(monkeypatch):
    monkeypatch.setattr(genlayer_indexer, "_QUICK_SYNC_INTERVAL_SECONDS", 0.01)
    escrow_id = asyncio.run(_create_escrow())

    fake, calls = _fake_read_and_check(
        [
            {"ok": False, "error": "transient RPC blip"},
            {"ok": True, "result": {"funded_amount": "5000000000000000000", "status": "active"}},
        ]
    )
    monkeypatch.setattr(genlayer_indexer.genlayer_rpc, "read_and_check", fake)

    asyncio.run(genlayer_indexer.quick_sync_escrow(escrow_id, max_attempts=10, interval_seconds=0.01))

    assert calls["n"] == 2  # a failed read isn't "changed" — tries again, then succeeds
    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.funded_amount == Decimal("5")


def test_quick_sync_exits_immediately_for_off_chain_escrow(monkeypatch):
    escrow_id = asyncio.run(_create_escrow(contract_address=None))

    def _fail_if_called(reads, tx_hashes):
        raise AssertionError("read_and_check should never be called for an off-chain escrow")

    monkeypatch.setattr(genlayer_indexer.genlayer_rpc, "read_and_check", _fail_if_called)

    asyncio.run(genlayer_indexer.quick_sync_escrow(escrow_id, max_attempts=3, interval_seconds=0.01))
    # Must not raise — the assertion inside _fail_if_called would only
    # fire if read_and_check were actually (wrongly) invoked.


def test_quick_sync_exits_immediately_for_nonexistent_escrow(monkeypatch):
    def _fail_if_called(reads, tx_hashes):
        raise AssertionError("read_and_check should never be called for a nonexistent escrow")

    monkeypatch.setattr(genlayer_indexer.genlayer_rpc, "read_and_check", _fail_if_called)

    asyncio.run(genlayer_indexer.quick_sync_escrow(999999, max_attempts=3, interval_seconds=0.01))


def test_fund_escrow_on_chain_does_not_sync_when_disabled(client: TestClient, monkeypatch):
    """The exact regression this whole file exists to prevent: relies on
    conftest.py's own autouse _disable_quick_escrow_sync_by_default
    fixture (does NOT override it, unlike the test below) — confirms
    that with the setting at its test-suite default, hitting a real
    on-chain ack endpoint does NOT attempt any real RPC call at all."""

    def _fail_if_called(reads, tx_hashes):
        raise AssertionError(
            "read_and_check should never be called — enable_quick_escrow_sync "
            "is off by default for the whole test suite"
        )

    monkeypatch.setattr(genlayer_indexer.genlayer_rpc, "read_and_check", _fail_if_called)

    creator = Account.create()
    escrow_id = asyncio.run(_create_escrow(_CONTRACT_ADDRESS))

    async def _set_creator() -> None:
        async with AsyncSessionLocal() as db:
            escrow = await db.get(Escrow, escrow_id)
            escrow.creator_address = creator.address.lower()
            await db.commit()

    asyncio.run(_set_creator())

    token = _get_token(client, creator)
    resp = client.post(
        f"/escrows/{escrow_id}/fund/on-chain",
        json={"tx_hash": "0x" + "ef" * 32},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    # If read_and_check had been called, the assertion inside
    # _fail_if_called would have raised — TestClient runs queued
    # background tasks synchronously, so reaching here at all is proof.


def test_fund_escrow_on_chain_queues_quick_sync(client: TestClient, monkeypatch):
    """Real, not mocked, end-to-end check of the call site itself —
    TestClient runs queued BackgroundTasks before the response returns,
    so this confirms fund_escrow_on_chain actually queues
    quick_sync_escrow rather than just testing the function in
    isolation. Overrides conftest.py's own enable_quick_escrow_sync=False
    default (forced off suite-wide specifically so every OTHER test
    hitting this endpoint doesn't fire a real background sync) — same
    override pattern test_auto_deploy_escrow.py's own endpoint-level test
    already uses for auto_deploy_escrow_contracts."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "enable_quick_escrow_sync", True)

    creator = Account.create()
    escrow_id = asyncio.run(_create_escrow(_CONTRACT_ADDRESS))

    async def _set_creator() -> None:
        async with AsyncSessionLocal() as db:
            escrow = await db.get(Escrow, escrow_id)
            escrow.creator_address = creator.address.lower()
            await db.commit()

    asyncio.run(_set_creator())

    called = {"escrow_id": None}

    async def _fake_quick_sync(escrow_id: int, **_kwargs) -> None:
        called["escrow_id"] = escrow_id

    monkeypatch.setattr(genlayer_indexer, "quick_sync_escrow", _fake_quick_sync)

    token = _get_token(client, creator)
    resp = client.post(
        f"/escrows/{escrow_id}/fund/on-chain",
        json={"tx_hash": "0x" + "cd" * 32},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    assert called["escrow_id"] == escrow_id
