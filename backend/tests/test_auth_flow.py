"""End-to-end verification of the Web3 auth flow + auth-guarded routes.

Covers exactly the four checks called for in the auth prompt:
  1. /auth/nonce persists a nonce and returns a signable message.
  2. A real eth_account signature verifies and issues a valid JWT.
  3. An invalid or reused signature is rejected with 401.
  4. Protected endpoints reject unauthenticated requests and accept a valid
     bearer token.

DATABASE_URL/JWT_SECRET are overridden *before* `app.main` (and therefore
app.db/app.config) is ever imported — config.get_settings() is
lru_cache'd, so it must see these env vars on its first call of the
process, not after.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DIR}/test.db"
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-only-32bytes+"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

import pytest  # noqa: E402
from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
from eth_account.signers.local import LocalAccount  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def wallet() -> LocalAccount:
    return Account.create()


def _sign(acct: LocalAccount, message: str) -> str:
    signed = acct.sign_message(encode_defunct(text=message))
    return signed.signature.hex()


def _get_token(client: TestClient, acct: LocalAccount) -> str:
    message = client.post("/auth/nonce", json={"wallet_address": acct.address}).json()["message"]
    signature = _sign(acct, message)
    resp = client.post(
        "/auth/verify",
        json={"wallet_address": acct.address, "message": message, "signature": signature},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# --- 1. Nonce generation --------------------------------------------------


def test_nonce_generates_and_persists(client, wallet):
    resp = client.post("/auth/nonce", json={"wallet_address": wallet.address})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nonce"]) == 32  # secrets.token_hex(16)
    assert body["nonce"] in body["message"]
    assert wallet.address.lower() in body["message"]

    # Persisted: a second call rotates it rather than erroring on an
    # existing User row.
    second = client.post("/auth/nonce", json={"wallet_address": wallet.address})
    assert second.status_code == 200
    assert second.json()["nonce"] != body["nonce"]


def test_nonce_accepts_lowercased_address(client, wallet):
    resp = client.post("/auth/nonce", json={"wallet_address": wallet.address.lower()})
    assert resp.status_code == 200


# --- 2. Real signature verifies + issues a valid JWT ----------------------


def test_verify_recovers_signer_and_issues_jwt(client, wallet):
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    signature = _sign(wallet, message)

    resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": signature},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["wallet_address"] == wallet.address.lower()

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["wallet_address"] == wallet.address.lower()


# --- 3. Invalid / reused signatures rejected with 401 ----------------------


def test_signature_from_wrong_key_is_rejected(client, wallet):
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    wrong_signer = Account.create()
    bad_signature = _sign(wrong_signer, message)

    resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": bad_signature},
    )
    assert resp.status_code == 401


def test_malformed_signature_is_rejected(client, wallet):
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": "0xnotasignature"},
    )
    assert resp.status_code == 401


def test_reused_signature_is_rejected(client, wallet):
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    signature = _sign(wallet, message)
    payload = {"wallet_address": wallet.address, "message": message, "signature": signature}

    first = client.post("/auth/verify", json=payload)
    assert first.status_code == 200

    replay = client.post("/auth/verify", json=payload)
    assert replay.status_code == 401


# --- 4. Protected endpoints reject/accept based on the bearer token -------


def test_protected_routes_reject_missing_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.post("/escrows", json={"title": "T", "counterparty_address": "0x1111111111111111111111111111111111111111", "total": "1.00"}).status_code == 401
    assert client.post("/disputes/1/messages", json={"content": "hello"}).status_code == 401
    assert client.post("/disputes/1/evidence", json={"description": "evidence"}).status_code == 401
    assert client.post("/disputes/1/enforce", json={"approved": True}).status_code == 401


def test_protected_routes_reject_garbage_token(client):
    headers = {"Authorization": "Bearer not-a-real-jwt"}
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_user_profile_and_settings_update(client, wallet):
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    # Verify initial me endpoint returns user with settings
    me_resp = client.get("/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me = me_resp.json()
    assert me["wallet_address"] == wallet.address.lower()
    assert me["settings"]["notify_on"] is True
    assert me["settings"]["auto_escalate_on"] is False

    # Update display name
    update_resp = client.patch("/auth/me", json={"display_name": "Test Validator"}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["display_name"] == "Test Validator"

    # Update settings
    settings_resp = client.patch(
        "/auth/settings", json={"notify_on": False, "auto_escalate_on": True}, headers=headers
    )
    assert settings_resp.status_code == 200
    assert settings_resp.json()["notify_on"] is False
    assert settings_resp.json()["auto_escalate_on"] is True


def test_protected_escrow_flow_accepts_valid_token(client, wallet):
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}
    counterparty = Account.create().address.lower()

    create = client.post(
        "/escrows",
        json={
            "title": "Landing page redesign",
            "counterparty_address": counterparty,
            "total": "500.00",
            "criteria": "Ships responsive, matches Figma.",
        },
        headers=headers,
    )
    assert create.status_code == 201
    escrow = create.json()
    assert escrow["creator_address"] == wallet.address.lower()
    assert escrow["counterparty_address"] == counterparty
    assert len(escrow["milestones"]) == 1
    escrow_id = escrow["id"]

    # Public read needs no auth at all.
    assert client.get(f"/escrows/{escrow_id}").status_code == 200

    deliver = client.post(
        f"/escrows/{escrow_id}/deliverable",
        json={"text": "Here is the finished deliverable."},
        headers=headers,
    )
    assert deliver.status_code == 201
    assert deliver.json()["wallet"] == wallet.address.lower()

    release = client.post(f"/escrows/{escrow_id}/release", headers=headers)
    assert release.status_code == 200
    assert release.json()["status_key"] == "approved"
    assert release.json()["milestones"][0]["status_key"] == "approved"


def test_dispute_messages_and_evidence_flow(client, wallet):
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}
    counterparty = Account.create().address.lower()

    # Create escrow
    create = client.post(
        "/escrows",
        json={
            "title": "Dispute room contract",
            "counterparty_address": counterparty,
            "total": "1000.00",
            "criteria": "Delivery matches QA specs.",
        },
        headers=headers,
    )
    assert create.status_code == 201
    escrow = create.json()
    escrow_id = escrow["id"]
    milestone_id = escrow["milestones"][0]["id"]

    # Seed a dispute against the escrow in DB directly or via seed
    from app.db import AsyncSessionLocal
    from app.enums import StatusKey
    from app.models import Dispute
    import asyncio

    async def _insert_dispute():
        async with AsyncSessionLocal() as db:
            d = Dispute(
                escrow_id=escrow_id,
                milestone_id=milestone_id,
                opened_by_address=wallet.address.lower(),
                issue="Scope mismatch",
                status_key=StatusKey.DISPUTED,
            )
            db.add(d)
            await db.commit()
            await db.refresh(d)
            return d.id

    dispute_id = asyncio.run(_insert_dispute())

    # Send message
    msg_resp = client.post(
        f"/disputes/{dispute_id}/messages",
        json={"content": "Here is why the work was rejected."},
        headers=headers,
    )
    assert msg_resp.status_code == 201
    msg = msg_resp.json()
    assert msg["sender_address"] == wallet.address.lower()
    assert msg["content"] == "Here is why the work was rejected."

    # Get messages
    msgs_resp = client.get(f"/disputes/{dispute_id}/messages")
    assert msgs_resp.status_code == 200
    assert len(msgs_resp.json()) >= 1
    assert msgs_resp.json()[-1]["content"] == "Here is why the work was rejected."

    # Submit evidence
    ev_resp = client.post(
        f"/disputes/{dispute_id}/evidence",
        json={
            "description": "Log files showing error trace",
            "link": "https://example.com/log.txt",
        },
        headers=headers,
    )
    assert ev_resp.status_code == 201
    ev = ev_resp.json()
    assert ev["submitter_address"] == wallet.address.lower()
    assert ev["description"] == "Log files showing error trace"
    assert ev["link"] == "https://example.com/log.txt"
    assert ev["consensus_job_id"] is not None

    # Get evidence
    evs_resp = client.get(f"/disputes/{dispute_id}/evidence")
    assert evs_resp.status_code == 200
    assert len(evs_resp.json()) >= 1
    assert evs_resp.json()[-1]["description"] == "Log files showing error trace"


