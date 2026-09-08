"""Tests for POST /disputes/{id}/evidence/on-chain — the ack endpoint
components/app/genlayer-write-client.ts's addEvidenceOnChain calls after
signing and sending a real NuanceDisputeCourt.add_evidence transaction.

Covers:
  1. Happy path: records a DisputeEvidence row, no ConsensusJob queued
     (unlike the off-chain POST /disputes/{id}/evidence).
  2. Rejects a malformed tx_hash (422, from the schema itself).
  3. Rejects a blank evidence_url (422).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-submit-evidence-onchain-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Dispute, Escrow, Milestone, User  # noqa: E402

_FAKE_TX_HASH = "0x" + "ab" * 32


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


async def _create_dispute(claimant: str, respondent: str) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (claimant, respondent):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=claimant,
            counterparty_address=respondent,
            title="Submit-evidence-on-chain test escrow",
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
        await db.flush()
        dispute = Dispute(
            escrow_id=escrow.id,
            opened_by_address=claimant,
            issue="Test claim for on-chain evidence.",
            status_key=StatusKey.DISPUTED,
        )
        db.add(dispute)
        await db.commit()
        await db.refresh(dispute)
        return dispute.id


async def _consensus_job_count_for_dispute(dispute_id: int) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count()).select_from(ConsensusJob).where(ConsensusJob.subject_id == dispute_id)
        )
        return result.scalar_one()


def test_submit_evidence_on_chain_happy_path(client: TestClient):
    claimant = Account.create()
    respondent = Account.create()
    token = _get_token(client, claimant)
    _get_token(client, respondent)
    dispute_id = asyncio.run(_create_dispute(claimant.address.lower(), respondent.address.lower()))

    resp = client.post(
        f"/disputes/{dispute_id}/evidence/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "evidence_url": "https://example.com/proof"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["dispute_id"] == dispute_id
    assert body["link"] == "https://example.com/proof"
    assert _FAKE_TX_HASH in body["description"]
    assert body["consensus_job_id"] is None

    # No ConsensusJob queued — GenVM's own committee is the jury once
    # adjudicate_dispute is called against the contract.
    job_count = asyncio.run(_consensus_job_count_for_dispute(dispute_id))
    assert job_count == 0


def test_submit_evidence_on_chain_rejects_malformed_hash(client: TestClient):
    claimant = Account.create()
    respondent = Account.create()
    token = _get_token(client, claimant)
    _get_token(client, respondent)
    dispute_id = asyncio.run(_create_dispute(claimant.address.lower(), respondent.address.lower()))

    resp = client.post(
        f"/disputes/{dispute_id}/evidence/on-chain",
        json={"tx_hash": "not-a-hash", "evidence_url": "https://example.com/proof"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_submit_evidence_on_chain_rejects_blank_url(client: TestClient):
    claimant = Account.create()
    respondent = Account.create()
    token = _get_token(client, claimant)
    _get_token(client, respondent)
    dispute_id = asyncio.run(_create_dispute(claimant.address.lower(), respondent.address.lower()))

    resp = client.post(
        f"/disputes/{dispute_id}/evidence/on-chain",
        json={"tx_hash": _FAKE_TX_HASH, "evidence_url": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
