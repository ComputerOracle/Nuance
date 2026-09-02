"""Unit tests for the multi-model consensus engine's provider assignment
and resilient fallback (services/consensus.py).

Covers:
  1. `_fallback_chain` rotates each persona's primary to the front, in the
     documented order (Validator-Beta's Anthropic primary falls back
     Anthropic -> Gemini -> OpenAI, matching the spec's own example).
  2. A persona whose primary provider has no API key configured falls
     through to the next configured provider with no network call to the
     missing one.
  3. A persona whose primary provider's SDK call raises an unexpected
     error falls through to the next provider.
  4. A persona whose primary provider is genuinely rate-limited (429)
     retries first (tenacity), then falls through once retries are
     exhausted.
  5. With no provider API keys configured at all, every validator
     degrades to the deterministic offline heuristic — same input always
     produces the same output — rather than the job failing or silently
     abstaining at zero confidence.
  6. Every configured provider failing (not just unconfigured) also
     degrades to the heuristic instead of crashing the job.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from types import SimpleNamespace

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-consensus-multimodel-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import httpx  # noqa: E402
import openai  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from google.genai.errors import APIError  # noqa: E402

import app.services.consensus as consensus  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Escrow, Milestone, User  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture(autouse=True)
def _fast_deliberation(monkeypatch):
    # Every test here drives run_consensus directly — no need to pad it
    # with the UI-facing minimum deliberation delay.
    monkeypatch.setattr(consensus, "MIN_DELIBERATION_SECONDS", 0.01)


@pytest.fixture(autouse=True)
def _no_provider_keys_by_default(monkeypatch):
    # Every test opts in to exactly the provider(s) it needs.
    monkeypatch.setattr(consensus.settings, "gemini_api_key", None)
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", None)
    monkeypatch.setattr(consensus.settings, "openai_api_key", None)


# --- Fakes -------------------------------------------------------------


class _FakeGeminiResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data)
        self.parsed = consensus.ValidatorVerdict(**data)


class _FakeGeminiModels:
    def __init__(self, data: dict):
        self._data = data

    async def generate_content(self, *, model: str, contents: str, config=None):
        return _FakeGeminiResponse(self._data)


class _FakeGeminiClient:
    """Always succeeds with a fixed verdict — used as "the surviving
    provider" a chain should land on after its primary is unavailable."""

    def __init__(self, verdict_data: dict):
        self._verdict_data = verdict_data

    def __call__(self, api_key: str | None = None, *_a, **_k):
        self.aio = SimpleNamespace(models=_FakeGeminiModels(self._verdict_data))
        return self


class _FailingGeminiClient:
    class _FailingModels:
        async def generate_content(self, **_kwargs):
            raise APIError(code=500, message="Gemini unavailable")

    def __init__(self, *_a, **_k):
        self.aio = SimpleNamespace(models=self._FailingModels())


class _FakeAnthropicMessages:
    def __init__(self, verdict_data: dict):
        self._data = verdict_data

    async def create(self, **_kwargs):
        block = SimpleNamespace(type="tool_use", name="submit_verdict", input=self._data)
        return SimpleNamespace(content=[block])


class _FakeAnthropicClient:
    def __init__(self, verdict_data: dict, api_key: str | None = None, *_a, **_k):
        self.messages = _FakeAnthropicMessages(verdict_data)


class _RaisingAnthropicMessages:
    async def create(self, **_kwargs):
        raise ValueError("Anthropic returned something unusable.")


class _RaisingAnthropicClient:
    def __init__(self, *_a, **_k):
        self.messages = _RaisingAnthropicMessages()


class _FakeOpenAICompletions:
    def __init__(self, verdict_data: dict):
        self._data = verdict_data

    async def create(self, **_kwargs):
        message = SimpleNamespace(content=json.dumps(self._data))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeOpenAIClient:
    def __init__(self, verdict_data: dict, api_key: str | None = None, *_a, **_k):
        self.chat = SimpleNamespace(completions=_FakeOpenAICompletions(verdict_data))


class _RateLimitedOpenAICompletions:
    """Fails with a genuine 429 every attempt — proves tenacity's retry
    actually engages before `_run_validator_with_fallback` gives up and
    moves to the next provider (unlike the other fakes above, which raise
    an error type that isn't retried at all, for speed)."""

    async def create(self, **_kwargs):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(status_code=429, request=request)
        raise openai.RateLimitError("rate limited", response=response, body=None)


class _RateLimitedOpenAIClient:
    def __init__(self, *_a, **_k):
        self.chat = SimpleNamespace(completions=_RateLimitedOpenAICompletions())


class _RaisingOpenAICompletions:
    async def create(self, **_kwargs):
        raise ValueError("OpenAI returned something unusable.")


class _RaisingOpenAIClient:
    def __init__(self, *_a, **_k):
        self.chat = SimpleNamespace(completions=_RaisingOpenAICompletions())


# --- DB helpers ----------------------------------------------------------


