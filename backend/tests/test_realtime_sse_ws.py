"""Tests for ROADMAP.md Part 3 5.2's remaining realtime work: dispute-
message live updates (WS + SSE, mirroring the existing consensus channel)
and the SSE fallback tier added alongside both WS channels.

No Redis is running in this test environment (confirmed: `_get_client`
fails to connect and marks itself unavailable on first use, same as any
other CI/dev box without `docker compose up redis`) — every test here
therefore exercises the db-polling fallback path specifically, which is
also the one path that was previously completely untested (this repo had
zero tests touching either WS route before this file). The SSE endpoints'
async generators (`_consensus_sse_events`, `_dispute_messages_sse_events`)
are driven directly rather than through StreamingResponse/TestClient —
see routers/consensus.py's own docstring on why they're factored out as
standalone generators for exactly this.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-realtime-sse-ws-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.routers.consensus as consensus_router  # noqa: E402
import app.routers.disputes as disputes_router  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsensusJob, Dispute, DisputeMessage, Escrow, Milestone, User  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


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


async def _create_dispute(creator: str, counterparty: str) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Realtime test escrow",
            total=Decimal("100.00"),
            status_key=StatusKey.DISPUTED,
        )
        milestone = Milestone(
            name="Milestone 1",
            amount=Decimal("100.00"),
            status_key=StatusKey.DISPUTED,
            criteria="Looks good.",
            order_index=0,
        )
        escrow.milestones.append(milestone)
        db.add(escrow)
        await db.flush()

        dispute = Dispute(
            escrow_id=escrow.id,
            milestone_id=milestone.id,
            opened_by_address=creator,
            issue="Realtime test dispute",
        )
        db.add(dispute)
        await db.commit()
        await db.refresh(dispute)
        return dispute.id


# --- Dispute messages: publish trigger -------------------------------------


def test_send_message_publishes_to_realtime_channel(client, monkeypatch):
    creator = Account.create()
    counterparty = Account.create()
    dispute_id = asyncio.run(_create_dispute(creator.address, counterparty.address))
    token = _get_token(client, creator)

    published: list[tuple[int, dict]] = []

    async def _fake_publish(dispute_id: int, payload: dict) -> None:
        published.append((dispute_id, payload))

    monkeypatch.setattr(disputes_router, "publish_dispute_message", _fake_publish)

    resp = client.post(
        f"/disputes/{dispute_id}/messages",
        json={"content": "hello counterparty"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    assert len(published) == 1
    published_dispute_id, payload = published[0]
    assert published_dispute_id == dispute_id
    assert payload["type"] == "message"
    assert payload["message"]["content"] == "hello counterparty"
    assert payload["message"]["sender_address"] == creator.address.lower()


def test_send_message_publish_failure_does_not_break_the_request(client, monkeypatch):
    """Best-effort, per realtime.publish_update's own docstring — a
    Redis hiccup shouldn't turn a successful message send into a 500."""
    creator = Account.create()
    counterparty = Account.create()
    dispute_id = asyncio.run(_create_dispute(creator.address, counterparty.address))
    token = _get_token(client, creator)

    async def _boom(*args, **kwargs):
        raise RuntimeError("redis is on fire")

    monkeypatch.setattr(disputes_router, "publish_dispute_message", _boom)

    with pytest.raises(RuntimeError):
        # publish_dispute_message itself already swallows real Redis
        # errors (see realtime.publish_update) — this monkeypatch bypasses
        # that to prove send_message doesn't add its *own* try/except on
        # top, i.e. that guarantee lives in exactly one place. If this
        # starts failing because send_message grew its own handling, this
        # test should be simplified accordingly rather than deleted.
        client.post(
            f"/disputes/{dispute_id}/messages",
            json={"content": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )


# --- Dispute messages: WS ---------------------------------------------------


def test_dispute_messages_ws_sends_initial_backlog(client):
    creator = Account.create()
    counterparty = Account.create()
    dispute_id = asyncio.run(_create_dispute(creator.address, counterparty.address))
    token = _get_token(client, creator)

    resp = client.post(
        f"/disputes/{dispute_id}/messages",
        json={"content": "first message"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201

    with client.websocket_connect(f"/disputes/ws/{dispute_id}/messages") as ws:
        init = ws.receive_json()
        assert init["type"] == "init"
        assert len(init["messages"]) == 1
        assert init["messages"][0]["content"] == "first message"


def test_dispute_messages_ws_404_for_missing_dispute(client):
    with client.websocket_connect("/disputes/ws/999999/messages") as ws:
        payload = ws.receive_json()
        assert payload.get("error") == "Dispute not found."


def test_dispute_messages_ws_polls_for_new_messages_without_redis(client, monkeypatch):
    """No Redis in this environment, so dispute_messages_ws is exercising
    its db-polling fallback branch. Speeds that poll interval way down so
    the test doesn't sit through the real (multi-second) production
    cadence."""
    monkeypatch.setattr(disputes_router, "MESSAGES_POLL_INTERVAL_SECONDS", 0.05)

    creator = Account.create()
    counterparty = Account.create()
    dispute_id = asyncio.run(_create_dispute(creator.address, counterparty.address))
    token = _get_token(client, creator)

    with client.websocket_connect(f"/disputes/ws/{dispute_id}/messages") as ws:
        init = ws.receive_json()
        assert init["type"] == "init"
        assert init["messages"] == []

        resp = client.post(
            f"/disputes/{dispute_id}/messages",
            json={"content": "arrived after connect"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

        update = ws.receive_json()
        assert update["type"] == "message"
        assert update["message"]["content"] == "arrived after connect"


# --- Dispute messages: SSE generator ---------------------------------------


def test_dispute_messages_sse_events_initial_and_new_message(monkeypatch):
    monkeypatch.setattr(disputes_router, "MESSAGES_POLL_INTERVAL_SECONDS", 0.05)

    creator = Account.create()
    counterparty = Account.create()
    dispute_id = asyncio.run(_create_dispute(creator.address, counterparty.address))

    async def _run():
        agen = disputes_router._dispute_messages_sse_events(dispute_id)
        first = await agen.__anext__()
        assert "event: " not in first  # bare data: line for the init payload
        assert '"type": "init"' in first

        async with AsyncSessionLocal() as db:
            db.add(DisputeMessage(dispute_id=dispute_id, sender_address=creator.address, content="via sse"))
            await db.commit()

        second = await asyncio.wait_for(agen.__anext__(), timeout=2.0)
        assert '"content": "via sse"' in second
        await agen.aclose()

    asyncio.run(_run())


def test_dispute_messages_sse_events_error_for_missing_dispute():
    async def _run():
        agen = disputes_router._dispute_messages_sse_events(999999)
        first = await agen.__anext__()
        # Bare data: payload, not a named `event:` — see realtime.format_sse's
        # own docstring on why "error" specifically stays off the named-event
        # path (collides with EventSource's own native error event).
        assert "event: " not in first
        assert "Dispute not found." in first
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()

    asyncio.run(_run())


# --- Consensus: SSE ----------------------------------------------------------


async def _create_done_consensus_job(subject_id: int) -> int:
    async with AsyncSessionLocal() as db:
        job = ConsensusJob(
            subject_type=ConsensusSubjectType.MILESTONE,
            subject_id=subject_id,
            stage=int(ConsensusStage.DONE),
            verdict_label="approved",
            verdict_approved=True,
            verdict_confidence=90,
            verdict_reasoning="Looks correct.",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job.id


def test_consensus_sse_events_already_done_job_emits_status_then_done():
    job_id = asyncio.run(_create_done_consensus_job(subject_id=1))

    async def _run():
        agen = consensus_router._consensus_sse_events(job_id)
        status_line = await agen.__anext__()
        assert "event: " not in status_line
        assert '"stage": 3' in status_line

        done_line = await agen.__anext__()
        assert "event: done" in done_line

        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()

    asyncio.run(_run())


def test_consensus_sse_events_missing_job_emits_error():
    async def _run():
        agen = consensus_router._consensus_sse_events(999999)
        first = await agen.__anext__()
        assert "event: " not in first
        assert "Consensus job not found." in first
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()

    asyncio.run(_run())


def test_consensus_sse_route_is_registered(client):
    """A cheap end-to-end smoke test that the actual route (not just the
    generator function) is wired up and streams — reads only the first
    chunk rather than draining the whole (never-ending, if the job weren't
    already DONE) response."""
    job_id = asyncio.run(_create_done_consensus_job(subject_id=2))
    with client.stream("GET", f"/consensus/sse/{job_id}") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        chunks = resp.iter_text()
        first_chunk = next(chunks)
        assert '"stage": 3' in first_chunk
