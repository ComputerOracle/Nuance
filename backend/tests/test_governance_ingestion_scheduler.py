"""Tests for services/governance_ingestion_scheduler.py — the governance
equivalent of test_market_ingestion_scheduler.py, asked for directly once
the identical weekly-refresh request was made for Governance: "refresh
and update the Governance use the API key." Structurally an exact mirror
of that file (see governance_ingestion_scheduler.py's own module
docstring for why this isn't a generalized shared scheduler); the same
four things are covered here, against the governance module's own
AppState key and settings.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-governance-ingestion-scheduler-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.governance_ingestion_scheduler as scheduler  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AppState  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


# --- 1. is_due's pure decision logic ----------------------------------------


def test_is_due_when_never_run_before():
    assert scheduler.is_due(None, datetime.now(timezone.utc), 604800) is True


def test_not_due_when_run_recently():
    now = datetime.now(timezone.utc)
    last_run = now - timedelta(days=1)
    assert scheduler.is_due(last_run, now, 604800) is False


def test_due_again_once_interval_has_elapsed():
    now = datetime.now(timezone.utc)
    last_run = now - timedelta(days=8)
    assert scheduler.is_due(last_run, now, 604800) is True


def test_is_due_handles_naive_timestamp_same_as_sqlite_round_trip():
    now = datetime.now(timezone.utc)
    naive_recent = (now - timedelta(days=1)).replace(tzinfo=None)
    naive_old = (now - timedelta(days=8)).replace(tzinfo=None)
    assert scheduler.is_due(naive_recent, now, 604800) is False
    assert scheduler.is_due(naive_old, now, 604800) is True


# --- 2/3/4. run_once_if_due end-to-end (process_latest_events mocked) ------


async def _get_state_value(key: str) -> str | None:
    async with AsyncSessionLocal() as db:
        state = await db.get(AppState, key)
        return state.value if state else None


async def _reset_state(key: str) -> None:
    async with AsyncSessionLocal() as db:
        state = await db.get(AppState, key)
        if state is not None:
            await db.delete(state)
            await db.commit()


def test_skips_the_real_sweep_when_not_due(monkeypatch):
    async def _run():
        async with AsyncSessionLocal() as db:
            db.add(
                AppState(
                    key=scheduler._LAST_RUN_STATE_KEY,
                    value=datetime.now(timezone.utc).isoformat(),
                )
            )
            await db.commit()

        def _fail_if_called(*_args, **_kwargs):
            raise AssertionError("process_latest_events should not be called — not due yet")

        monkeypatch.setattr(scheduler, "process_latest_events", _fail_if_called)

        result = await scheduler.run_once_if_due()
        assert result == []

    asyncio.run(_run())


class _FakeProposal:
    """A minimal stand-in for a real Proposal row — run_once_if_due only
    ever reads .id/.title off whatever process_latest_events returns, for
    its own log line."""

    def __init__(self, id: int, title: str):
        self.id = id
        self.title = title


def test_runs_the_real_sweep_and_persists_the_timestamp_when_due(monkeypatch):
    fake_proposal = _FakeProposal(id=1, title="A fake proposal")

    async def _fake_process_latest_events(db, auto_publish=True):
        return [fake_proposal]

    monkeypatch.setattr(scheduler, "process_latest_events", _fake_process_latest_events)

    async def _run():
        await _reset_state(scheduler._LAST_RUN_STATE_KEY)
        before = datetime.now(timezone.utc)
        result = await scheduler.run_once_if_due()
        assert result == [fake_proposal]

        raw_value = await _get_state_value(scheduler._LAST_RUN_STATE_KEY)
        assert raw_value is not None
        persisted = datetime.fromisoformat(raw_value)
        assert persisted >= before

    asyncio.run(_run())


def test_second_call_with_no_time_elapsed_does_not_sweep_again(monkeypatch):
    calls = []

    async def _fake_process_latest_events(db, auto_publish=True):
        calls.append(1)
        return []

    monkeypatch.setattr(scheduler, "process_latest_events", _fake_process_latest_events)

    async def _run():
        await _reset_state(scheduler._LAST_RUN_STATE_KEY)
        first = await scheduler.run_once_if_due()
        second = await scheduler.run_once_if_due()
        assert first == []
        assert second == []
        assert len(calls) == 1, "the second call should have found itself not due yet"

    asyncio.run(_run())


def test_governance_and_market_scheduler_state_keys_are_independent():
    """The two schedulers must not collide on the same AppState row — see
    governance_ingestion_scheduler.py's own docstring on why this key is
    deliberately its own, not shared with market_ingestion_scheduler.py."""
    import app.services.market_ingestion_scheduler as market_scheduler

    assert scheduler._LAST_RUN_STATE_KEY != market_scheduler._LAST_RUN_STATE_KEY
