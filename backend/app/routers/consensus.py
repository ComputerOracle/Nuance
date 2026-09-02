"""GET /consensus/{job_id} and WS /consensus/ws/{job_id} — both drive the
frontend's ConsensusPanel after a deliverable/evidence submission, replacing
the local stage timers plan.md describes in nuance-app.tsx today.

The WS route is the primary path (use-consensus-polling.ts tries it first,
falling back to the GET route's ~500ms polling only if the socket never
connects or drops early) — it exists because a single long-lived connection
beats one HTTP round-trip every 500ms, not because it pushes on real
events: there's no pub/sub between the consensus worker and this process,
so the handler just polls the db server-side on the same cadence and
forwards whatever changed.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, get_db
from app.enums import ConsensusStage
from app.models import ConsensusJob
from app.schemas import ConsensusStatus, ConsensusVerdict

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


@router.websocket("/ws/{job_id}")
async def consensus_status_ws(websocket: WebSocket, job_id: int) -> None:
    await websocket.accept()
    try:
        while True:
            # A fresh session per tick, not one held for the connection's
            # whole life — SQLAlchemy's identity map would otherwise keep
            # returning this same (stale) ConsensusJob instance instead of
            # picking up writes committed by the consensus worker's own
            # session in between polls.
            async with AsyncSessionLocal() as db:
                job = await db.get(ConsensusJob, job_id)

            if job is None:
                await websocket.send_json({"error": "Consensus job not found."})
                await websocket.close(code=1008)
                return

            payload = _status_from_job(job)
            await websocket.send_text(payload.model_dump_json())

            if job.stage >= int(ConsensusStage.DONE):
                await websocket.close(code=1000)
                return

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — never let a bad tick crash the server, just drop this connection
        logger.exception("Consensus WS tick failed for job %s", job_id)
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass  # already closed