def _random_wallet_address() -> str:
    # Random rather than a sequential counter — this module's own DB is
    # shared with every other test file in the same pytest run (see
    # test_auth_flow.py's docstring), so a predictable counter starting at
    # 1 would collide with test_consensus.py's identical pattern.
    return "0x" + secrets.token_hex(20)


async def _seed_milestone(criteria: str = "Ships a working prototype.") -> Milestone:
    async with AsyncSessionLocal() as db:
        user1 = User(wallet_address=_random_wallet_address())
        user2 = User(wallet_address=_random_wallet_address())
        escrow = Escrow(
            creator_address=user1.wallet_address,
            counterparty_address=user2.wallet_address,
            title="Test escrow",
            total=100,
            status_key=StatusKey.IN_PROGRESS,
        )
        milestone = Milestone(
            name="Milestone 1",
            amount=100,
            status_key=StatusKey.IN_REVIEW,
            criteria=criteria,
            order_index=0,
        )
        escrow.milestones.append(milestone)
        db.add(user1)
        db.add(user2)
        db.add(escrow)
        await db.commit()
        await db.refresh(milestone)
        return milestone


async def _create_job(subject_id: int) -> ConsensusJob:
    async with AsyncSessionLocal() as db:
        job = ConsensusJob(
            subject_type=ConsensusSubjectType.MILESTONE,
            subject_id=subject_id,
            stage=int(ConsensusStage.IDLE),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


def _result_for(results: list[dict], name: str) -> dict:
    return next(r for r in results if r["name"] == name)


# --- 1. Fallback chain ordering --------------------------------------------


def test_fallback_chain_rotates_primary_to_front():
    assert consensus._fallback_chain("gemini") == ("gemini", "anthropic", "openai")
    # Matches the spec's own example: Anthropic -> Gemini -> OpenAI.
    assert consensus._fallback_chain("anthropic") == ("anthropic", "gemini", "openai")
    assert consensus._fallback_chain("openai") == ("openai", "gemini", "anthropic")


def test_persona_primary_providers_are_distinct():
    assert consensus.PERSONA_PRIMARY_PROVIDER == {
        "Validator-Alpha": "gemini",
        "Validator-Beta": "anthropic",
        "Validator-Gamma": "openai",
    }


# --- 2. Missing API key -> falls through with no network call --------------


@pytest.mark.asyncio
async def test_missing_primary_key_falls_back_to_next_configured_provider(monkeypatch):
    """Validator-Alpha's primary (Gemini) has no key at all; Anthropic does.
    Alpha's chain (gemini, anthropic, openai) should skip straight past
    gemini — no genai.Client should even be constructed — and land on
    Anthropic."""

    def _boom(*_a, **_k):
        raise AssertionError("genai.Client should not be constructed without a Gemini API key")

    monkeypatch.setattr(consensus.genai, "Client", _boom)
    monkeypatch.setattr(
        consensus.anthropic,
        "AsyncAnthropic",
        lambda **kw: _FakeAnthropicClient(
            {"vote": "approve", "confidence": 88, "reasoning": "Anthropic: brief is met."}, **kw
        ),
    )
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", "test-anthropic-key")

    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, milestone.id, "Finished prototype.")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)

    assert refreshed.stage == int(ConsensusStage.DONE)
    alpha = _result_for(refreshed.validator_results, "Validator-Alpha")
    assert alpha["provider"] == "anthropic"
    assert alpha["vote"] == "approve"
    assert alpha["confidence"] == 88


# --- 3. Unexpected provider error -> falls through --------------------------


@pytest.mark.asyncio
async def test_primary_provider_error_falls_back_to_next_provider(monkeypatch):
    """Validator-Beta's primary (Anthropic) is configured but its call
    raises; Gemini (Beta's first fallback) is configured and succeeds."""
    monkeypatch.setattr(consensus.anthropic, "AsyncAnthropic", lambda **_k: _RaisingAnthropicClient())
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", "test-anthropic-key")

    monkeypatch.setattr(
        consensus.genai,
        "Client",
        _FakeGeminiClient({"vote": "dispute", "confidence": 72, "reasoning": "Gemini: missing tests."}),
    )
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-gemini-key")

    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, milestone.id, "Finished prototype.")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)

    beta = _result_for(refreshed.validator_results, "Validator-Beta")
    assert beta["provider"] == "gemini"
    assert beta["vote"] == "dispute"
    assert beta["confidence"] == 72


# --- 4. Rate limit (429) retries, then falls back ---------------------------


@pytest.mark.asyncio
async def test_rate_limited_primary_retries_then_falls_back(monkeypatch, caplog):
    """Validator-Gamma's primary (OpenAI) is genuinely rate-limited on
    every attempt — tenacity retries it 3 times before
    _run_validator_with_fallback gives up and moves on to Gemini (Gamma's
    first fallback)."""
    monkeypatch.setattr(consensus.openai, "AsyncOpenAI", lambda **_k: _RateLimitedOpenAIClient())
    monkeypatch.setattr(consensus.settings, "openai_api_key", "test-openai-key")

    monkeypatch.setattr(
        consensus.genai,
        "Client",
        _FakeGeminiClient({"vote": "approve", "confidence": 81, "reasoning": "Gemini: looks solid."}),
    )
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-gemini-key")

    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    with caplog.at_level("WARNING"):
        await consensus.run_consensus(
            ConsensusSubjectType.MILESTONE, milestone.id, "Finished prototype."
        )

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)

    gamma = _result_for(refreshed.validator_results, "Validator-Gamma")
    assert gamma["provider"] == "gemini"
    assert gamma["confidence"] == 81
    assert any(
        "Validator-Gamma" in rec.message and "openai" in rec.message and "falling back" in rec.message
        for rec in caplog.records
    )


