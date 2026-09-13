"""Tests for services/genlayer_indexer.py's governance-specific sync
functions — create_proposal_on_chain, retry_uncreated_proposals,
_apply_proposal_view, _apply_governance_balance, and _build_read_batch's
per-proposal + shared-registry-balance reads.

Asked directly: "any user that vote and unvote you will have to use Gen
token ... like a real Governance." Mocks app.services.genlayer_write.
write_contract entirely (no subprocess, no real network, no real testnet
GEN spent).

Covers:
  1. create_proposal_on_chain sends the real create_proposal call with the
     proposal's own fields, in order, and records the tx hash.
  2. create_proposal_on_chain is a no-op if GOVERNANCE_CONTRACT_ADDRESS
     isn't configured — stays off-chain, same as every other auto-deploy
     gate in this app when its address isn't set.
  3. create_proposal_on_chain never re-sends once on_chain_tx_hash is set
     (idempotency).
  4. retry_uncreated_proposals: a stale failed attempt (deploy_attempted_at
     set, past cooldown, no tx hash yet) gets retried; a recent attempt
     (within cooldown) is left alone; a proposal that never attempted at
     all (deploy_attempted_at null — a legacy, pre-2026-09-13 row) is
     LEFT ALONE FOREVER, confirmed directly per that function's own
     docstring on why this differs from escrows'/predictions' own retry
     sweeps (which also catch "never attempted").
  5. _apply_proposal_view syncs status (active/passed/rejected) and the
     three Decimal wei-sum tallies from a real get_proposal() read.
  6. _apply_governance_balance writes the shared registry's real native
     balance into AppState, not a per-row column.
  7. _build_read_batch includes one get_proposal read per linked
     proposal, and exactly one shared "balance:governance" read overall
     (not one per proposal) once any proposal is linked.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-governance-chain-sync-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_indexer as genlayer_indexer  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ProposalStatus  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AppState, Proposal  # noqa: E402

_CONTRACT_ADDRESS = "0xF00Dbabe0000000000000000000000000000CCCC"
_FAKE_TX_HASH = "0x" + "77" * 32


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


async def _create_proposal(
    *,
    deploy_attempted_at: datetime | None = None,
    on_chain_tx_hash: str | None = None,
    on_chain_proposal_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        proposal = Proposal(
            title="Governance chain-sync test proposal",
            description="Test description.",
            category="Test",
            proposer_address="0x" + "1" * 40,
            status=ProposalStatus.ACTIVE,
            start_time=now,
            end_time=now + timedelta(days=5),
            quorum_threshold=20,
            pass_threshold=50,
            deploy_attempted_at=deploy_attempted_at,
            on_chain_tx_hash=on_chain_tx_hash,
            on_chain_proposal_id=on_chain_proposal_id,
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)
        return proposal.id


async def _get_proposal(proposal_id: int) -> Proposal:
    async with AsyncSessionLocal() as db:
        proposal = await db.get(Proposal, proposal_id)
        assert proposal is not None
        return proposal


def _set_governance_address(monkeypatch, address: str | None) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "governance_contract_address", address)


# --- 1/2/3. create_proposal_on_chain ----------------------------------------


def test_create_proposal_on_chain_sends_the_real_call(monkeypatch):
    _set_governance_address(monkeypatch, _CONTRACT_ADDRESS)
    proposal_id = asyncio.run(_create_proposal())

    captured: dict = {}

    async def _fake_write_contract(address, function_name, args):
        captured["address"] = address
        captured["function_name"] = function_name
        captured["args"] = args
        return _FAKE_TX_HASH

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fake_write_contract)

    asyncio.run(genlayer_indexer.create_proposal_on_chain(proposal_id))

    assert captured["address"] == _CONTRACT_ADDRESS
    assert captured["function_name"] == "create_proposal"
    assert captured["args"][0] == "Governance chain-sync test proposal"
    # FIXED 2026-09-13 — a real bug found live: this call used to pass
    # the off-chain PERCENTAGE quorum_threshold (20, meaning "20%")
    # straight through as the contract's own quorum_threshold argument,
    # which treats it as an ABSOLUTE WEI TURNOUT — "20" became a real
    # on-chain quorum of 20 wei, trivially met by any single vote. This
    # proposal has no quorum_threshold_gen set, so the defensive fallback
    # (_DEFAULT_ON_CHAIN_QUORUM_GEN = 1 GEN) applies — see the dedicated
    # test below for the case where a real value IS set.
    assert captured["args"][4] == 1_000_000_000_000_000_000  # 1 GEN, in wei
    assert captured["args"][5] == 50  # pass_threshold

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_tx_hash == _FAKE_TX_HASH
    assert proposal.deploy_attempted_at is not None
    assert proposal.quorum_threshold_gen == Decimal("1"), (
        "the fallback default must be persisted, not just used for this one call"
    )


def test_create_proposal_on_chain_uses_the_real_gen_quorum_when_set(monkeypatch):
    """The actual fix, not just its fallback: a proposal with a real
    quorum_threshold_gen set (e.g. by routers/governance.py::
    create_proposal, which always sets one before queuing on-chain
    creation) must have THAT value sent, converted to wei — not the
    unrelated percentage field, and not silently overwritten by the
    fallback default either."""
    _set_governance_address(monkeypatch, _CONTRACT_ADDRESS)

    async def _seed() -> int:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            proposal = Proposal(
                title="Real GEN quorum test proposal",
                description="Test description.",
                category="Test",
                proposer_address="0x" + "1" * 40,
                status=ProposalStatus.ACTIVE,
                start_time=now,
                end_time=now + timedelta(days=5),
                quorum_threshold=20,
                quorum_threshold_gen=Decimal("2.5"),
                pass_threshold=50,
            )
            db.add(proposal)
            await db.commit()
            await db.refresh(proposal)
            return proposal.id

    proposal_id = asyncio.run(_seed())

    captured: dict = {}

    async def _fake_write_contract(address, function_name, args):
        captured["args"] = args
        return _FAKE_TX_HASH

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fake_write_contract)

    asyncio.run(genlayer_indexer.create_proposal_on_chain(proposal_id))

    assert captured["args"][4] == 2_500_000_000_000_000_000  # 2.5 GEN, in wei

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.quorum_threshold_gen == Decimal("2.5"), "must not be overwritten by the fallback"


def test_create_proposal_on_chain_noop_without_configured_address(monkeypatch):
    _set_governance_address(monkeypatch, None)
    proposal_id = asyncio.run(_create_proposal())

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("write_contract should never be called with no configured address")

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(genlayer_indexer.create_proposal_on_chain(proposal_id))  # must not raise

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_tx_hash is None


def test_create_proposal_on_chain_never_resends(monkeypatch):
    _set_governance_address(monkeypatch, _CONTRACT_ADDRESS)
    proposal_id = asyncio.run(_create_proposal(on_chain_tx_hash=_FAKE_TX_HASH))

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("write_contract should not be called again once already sent")

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(genlayer_indexer.create_proposal_on_chain(proposal_id))  # must not raise


# --- 4. retry_uncreated_proposals --------------------------------------------


def test_retries_a_stale_failed_attempt(monkeypatch):
    _set_governance_address(monkeypatch, _CONTRACT_ADDRESS)
    stale = datetime.now(timezone.utc) - genlayer_indexer._PROPOSAL_CREATE_RETRY_COOLDOWN - timedelta(minutes=1)
    proposal_id = asyncio.run(_create_proposal(deploy_attempted_at=stale))

    async def _fake_write_contract(address, function_name, args):
        return _FAKE_TX_HASH

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fake_write_contract)

    asyncio.run(genlayer_indexer.retry_uncreated_proposals())

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_tx_hash == _FAKE_TX_HASH


def test_skips_a_recent_attempt_in_cooldown(monkeypatch):
    _set_governance_address(monkeypatch, _CONTRACT_ADDRESS)
    recent = datetime.now(timezone.utc) - timedelta(minutes=1)
    proposal_id = asyncio.run(_create_proposal(deploy_attempted_at=recent))

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("write_contract should not be called for an attempt still in cooldown")

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(genlayer_indexer.retry_uncreated_proposals())  # must not raise

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_tx_hash is None


def test_never_attempted_legacy_proposal_is_left_alone_forever(monkeypatch):
    """The real scoping decision this function's own docstring makes,
    confirmed directly: unlike retry_undeployed_escrows/retry_undeployed_
    predictions (which also catch "never attempted" rows predating their
    own feature), a proposal that never had deploy_attempted_at set at
    all must NEVER be picked up here — every proposal created before this
    2026-09-13 update stays off-chain on purpose."""
    _set_governance_address(monkeypatch, _CONTRACT_ADDRESS)
    proposal_id = asyncio.run(_create_proposal(deploy_attempted_at=None))

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("write_contract should never be called for a legacy, never-attempted proposal")

    monkeypatch.setattr(genlayer_indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(genlayer_indexer.retry_uncreated_proposals())  # must not raise

    proposal = asyncio.run(_get_proposal(proposal_id))
    assert proposal.on_chain_tx_hash is None
    assert proposal.deploy_attempted_at is None


# --- 5. _apply_proposal_view -------------------------------------------------


def test_apply_proposal_view_syncs_status_and_tallies():
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=0))

    async def _run():
        proposal = await _get_proposal(proposal_id)
        await genlayer_indexer._apply_proposal_view(
            proposal,
            {
                "ok": True,
                "result": {
                    "status": "passed",
                    "total_for": "3000000000000000000",
                    "total_against": "1000000000000000000",
                    "total_abstain": "0",
                },
            },
        )
        async with AsyncSessionLocal() as db:
            db.add(proposal)
            await db.commit()

        refetched = await _get_proposal(proposal_id)
        assert refetched.status == ProposalStatus.PASSED
        assert refetched.total_for == Decimal("3")
        assert refetched.total_against == Decimal("1")

    asyncio.run(_run())


def test_apply_proposal_view_self_heals_a_locally_wrong_status():
    """FIXED 2026-09-13 — a real bug found live, not hypothesized: this
    used to only ever move status FORWARD (active -> passed/rejected),
    with "active needs no change either way" as an explicit no-op. An
    unrelated incident (a stray test run mutating a live DB row directly
    with fabricated data) left a local Proposal at status=REJECTED while
    the real, actual contract had always said "active" — and the old
    version of this function had no way to ever notice or correct that,
    since local "active" was never touched, and only "passed"/"rejected"
    triggered a write. Confirms the fix: a local row that has drifted
    from the contract's own truth is corrected back to whatever the
    contract actually says, in EITHER direction — safe because the
    contract's own status transition is one-way, so a real "passed"/
    "rejected" read is never followed by a real "active" one; this can
    only ever fix drift, never un-finalize a genuinely decided proposal.
    """
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=0))

    async def _run():
        # Simulate the exact corruption found live: local status says
        # REJECTED (with some stray tally), but nothing on the real
        # contract ever actually decided that.
        async with AsyncSessionLocal() as db:
            proposal = await db.get(Proposal, proposal_id)
            proposal.status = ProposalStatus.REJECTED
            proposal.total_against = Decimal("0.000000000000000001")
            await db.commit()

        proposal = await _get_proposal(proposal_id)
        await genlayer_indexer._apply_proposal_view(
            proposal,
            {
                "ok": True,
                "result": {
                    "status": "active",
                    "total_for": "0",
                    "total_against": "0",
                    "total_abstain": "0",
                },
            },
        )
        async with AsyncSessionLocal() as db:
            db.add(proposal)
            await db.commit()

        refetched = await _get_proposal(proposal_id)
        assert refetched.status == ProposalStatus.ACTIVE
        assert refetched.total_against == Decimal("0")

    asyncio.run(_run())


# --- 6. _apply_governance_balance --------------------------------------------


def test_apply_governance_balance_writes_app_state():
    async def _run():
        async with AsyncSessionLocal() as db:
            existing = await db.get(AppState, genlayer_indexer._GOVERNANCE_BALANCE_STATE_KEY)
            assert existing is None

            await genlayer_indexer._apply_governance_balance(
                db, {"ok": True, "result": "5000000000000000000"}
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            state = await db.get(AppState, genlayer_indexer._GOVERNANCE_BALANCE_STATE_KEY)
            assert state is not None
            assert Decimal(state.value) == Decimal("5")

    asyncio.run(_run())


# --- 7. _build_read_batch ----------------------------------------------------


def test_build_read_batch_includes_proposal_and_one_shared_balance_read():
    proposal_id_a = asyncio.run(_create_proposal(on_chain_proposal_id=0))
    proposal_id_b = asyncio.run(_create_proposal(on_chain_proposal_id=1))
    proposal_a = asyncio.run(_get_proposal(proposal_id_a))
    proposal_b = asyncio.run(_get_proposal(proposal_id_b))

    from app.config import get_settings

    get_settings().governance_contract_address = _CONTRACT_ADDRESS
    try:
        reads = genlayer_indexer._build_read_batch([], [], [], [proposal_a, proposal_b])
    finally:
        get_settings().governance_contract_address = None

    proposal_reads = [r for r in reads if r["id"].startswith("proposal:")]
    assert len(proposal_reads) == 2
    assert all(r["functionName"] == "get_proposal" for r in proposal_reads)

    balance_reads = [r for r in reads if r["id"] == "balance:governance"]
    assert len(balance_reads) == 1, "one shared balance read for the whole registry, not per-proposal"
    assert balance_reads[0]["address"] == _CONTRACT_ADDRESS
