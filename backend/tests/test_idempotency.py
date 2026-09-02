"""Tests for Idempotency-Key handling and write-path rate limiting
(app/middleware/idempotency.py, app/middleware/rate_limit.py).

Covers:
  1. A duplicate POST with the same Idempotency-Key replays the cached
     response and creates no duplicate database row.
  2. The same key reused with a different request body is rejected (409)
     rather than silently replayed or re-executed.
  3. A key that's currently mid-flight is rejected (409) instead of
     racing the in-progress request.
  4. Omitting the header is a normal, un-deduplicated request — the
     header is opt-in.
  5. More than `write_rate_limit_per_minute` write requests from the same
     wallet in a rolling minute get 429.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-idempotency-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, IdempotencyRecord, Prediction, PredictionPosition  # noqa: E402


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


async def _seed_open_prediction() -> int:
    async with AsyncSessionLocal() as db:
        pred = Prediction(
            title="Idempotency test market",
            description="Market used to exercise idempotency/rate-limit middleware.",
            category="TEST",
            resolution_date=datetime.now(timezone.utc) + timedelta(days=30),
            volume=0,
            status_key="open",
        )
        db.add(pred)
        await db.commit()
        await db.refresh(pred)
        return pred.id


async def _count_positions(prediction_id: int) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count())
            .select_from(PredictionPosition)
            .where(PredictionPosition.prediction_id == prediction_id)
        )
        return result.scalar_one()


async def _count_escrows_by_creator(creator_address: str) -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count()).select_from(Escrow).where(Escrow.creator_address == creator_address)
        )
        return result.scalar_one()


# --- 1. Duplicate key -> cached response, no duplicate row -----------------


def test_duplicate_idempotency_key_replays_cached_response_no_duplicate_row(client, wallet):
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "escrow-create-key-1"}
    counterparty = Account.create().address.lower()
    payload = {
        "title": "Landing page redesign",
        "counterparty_address": counterparty,
        "total": "500.00",
        "criteria": "Ships responsive, matches Figma.",
    }

    first = client.post("/escrows", json=payload, headers=headers)
    assert first.status_code == 201
    first_body = first.json()

    second = client.post("/escrows", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.json() == first_body  # byte-for-byte the cached response

    # Only one row actually landed in the database.
    creator = wallet.address.lower()
    count = asyncio.run(_count_escrows_by_creator(creator))
    assert count == 1


def test_duplicate_idempotency_key_on_bet_does_not_double_the_position(client, wallet):
    pred_id = asyncio.run(_seed_open_prediction())
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "bet-key-1"}
    payload = {"side": "YES", "amount": 250}

    first = client.post(f"/predictions/{pred_id}/bet", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["volume"] == 250

    second = client.post(f"/predictions/{pred_id}/bet", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.json() == first.json()  # cached, not re-executed

    assert asyncio.run(_count_positions(pred_id)) == 1


# --- 2. Same key, different body -> 409 -------------------------------------


def test_same_key_different_body_is_rejected_with_409(client, wallet):
    pred_id = asyncio.run(_seed_open_prediction())
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "bet-key-conflict"}

    first = client.post(
        f"/predictions/{pred_id}/bet", json={"side": "YES", "amount": 100}, headers=headers
    )
    assert first.status_code == 201

    second = client.post(
        f"/predictions/{pred_id}/bet", json={"side": "YES", "amount": 999}, headers=headers
    )
    assert second.status_code == 409
    assert "different request" in second.json()["detail"].lower()

    # The mismatched second call never ran — still just the one position.
    assert asyncio.run(_count_positions(pred_id)) == 1


# --- 3. Key currently mid-flight -> 409 -------------------------------------


def test_in_flight_key_is_rejected_with_409(client, wallet):
    pred_id = asyncio.run(_seed_open_prediction())
    token = _get_token(client, wallet)
    wallet_addr = wallet.address.lower()
    endpoint = f"POST /predictions/{pred_id}/bet"

    async def _claim_in_flight():
        async with AsyncSessionLocal() as db:
            db.add(
                IdempotencyRecord(
                    key="bet-key-in-flight",
                    user_address=wallet_addr,
                    endpoint=endpoint,
                    request_hash=hashlib.sha256(b"placeholder").hexdigest(),
                    status="in_progress",
                )
            )
            await db.commit()

    asyncio.run(_claim_in_flight())

    resp = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 100},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "bet-key-in-flight"},
    )
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"].lower()

    # The blocked request never touched the database.
    assert asyncio.run(_count_positions(pred_id)) == 0


# --- 4. Header is opt-in -----------------------------------------------------


def test_missing_idempotency_key_header_is_not_deduplicated(client, wallet):
    pred_id = asyncio.run(_seed_open_prediction())
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}  # no Idempotency-Key
    payload = {"side": "NO", "amount": 50}

    first = client.post(f"/predictions/{pred_id}/bet", json=payload, headers=headers)
    second = client.post(f"/predictions/{pred_id}/bet", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["volume"] == 100  # both bets actually landed

    assert asyncio.run(_count_positions(pred_id)) == 2


# --- 5. Rate limiting --------------------------------------------------------


def test_write_rate_limit_returns_429_after_the_configured_max(client, wallet, monkeypatch):
    monkeypatch.setattr(get_settings(), "write_rate_limit_per_minute", 3)

    pred_id = asyncio.run(_seed_open_prediction())
    token = _get_token(client, wallet)
    headers = {"Authorization": f"Bearer {token}"}

    statuses = [
        client.post(
            f"/predictions/{pred_id}/bet", json={"side": "YES", "amount": 10}, headers=headers
        ).status_code
        for _ in range(4)
    ]

    assert statuses[:3] == [201, 201, 201]
    assert statuses[3] == 429


def test_rate_limit_is_scoped_per_wallet(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "write_rate_limit_per_minute", 1)

    pred_id = asyncio.run(_seed_open_prediction())
    wallet_a = Account.create()
    wallet_b = Account.create()
    token_a = _get_token(client, wallet_a)
    token_b = _get_token(client, wallet_b)

    first = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 10},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    second_same_wallet = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 10},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    third_other_wallet = client.post(
        f"/predictions/{pred_id}/bet",
        json={"side": "YES", "amount": 10},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert first.status_code == 201
    assert second_same_wallet.status_code == 429  # wallet_a's own budget is exhausted
    assert third_other_wallet.status_code == 201  # wallet_b has its own, separate budget
