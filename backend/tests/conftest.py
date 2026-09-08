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

import os

import pytest

# Set BEFORE any test module (or app.config) is imported — conftest.py is
# always collected first, guaranteeing Settings() never sees these as True
# in the first place. This is the actual fix for a real gap the function-
# scoped fixtures below can't close on their own: several test files (e.g.
# test_consensus.py, test_dispute_id_resolution.py) use a *module*-scoped
# `_init_schema` fixture that opens `with TestClient(app)` once for the
# whole file — and pytest sets up module-scoped fixtures BEFORE any
# function-scoped one (the monkeypatch fixtures below), for that file's
# first test. That ordering means app.main's lifespan can start a REAL
# background indexer (or, without this, attempt a REAL contract auto-
# deploy) before `_disable_chain_indexer_by_default`/
# `_disable_auto_deploy_by_default` ever get a chance to monkeypatch it
# off — confirmed by hitting exactly this race (an extra, unaccounted-for
# indexer poll cycle) while adding the auto-deploy feature. Env-var
# defaults close it at the source; the fixtures below stay too, as
# explicit, self-documenting intent and a second layer of defense.
os.environ.setdefault("ENABLE_CHAIN_INDEXER", "false")
os.environ.setdefault("AUTO_DEPLOY_ESCROW_CONTRACTS", "false")
# test_market_generator.py calls _process_events directly, many times —
# same reasoning as the escrow one above, just for
# services/market_generator.py's own auto-deploy hook.
os.environ.setdefault("AUTO_DEPLOY_PREDICTION_CONTRACTS", "false")


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


@pytest.fixture(autouse=True)
def _disable_auto_deploy_by_default(monkeypatch):
    """routers/escrows.py::create_escrow queues services/genlayer_deploy.
    deploy_escrow_contract as a background task whenever settings.
    auto_deploy_escrow_contracts is true (the .env default) — FastAPI's
    TestClient actually runs background tasks before a request call
    returns, so any test hitting POST /escrows would otherwise fire a
    real ~3-minute Bradbury deployment, spending real testnet GEN from the
    deployer key. Forced off here regardless of what's in .env — same
    pattern as _disable_chain_indexer_by_default above. Tests that
    specifically want to exercise the deploy path mock
    genlayer_deploy.deploy_contract instead (see
    test_auto_deploy_escrow.py) — they don't need this flag on, since
    they call deploy_escrow_contract directly rather than through the
    live create_escrow endpoint."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_deploy_escrow_contracts", False)


@pytest.fixture(autouse=True)
def _disable_prediction_auto_deploy_by_default(monkeypatch):
    """services/market_generator.py's _process_events calls
    deploy_prediction_contract for every auto-published market whenever
    settings.auto_deploy_prediction_contracts is true (the .env default) —
    test_market_generator.py calls _process_events directly, many times,
    and has no business firing real Bradbury deployments. Same reasoning
    as _disable_auto_deploy_by_default above."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_deploy_prediction_contracts", False)
