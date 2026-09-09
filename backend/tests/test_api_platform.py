"""Tests for ROADMAP.md Part 4 6.1/6.2 — API keys, webhooks, and
multi-asset escrows.

Covers:
  1. Issuing an API key and using it via X-Api-Key to create an escrow —
     resolves to the issuing wallet, same as a JWT would.
  2. A key missing the required scope gets 403, not a silent no-op.
  3. A revoked key gets 401.
  4. An unknown/malformed key gets 401.
  5. Per-API-key rate limiting is distinct from per-wallet rate limiting.
  6. Escrow creation defaults to GEN, accepts an explicit asset symbol,
     and 400s on an unknown one.
  7. Webhook registration/listing/deletion, and that a real delivery
     (via services/webhooks.notify, called directly — see
     test_consensus.py's own precedent for testing a service function
     directly rather than racing a fire-and-forget background task)
     sends a correctly HMAC-signed payload only to a matching, active
     subscriber.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-api-platform-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Webhook  # noqa: E402
from app.services import webhooks as webhooks_service  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def wallet():
    return Account.create()


def _get_token(client: TestClient, wallet: Account) -> str:
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    signed = wallet.sign_message(encode_defunct(text=message))
    resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": signed.signature.hex()},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _issue_api_key(client: TestClient, token: str, scopes: list[str]) -> dict:
    resp = client.post(
        "/auth/api-keys",
        json={"label": "test key", "scopes": scopes},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- 1/2/3/4. API key auth: success, missing scope, revoked, malformed -----


def test_api_key_creates_escrow_as_issuing_wallet(client, wallet):
    token = _get_token(client, wallet)
    issued = _issue_api_key(client, token, ["escrow:create"])
    counterparty = Account.create().address.lower()

    resp = client.post(
        "/escrows",
        json={"title": "Agent-created escrow", "counterparty_address": counterparty, "total": "10.00"},
        headers={"X-Api-Key": issued["api_key"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["creator_address"] == wallet.address.lower()
    assert body["asset"]["symbol"] == "GEN"  # default, unaffected by API-key auth path


def test_api_key_without_required_scope_is_403(client, wallet):
    token = _get_token(client, wallet)
    issued = _issue_api_key(client, token, ["bet:place"])  # not escrow:create

    resp = client.post(
        "/escrows",
        json={
            "title": "Should fail",
            "counterparty_address": Account.create().address.lower(),
            "total": "10.00",
        },
        headers={"X-Api-Key": issued["api_key"]},
    )
    assert resp.status_code == 403


def test_revoked_api_key_is_401(client, wallet):
    token = _get_token(client, wallet)
    issued = _issue_api_key(client, token, ["escrow:create"])

    revoke = client.delete(
        f"/auth/api-keys/{issued['id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert revoke.status_code == 204

    resp = client.post(
        "/escrows",
        json={
            "title": "Should fail",
            "counterparty_address": Account.create().address.lower(),
            "total": "10.00",
        },
        headers={"X-Api-Key": issued["api_key"]},
    )
    assert resp.status_code == 401


def test_malformed_api_key_is_401(client):
    resp = client.post(
        "/escrows",
        json={
            "title": "Should fail",
            "counterparty_address": Account.create().address.lower(),
            "total": "10.00",
        },
        headers={"X-Api-Key": "not-a-real-key"},
    )
    assert resp.status_code == 401


def test_api_key_rejects_unknown_scope_at_issuance(client, wallet):
    token = _get_token(client, wallet)
    resp = client.post(
        "/auth/api-keys",
        json={"scopes": ["totally:madeup"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_list_and_revoke_api_keys(client, wallet):
    token = _get_token(client, wallet)
    issued = _issue_api_key(client, token, ["escrow:create"])

    listed = client.get("/auth/api-keys", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    keys = listed.json()
    assert any(k["id"] == issued["id"] for k in keys)
    # The full secret is never listed back, only shown once at creation.
    assert all("api_key" not in k and "secret" not in k for k in keys)

    other_token = _get_token(client, Account.create())
    forbidden = client.delete(
        f"/auth/api-keys/{issued['id']}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert forbidden.status_code == 404  # someone else's key — not found, not forbidden


# --- 5. Per-API-key rate limiting, distinct from per-wallet -----------------


def test_api_key_rate_limit_is_separate_from_wallet_rate_limit(client, wallet, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_key_write_rate_limit_per_minute", 1)

    token = _get_token(client, wallet)
    issued = _issue_api_key(client, token, ["escrow:create"])

    def _create(headers):
        return client.post(
            "/escrows",
            json={
                "title": "Rate limit test",
                "counterparty_address": Account.create().address.lower(),
                "total": "1.00",
            },
            headers=headers,
        )

    api_key_headers = {"X-Api-Key": issued["api_key"]}
    first = _create(api_key_headers)
    assert first.status_code == 201
    second = _create(api_key_headers)
    assert second.status_code == 429
    assert "API key" in second.json()["detail"]

    # The wallet's own JWT-based bucket is untouched by the API key's —
    # same wallet, different auth path, still allowed through.
    jwt_headers = {"Authorization": f"Bearer {token}"}
    third = _create(jwt_headers)
    assert third.status_code == 201


# --- 6. Multi-asset escrows --------------------------------------------------


def test_escrow_defaults_to_gen_asset(client, wallet):
    token = _get_token(client, wallet)
    resp = client.post(
        "/escrows",
        json={
            "title": "Default asset",
            "counterparty_address": Account.create().address.lower(),
            "total": "5.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    asset = resp.json()["asset"]
    assert asset["symbol"] == "GEN"
    assert asset["decimals"] == 18
    assert asset["is_native"] is True


def test_escrow_accepts_explicit_asset_symbol(client, wallet):
    token = _get_token(client, wallet)
    resp = client.post(
        "/escrows",
        json={
            "title": "Stablecoin escrow",
            "counterparty_address": Account.create().address.lower(),
            "total": "500.00",
            "asset_symbol": "usdc",  # lowercase — normalized to USDC
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    asset = resp.json()["asset"]
    assert asset["symbol"] == "USDC"
    assert asset["decimals"] == 6
    assert asset["is_native"] is False


def test_escrow_rejects_unknown_asset_symbol(client, wallet):
    token = _get_token(client, wallet)
    resp = client.post(
        "/escrows",
        json={
            "title": "Bad asset",
            "counterparty_address": Account.create().address.lower(),
            "total": "5.00",
            "asset_symbol": "DOGE",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# --- 7. Webhooks --------------------------------------------------------


def test_webhook_registration_lifecycle(client, wallet):
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["consensus.completed"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert "secret" in body and len(body["secret"]) > 0

    listed = client.get("/webhooks", headers=headers)
    assert listed.status_code == 200
    hooks = listed.json()
    assert len(hooks) == 1
    assert "secret" not in hooks[0]  # never listed back after creation

    deleted = client.delete(f"/webhooks/{body['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/webhooks", headers=headers).json() == []


def test_webhook_rejects_unknown_event_type(client, wallet):
    token = _get_token(client, wallet)
    resp = client.post(
        "/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["made.up.event"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeAsyncClient:
    """Records every call instead of making a real network request —
    same "monkeypatch the SDK client" pattern test_consensus.py's own
    _FakeGenaiClient uses for the AI providers."""

    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, content=None, headers=None):
        _FakeAsyncClient.calls.append({"url": url, "content": content, "headers": headers})
        return _FakeResponse(200)


async def _seed_webhook(wallet_address: str, event_types: list[str], secret: str = "test-secret") -> Webhook:
    async with AsyncSessionLocal() as db:
        webhook = Webhook(
            wallet_address=wallet_address,
            url="https://example.com/hook",
            event_types=event_types,
            secret=secret,
        )
        db.add(webhook)
        await db.commit()
        await db.refresh(webhook)
        return webhook


@pytest.mark.asyncio
async def test_webhook_delivery_signs_payload_and_only_notifies_matching_active_hooks(
    client, wallet, monkeypatch
):
    from app.db import AsyncSessionLocal as _Session
    from app.models import User

    async with _Session() as db:
        db.add(User(wallet_address=wallet.address.lower()))
        await db.commit()

    matching = await _seed_webhook(wallet.address.lower(), ["consensus.completed"], secret="s3cr3t")
    non_matching = await _seed_webhook(
        wallet.address.lower(), ["dispute.resolved"], secret="other-secret"
    )
    inactive = await _seed_webhook(wallet.address.lower(), ["consensus.completed"], secret="inactive")
    async with AsyncSessionLocal() as db:
        row = await db.get(Webhook, inactive.id)
        row.is_active = False
        await db.commit()

    _FakeAsyncClient.calls = []
    monkeypatch.setattr(webhooks_service.httpx, "AsyncClient", _FakeAsyncClient)

    payload = {"job_id": 123, "stage": 3}
    await webhooks_service.notify("consensus.completed", payload)

    assert len(_FakeAsyncClient.calls) == 1  # not non_matching (wrong event), not inactive
    call = _FakeAsyncClient.calls[0]
    assert call["url"] == matching.url

    body = call["content"]
    parsed = json.loads(body)
    assert parsed == {"event": "consensus.completed", "data": payload}

    expected_sig = "sha256=" + hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
    assert call["headers"]["X-Nuance-Signature"] == expected_sig
    assert call["headers"]["X-Nuance-Event"] == "consensus.completed"

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Webhook, matching.id)
        assert refreshed.last_delivery_status == 200
        assert refreshed.last_delivered_at is not None


@pytest.mark.asyncio
async def test_webhook_delivery_records_error_status_without_raising(client, wallet, monkeypatch):
    from app.db import AsyncSessionLocal as _Session
    from app.models import User

    async with _Session() as db:
        db.add(User(wallet_address=wallet.address.lower()))
        await db.commit()

    webhook = await _seed_webhook(wallet.address.lower(), ["prediction.resolved"])

    class _FailingClient(_FakeAsyncClient):
        async def post(self, *args, **kwargs):
            raise ConnectionError("simulated network failure")

    monkeypatch.setattr(webhooks_service.httpx, "AsyncClient", _FailingClient)

    # Must not raise — a bad callback URL can never propagate out of notify().
    await webhooks_service.notify("prediction.resolved", {"prediction_id": 1})

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Webhook, webhook.id)
        assert refreshed.last_delivery_status == webhooks_service.DELIVERY_ERROR_STATUS
