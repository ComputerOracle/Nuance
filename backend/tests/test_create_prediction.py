"""POST /predictions no longer exists — REVERSED 2026-09-14, asked
directly ("I do not want user to be able to create a Prediction Markets,
I want it will be fetching data about genlayer using the API key"). This
file used to cover the 2026-09-12 rebrand's real Create-Market form (a
person authoring a market directly); that form is gone, and markets are
back to being sourced exclusively from services/market_generator.py's
real TwitterAPI.io + Gemini pipeline — see routers/predictions.py's own
updated module docstring for the full account, including the real,
practical reason beyond following the request literally (an unmetered
drain on this deployment's shared GEN balance via auto-deploy, reachable
by any signed-in wallet on demand).

This suite now only proves the removal actually holds: POST /predictions
is rejected (not silently 200/201) regardless of auth, and existing
markets are unaffected — still only ever created by the real generator or
already-seeded test fixtures, never by this endpoint.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-create-prediction-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


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


_VALID_PAYLOAD = {
    "title": "Will GenLayer ship testnet v2 by end of Q4 2026?",
    "description": "Resolves YES if genlayer.com's official blog announces testnet v2 has "
    "launched before 2027-01-01. Resolves NO otherwise.",
    "category": "GenLayer Ecosystem",
    "resolution_date": "2027-01-01T00:00:00+00:00",
    "resolution_source_url": "https://genlayer.com/blog",
}


def test_post_predictions_no_longer_exists_unauthenticated(client: TestClient):
    resp = client.post("/predictions", json=_VALID_PAYLOAD)
    # Not 201 — that's the actual regression this guards against. 404/405
    # both mean "gone"; which one FastAPI picks isn't the point here.
    assert resp.status_code in (404, 405)


def test_post_predictions_no_longer_exists_even_authenticated(client: TestClient):
    """The real regression risk: a signed-in wallet specifically — this is
    the exact caller create_prediction used to accept unconditionally."""
    wallet = Account.create()
    token = _get_token(client, wallet)

    resp = client.post(
        "/predictions", json=_VALID_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code in (404, 405)


def test_get_predictions_still_works(client: TestClient):
    """Removing the create route must not have taken GET down with it.
    Not asserting an empty list — this suite shares one sqlite DB across
    the whole test run (same DATABASE_URL env var, first file's setdefault
    wins), so other test files' seeded predictions are legitimately
    already there by the time this one runs."""
    resp = client.get("/predictions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
