"""The AI-validator consensus engine — plan.md section 4, made real with Gemini.

`run_consensus` is scheduled as a FastAPI BackgroundTask by
routers/escrows.py and routers/disputes.py right after they synchronously
insert a queued `ConsensusJob` row and hand its id back to the caller in
the 201 response. From there this module owns the job's entire stage
lifecycle end to end: QUEUED -> ANALYZING -> DONE.

Runs its own DB session (rather than reusing the request's) since it
executes after the HTTP request that scheduled it has already returned.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.enums import ConsensusStage, ConsensusSubjectType, StatusKey
from app.models import ConsensusJob, Dispute, DisputeEvidence, DisputeMessage, Escrow, Milestone

logger = logging.getLogger(__name__)

settings = get_settings()

# Matches VALIDATOR_NAMES in the frontend's consensus-panel.tsx — rows are
# rendered by iterating this exact list, in this exact order, and
# asyncio.gather preserves that order in its results regardless of which
# call actually resolves first.
VALIDATOR_NAMES = ("Validator-Alpha", "Validator-Beta", "Validator-Gamma")

MODEL = "gemini-3.5-flash"

# Floor enforced below so a fast LLM response doesn't make the frontend's
# consensus panel flash instead of feeling like real deliberation
# (plan.md section 4.6).
MIN_DELIBERATION_SECONDS = 1.5


class ValidatorVerdict(BaseModel):
    vote: Literal["approve", "dispute"] = Field(
        description="approve if the claim or submission is justified and valid; dispute otherwise."
    )
    confidence: int = Field(
        ge=0, le=100, description="Confidence in this vote, 0-100."
    )
    reasoning: str = Field(
        description="One or two sentences explaining the verdict based on the facts and evidence."
    )


# Only network/rate-limit/server-side failures are worth retrying
_RETRYABLE_ERRORS = (errors.APIError,)


def _persona_system_prompt(name: str, subject_type: ConsensusSubjectType) -> str:
    if subject_type == ConsensusSubjectType.DISPUTE:
        return (
            f"You are {name}, one of three independent AI validators on GenLayer's Internet Court "
            "for Nuance. Your role is to adjudicate disputes between counterparties based on the "
            "agreement terms, the chat transcript/arguments exchanged, and all submitted evidence. "
            "Evaluate the claims objectively. Vote 'approve' if the claimant's dispute/evidence is "
            "justified and supported; vote 'dispute' (reject claimant's claim) if the counterparty's "
            "position is valid or if the claim lacks sufficient evidence. Provide structured JSON with "
            "vote ('approve' or 'dispute'), confidence (0-100), and concise reasoning."
        )
    return (
        f"You are {name}, one of three independent AI validators adjudicating a milestone deliverable "
        "for Nuance. Read the criteria and the submitted text, then provide your independent judgment as "
        "structured JSON with vote (approve or dispute), confidence (0-100), and reasoning. "
        "Be skeptical of vague, unsupported, or evasive submissions."
    )


def _build_user_prompt(context: str, submission_text: str) -> str:
    return (
        f"{context}\n\n"
        f"Latest Submission / Evidence:\n{submission_text}\n\n"
        "Evaluate the case based on all the facts, dialogue, and evidence provided above. "
        "Provide your vote ('approve' or 'dispute'), a confidence score (0-100), and brief reasoning."
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_validator(
    client: genai.Client,
    name: str,
    subject_type: ConsensusSubjectType,
    context: str,
    submission_text: str,
) -> dict:
    config = types.GenerateContentConfig(
        system_instruction=_persona_system_prompt(name, subject_type),
        response_mime_type="application/json",
        response_schema=ValidatorVerdict,
        temperature=0.5,
    )
    prompt = _build_user_prompt(context, submission_text)

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=config,
    )

    if response.parsed and isinstance(response.parsed, ValidatorVerdict):
        parsed = response.parsed
        return {
            "name": name,
            "vote": parsed.vote,
            "confidence": int(parsed.confidence),
            "reasoning": parsed.reasoning,
        }

    if response.text:
        data = json.loads(response.text)
        return {
            "name": name,
            "vote": data.get("vote", "dispute"),
            "confidence": int(data.get("confidence", 0)),
            "reasoning": data.get("reasoning", ""),
        }

    raise ValueError("Empty response received from validator.")


async def _run_validator(
    client: genai.Client,
    name: str,
    subject_type: ConsensusSubjectType,
    context: str,
    submission_text: str,
) -> dict:
    """A validator that exhausts its retries doesn't get to silently vanish
    from the panel — it's recorded as a zero-confidence abstention so the
    majority vote below always has three ballots to count."""
    try:
        return await _call_validator(client, name, subject_type, context, submission_text)
    except Exception as exc:  # noqa: BLE001 — any exhausted-retry failure degrades to an abstention
        logger.warning("Validator %s failed after retries: %s", name, exc)
        return {
            "name": name,
            "vote": "dispute",
            "confidence": 0,
            "reasoning": f"Validator unavailable: {exc}",
        }


def _aggregate(results: list[dict]) -> dict:
    """Majority vote decides direction; confidence is the average of the
    majority's own scores; reasoning is the majority's own reasoning
    concatenated."""
    approve = [r for r in results if r["vote"] == "approve"]
    dispute = [r for r in results if r["vote"] == "dispute"]
    majority = approve if len(approve) >= len(dispute) else dispute
    approved = majority is approve

    avg_confidence = round(sum(r["confidence"] for r in majority) / len(majority))
    reasoning = " ".join(r["reasoning"] for r in majority)

    return {
        "verdict_label": "approve" if approved else "dispute",
        "verdict_approved": approved,
        "verdict_confidence": avg_confidence,
        "verdict_reasoning": reasoning,
    }


async def _build_consensus_context(
    db: AsyncSession, subject_type: ConsensusSubjectType, subject_id: int
) -> str:
    """Builds a rich context block including conversation history, evidence,
    and agreement terms for AI evaluation."""
    if subject_type == ConsensusSubjectType.MILESTONE:
        result = await db.execute(
            select(Milestone)
            .where(Milestone.id == subject_id)
            .options(selectinload(Milestone.escrow))
        )
        milestone = result.scalar_one_or_none()
        if milestone is None:
            return "Criteria: Deliverable meets the agreed brief."
        escrow_title = milestone.escrow.title if milestone.escrow else "Escrow"
        return (
            f"Escrow: {escrow_title}\n"
            f"Milestone: {milestone.name} ({milestone.amount} USDC)\n"
            f"Agreed Criteria:\n{milestone.criteria}"
        )

    # Dispute subject — fetch complete dispute room history
    result = await db.execute(
        select(Dispute)
        .where(Dispute.id == subject_id)
        .options(
            selectinload(Dispute.escrow).selectinload(Escrow.milestones),
            selectinload(Dispute.messages),
            selectinload(Dispute.evidence),
        )
    )
    dispute = result.scalar_one_or_none()
    if dispute is None:
        return "Dispute case record."

    escrow = dispute.escrow
    escrow_title = escrow.title if escrow else "Escrow Contract"
    escrow_total = str(escrow.total) if escrow else "N/A"
    creator_addr = escrow.creator_address if escrow else "Unknown"
    counterparty_addr = escrow.counterparty_address if escrow else "Unknown"

    lines = [
        f"=== DISPUTE CASE #{dispute.id} ===",
        f"Escrow Title: {escrow_title} (Total: {escrow_total} USDC)",
        f"Escrow Creator: {creator_addr}",
        f"Escrow Counterparty: {counterparty_addr}",
        f"Claimant (Opened By): {dispute.opened_by_address}",
        f"Issue / Reason for Dispute:\n{dispute.issue}",
    ]

    # Include milestone criteria if milestone is attached
    if dispute.milestone_id and escrow:
        ms = next((m for m in escrow.milestones if m.id == dispute.milestone_id), None)
        if ms:
            lines.append(f"Milestone Criteria ({ms.name}): {ms.criteria}")

    # Conversation history
    lines.append("\n--- CHAT TRANSCRIPT BETWEEN PARTIES ---")
    if dispute.messages:
        for msg in dispute.messages:
            lines.append(f"[{msg.sender_address}]: {msg.content}")
    else:
        lines.append("(No messages in dispute room yet.)")

    # Prior evidence
    lines.append("\n--- SUBMITTED EVIDENCE RECORDS ---")
    if dispute.evidence:
        for ev in dispute.evidence:
            link_text = f" (Link: {ev.link})" if ev.link else ""
            lines.append(f"• By {ev.submitter_address}: {ev.description}{link_text}")
    else:
        lines.append("(No prior evidence records.)")

    return "\n".join(lines)


async def _latest_job(
    db: AsyncSession, subject_type: ConsensusSubjectType, subject_id: int
) -> ConsensusJob | None:
    result = await db.execute(
        select(ConsensusJob)
        .where(ConsensusJob.subject_type == subject_type, ConsensusJob.subject_id == subject_id)
        .order_by(ConsensusJob.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def run_consensus(
    subject_type: ConsensusSubjectType, subject_id: int, text_payload: str
) -> None:
    """Advances the newest ConsensusJob for (subject_type, subject_id)
    through its full stage lifecycle and persists the final verdict.
    """
    try:
        async with AsyncSessionLocal() as db:
            job = await _latest_job(db, subject_type, subject_id)
            if job is None:
                logger.error(
                    "run_consensus: no ConsensusJob for subject_type=%s subject_id=%s",
                    subject_type,
                    subject_id,
                )
                return

            # Stage 1 — Queued.
            job.stage = int(ConsensusStage.QUEUED)
            await db.commit()

            context = await _build_consensus_context(db, subject_type, subject_id)

            # Stage 2 — Analyzing.
            job.stage = int(ConsensusStage.ANALYZING)
            await db.commit()

            if not settings.gemini_api_key:
                logger.warning(
                    "GEMINI_API_KEY not set — consensus job %s completed with abstentions.",
                    job.id,
                )
                results = [
                    {
                        "name": name,
                        "vote": "dispute",
                        "confidence": 0,
                        "reasoning": "GEMINI_API_KEY not configured.",
                    }
                    for name in VALIDATOR_NAMES
                ]
            else:
                client = genai.Client(api_key=settings.gemini_api_key)
                deliberation = asyncio.gather(
                    *(
                        _run_validator(client, name, subject_type, context, text_payload)
                        for name in VALIDATOR_NAMES
                    )
                )
                results, _ = await asyncio.gather(
                    deliberation, asyncio.sleep(MIN_DELIBERATION_SECONDS)
                )

            verdict = _aggregate(results)

            # Apply state mutation to Milestone, Escrow, and Dispute models
            await _apply_verdict_to_state(
                db,
                subject_type,
                subject_id,
                verdict["verdict_approved"],
                verdict["verdict_reasoning"],
            )

            # Stage 3 — Consensus recorded.
            job.validator_results = results
            job.stage = int(ConsensusStage.DONE)
            job.verdict_label = verdict["verdict_label"]
            job.verdict_approved = verdict["verdict_approved"]
            job.verdict_confidence = verdict["verdict_confidence"]
            job.verdict_reasoning = verdict["verdict_reasoning"]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "run_consensus crashed for subject_type=%s subject_id=%s", subject_type, subject_id
        )


async def _apply_verdict_to_state(
    db: AsyncSession,
    subject_type: ConsensusSubjectType,
    subject_id: int,
    verdict_approved: bool,
    verdict_reasoning: str,
) -> None:
    """Mutates the underlying Milestone, Escrow, and Dispute statuses based
    on the AI consensus verdict."""
    if subject_type == ConsensusSubjectType.MILESTONE:
        result = await db.execute(
            select(Milestone)
            .where(Milestone.id == subject_id)
            .options(selectinload(Milestone.escrow).selectinload(Escrow.milestones))
        )
        milestone = result.scalar_one_or_none()
        if milestone is None:
            return

        if verdict_approved:
            milestone.status_key = StatusKey.APPROVED
            escrow = milestone.escrow
            if escrow:
                all_milestones = sorted(escrow.milestones, key=lambda m: m.order_index)
                all_approved = all(m.status_key == StatusKey.APPROVED for m in all_milestones)
                if all_approved:
                    escrow.status_key = StatusKey.APPROVED
                else:
                    # Advance next pending milestone to in_progress
                    for m in all_milestones:
                        if m.status_key == StatusKey.PENDING:
                            m.status_key = StatusKey.IN_PROGRESS
                            break
                    escrow.status_key = StatusKey.IN_PROGRESS
        else:
            milestone.status_key = StatusKey.DISPUTED
            if milestone.escrow:
                milestone.escrow.status_key = StatusKey.DISPUTED

    elif subject_type == ConsensusSubjectType.DISPUTE:
        result = await db.execute(
            select(Dispute)
            .where(Dispute.id == subject_id)
            .options(
                selectinload(Dispute.escrow).selectinload(Escrow.milestones),
            )
        )
        dispute = result.scalar_one_or_none()
        if dispute is None:
            return

        dispute.ruling = verdict_reasoning
        dispute.resolved_at = datetime.now(timezone.utc)
        # Bug fix: this used to be a bare `StatusKey.APPROVED` regardless of
        # verdict_approved, so a rejected claim and an upheld one were
        # indistinguishable from Dispute.status_key alone — anything reading
        # it (e.g. routers/agents.py's trust-score calc, which deliberately
        # reads ConsensusJob.verdict_approved instead for exactly this
        # reason) would see every resolved dispute as "approved".
        dispute.status_key = StatusKey.APPROVED if verdict_approved else StatusKey.REJECTED

        escrow = dispute.escrow
        if verdict_approved:
            # Claimant's dispute is upheld -> milestone and escrow marked disputed/locked
            if dispute.milestone_id and escrow:
                for m in escrow.milestones:
                    if m.id == dispute.milestone_id:
                        m.status_key = StatusKey.DISPUTED
            if escrow:
                escrow.status_key = StatusKey.DISPUTED
        else:
            # Claimant's dispute rejected (counterparty position / delivery accepted)
            if dispute.milestone_id and escrow:
                for m in escrow.milestones:
                    if m.id == dispute.milestone_id:
                        m.status_key = StatusKey.APPROVED
                all_approved = all(m.status_key == StatusKey.APPROVED for m in escrow.milestones)
                if all_approved:
                    escrow.status_key = StatusKey.APPROVED


