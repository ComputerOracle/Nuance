"""GET /consensus/{job_id}, WS /consensus/ws/{job_id}, and SSE /consensus/
sse/{job_id} — all three drive the frontend's ConsensusPanel after a
deliverable/evidence submission, replacing the local stage timers plan.md
describes in nuance-app.tsx today.

The WS route is the primary path (use-consensus-polling.ts tries it first).
SSE is the ROADMAP.md Part 3 5.2 fallback tier for exactly the case WS
can't cover — a proxy/corporate network that blocks the WebSocket
upgrade handshake outright but passes plain HTTP(S) through fine, SSE
included; the frontend falls to it before giving up to raw polling
entirely, since a live push channel that only needs a normal GET beats
polling on both latency and server load. Both routes prefer Redis
pub/sub (app/services/realtime.py) over db polling when Redis is
reachable — subscribing to a shared channel every worker process can
publish into, rather than each connection independently polling the db
on its own schedule (see realtime.py's own docstring on why that
distinction matters behind more than one worker). Both fall back to the
original per-connection db-polling loop unchanged if Redis isn't
configured/reachable at all — the plain GET route above is the final,
always-available fallback beneath both.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, get_db
from app.enums import ConsensusStage
from app.models import ConsensusJob
from app.schemas import ConsensusStatus, ConsensusVerdict
from app.services.realtime import format_sse, subscribe_consensus_updates

router = APIRouter(prefix="/consensus", tags=["consensus"])
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 0.5


def _status_from_job(job: ConsensusJob) -> ConsensusStatus:
    verdict = None
    if job.verdict_label is not None:
        verdict = ConsensusVerdict(
            label=job.verdict_label,
            approved=job.verdict_approved,
            confidence=job.verdict_confidence,
            reasoning=job.verdict_reasoning,
        )
    return ConsensusStatus(stage=job.stage, validator_results=job.validator_results, verdict=verdict)


@router.get("/{job_id}", response_model=ConsensusStatus)
async def get_consensus_status(job_id: int, db: AsyncSession = Depends(get_db)) -> ConsensusStatus:
    job = await db.get(ConsensusJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consensus job not found.")
    return _status_from_job(job)


async def _get_job_or_none(job_id: int) -> ConsensusJob | None:
    # A fresh session per call, not one held for the connection's whole
    # life — SQLAlchemy's identity map would otherwise keep returning this
    # same (stale) ConsensusJob instance instead of picking up writes
    # committed by the consensus worker's own session in between polls.
    async with AsyncSessionLocal() as db:
        return await db.get(ConsensusJob, job_id)


@router.websocket("/ws/{job_id}")
async def consensus_status_ws(websocket: WebSocket, job_id: int) -> None:
    await websocket.accept()
    try:
        # Subscribe *before* reading current state — see
        # subscribe_consensus_updates's own docstring on why this order
        # closes the race between "read current state" and "start
        # listening" (a stage transition published in between would
        # otherwise be missed).
        updates = await subscribe_consensus_updates(job_id)

        job = await _get_job_or_none(job_id)
        if job is None:
            await websocket.send_json({"error": "Consensus job not found."})
            await websocket.close(code=1008)
            return

        await websocket.send_text(_status_from_job(job).model_dump_json())
        already_done = job.stage >= int(ConsensusStage.DONE)

        if updates is not None:
            if already_done:
                await websocket.close(code=1000)
                return
            async for payload in updates:
                await websocket.send_text(json.dumps(payload))
                if payload.get("stage", 0) >= int(ConsensusStage.DONE):
                    break
            await websocket.close(code=1000)
            return

        # Redis unavailable — fall back to the original per-connection db
        # polling, unchanged.
        if already_done:
            await websocket.close(code=1000)
            return
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            job = await _get_job_or_none(job_id)
            if job is None:
                await websocket.send_json({"error": "Consensus job not found."})
                await websocket.close(code=1008)
                return

            await websocket.send_text(_status_from_job(job).model_dump_json())
            if job.stage >= int(ConsensusStage.DONE):
                await websocket.close(code=1000)
                return
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — never let a bad tick crash the server, just drop this connection
        logger.exception("Consensus WS tick failed for job %s", job_id)
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass  # already closed


async def _consensus_sse_events(job_id: int) -> AsyncIterator[str]:
    """The actual stream body for consensus_status_sse below, factored out
    as its own async generator so a test can drive it directly (collecting
    a bounded number of `async for` items) without needing StreamingResponse/
    ASGI disconnect plumbing in the loop — same reasoning `_status_from_job`
    was already a standalone helper. Mirrors consensus_status_ws's own
    subscribe-before-read / pubsub-or-poll-fallback structure exactly; see
    that function's inline comments for why each piece is ordered the way
    it is. Emits a named `event: done` (see realtime.format_sse's own
    docstring on why NOT `event: error` too) specifically so the frontend
    can call `EventSource.close()` itself once the job is done — plain
    `EventSource` has no "the stream ended on purpose" signal otherwise
    and will auto-reconnect a cleanly closed connection, which for an
    already-DONE job would just be a harmless extra round trip, but is
    worth closing off cleanly regardless. The not-found case stays a bare
    `data:` payload with an `error` field instead, parsed the same way
    the WS handler's `{"error": ...}` already is.
    """
    updates = await subscribe_consensus_updates(job_id)

    job = await _get_job_or_none(job_id)
    if job is None:
        yield format_sse({"error": "Consensus job not found."})
        return

    yield format_sse(_status_from_job(job).model_dump())
    already_done = job.stage >= int(ConsensusStage.DONE)

    if updates is not None:
        if already_done:
            yield format_sse({"stage": job.stage}, event="done")
            return
        async for payload in updates:
            yield format_sse(payload)
            if payload.get("stage", 0) >= int(ConsensusStage.DONE):
                yield format_sse({"stage": payload.get("stage", 0)}, event="done")
                break
        return

    # Redis unavailable — fall back to the original per-connection db
    # polling, unchanged.
    if already_done:
        yield format_sse({"stage": job.stage}, event="done")
        return
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        job = await _get_job_or_none(job_id)
        if job is None:
            yield format_sse({"error": "Consensus job not found."})
            return

        yield format_sse(_status_from_job(job).model_dump())
        if job.stage >= int(ConsensusStage.DONE):
            yield format_sse({"stage": job.stage}, event="done")
            return


@router.get("/sse/{job_id}")
async def consensus_status_sse(job_id: int) -> StreamingResponse:
    """SSE counterpart to consensus_status_ws — see this module's own
    docstring for why it exists (ROADMAP.md Part 3 5.2's fallback tier).
    No explicit disconnect-polling here: Starlette's StreamingResponse
    already races the body-streaming task against `listen_for_disconnect`
    on the ASGI `receive` channel and cancels the former the moment the
    client goes away, which is what actually stops _consensus_sse_events's
    poll-fallback `while True` from looping forever after a client
    disconnects."""
    return StreamingResponse(
        _consensus_sse_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