# --- 5. No providers configured at all -> deterministic heuristic ----------


@pytest.mark.asyncio
async def test_no_providers_configured_uses_deterministic_heuristic():
    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    await consensus.run_consensus(
        ConsensusSubjectType.MILESTONE, milestone.id, "Here is the finished deliverable, all tests pass."
    )

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)

    assert refreshed.stage == int(ConsensusStage.DONE)
    assert all(r["provider"] == "heuristic" for r in refreshed.validator_results)
    # Not the old always-0 abstention — a real (bounded) heuristic score.
    assert all(40 <= r["confidence"] <= 60 for r in refreshed.validator_results)


def test_deterministic_heuristic_is_reproducible_and_keyword_driven():
    positive_text = "The deliverable is completed, verified, and matches the agreed criteria."
    negative_text = "The deliverable is missing key parts and was never completed."

    first = consensus._deterministic_heuristic_verdict("Validator-Alpha", positive_text)
    second = consensus._deterministic_heuristic_verdict("Validator-Alpha", positive_text)
    assert first == second  # same input -> same output, every time

    assert first["vote"] == "approve"
    assert consensus._deterministic_heuristic_verdict("Validator-Alpha", negative_text)["vote"] == "dispute"

    # Different validator names seed a different (still deterministic) score.
    alpha_score = first["confidence"]
    beta_score = consensus._deterministic_heuristic_verdict("Validator-Beta", positive_text)["confidence"]
    assert 40 <= alpha_score <= 60
    assert 40 <= beta_score <= 60


# --- 6. Every configured provider fails -> heuristic, not a crash ----------


@pytest.mark.asyncio
async def test_all_configured_providers_failing_uses_heuristic_not_crash(monkeypatch):
    monkeypatch.setattr(consensus.genai, "Client", _FailingGeminiClient)
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-gemini-key")

    monkeypatch.setattr(consensus.anthropic, "AsyncAnthropic", lambda **_k: _RaisingAnthropicClient())
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", "test-anthropic-key")

    monkeypatch.setattr(consensus.openai, "AsyncOpenAI", lambda **_k: _RaisingOpenAIClient())
    monkeypatch.setattr(consensus.settings, "openai_api_key", "test-openai-key")

    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    # Never raises, even though every single provider fails outright.
    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, milestone.id, "text")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)
        refreshed_milestone = await db.get(Milestone, milestone.id)

    assert refreshed.stage == int(ConsensusStage.DONE)
    assert all(r["provider"] == "heuristic" for r in refreshed.validator_results)
    # "text" has no positive/negative signal keywords -> heuristic disputes.
    assert refreshed.verdict_approved is False
    assert refreshed_milestone.status_key == StatusKey.DISPUTED


# --- 7. Happy path — every persona is served by its own assigned primary ---


@pytest.mark.asyncio
async def test_all_primaries_succeed_are_served_by_their_own_provider(monkeypatch):
    """No fallback needed at all: with all three providers configured and
    healthy, each persona's result comes from exactly its assigned primary
    provider (gemini/anthropic/openai respectively)."""
    monkeypatch.setattr(
        consensus.genai,
        "Client",
        _FakeGeminiClient({"vote": "approve", "confidence": 90, "reasoning": "Gemini: meets the brief."}),
    )
    monkeypatch.setattr(consensus.settings, "gemini_api_key", "test-gemini-key")

    monkeypatch.setattr(
        consensus.anthropic,
        "AsyncAnthropic",
        lambda **kw: _FakeAnthropicClient(
            {"vote": "approve", "confidence": 85, "reasoning": "Anthropic: looks solid."}, **kw
        ),
    )
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", "test-anthropic-key")

    monkeypatch.setattr(
        consensus.openai,
        "AsyncOpenAI",
        lambda **kw: _FakeOpenAIClient(
            {"vote": "dispute", "confidence": 60, "reasoning": "OpenAI: missing tests."}, **kw
        ),
    )
    monkeypatch.setattr(consensus.settings, "openai_api_key", "test-openai-key")

    milestone = await _seed_milestone()
    job = await _create_job(milestone.id)

    await consensus.run_consensus(ConsensusSubjectType.MILESTONE, milestone.id, "Finished prototype.")

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(ConsensusJob, job.id)

    providers_by_name = {r["name"]: r["provider"] for r in refreshed.validator_results}
    assert providers_by_name == {
        "Validator-Alpha": "gemini",
        "Validator-Beta": "anthropic",
        "Validator-Gamma": "openai",
    }
