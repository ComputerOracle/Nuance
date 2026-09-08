"""Tests for services/genlayer_indexer.py's trigger_pending_adjudications —
the piece that closes the gap flagged repeatedly elsewhere: filing a
dispute on-chain never got it a verdict, because nothing called
NuanceDisputeCourt.adjudicate_dispute. Mocks
app.services.genlayer_write.write_contract entirely (no subprocess, no
real network, no real testnet GEN spent).

Covers:
  1. Happy path: a still-open, resolved-id, never-triggered dispute gets
     adjudicate_dispute sent with the right address/args, and
     adjudication_tx_hash is recorded on success.
  2. Already-triggered (adjudication_tx_hash already set) — never sent
     twice.
  3. Already resolved off-chain (status_key no longer DISPUTED, e.g. a
     view-sync in the same cycle already flipped it) — never triggered;
     nothing left to adjudicate.
  4. A failed *send* (write_contract returns None) leaves
     adjudication_tx_hash null — safe to retry next cycle, since nothing
     was actually submitted.
  5. No DISPUTE_COURT_CONTRACT_ADDRESS configured — skipped entirely, zero
     calls made.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-adjudication-trigger-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_indexer as indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Dispute, Escrow, User  # noqa: E402

_DISPUTE_COURT = "0xf7b4C186fF9d69701F41AA3Aa1aCF8cED0c9b057"
_CLAIMANT = "0x1111111111111111111111111111111111111111"
_COUNTERPARTY = "0x2222222222222222222222222222222222222222"
_FAKE_TX_HASH = "0x" + "aa" * 32


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture(autouse=True)
def _set_dispute_court_address(monkeypatch):
    monkeypatch.setattr(indexer.settings, "dispute_court_contract_address", _DISPUTE_COURT)


async def _create_dispute(
    on_chain_dispute_id: int | None, status_key: StatusKey, adjudication_tx_hash: str | None = None
) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (_CLAIMANT, _COUNTERPARTY):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=_CLAIMANT,
            counterparty_address=_COUNTERPARTY,
            title="Adjudication trigger test escrow",
            total=Decimal("10.00"),
            status_key=StatusKey.DISPUTED,
        )
        db.add(escrow)
        await db.flush()
        dispute = Dispute(
            escrow_id=escrow.id,
            opened_by_address=_CLAIMANT,
            issue="Some claim.",
            status_key=status_key,
            on_chain_dispute_id=on_chain_dispute_id,
            adjudication_tx_hash=adjudication_tx_hash,
        )
        db.add(dispute)
        await db.commit()
        await db.refresh(dispute)
        return dispute.id


async def _get_dispute(dispute_id: int) -> Dispute:
    async with AsyncSessionLocal() as db:
        return await db.get(Dispute, dispute_id)


def test_triggers_adjudication_for_a_resolved_open_dispute(monkeypatch):
    dispute_id = asyncio.run(_create_dispute(on_chain_dispute_id=3, status_key=StatusKey.DISPUTED))

    captured = {}

    async def _fake_write_contract(address, function_name, args):
        captured["address"] = address
        captured["function_name"] = function_name
        captured["args"] = args
        return _FAKE_TX_HASH

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fake_write_contract)

    async def _run():
        async with AsyncSessionLocal() as db:
            dispute = await db.get(Dispute, dispute_id)
            await indexer.trigger_pending_adjudications([dispute])
            await db.commit()

    asyncio.run(_run())

    assert captured["address"] == _DISPUTE_COURT
    assert captured["function_name"] == "adjudicate_dispute"
    assert captured["args"] == [3]

    dispute = asyncio.run(_get_dispute(dispute_id))
    assert dispute.adjudication_tx_hash == _FAKE_TX_HASH


def test_does_not_resend_an_already_triggered_dispute(monkeypatch):
    dispute_id = asyncio.run(
        _create_dispute(
            on_chain_dispute_id=4, status_key=StatusKey.DISPUTED, adjudication_tx_hash="0x" + "bb" * 32
        )
    )

    def _fail_if_called(address, function_name, args):
        raise AssertionError("write_contract should never be called for an already-triggered dispute")

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fail_if_called)

    async def _run():
        dispute = await _get_dispute(dispute_id)
        await indexer.trigger_pending_adjudications([dispute])

    asyncio.run(_run())  # must not raise


def test_skips_a_dispute_already_resolved_off_chain(monkeypatch):
    dispute_id = asyncio.run(_create_dispute(on_chain_dispute_id=5, status_key=StatusKey.APPROVED))

    def _fail_if_called(address, function_name, args):
        raise AssertionError("write_contract should never be called for an already-resolved dispute")

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fail_if_called)

    async def _run():
        dispute = await _get_dispute(dispute_id)
        await indexer.trigger_pending_adjudications([dispute])

    asyncio.run(_run())  # must not raise


def test_failed_send_leaves_it_retryable(monkeypatch):
    dispute_id = asyncio.run(_create_dispute(on_chain_dispute_id=6, status_key=StatusKey.DISPUTED))

    async def _fake_failed_write(address, function_name, args):
        return None  # simulates a real send failure

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fake_failed_write)

    async def _run() -> Dispute:
        dispute = await _get_dispute(dispute_id)
        await indexer.trigger_pending_adjudications([dispute])
        return dispute

    dispute = asyncio.run(_run())
    # Checked on the in-memory object directly, not a DB reload —
    # trigger_pending_adjudications never commits itself (same as
    # resolve_pending_dispute_ids, by design: the caller's session/commit
    # owns that), so a reload here would trivially read back "null"
    # regardless of whether the function behaved correctly.
    assert dispute.adjudication_tx_hash is None


def test_skipped_entirely_when_no_dispute_court_address(monkeypatch):
    monkeypatch.setattr(indexer.settings, "dispute_court_contract_address", None)
    dispute_id = asyncio.run(_create_dispute(on_chain_dispute_id=7, status_key=StatusKey.DISPUTED))

    def _fail_if_called(address, function_name, args):
        raise AssertionError("write_contract should never be called with no configured address")

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fail_if_called)

    async def _run():
        dispute = await _get_dispute(dispute_id)
        await indexer.trigger_pending_adjudications([dispute])

    asyncio.run(_run())  # must not raise
