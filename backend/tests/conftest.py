"""Shared pytest fixtures.

`_no_real_provider_keys_by_default` is a safety net: a developer's real
Gemini/Anthropic/OpenAI keys living in backend/.env must never leak into
an automated test run and trigger real, billed network calls just because
a test forgot to monkeypatch one of the three provider keys explicitly.
Every test that actually wants a "configured" provider already
monkeypatches that specific key back on inside the test itself (see
test_consensus.py, test_consensus_multimodel.py) — this fixture only
establishes the "nothing configured" baseline those tests build on top of,
applied before every test in the whole suite regardless of which file
it's in.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_provider_keys_by_default(monkeypatch):
    try:
        import app.services.consensus as consensus
    except ImportError:
        return

    monkeypatch.setattr(consensus.settings, "gemini_api_key", None)
    monkeypatch.setattr(consensus.settings, "anthropic_api_key", None)
    monkeypatch.setattr(consensus.settings, "openai_api_key", None)


@pytest.fixture(autouse=True)
def _disable_chain_indexer_by_default(monkeypatch):
    """app.main's lifespan launches services/genlayer_indexer.run_forever
    as a background task whenever settings.enable_chain_indexer is true
    (the .env default) — every test in this suite triggers that lifespan
    via `with TestClient(app)`, and a real poll loop that shells out to
    `npx tsx` every cycle has no business running during unit tests.
    Forced off here regardless of what's in .env — same pattern as
    _no_real_provider_keys_by_default above: get_settings() is
    lru_cached, so every module that calls it (app.main,
    genlayer_indexer, ...) shares this exact instance, and monkeypatch
    reverts it automatically after each test."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "enable_chain_indexer", False)
