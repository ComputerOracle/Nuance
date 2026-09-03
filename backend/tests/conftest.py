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
