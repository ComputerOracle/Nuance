"""Tests for Prediction Markets API — GET /predictions, GET /predictions/{id}, POST /predictions/{id}/bet.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_account.messages import encode_defunct
import pytest
from fastapi.testclient import TestClient

from app.db import AsyncSessionLocal
from app.main import app
from app.models import Prediction, PredictionPosition, User
from app.services import prediction_oracle


# --- Fakes for prediction_oracle's genai.Client — same shape/pattern as
# test_consensus.py's own _FakeGenaiClient (see that file for why: no real
# network call, deterministic, matches the SDK's actual response shape
# closely enough for `response.parsed`/`response.text` to both work).
class _FakeOracleResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)
        self.parsed = prediction_oracle.OracleValidatorVerdict(**data)


class _FakeOracleAsyncModels:
    def __init__(self, verdict: dict):
        self._verdict = verdict

    async def generate_content(self, *, model: str, contents: str, config=None):
        return _FakeOracleResponse(self._verdict)


class _FakeOracleAio:
    def __init__(self, verdict: dict):
        self.models = _FakeOracleAsyncModels(verdict)


class _FakeOracleGenaiClient:
    """Every persona returns the same fixed verdict — enough to test the
    majority-vote/payout math deterministically without needing three
    different canned responses the way test_consensus.py's fake does."""

    def __init__(self, api_key: str | None = None, *_args, **_kwargs):
        self.api_key = api_key
        self.aio = _FakeOracleAio(_FakeOracleGenaiClient.verdict)


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
    signature = signed.signature.hex()
    verify_resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": signature},
    )
    assert verify_resp.status_code == 200
    return verify_resp.json()["access_token"]


async def _seed_prediction(
    title: str = "Test Market",
    status_key: str = "open",
    resolution_delta_days: int = 30,
    volume: int = 1000,
) -> int:
    async with AsyncSessionLocal() as db:
        pred = Prediction(
            title=title,
            description="Market description for testing.",
            category="LEGAL",
            resolution_date=datetime.now(timezone.utc) + timedelta(days=resolution_delta_days),
            volume=volume,
            status_key=status_key,
        )
        db.add(pred)
        await db.commit()
        await db.refresh(pred)
        return pred.id


def test_list_and_get_predictions(client):
    resp = client.get("/predictions")
    assert resp.status_code == 200
    preds = resp.json()
    assert isinstance(preds, list)


def test_place_bet_unauthenticated_rejected(client):
    resp = client.post("/predictions/1/bet", json={"side": "YES", "amount": 100})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_place_bet_authenticated_success(client, wallet):
    pred_id = await _seed_prediction(title="Will Company X win?", volume=5000)
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    bet_resp = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 500},
        headers=headers,
    )
    assert bet_resp.status_code == 201
    updated_pred = bet_resp.json()
    assert updated_pred["id"] == pred_id
    assert updated_pred["volume"] == 5500
    assert len(updated_pred["positions"]) >= 1

    user_pos = next(
        p for p in updated_pred["positions"] if p["wallet_address"] == wallet.address.lower()
    )
    assert user_pos["side"] == "YES"
    assert user_pos["amount"] == 500


@pytest.mark.asyncio
async def test_place_bet_rejected_on_closed_market(client, wallet):
    pred_id = await _seed_prediction(title="Closed Market", status_key="resolved")
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    bet_resp = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "NO", "amount": 500},
        headers=headers,
    )
    assert bet_resp.status_code == 400
    assert "not open" in bet_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_place_bet_rejected_on_expired_date(client, wallet):
    pred_id = await _seed_prediction(
        title="Expired Market", status_key="open", resolution_delta_days=-2
    )
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    bet_resp = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 500},
        headers=headers,
    )
    assert bet_resp.status_code == 400
    assert "betting has closed for this market" in bet_resp.json()["detail"].lower()


