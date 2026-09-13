"""Tests for the on-chain governance endpoints in routers/governance.py:
  - POST /proposals/{id}/vote/on-chain (cast_vote_on_chain)
  - POST /proposals/{id}/retract-vote/on-chain (retract_vote_on_chain)
  - the off-chain guard added to POST /proposals/{id}/vote and
    POST /proposals/{id}/finalize

Asked directly: "any user that vote and unvote you will have to use Gen
token ... like a real Governance." Mirrors test_prediction_on_chain_
endpoints.py's own shape and reasoning throughout.

Covers:
  1. cast_vote_on_chain happy path: mirrors the stake into a Vote row,
     bumps the proposal's Decimal tally, and reports it back via
     user_vote/user_vote_stake_amount.
  2. cast_vote_on_chain rejects a proposal with no on_chain_proposal_id
     (400) — nothing to vote on there yet.
  3. cast_vote_on_chain rejects a second active vote from the same wallet
     (400) — matches contracts/nuance_governance.py::cast_vote's own
     "retract first" rule.
  4. retract_vote_on_chain happy path: backs the stake out of the
     proposal's tally, marks the Vote retracted, and a subsequent
     cast_vote_on_chain call from the same wallet succeeds again (reuses
     the row rather than being permanently blocked).
  5. retract_vote_on_chain rejects a wallet with no active vote (400).
  6. The off-chain POST /proposals/{id}/vote 503s once deploy_attempted_at
     is set — whether or not on_chain_proposal_id has resolved yet (the
     race window this whole guard exists to close, see routers/
     governance.py::cast_vote's own docstring).
  7. The off-chain POST /proposals/{id}/finalize 400s for an on-chain-
     linked proposal instead of silently no-op'ing.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-governance-onchain-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ProposalStatus  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Proposal  # noqa: E402

_FAKE_TX_HASH = "0x" + "dd" * 32
_CONTRACT_ADDRESS = "0xF00Dbabe0000000000000000000000000000BBBB"


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


async def _create_proposal(
    *,
    on_chain_proposal_id: int | None,
    deploy_attempted_at: datetime | None = None,
    end_delta_days: int = 5,
    proposer: str | None = None,
    quorum_threshold_gen: Decimal | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        proposal = Proposal(
            title="On-chain governance test proposal",
            description="Test description.",
            category="Test",
            proposer_address=proposer or ("0x" + "1" * 40),
            status=ProposalStatus.ACTIVE,
            start_time=now,
            end_time=now + timedelta(days=end_delta_days),
            quorum_threshold=20,
            quorum_threshold_gen=quorum_threshold_gen,
            pass_threshold=50,
            on_chain_proposal_id=on_chain_proposal_id,
            deploy_attempted_at=deploy_attempted_at,
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)
        return proposal.id


def _set_governance_address(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "governance_contract_address", _CONTRACT_ADDRESS)


# --- 1/2/3. cast_vote_on_chain ------------------------------------------


def test_cast_vote_on_chain_happy_path(client: TestClient, monkeypatch):
    _set_governance_address(monkeypatch)
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=0))

    resp = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "choice": "for", "stake_amount": "2.5"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_vote"] == "for"
    assert Decimal(body["user_vote_stake_amount"]) == Decimal("2.5")
    assert Decimal(body["total_for"]) == Decimal("2.5")
    assert Decimal(body["total_against"]) == 0


def test_cast_vote_on_chain_rejects_unlinked_proposal(client: TestClient, monkeypatch):
    _set_governance_address(monkeypatch)
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(
        _create_proposal(on_chain_proposal_id=None, deploy_attempted_at=datetime.now(timezone.utc))
    )

    resp = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "choice": "for", "stake_amount": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "on-chain governance registry" in resp.json()["detail"]


def test_cast_vote_on_chain_rejects_second_active_vote(client: TestClient, monkeypatch):
    _set_governance_address(monkeypatch)
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=0))
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "choice": "for", "stake_amount": "1"},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": "0x" + "cc" * 32, "choice": "against", "stake_amount": "1"},
        headers=headers,
    )
    assert second.status_code == 400
    assert "retract" in second.json()["detail"].lower()


# --- 4/5. retract_vote_on_chain ------------------------------------------


def test_retract_vote_on_chain_happy_path_and_allows_revote(client: TestClient, monkeypatch):
    _set_governance_address(monkeypatch)
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=0))
    headers = {"Authorization": f"Bearer {token}"}

    voted = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "choice": "for", "stake_amount": "3"},
        headers=headers,
    )
    assert voted.status_code == 201, voted.text
    assert Decimal(voted.json()["total_for"]) == Decimal("3")

    retracted = client.post(
        f"/proposals/{proposal_id}/retract-vote/on-chain",
        json={"tx_hash": "0x" + "bb" * 32},
        headers=headers,
    )
    assert retracted.status_code == 200, retracted.text
    body = retracted.json()
    assert body["user_vote"] is None
    assert Decimal(body["total_for"]) == 0, "the retracted stake must leave the tally"

    # Same wallet can vote again — proves the row is reused, not
    # permanently blocked (see retract_vote_on_chain's own docstring).
    revoted = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": "0x" + "aa" * 32, "choice": "against", "stake_amount": "1"},
        headers=headers,
    )
    assert revoted.status_code == 201, revoted.text
    assert revoted.json()["user_vote"] == "against"
    assert Decimal(revoted.json()["total_against"]) == Decimal("1")


def test_retract_vote_on_chain_rejects_no_active_vote(client: TestClient, monkeypatch):
    _set_governance_address(monkeypatch)
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=0))

    resp = client.post(
        f"/proposals/{proposal_id}/retract-vote/on-chain",
        json={"tx_hash": _FAKE_TX_HASH},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "no active vote" in resp.json()["detail"].lower()


# --- 6. Off-chain vote guard ----------------------------------------------


def test_off_chain_vote_rejects_queued_proposal(client: TestClient):
    """The exact race this guard exists to close (see routers/
    governance.py::cast_vote's own docstring, and routers/predictions.py::
    place_bet's identical 2026-09-13 fix note): deploy_attempted_at set
    but on_chain_proposal_id not resolved yet must still be refused, not
    just a fully-linked proposal."""
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(
        _create_proposal(on_chain_proposal_id=None, deploy_attempted_at=datetime.now(timezone.utc))
    )

    resp = client.post(
        f"/proposals/{proposal_id}/vote",
        json={"choice": "for"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert "vote/on-chain" in resp.json()["detail"]


def test_off_chain_vote_rejects_fully_linked_proposal(client: TestClient):
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(
        _create_proposal(on_chain_proposal_id=0, deploy_attempted_at=datetime.now(timezone.utc))
    )

    resp = client.post(
        f"/proposals/{proposal_id}/vote",
        json={"choice": "for"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503


def test_off_chain_vote_allows_legacy_proposal(client: TestClient):
    """A proposal with deploy_attempted_at never set (every proposal
    created before this update, by design) is completely unaffected."""
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(_create_proposal(on_chain_proposal_id=None, deploy_attempted_at=None))

    resp = client.post(
        f"/proposals/{proposal_id}/vote",
        json={"choice": "for"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


# --- 7. Off-chain finalize guard -------------------------------------------


def test_finalize_rejects_on_chain_linked_proposal(client: TestClient):
    proposal_id = asyncio.run(
        _create_proposal(on_chain_proposal_id=0, end_delta_days=-1, deploy_attempted_at=datetime.now(timezone.utc))
    )

    resp = client.post(f"/proposals/{proposal_id}/finalize")
    assert resp.status_code == 400
    assert "automatically on-chain" in resp.json()["detail"]


# --- 8. quorum_met/turnout_pct use real GEN for an on-chain proposal ------


def test_on_chain_proposal_quorum_uses_gen_not_eligible_voters(client: TestClient, monkeypatch):
    """FIXED 2026-09-13 — a real bug found live: services/genlayer_
    indexer.py::create_proposal_on_chain used to send the off-chain
    PERCENTAGE quorum_threshold straight through as the contract's own
    (wei-denominated) quorum_threshold argument — silently defeating
    quorum for every on-chain proposal. This confirms the DISPLAY side of
    the fix too: an on-chain proposal's quorum_met/turnout_pct must
    compare real GEN turnout against quorum_threshold_gen, never against
    eligible_voters (a concept — "every wallet that's ever signed in" —
    that has no on-chain equivalent at all)."""
    _set_governance_address(monkeypatch)
    wallet = Account.create()
    token = _get_token(client, wallet)
    proposal_id = asyncio.run(
        _create_proposal(on_chain_proposal_id=0, quorum_threshold_gen=Decimal("2"))
    )

    # Stake exactly half the 2 GEN quorum — quorum must NOT read as met,
    # regardless of how many (or few) wallets have ever signed in.
    resp = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "choice": "for", "stake_amount": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert Decimal(body["quorum_threshold_gen"]) == Decimal("2")
    assert body["quorum_met"] is False
    assert body["turnout_pct"] == 50.0  # 1 of 2 GEN quorum — not a % of any wallet count

    # Top up to exactly the 2 GEN quorum via a second wallet's vote —
    # now it must read as met.
    other_token = _get_token(client, Account.create())
    resp2 = client.post(
        f"/proposals/{proposal_id}/vote/on-chain",
        json={"tx_hash": "0x" + "ab" * 32, "choice": "against", "stake_amount": "1"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp2.status_code == 201, resp2.text
    body2 = resp2.json()
    assert body2["quorum_met"] is True
    assert body2["turnout_pct"] == 100.0
