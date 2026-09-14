"""Tests for services/genlayer_indexer.py's resolve_pending_proposal_ids —
the async match-by-(title, category, description) resolution that fills
in Proposal.on_chain_proposal_id after create_proposal_on_chain creates a
proposal with only a tx hash to go on (genlayer-js can't hand back
create_proposal's actual return value the way scripts/deploy.ts reads a
deployed address — see governance_proposal_id_scan_window's own comment).

FOUND 2026-09-14, live on the first real production deploy: the matching
used to also require onchain.proposer == proposal.proposer_address — but
create_proposal_on_chain is unconditionally backend-signed (no per-user
wallet ever calls it), so the real on-chain `proposer` is always this
deployment's own GENLAYER_PRIVATE_KEY-derived address, never the real end
user who authored the proposal through the API. That comparison could
only ever pass by coincidence (every local dev/test proposal that night
happened to reuse the same wallet as the deployer key) — 5 real production
proposals, confirmed live on-chain via a direct get_proposal read, never
resolved their on_chain_proposal_id because of it. This suite locks in the
fix: matching now uses (title, category, description) — real data
create_proposal_on_chain actually passed — and proposer is asserted to be
irrelevant to a match by using a local proposer address that's the same
address across every test row below while different on-chain proposals'
"proposer" fields are all left as the (irrelevant) backend address.

Mocks app.services.genlayer_rpc.read_and_check entirely (no subprocess, no
real network) and covers:
  1. Regression: the real production shape — every on-chain proposer is
     the backend's own address, never proposal.proposer_address — still
     resolves correctly.
  2. Happy path: a FINALIZED tx and a scan window containing a real match
     at some index other than the last one.
  3. No match found in the scan window — chain_status still advances,
     but on_chain_proposal_id stays null; next cycle tries again.
  4. Two local proposals whose (title, category, description) collide —
     only one claims the matching on-chain id; the other stays
     unresolved rather than both claiming it.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-proposal-id-resolution-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_indexer as indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ChainStatus, ProposalStatus  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Proposal  # noqa: E402

_GOVERNANCE_CONTRACT = "0x37303291cA1438F05b2236b7Dd9667aEeFA8f310"
# The deployment's own backend-signed wallet — matches what production
# actually saw: every real on-chain proposal's "proposer" is this address,
# regardless of who authored the proposal through the API.
_BACKEND_SIGNER = "0xCAFc5f0a599475C61f700fF02A11B5647c188fcd"
# A real end user's wallet — deliberately NEVER equal to _BACKEND_SIGNER,
# the exact production shape that broke the old proposer-matching field.
_REAL_USER = "0x9999999999999999999999999999999999999999"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture(autouse=True)
def _set_governance_address(monkeypatch):
    monkeypatch.setattr(indexer.settings, "governance_contract_address", _GOVERNANCE_CONTRACT)
    monkeypatch.setattr(indexer.settings, "governance_proposal_id_scan_window", 50)


async def _create_unresolved_proposal(title: str, category: str, description: str, tx_hash: str) -> int:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        proposal = Proposal(
            title=title,
            description=description,
            category=category,
            proposer_address=_REAL_USER,
            status=ProposalStatus.ACTIVE,
            start_time=now,
            end_time=now + timedelta(days=5),
            quorum_threshold=20,
            pass_threshold=50,
            quorum_threshold_gen=Decimal("1"),
            deploy_attempted_at=now,
            on_chain_tx_hash=tx_hash,
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)
        return proposal.id


async def _get_proposal(proposal_id: int) -> Proposal:
    async with AsyncSessionLocal() as db:
        return await db.get(Proposal, proposal_id)


def _make_fake_rpc(tx_bucket_by_hash: dict[str, str], onchain_proposals: dict[int, dict], count: int):
    """Same dispatch-on-shape stand-in test_dispute_id_resolution.py's own
    copy uses for genlayer_rpc.read_and_check — kept as its own copy here
    for the identical reason that file's fixtures aren't shared with this
    one (different entities, independently evolvable test data)."""

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
                if i in onchain_proposals:
                    out[r["id"]] = {"ok": True, "result": onchain_proposals[i]}
                else:
                    out[r["id"]] = {"ok": False, "error": "No such proposal."}
            return out, {}
        return {}, {}

    return _fake


def test_regression_real_user_proposer_never_matches_backend_signer(monkeypatch):
    """The actual production bug: proposal.proposer_address (_REAL_USER)
    never equals the on-chain proposer (_BACKEND_SIGNER) for ANY real
    proposal — this must resolve anyway."""
    tx_hash = "0x" + "44" * 32
    proposal_id = asyncio.run(
        _create_unresolved_proposal(
            "Fund a GenLayer community grants program",
            "Treasury",
            "Allocate treasury GEN toward a recurring community grants program.",
            tx_hash,
        )
    )

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_hash: "finalized"},
        onchain_proposals={
            23: {
                "proposer": _BACKEND_SIGNER,  # never _REAL_USER — the real shape
                "title": "Fund a GenLayer community grants program",
                "category": "Treasury",
                "description": "Allocate treasury GEN toward a recurring community grants program.",
            },
        },
        count=24,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_uncreated_proposal_ids(db)
            unresolved = [p for p in unresolved if p.id == proposal_id]
            assert len(unresolved) == 1
            await indexer.resolve_pending_proposal_ids(db, unresolved)
            await db.commit()

    asyncio.run(_run())

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_proposal_id == 23
    assert proposal.chain_status == ChainStatus.FINALIZED


def test_resolves_id_from_matching_scan_entry(monkeypatch):
    tx_hash = "0x" + "11" * 32
    proposal_id = asyncio.run(
        _create_unresolved_proposal(
            "Expand the GenVM validator set",
            "Protocol",
            "Raise the default validator count.",
            tx_hash,
        )
    )

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_hash: "finalized"},
        onchain_proposals={
            2: {"proposer": _BACKEND_SIGNER, "title": "unrelated", "category": "Protocol", "description": "x"},
            1: {
                "proposer": _BACKEND_SIGNER,
                "title": "Expand the GenVM validator set",
                "category": "Protocol",
                "description": "Raise the default validator count.",
            },
            0: {"proposer": _BACKEND_SIGNER, "title": "also unrelated", "category": "Protocol", "description": "y"},
        },
        count=3,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_uncreated_proposal_ids(db)
            unresolved = [p for p in unresolved if p.id == proposal_id]
            await indexer.resolve_pending_proposal_ids(db, unresolved)
            await db.commit()

    asyncio.run(_run())

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_proposal_id == 1
    assert proposal.chain_status == ChainStatus.FINALIZED


def test_no_match_leaves_id_null_but_advances_chain_status(monkeypatch):
    tx_hash = "0x" + "22" * 32
    proposal_id = asyncio.run(
        _create_unresolved_proposal("Never actually filed on-chain", "Test", "desc", tx_hash)
    )

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_hash: "decided"},
        onchain_proposals={0: {"proposer": _BACKEND_SIGNER, "title": "nope", "category": "Test", "description": "z"}},
        count=1,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_uncreated_proposal_ids(db)
            unresolved = [p for p in unresolved if p.id == proposal_id]
            await indexer.resolve_pending_proposal_ids(db, unresolved)
            await db.commit()

    asyncio.run(_run())

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_proposal_id is None
    assert proposal.chain_status == ChainStatus.DECIDED


def test_colliding_title_category_description_claims_only_one_id(monkeypatch):
    tx_a = "0x" + "55" * 32
    tx_b = "0x" + "66" * 32
    proposal_id_a = asyncio.run(
        _create_unresolved_proposal("Duplicate idea", "Grants", "Same text both times.", tx_a)
    )
    proposal_id_b = asyncio.run(
        _create_unresolved_proposal("Duplicate idea", "Grants", "Same text both times.", tx_b)
    )

    fake = _make_fake_rpc(
        tx_bucket_by_hash={tx_a: "finalized", tx_b: "finalized"},
        onchain_proposals={
            0: {
                "proposer": _BACKEND_SIGNER,
                "title": "Duplicate idea",
                "category": "Grants",
                "description": "Same text both times.",
            },
        },
        count=1,
    )
    monkeypatch.setattr(indexer.genlayer_rpc, "read_and_check", fake)

    async def _run():
        async with AsyncSessionLocal() as db:
            unresolved = await indexer._load_uncreated_proposal_ids(db)
            unresolved = [p for p in unresolved if p.id in (proposal_id_a, proposal_id_b)]
            assert len(unresolved) == 2
            await indexer.resolve_pending_proposal_ids(db, unresolved)
            await db.commit()

    asyncio.run(_run())

    proposal_a = asyncio.run(_get_proposal(proposal_id_a))
    proposal_b = asyncio.run(_get_proposal(proposal_id_b))
    resolved = [p.on_chain_proposal_id for p in (proposal_a, proposal_b)]
    assert sorted(x for x in resolved if x is not None) == [0]
    assert resolved.count(None) == 1
