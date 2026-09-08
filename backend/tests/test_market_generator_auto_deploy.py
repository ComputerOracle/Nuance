"""Tests for services/market_generator.py's own auto-deploy hook — the
call to services/genlayer_deploy.deploy_prediction_contract for every
market _process_events auto-publishes. Mocks deploy_prediction_contract
entirely (no subprocess, no real network, no real testnet GEN spent) and
google.genai.Client (same as test_market_generator.py — no real LLM call).

Covers:
  1. An auto-published (auto_publish=True) market triggers exactly one
     deploy_prediction_contract call, for the right prediction id.
  2. A "pending_review" draft (auto_publish=False) triggers NONE — it
     might still be discarded/edited before a human makes it live.
  3. The setting itself off (auto_deploy_prediction_contracts=False, this
     whole suite's own default via conftest.py) means no call at all,
     even for an auto-published market — proven directly, not just
     trusted from the conftest fixture existing.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.services.genlayer_deploy as genlayer_deploy
from app.main import app
from app.services.market_generator import ExtractedMarket, RawEvent, _process_events

_id_counter = itertools.count(1)


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


def _event(text: str, *, author: str = "genlayer") -> RawEvent:
    n = next(_id_counter)
    return RawEvent(
        source_id=f"auto-deploy-test:{n}",
        source="twitter",
        author=author,
        text=text,
        url=f"https://x.com/{author}/status/{n}",
        published_at=datetime.now(timezone.utc),
    )


class _FakeResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)
        self.parsed = ExtractedMarket(**data)


class _FakeAsyncModels:
    async def generate_content(self, *, model: str, contents: str, config=None):
        future = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        return _FakeResponse(
            {
                "is_verifiable_milestone": True,
                "title": "Will GenLayer ship the marked milestone?",
                "resolution_rules": "Resolves YES if the milestone ships as described.",
                "end_time": future,
            }
        )


class _FakeAio:
    def __init__(self):
        self.models = _FakeAsyncModels()


class _FakeGenaiClient:
    def __init__(self):
        self.aio = _FakeAio()


def test_auto_published_market_triggers_one_deploy(monkeypatch):
    from app.config import get_settings
    from app.db import AsyncSessionLocal

    monkeypatch.setattr(get_settings(), "auto_deploy_prediction_contracts", True)

    calls = []

    async def _fake_deploy_prediction_contract(prediction_id):
        calls.append(prediction_id)

    monkeypatch.setattr(genlayer_deploy, "deploy_prediction_contract", _fake_deploy_prediction_contract)

    event = _event("MILESTONE_MARKER: mainnet consensus release date set")

    async def _run():
        async with AsyncSessionLocal() as db:
            return await _process_events(
                db,
                [event],
                auto_publish=True,
                gemini_client=_FakeGenaiClient(),
                trusted_accounts={"genlayer"},
            )

    created = asyncio.run(_run())

    assert len(created) == 1
    assert calls == [created[0].id]


def test_pending_review_draft_triggers_no_deploy(monkeypatch):
    from app.config import get_settings
    from app.db import AsyncSessionLocal

    monkeypatch.setattr(get_settings(), "auto_deploy_prediction_contracts", True)

    def _fail_if_called(prediction_id):
        raise AssertionError("deploy_prediction_contract should never be called for a draft")

    monkeypatch.setattr(genlayer_deploy, "deploy_prediction_contract", _fail_if_called)

    event = _event("MILESTONE_MARKER: a draft milestone, not yet live")

    async def _run():
        async with AsyncSessionLocal() as db:
            return await _process_events(
                db,
                [event],
                auto_publish=False,
                gemini_client=_FakeGenaiClient(),
                trusted_accounts={"genlayer"},
            )

    created = asyncio.run(_run())
    assert created[0].status_key == "pending_review"


def test_setting_off_means_no_deploy_even_when_auto_published(monkeypatch):
    from app.config import get_settings
    from app.db import AsyncSessionLocal

    # Explicit, not relying on conftest.py's own default — proves the
    # gate itself works, not just that it happens to be off in this suite.
    monkeypatch.setattr(get_settings(), "auto_deploy_prediction_contracts", False)

    def _fail_if_called(prediction_id):
        raise AssertionError("deploy_prediction_contract should never be called with the setting off")

    monkeypatch.setattr(genlayer_deploy, "deploy_prediction_contract", _fail_if_called)

    event = _event("MILESTONE_MARKER: yet another real milestone")

    async def _run():
        async with AsyncSessionLocal() as db:
            return await _process_events(
                db,
                [event],
                auto_publish=True,
                gemini_client=_FakeGenaiClient(),
                trusted_accounts={"genlayer"},
            )

    created = asyncio.run(_run())
    assert created[0].status_key == "open"