def test_place_bet_invalid_payload(client, wallet):
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    # Invalid amount <= 0
    resp1 = client.post(
        "/predictions/1/bet",
        json={"side": "YES", "amount": 0},
        headers=headers,
    )
    assert resp1.status_code == 422

    # Invalid side (amount is a valid preset here on purpose, so this
    # fails specifically on `side`, not incidentally on `amount` too)
    resp2 = client.post(
        "/predictions/1/bet",
        json={"side": "MAYBE", "amount": 500},
        headers=headers,
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_resolve_prediction_market_oracle_and_payouts(client, wallet, monkeypatch):
    # A configured key + a fixed-YES fake client — see prediction_oracle.py's
    # 2026-09-08 fix: with no key configured at all, resolution now raises
    # OracleUnavailableError (503) rather than ever fabricating an outcome
    # (see test_resolve_prediction_market_without_oracle_key below for
    # that path) — so exercising the actual payout math here needs a real,
    # if fake, oracle response.
    _FakeOracleGenaiClient.verdict = {"outcome": "YES", "confidence": 90, "reasoning": "Fake oracle: YES."}
    monkeypatch.setattr(prediction_oracle.genai, "Client", _FakeOracleGenaiClient)
    monkeypatch.setattr(prediction_oracle.settings, "gemini_api_key", "test-key")

    # Seed a prediction with 3 distinct user positions:
    # Alice (100 YES), Bob (100 NO), Charlie (300 YES) -> Total volume = 500
    user1_addr = "0x1111111111111111111111111111111111111111"
    user2_addr = "0x2222222222222222222222222222222222222222"
    user3_addr = "0x3333333333333333333333333333333333333333"

    async with AsyncSessionLocal() as db:
        for addr in (user1_addr, user2_addr, user3_addr):
            existing = await db.get(User, addr)
            if not existing:
                db.add(User(wallet_address=addr))
        await db.flush()

        pred = Prediction(
            title="Will GenLayer Season 1 distribute over 8,000,000 GLP?",
            description="Resolves YES if distributed GLP exceeds 8,000,000 GLP.",
            category="POINTS & REWARDS",
            resolution_date=datetime.now(timezone.utc) - timedelta(days=2),
            volume=500,
            status_key="open",
        )
        db.add(pred)
        await db.flush()

        pos1 = PredictionPosition(
            prediction_id=pred.id,
            wallet_address=user1_addr,
            side="YES",
            amount=100,
        )
        pos2 = PredictionPosition(
            prediction_id=pred.id,
            wallet_address=user2_addr,
            side="NO",
            amount=100,
        )
        pos3 = PredictionPosition(
            prediction_id=pred.id,
            wallet_address=user3_addr,
            side="YES",
            amount=300,
        )
        db.add_all([pos1, pos2, pos3])
        await db.commit()
        pred_id = pred.id

    # Trigger resolution endpoint
    resolve_resp = client.post(f"/predictions/{pred_id}/resolve")
    assert resolve_resp.status_code == 200
    data = resolve_resp.json()

    assert data["status_key"] == "RESOLVED"
    assert data["outcome"] in ("YES", "NO")
    assert data["resolution_reasoning"] is not None
    assert len(data["positions"]) == 3

    if data["outcome"] == "YES":
        alice = next(p for p in data["positions"] if p["wallet_address"] == user1_addr)
        bob = next(p for p in data["positions"] if p["wallet_address"] == user2_addr)
        charlie = next(p for p in data["positions"] if p["wallet_address"] == user3_addr)

        # Pari-mutuel: Alice = (100 / 400) * 500 = 125.0, Charlie = (300 / 400) * 500 = 375.0, Bob = 0.0
        assert alice["status"] == "WON"
        assert alice["payout"] == 125.0

        assert charlie["status"] == "WON"
        assert charlie["payout"] == 375.0

        assert bob["status"] == "LOST"
        assert bob["payout"] == 0.0

    # Verify subsequent bet on resolved market is rejected
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}
    bet_resp = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 500},
        headers=headers,
    )
    assert bet_resp.status_code == 400
    assert "not open" in bet_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resolve_future_market_rejected_with_400(client):
    pred_id = await _seed_prediction(
        title="Future Market", status_key="open", resolution_delta_days=30
    )
    resp = client.post(f"/predictions/{pred_id}/resolve")
    assert resp.status_code == 400
    assert "cannot be resolved before its resolution date" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_resolve_prediction_market_without_oracle_key_returns_503(client, monkeypatch):
    """FIXED 2026-09-08 — resolving with no GEMINI_API_KEY configured used
    to silently fabricate a "YES" outcome (see prediction_oracle.py's own
    docstring on why that was a real landmine, not a graceful degrade).
    It must now refuse instead: a clean 503, and the market left exactly
    as it was (still "open", not resolved, not any new terminal-looking
    status) so it can just be retried once the oracle is configured."""
    monkeypatch.setattr(prediction_oracle.settings, "gemini_api_key", None)

    pred_id = await _seed_prediction(
        title="Unconfigured Oracle Market", status_key="open", resolution_delta_days=-2
    )
    resp = client.post(f"/predictions/{pred_id}/resolve")
    assert resp.status_code == 503
    assert "oracle" in resp.json()["detail"].lower()

    # Confirm nothing was mutated — still open, no outcome, no reasoning.
    async with AsyncSessionLocal() as db:
        pred = await db.get(Prediction, pred_id)
        assert pred.status_key == "open"
        assert pred.outcome is None
        assert pred.resolution_reasoning is None


