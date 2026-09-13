"""Tests for services/genlayer_deploy.py's retry_undeployed_predictions —
the prediction-market equivalent of retry_undeployed_escrows's own gap
and fix (see that function's docstring in genlayer_deploy.py).

Reported live (2026-09-13): a user asked that every bet on a prediction
market use real GEN, "like a real Prediction Markets." Checked the actual
database rather than assuming the already-built on-chain betting path
(routers/predictions.py's place_bet already refuses a contract-linked
market's off-chain endpoint) covered everything — it found several
markets already `status_key == "open"` (genuinely accepting bets right
now) with `contract_address` still null, mostly predating
deploy_prediction_contract's per-market background task. Every bet on one
of those goes through the plain off-chain endpoint: notional
PredictionPosition bookkeeping, no real GEN behind it.

Mocks app.services.genlayer_deploy.deploy_contract entirely (no
subprocess, no real network, no real testnet GEN spent). Covers:
  1. A never-attempted, already-"open" market gets deployed and linked.
  2. A stale failed attempt (past the cooldown) gets retried.
  3. A recent attempt (within cooldown) is left alone — the same
     double-submission safety property retry_undeployed_escrows has.
  4. A "pending_review" (unreviewed draft) market is skipped — deploying
     one nobody chose to publish would spend real testnet GEN on content
     that may never launch. See retry_undeployed_predictions's own
     docstring on why this differs from retry_undeployed_escrows's
     status filter.
  5. A market with no resolution_source_url is skipped (nothing for
     NuancePredictionMarket.resolve_market to judge against — same guard
     deploy_prediction_contract's own docstring documents).
  6. An already-linked market is left alone (idempotency).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-prediction-retry-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.genlayer_deploy as genlayer_deploy  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Prediction

_FAKE_ADDRESS = "0xF00Dbabe00000000000000000000000000000077"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


async def _create_prediction_row(
    title: str,
    *,
    status_key: str = "open",
    contract_address: str | None = None,
    resolution_source_url: str | None = "https://example.com/announcement",
    deploy_attempted_at: datetime | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        prediction = Prediction(
            title=title,
            description="A test market.",
            category="Test",
            resolution_date=datetime.now(timezone.utc) + timedelta(days=30),
            status_key=status_key,
            contract_address=contract_address,
            resolution_source_url=resolution_source_url,
            deploy_attempted_at=deploy_attempted_at,
        )
        db.add(prediction)
        await db.commit()
        await db.refresh(prediction)
        return prediction.id


async def _get_prediction(prediction_id: int) -> Prediction:
    async with AsyncSessionLocal() as db:
        return await db.get(Prediction, prediction_id)


def test_retries_a_never_attempted_open_market(monkeypatch):
    prediction_id = asyncio.run(_create_prediction_row("Never attempted yet?"))

    async def _fake_deploy_contract(file, args):
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.retry_undeployed_predictions())

    prediction = asyncio.run(_get_prediction(prediction_id))
    assert prediction.contract_address == _FAKE_ADDRESS


def test_retries_a_stale_failed_attempt(monkeypatch):
    stale = datetime.now(timezone.utc) - genlayer_deploy._DEPLOY_RETRY_COOLDOWN - timedelta(minutes=1)
    prediction_id = asyncio.run(
        _create_prediction_row("Failed a while ago?", deploy_attempted_at=stale)
    )

    async def _fake_deploy_contract(file, args):
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.retry_undeployed_predictions())

    prediction = asyncio.run(_get_prediction(prediction_id))
    assert prediction.contract_address == _FAKE_ADDRESS


def test_skips_a_recent_attempt_in_cooldown(monkeypatch):
    recent = datetime.now(timezone.utc) - timedelta(minutes=1)
    prediction_id = asyncio.run(
        _create_prediction_row("Attempted very recently?", deploy_attempted_at=recent)
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should not be called for an attempt still in cooldown")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_predictions())  # must not raise

    prediction = asyncio.run(_get_prediction(prediction_id))
    assert prediction.contract_address is None


def test_skips_pending_review_drafts(monkeypatch):
    prediction_id = asyncio.run(
        _create_prediction_row("An unreviewed draft?", status_key="pending_review")
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called for a pending_review draft")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_predictions())  # must not raise

    prediction = asyncio.run(_get_prediction(prediction_id))
    assert prediction.contract_address is None


def test_skips_market_with_no_resolution_source_url(monkeypatch):
    prediction_id = asyncio.run(
        _create_prediction_row("Nothing to resolve against?", resolution_source_url=None)
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called with no resolution_source_url")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_predictions())  # must not raise

    prediction = asyncio.run(_get_prediction(prediction_id))
    assert prediction.contract_address is None


def test_skips_already_linked(monkeypatch):
    prediction_id = asyncio.run(
        _create_prediction_row(
            "Already linked?", contract_address="0xAlreadyLinked000000000000000000000003"
        )
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called for an already-linked market")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_predictions())  # must not raise

    prediction = asyncio.run(_get_prediction(prediction_id))
    assert prediction.contract_address == "0xAlreadyLinked000000000000000000000003"
