"""Tests for services/genlayer_indexer.py's resolve_pending_dispute_ids —
the async match-by-(claimant, escrow_address, claim_statement) resolution
that fills in Dispute.on_chain_dispute_id after routers/escrows.py's
raise_dispute_on_chain creates a dispute with only a tx hash to go on
(genlayer-js can't hand back file_dispute's actual return value the way
scripts/deploy.ts reads a deployed address — see Settings.
dispute_id_scan_window's own comment).

Mocks app.services.genlayer_rpc.read_and_check entirely (no subprocess,
no real network) and covers:
  1. Happy path: a FINALIZED tx, get_dispute_count, and a scan window
     containing a real match at some index other than the last one —
     resolves on_chain_dispute_id and chain_status correctly.
  2. No match found in the scan window — chain_status still advances
     (e.g. to "decided"), but on_chain_dispute_id stays null; next cycle
     tries again.
  3. A CANCELED tx is logged and left permanently unresolved — never
     included in a get_dispute_count/scan call at all (nothing to match).
  4. Two local disputes whose claim text collides only one claims the
     matching on-chain id; the other stays unresolved rather than both
     claiming it.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-dispute-id-resolution-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.services.genlayer_indexer as indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ChainStatus, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Dispute, Escrow, User  # noqa: E402

_ESCROW_CONTRACT = "0xDB6939bD12775e5F77e48138F0DE103D804268f7"
_DISPUTE_COURT = "0xf7b4C186fF9d69701F41AA3Aa1aCF8cED0c9b057"
_CLAIMANT = "0x1111111111111111111111111111111111111111"
_COUNTERPARTY = "0x2222222222222222222222222222222222222222"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture(autouse=True)
def _set_dispute_court_address(monkeypatch):
    monkeypatch.setattr(indexer.settings, "dispute_court_contract_address", _DISPUTE_COURT)
    monkeypatch.setattr(indexer.settings, "dispute_id_scan_window", 50)


async def _create_unresolved_dispute(issue: str, tx_hash: str) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        for addr in (_CLAIMANT, _COUNTERPARTY):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=_CLAIMANT,
            counterparty_address=_COUNTERPARTY,
            title="Dispute-id-resolution test escrow",
            total=Decimal("10.00"),
            status_key=StatusKey.DISPUTED,
            contract_address=_ESCROW_CONTRACT,
        )
        db.add(escrow)
        await db.flush()
        dispute = Dispute(
            escrow_id=escrow.id,
            opened_by_address=_CLAIMANT,
            issue=issue,
            status_key=StatusKey.DISPUTED,
            on_chain_tx_hash=tx_hash,
            chain_status=ChainStatus.PROCESSING,
        )
        db.add(dispute)
        await db.commit()
        return escrow.id, dispute.id


def _finalized_tx_result(tx_hash: str) -> dict:
    return {tx_hash: {"ok": True, "bucket": "finalized", "rawStatusName": "FINALIZED", "success": True, "raw": {}}}


def _make_fake_rpc(tx_bucket_by_hash: dict[str, str], onchain_disputes: dict[int, dict], count: int):
    """A stand-in for genlayer_rpc.read_and_check that dispatches on the
    shape of what's being asked, same as the real subprocess bridge would
    answer for these exact calls."""

    async def _fake(reads, transaction_hashes):
        if transaction_hashes:
            out = {}
            for h in transaction_hashes:
                bucket = tx_bucket_by_hash.get(h, "processing")
                out[h] = {
                    "ok": True,
                    "bucket": bucket,
                    "rawStatusName": bucket.upper(),
                    "success": bucket == "finalized",
                    "raw": {},
                }
            return {}, out
        if reads and reads[0]["id"] == "count":
            return {"count": {"ok": True, "result": count}}, {}
        if reads and reads[0]["id"].startswith("scan:"):
            out = {}
            for r in reads:
                i = int(r["id"].split(":")[1])
                if i in onchain_disputes:
                    out[r["id"]] = {"ok": True, "result": onchain_disputes[i]}
                else:
                    out[r["id"]] = {"ok": False, "error": "No such dispute."}
            return out, {}
        return {}, {}

    return _fake


async def _get_dispute(dispute_id: int) -> Dispute:
    async with AsyncSessionLocal() as db:
        return await db.get(Dispute, dispute_id)


def test_resolves_id_from_matching_scan_entry(monkeypatch):
    tx_hash = "0x" + "11" * 32
    escrow_id, dispute_id = asyncio.run(
        _create_unresolved_dispute("The deliverable link was dead.", tx_hash)
    )

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_hash: "finalized"},
        onchain_disputes={
            2: {"claimant": "0xaaaa", "escrow_address": _ESCROW_CONTRACT, "claim_statement": "unrelated"},
            1: {
                "claimant": _CLAIMANT,
                "escrow_address": _ESCROW_CONTRACT,
                "claim_statement": "The deliverable link was dead.",
            },
            0: {"claimant": "0xbbbb", "escrow_address": _ESCROW_CONTRACT, "claim_statement": "also unrelated"},
        },
        count=3,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_unresolved_disputes(db)
            target = [d for d in unresolved if d.id == dispute_id]
            assert len(target) == 1
            await indexer.resolve_pending_dispute_ids(db, target)
            await db.commit()

    asyncio.run(_run())

    dispute = asyncio.run(_get_dispute(dispute_id))
    assert dispute.on_chain_dispute_id == 1
    assert dispute.chain_status == ChainStatus.FINALIZED


def test_no_match_leaves_id_null_but_advances_chain_status(monkeypatch):
    tx_hash = "0x" + "22" * 32
    _, dispute_id = asyncio.run(_create_unresolved_dispute("Never actually filed on-chain.", tx_hash))

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_hash: "decided"},
        onchain_disputes={0: {"claimant": "0xzzzz", "escrow_address": "0xyyyy", "claim_statement": "nope"}},
        count=1,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_unresolved_disputes(db)
            target = [d for d in unresolved if d.id == dispute_id]
            await indexer.resolve_pending_dispute_ids(db, target)
            await db.commit()

    asyncio.run(_run())

    dispute = asyncio.run(_get_dispute(dispute_id))
    assert dispute.on_chain_dispute_id is None
    assert dispute.chain_status == ChainStatus.DECIDED


def test_canceled_tx_never_scanned(monkeypatch):
    tx_hash = "0x" + "33" * 32
    _, dispute_id = asyncio.run(_create_unresolved_dispute("A dispute whose tx got canceled.", tx_hash))

    calls = {"count_or_scan": 0}

    async def _fake(reads, transaction_hashes):
        if transaction_hashes:
            return {}, {
                h: {"ok": True, "bucket": "canceled", "rawStatusName": "CANCELED", "success": False, "raw": {}}
                for h in transaction_hashes
            }
        calls["count_or_scan"] += 1
        return {}, {}

    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", _fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_unresolved_disputes(db)
            target = [d for d in unresolved if d.id == dispute_id]
            await indexer.resolve_pending_dispute_ids(db, target)
            await db.commit()

    asyncio.run(_run())

    dispute = asyncio.run(_get_dispute(dispute_id))
    assert dispute.on_chain_dispute_id is None
    assert dispute.chain_status == ChainStatus.CANCELED
    # A canceled tx will never appear in the contract's history — no
    # get_dispute_count/scan call should have been made for it at all.
    assert calls["count_or_scan"] == 0


def test_colliding_claim_text_only_one_dispute_claims_the_match(monkeypatch):
    tx_a = "0x" + "44" * 32
    tx_b = "0x" + "55" * 32
    same_text = "Identical wording, filed twice."
    _, dispute_a_id = asyncio.run(_create_unresolved_dispute(same_text, tx_a))
    _, dispute_b_id = asyncio.run(_create_unresolved_dispute(same_text, tx_b))

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_a: "finalized", tx_b: "finalized"},
        # Only ONE real on-chain dispute exists with this text/claimant/escrow.
        onchain_disputes={0: {"claimant": _CLAIMANT, "escrow_address": _ESCROW_CONTRACT, "claim_statement": same_text}},
        count=1,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_unresolved_disputes(db)
            target = [d for d in unresolved if d.id in (dispute_a_id, dispute_b_id)]
            await indexer.resolve_pending_dispute_ids(db, target)
            await db.commit()

    asyncio.run(_run())

    dispute_a = asyncio.run(_get_dispute(dispute_a_id))
    dispute_b = asyncio.run(_get_dispute(dispute_b_id))
    resolved = [d for d in (dispute_a, dispute_b) if d.on_chain_dispute_id is not None]
    unresolved_after = [d for d in (dispute_a, dispute_b) if d.on_chain_dispute_id is None]
    assert len(resolved) == 1
    assert len(unresolved_after) == 1
    assert resolved[0].on_chain_dispute_id == 0
