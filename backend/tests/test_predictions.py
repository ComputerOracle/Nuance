"""Tests for Prediction Markets API — GET /predictions, GET /predictions/{id}, POST /predictions/{id}/bet.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_account.messages import encode_defunct
import pytest
from fastapi.testclient import TestClient

from app.db import AsyncSessionLocal
from app.main import app
from app.models import Prediction, PredictionPosition, User


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
        json={"side": "YES", "amount": 250},
        headers=headers,
    )
    assert bet_resp.status_code == 201
    updated_pred = bet_resp.json()
    assert updated_pred["id"] == pred_id
    assert updated_pred["volume"] == 5250
    assert len(updated_pred["positions"]) >= 1

    user_pos = next(
        p for p in updated_pred["positions"] if p["wallet_address"] == wallet.address.lower()
    )
    assert user_pos["side"] == "YES"
    assert user_pos["amount"] == 250


@pytest.mark.asyncio
async def test_place_bet_rejected_on_closed_market(client, wallet):
    pred_id = await _seed_prediction(title="Closed Market", status_key="resolved")
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    bet_resp = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "NO", "amount": 100},
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
        json={"side": "YES", "amount": 100},
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

    # Invalid side
    resp2 = client.post(
        "/predictions/1/bet",
        json={"side": "MAYBE", "amount": 100},
        headers=headers,
    )
    assert resp2.status_code == 422


@pytest.mark.asyncio
async def test_resolve_prediction_market_oracle_and_payouts(client, wallet):
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
        json={"side": "YES", "amount": 50},
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


