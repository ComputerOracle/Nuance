"""Tests for services/genlayer_indexer.py's trigger_pending_market_resolutions
— the prediction-market equivalent of trigger_pending_adjudications. Mocks
app.services.genlayer_write.write_contract entirely (no subprocess, no
real network, no real testnet GEN spent).

Covers:
  1. Happy path: a linked, still-open, past-cutoff, never-triggered market
     gets resolve_market sent with the right address, and
     resolution_trigger_tx_hash is recorded on success.
  2. Not yet past its cutoff — never triggered (resolve_market would just
     fail on-chain before then).
  3. Already resolved off-chain (status_key already "RESOLVED", e.g. a
     view-sync in the same cycle already flipped it) — never triggered.
  4. Already triggered (resolution_trigger_tx_hash already set) — never
     sent twice.
  5. A failed *send* (write_contract returns None) leaves
     resolution_trigger_tx_hash null — safe to retry next cycle.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import app.services.genlayer_indexer as indexer
from app.models import Prediction

_CONTRACT_ADDRESS = "0xF34c75330bEd61B7e559e554a5628b4fa50CDd24"
_FAKE_TX_HASH = "0x" + "cc" * 32


def _make_prediction(
    *,
    contract_address: str | None,
    status_key: str,
    resolution_date: datetime,
    resolution_trigger_tx_hash: str | None = None,
) -> Prediction:
    return Prediction(
        id=1,
        title="Test market",
        description="Test description",
        category="TEST",
        resolution_date=resolution_date,
        volume=0,
        status_key=status_key,
        contract_address=contract_address,
        resolution_trigger_tx_hash=resolution_trigger_tx_hash,
    )


def test_triggers_resolution_for_a_past_cutoff_open_market(monkeypatch):
    prediction = _make_prediction(
        contract_address=_CONTRACT_ADDRESS,
        status_key="open",
        resolution_date=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    captured = {}

    async def _fake_write_contract(address, function_name, args):
        captured["address"] = address
        captured["function_name"] = function_name
        captured["args"] = args
        return _FAKE_TX_HASH

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fake_write_contract)

    asyncio.run(indexer.trigger_pending_market_resolutions([prediction]))

    assert captured["address"] == _CONTRACT_ADDRESS
    assert captured["function_name"] == "resolve_market"
    assert captured["args"] == []
    assert prediction.resolution_trigger_tx_hash == _FAKE_TX_HASH


def test_skips_market_before_its_cutoff(monkeypatch):
    prediction = _make_prediction(
        contract_address=_CONTRACT_ADDRESS,
        status_key="open",
        resolution_date=datetime.now(timezone.utc) + timedelta(days=1),
    )

    def _fail_if_called(address, function_name, args):
        raise AssertionError("write_contract should never be called before the cutoff")

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(indexer.trigger_pending_market_resolutions([prediction]))  # must not raise
    assert prediction.resolution_trigger_tx_hash is None


def test_skips_already_resolved_market(monkeypatch):
    prediction = _make_prediction(
        contract_address=_CONTRACT_ADDRESS,
        status_key="RESOLVED",
        resolution_date=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    def _fail_if_called(address, function_name, args):
        raise AssertionError("write_contract should never be called for an already-resolved market")

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(indexer.trigger_pending_market_resolutions([prediction]))  # must not raise


def test_does_not_resend_an_already_triggered_market(monkeypatch):
    prediction = _make_prediction(
        contract_address=_CONTRACT_ADDRESS,
        status_key="open",
        resolution_date=datetime.now(timezone.utc) - timedelta(hours=1),
        resolution_trigger_tx_hash="0x" + "dd" * 32,
    )

    def _fail_if_called(address, function_name, args):
        raise AssertionError("write_contract should never be called for an already-triggered market")

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fail_if_called)

    asyncio.run(indexer.trigger_pending_market_resolutions([prediction]))  # must not raise


def test_failed_send_leaves_it_retryable(monkeypatch):
    prediction = _make_prediction(
        contract_address=_CONTRACT_ADDRESS,
        status_key="open",
        resolution_date=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    async def _fake_failed_write(address, function_name, args):
        return None

    monkeypatch.setattr(indexer.genlayer_write, "write_contract", _fake_failed_write)

    asyncio.run(indexer.trigger_pending_market_resolutions([prediction]))
    assert prediction.resolution_trigger_tx_hash is None
