"""The AI-validator consensus engine — plan.md section 4, now backed by
three distinct providers instead of three calls to the same one.

`run_consensus` is scheduled as a FastAPI BackgroundTask by
routers/escrows.py and routers/disputes.py right after they synchronously
insert a queued `ConsensusJob` row and hand its id back to the caller in
the 201 response. From there this module owns the job's entire stage
lifecycle end to end: QUEUED -> ANALYZING -> DONE.

Runs its own DB session (rather than reusing the request's) since it
executes after the HTTP request that scheduled it has already returned.

--- Multi-model consensus ------------------------------------------------

Each validator persona has its own primary provider and its own persona
flavor (mirrors plan.md's "three independent minds" framing rather than
three copies of the same model):

  - Validator-Alpha ("The Formalist") -> Google Gemini
  - Validator-Beta  ("The Realist")   -> Anthropic Claude
  - Validator-Gamma ("The Auditor")   -> OpenAI

`VALIDATOR_NAMES` itself is unchanged from the single-provider version —
routers/validators.py's stats and the frontend's ConsensusPanel both match
on this exact list/order (see routers/validators.py's docstring), and
nothing about switching providers requires renaming the personas.

Resilient fallback: `_run_validator_with_fallback` tries a persona's
primary provider first, then walks the remaining two providers in
`_fallback_chain` order on *any* failure — a missing API key, a 429, a
connection timeout, a 5xx, or anything else an SDK call can raise. If
every provider is unconfigured or fails, it degrades to
`_deterministic_heuristic_verdict` (a keyword-driven, hash-seeded stand-in
verdict — same input always produces the same output) rather than ever
failing the consensus job outright. Every hop is logged as a warning for
observability.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Literal

import anthropic
import httpx
import openai
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
from app.services.prompt_safety import (
    PROMPT_INJECTION_DEFENSE,
    fence_user_content,
    scan_for_injection,
)
from app.services.realtime import publish_consensus_update
from app.services.webhooks import schedule_notify as schedule_webhook_notify

logger = logging.getLogger(__name__)

settings = get_settings()

# Matches VALIDATOR_NAMES in the frontend's consensus-panel.tsx — rows are
# rendered by iterating this exact list, in this exact order, and
# asyncio.gather preserves that order in its results regardless of which
# call actually resolves first.
VALIDATOR_NAMES = ("Validator-Alpha", "Validator-Beta", "Validator-Gamma")

PERSONA_TITLES: dict[str, str] = {
    "Validator-Alpha": "The Formalist",
    "Validator-Beta": "The Realist",
    "Validator-Gamma": "The Auditor",
}

# Each persona's primary provider — see module docstring.
PERSONA_PRIMARY_PROVIDER: dict[str, str] = {
    "Validator-Alpha": "gemini",
    "Validator-Beta": "anthropic",
    "Validator-Gamma": "openai",
}

PROVIDER_MODELS: dict[str, str] = {
    # "gemini-2.5-flash" retired 2026-09-08 (Google's own 404: "no longer
    # available to new users") — confirmed live that both -3.5 and -3.6
    # flash work now; using -3.5 to match services/market_generator.py's
    # own EXTRACTION_MODEL, already proven live elsewhere in this exact
    # codebase, rather than introduce a third distinct model name.
    "gemini": "gemini-3.5-flash",
    "anthropic": "claude-3-5-sonnet-latest",
    "openai": "gpt-4o-mini",
}

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


def _persona_system_prompt(name: str, subject_type: ConsensusSubjectType) -> str:
    # Deliberately says "for Nuance," not "on GenLayer's Internet Court" —
    # this is our own backend calling three commercial LLM APIs directly
    # and majority-voting the result in this file's own Python, not
    # GenLayer's real on-chain NuanceDisputeCourt/GenVM validator
    # consensus (that only happens once a dispute is linked to that
    # deployed contract — see services/genlayer_indexer.py's
    # trigger_pending_adjudications instead). "Internet Court" is that
    # real contract's actual name; claiming this off-chain path runs "on"
    # it would be the exact fiction fixed elsewhere in this pass (see
    # services/prediction_oracle.py's own module docstring).
    title = PERSONA_TITLES.get(name, name)
    if subject_type == ConsensusSubjectType.DISPUTE:
        return (
            f"You are {name} ('{title}'), one of three independent AI validators for Nuance's "
            "off-chain dispute review. Your role is to adjudicate disputes between counterparties "
            "based on the agreement terms, the chat transcript/arguments exchanged, and all "
            "submitted evidence. Evaluate the claims objectively. Vote 'approve' if the claimant's "
            "dispute/evidence is justified and supported; vote 'dispute' (reject claimant's claim) "
            "if the counterparty's position is valid or if the claim lacks sufficient evidence. "
            "If live-fetched page content is included below, weigh it as ground truth over the "
            "submitter's own description of it — a claim contradicted by or unsupported by that "
            "fetched content should not be taken at face value just because it reads convincingly. "
            "Provide structured JSON with vote ('approve' or 'dispute'), confidence (0-100), and "
            f"concise reasoning. {PROMPT_INJECTION_DEFENSE}"
        )
    return (
        f"You are {name} ('{title}'), one of three independent AI validators adjudicating a "
        "milestone deliverable for Nuance. Read the criteria and the submitted text, then provide "
        "your independent judgment as structured JSON with vote (approve or dispute), confidence "
        "(0-100), and reasoning. Be skeptical of vague, unsupported, or evasive submissions. If "
        "live-fetched page content is included below, weigh it as ground truth over the "
        "submitter's own description of it — a claim contradicted by or unsupported by that "
        "fetched content should not be taken at face value just because it reads convincingly. "
        f"{PROMPT_INJECTION_DEFENSE}"
    )


# --- Live URL verification --------------------------------------------------
#
# FIXED 2026-09-12 — a real gap found live: this off-chain path judged
# *only* the submitter's own typed text, with no way to check whether a
# claimed link even existed, let alone actually supported the claim (a
# submission could say "see https://example.com/proof" and be judged
# purely on how convincing that sentence sounded). escrow-detail-view.tsx's
# own deliverable placeholder ("Paste deliverable URL, PR link, or
# describe the completed work for AI review…") already implied a pasted
# URL would be reviewed — nothing ever fetched one. The on-chain path
# doesn't have this gap: contracts/nuance_escrow.py's submit_deliverable
# (gl.nondet.web.render) and nuance_dispute_court.py's adjudicate_dispute
# (gl.nondet.web.get) both already fetch a submitted URL as part of the
# real GenVM verdict. This closes the same gap off-chain, in the same
# spirit: best-effort, never fatal, truncated, and clearly labeled as
# live-fetched so validators can compare it against the claim rather than
# trust the claim on its own.
_URL_PATTERN = re.compile(r"https?://[^\s<>\"')]+")
# Matches nuance_dispute_court.py's own truncation length for its
# equivalent fetch — plenty for an LLM to judge relevance/support without
# risking a huge page blowing the prompt's own context budget.
_MAX_FETCHED_CHARS = 3000


def _extract_first_url(text: str) -> str | None:
    """Only the first URL in a submission is fetched — mirrors
    nuance_dispute_court.py's own "only the most recently added URL is
    fetched" scope limit (that contract's docstring explains why: bounding
    how much untrusted, potentially slow, external fetching one judgment
    can trigger). Every URL the submitter typed still reaches the
    validators verbatim as part of the submission text either way."""
    match = _URL_PATTERN.search(text)
    return match.group(0) if match else None


async def _fetch_url_for_verification(url: str) -> str:
    """Best-effort live fetch of a URL a submission points at. Never
    raises — an unreachable, slow, or non-HTML URL becomes an honest note
    in the prompt instead of failing the whole consensus job, same
    reasoning as nuance_dispute_court.py's own try/except around
    gl.nondet.web.get."""
    headers = {"User-Agent": "NuanceConsensus/1.0 (+https://genlayer.com)"}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"(This URL was unreachable or timed out: {exc})"

    content_type = response.headers.get("content-type", "")
    if "html" in content_type:
        try:
            from bs4 import BeautifulSoup

            text = BeautifulSoup(response.text, "html.parser").get_text(separator=" ", strip=True)
        except ImportError:
            text = response.text
    else:
        text = response.text

    return text[:_MAX_FETCHED_CHARS] or "(The page loaded but had no readable text content.)"


def _build_user_prompt(context: str, submission_text: str) -> str:
    # Both blocks are fenced independently (see prompt_safety.py) — the
    # context block already carries earlier submissions/evidence in its
    # own right (services/consensus.py::_build_consensus_context), so it
    # needs the same "this is data" framing as the latest submission does.
    return (
        f"{fence_user_content('case context', context)}\n\n"
        f"{fence_user_content('latest submission or evidence', submission_text)}\n\n"
        "Evaluate the case based on all the facts, dialogue, and evidence provided above. "
        "Provide your vote ('approve' or 'dispute'), a confidence score (0-100), and brief reasoning."
    )


def _result_from_verdict(name: str, verdict: ValidatorVerdict) -> dict:
    return {
        "name": name,
        "vote": verdict.vote,
        "confidence": int(verdict.confidence),
        "reasoning": verdict.reasoning,
    }


# --- Provider calls ---------------------------------------------------------
#
# One `_call_<provider>` per SDK, each with its own retry policy for that
# SDK's own transient-error types (rate limits, connection issues, 5xx).
# Retries are exhausted *within* a provider before `_run_validator_with_
# fallback` below gives up on it and moves to the next one in the chain —
# so a single 429 doesn't immediately burn a fallback hop.

_GEMINI_RETRYABLE_ERRORS = (errors.APIError,)


@retry(
    retry=retry_if_exception_type(_GEMINI_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_gemini(
    client: genai.Client,
    model: str,
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
    response = await client.aio.models.generate_content(
        model=model,
        contents=_build_user_prompt(context, submission_text),
        config=config,
    )

    if response.parsed and isinstance(response.parsed, ValidatorVerdict):
        return _result_from_verdict(name, response.parsed)
    if response.text:
        return _result_from_verdict(name, ValidatorVerdict(**json.loads(response.text)))
    raise ValueError("Empty response received from Gemini validator.")


_ANTHROPIC_RETRYABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)

# Forcing this exact tool call is Anthropic's structured-output equivalent
# of Gemini's response_schema / OpenAI's response_format=json_object.
_ANTHROPIC_VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": "Submit your structured validator verdict for this case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vote": {"type": "string", "enum": ["approve", "dispute"]},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "reasoning": {"type": "string"},
        },
        "required": ["vote", "confidence", "reasoning"],
    },
}


@retry(
    retry=retry_if_exception_type(_ANTHROPIC_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_anthropic(
    client: anthropic.AsyncAnthropic,
    model: str,
    name: str,
    subject_type: ConsensusSubjectType,
    context: str,
    submission_text: str,
) -> dict:
    response = await client.messages.create(
        model=model,
        max_tokens=512,
        # `temperature` removed 2026-09-08 — confirmed by inspecting the
        # actually-installed anthropic==1.0.0 SDK's real
        # AsyncMessages.create signature directly: it has no such
        # parameter at all (a real API surface change, not a typo on our
        # end). Passing it made every Anthropic call fail outright,
        # silently falling every dispute/milestone judgment through to
        # the offline heuristic fallback instead — found live, tracing a
        # ruling that claimed to be real GenVM consensus but was actually
        # keyword-matching. Re-check this SDK's docs for the current
        # equivalent (if any) before assuming none exists, if
        # determinism control is ever actually needed here.
        system=_persona_system_prompt(name, subject_type),
        messages=[{"role": "user", "content": _build_user_prompt(context, submission_text)}],
        tools=[_ANTHROPIC_VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "submit_verdict"},
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_verdict":
            return _result_from_verdict(name, ValidatorVerdict(**block.input))
    raise ValueError("Anthropic response did not include the expected submit_verdict tool call.")


_OPENAI_RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


@retry(
    retry=retry_if_exception_type(_OPENAI_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _call_openai(
    client: openai.AsyncOpenAI,
    model: str,
    name: str,
    subject_type: ConsensusSubjectType,
    context: str,
    submission_text: str,
) -> dict:
    system_prompt = (
        f"{_persona_system_prompt(name, subject_type)}\n\n"
        "Respond with only a single json object (no prose, no markdown fences) containing "
        "exactly these keys: \"vote\" ('approve' or 'dispute'), \"confidence\" (integer 0-100), "
        "\"reasoning\" (string)."
    )
    response = await client.chat.completions.create(
        model=model,
        temperature=0.5,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_user_prompt(context, submission_text)},
        ],
    )

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise ValueError("Empty response received from OpenAI validator.")
    return _result_from_verdict(name, ValidatorVerdict(**json.loads(content)))


_ProviderCaller = Callable[
    [object, str, str, ConsensusSubjectType, str, str], Awaitable[dict]
]

_PROVIDER_CALLERS: dict[str, _ProviderCaller] = {
    "gemini": _call_gemini,
    "anthropic": _call_anthropic,
    "openai": _call_openai,
}

# Fallback rotation order, before rotating each persona to start on its own
# primary — see _fallback_chain.
_CANONICAL_PROVIDER_ORDER: tuple[str, ...] = ("gemini", "anthropic", "openai")


def _fallback_chain(primary: str) -> tuple[str, ...]:
    """Primary first, then the remaining providers in their canonical
    order — e.g. Validator-Beta's Anthropic primary falls back
    Anthropic -> Gemini -> OpenAI."""
    return (primary, *(p for p in _CANONICAL_PROVIDER_ORDER if p != primary))


def _build_provider_clients(app_settings) -> dict[str, object]:
    """Only providers with a configured API key get a client — an
    unconfigured provider is skipped in `_run_validator_with_fallback`
    without ever attempting a network call."""
    clients: dict[str, object] = {}
    if app_settings.gemini_api_key:
        clients["gemini"] = genai.Client(api_key=app_settings.gemini_api_key)
    if app_settings.anthropic_api_key:
        clients["anthropic"] = anthropic.AsyncAnthropic(api_key=app_settings.anthropic_api_key)
    if app_settings.openai_api_key:
        clients["openai"] = openai.AsyncOpenAI(api_key=app_settings.openai_api_key)
    return clients


# --- Deterministic offline heuristic ---------------------------------------

_HEURISTIC_POSITIVE_SIGNALS: tuple[str, ...] = (
    "completed", "delivered", "verified", "confirmed", "resolved", "shipped",
    "passed", "matches", "attached", "documented", "approved", "satisfied",
    "done", "fixed",
)
# Deliberately no bare "evidence"/"proof" here — those nouns are neutral on
# their own (e.g. "no evidence"/"lacks proof" is a *negative* signal), so
# treating them as inherently positive would misread a denial as an
# endorsement. The negative list below covers evidence/proof only in their
# explicitly-negated forms instead.
_HEURISTIC_NEGATIVE_SIGNALS: tuple[str, ...] = (
    "missing", "incomplete", "unable", "lacks", "lacking", "failed", "fail",
    "no evidence", "lack of evidence", "insufficient evidence",
    "without evidence", "unproven", "unsupported", "not done", "did not",
    "didn't", "never", "broken", "unresolved", "pending", "unverified",
    "false",
)


def _deterministic_heuristic_verdict(name: str, submission_text: str) -> dict:
    """Every provider in this validator's fallback chain was either
    unconfigured or failed. Rather than failing the consensus job (or, the
    old behavior, silently abstaining at zero confidence), produce a
    deterministic, keyword-driven stand-in verdict — same philosophy as
    services/market_generator.py's own `_extract_market_offline`. Same
    input always produces the same output, so this is exercisable and
    assertable in tests with no network call at all.
    """
    haystack = submission_text.lower()
    positive_hits = sum(1 for signal in _HEURISTIC_POSITIVE_SIGNALS if signal in haystack)
    negative_hits = sum(1 for signal in _HEURISTIC_NEGATIVE_SIGNALS if signal in haystack)
    approved = positive_hits > negative_hits

    # Deterministic but not a fixed number — derived from a stable hash of
    # the actual input so different submissions land on different
    # (reproducible) scores, bounded to a modest range since this is a
    # heuristic stand-in, not a real judgment.
    digest = hashlib.sha256(f"{name}:{submission_text}".encode("utf-8")).hexdigest()
    confidence = 40 + (int(digest[:4], 16) % 21)  # 40-60

    return {
        "name": name,
        "vote": "approve" if approved else "dispute",
        "confidence": confidence,
        "reasoning": (
            f"Offline heuristic fallback: no LLM provider was reachable for {name}. Matched "
            f"{positive_hits} positive vs {negative_hits} negative signal keyword(s) in the "
            "submission — a deterministic stand-in, not an independent AI judgment."
        ),
    }


async def _run_validator_with_fallback(
    clients: dict[str, object],
    name: str,
    subject_type: ConsensusSubjectType,
    context: str,
    submission_text: str,
) -> dict:
    """Tries `name`'s persona-assigned primary provider first, then walks
    the rest of `_fallback_chain` on any failure — a missing key (skipped
    without a network call), or an exhausted-retries exception from the
    provider itself (429, timeout, 5xx, or anything else). Never raises:
    if every provider is unconfigured or fails, returns
    `_deterministic_heuristic_verdict` instead of failing the job.
    """
    primary = PERSONA_PRIMARY_PROVIDER[name]
    chain = _fallback_chain(primary)
    last_error: Exception | None = None

    for provider in chain:
        client = clients.get(provider)
        if client is None:
            logger.warning(
                "Validator %s: provider '%s' has no API key configured — skipping.",
                name, provider,
            )
            continue

        try:
            result = await _PROVIDER_CALLERS[provider](
                client, PROVIDER_MODELS[provider], name, subject_type, context, submission_text
            )
        except Exception as exc:  # noqa: BLE001 — any failure tries the next provider in the chain
            last_error = exc
            logger.warning(
                "Validator %s: provider '%s' failed (%s) — falling back to the next provider.",
                name, provider, exc,
            )
            continue

        if provider != primary:
            logger.warning(
                "Validator %s: served by fallback provider '%s' (primary '%s' was unavailable).",
                name, provider, primary,
            )
        result["provider"] = provider
        return result

    logger.warning(
        "Validator %s: every configured provider failed%s — using the deterministic offline "
        "heuristic instead of failing the consensus job.",
        name,
        f" (last error: {last_error})" if last_error is not None else " (none were configured)",
    )
    result = _deterministic_heuristic_verdict(name, submission_text)
    result["provider"] = "heuristic"
    return result


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
            f"Milestone: {milestone.name} ({milestone.amount} GEN)\n"
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
        f"Escrow Title: {escrow_title} (Total: {escrow_total} GEN)",
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


def _publishable_status(job: ConsensusJob) -> dict:
    """Same shape as routers/consensus.py's ConsensusStatus response
    model — the WS handler forwards this dict straight to the browser
    as-is, so the two must stay in sync (a schema import here would be a
    circular import: routers imports this module's run_consensus)."""
    verdict = None
    if job.verdict_label is not None:
        verdict = {
            "label": job.verdict_label,
            "approved": job.verdict_approved,
            "confidence": job.verdict_confidence,
            "reasoning": job.verdict_reasoning,
        }
    return {"stage": job.stage, "validator_results": job.validator_results, "verdict": verdict}


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

            flags = scan_for_injection(text_payload)
            if flags:
                # Not a rejection (see prompt_safety.py's own docstring on
                # why a heuristic this cheap shouldn't block on its own) —
                # a clearly grep-able signal for review, and the fencing
                # in _build_user_prompt is what actually defends the
                # prompt regardless of whether this fired.
                logger.warning(
                    "Possible prompt injection in consensus job %s (subject_type=%s "
                    "subject_id=%s): matched %s",
                    job.id, subject_type, subject_id, flags,
                )

            # Live URL verification (see _fetch_url_for_verification's own
            # docstring for the full account) — if the submission points
            # at a URL, fetch it for real and hand validators the actual
            # page content alongside the claim, rather than letting them
            # judge the claim on its own telling. Best-effort: a fetch
            # failure becomes an honest note in the prompt, never a
            # reason to fail this job.
            submission_url = _extract_first_url(text_payload)
            if submission_url:
                fetched_content = await _fetch_url_for_verification(submission_url)
                url_flags = scan_for_injection(fetched_content)
                if url_flags:
                    # Extra-worth logging here specifically, same reasoning
                    # as prediction_oracle.py's own note on ingested content:
                    # this text came from an arbitrary external page nobody
                    # at Nuance wrote or reviewed, unlike a wallet's own
                    # typed submission.
                    logger.warning(
                        "Possible prompt injection in fetched URL %s for consensus job %s: %s",
                        submission_url, job.id, url_flags,
                    )
                text_payload = (
                    f"{text_payload}\n\n"
                    f"--- Live-fetched content actually found at {submission_url} "
                    "(verify the claim above against this, don't just trust the "
                    f"submitter's own description of it) ---\n{fetched_content}"
                )

            # Stage 1 — Queued.
            job.stage = int(ConsensusStage.QUEUED)
            await db.commit()
            await publish_consensus_update(job.id, _publishable_status(job))

            context = await _build_consensus_context(db, subject_type, subject_id)

            # Stage 2 — Analyzing.
            job.stage = int(ConsensusStage.ANALYZING)
            await db.commit()
            await publish_consensus_update(job.id, _publishable_status(job))

            clients = _build_provider_clients(settings)
            if not clients:
                logger.warning(
                    "No LLM provider API keys configured (gemini/anthropic/openai) — "
                    "consensus job %s will use the deterministic offline heuristic for "
                    "every validator.",
                    job.id,
                )

            deliberation = asyncio.gather(
                *(
                    _run_validator_with_fallback(clients, name, subject_type, context, text_payload)
                    for name in VALIDATOR_NAMES
                )
            )
            results, _ = await asyncio.gather(
                deliberation, asyncio.sleep(MIN_DELIBERATION_SECONDS)
            )

            verdict = _aggregate(results)

            # Apply state mutation to Milestone, Escrow, and Dispute models
            affected_escrow_id = await _apply_verdict_to_state(
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
            await publish_consensus_update(job.id, _publishable_status(job))
            if affected_escrow_id is not None:
                # Imported inline — routers/escrows.py already imports
                # from this module (run_consensus), so a top-level import
                # the other way would be circular.
                from app.routers.escrows import _publish_escrow_snapshot

                await _publish_escrow_snapshot(affected_escrow_id)
            # Fire-and-forget (services/webhooks.py's own contract) — a
            # subscriber's callback being slow/down must never delay or
            # fail the consensus job itself. Same completion point Redis's
            # publish above fires from, just a different transport.
            schedule_webhook_notify(
                "consensus.completed", {"job_id": job.id, **_publishable_status(job)}
            )
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
) -> int | None:
    """Mutates the underlying Milestone, Escrow, and Dispute statuses based
    on the AI consensus verdict. Returns the affected Escrow's id (or
    None if the subject itself no longer exists) — added 2026-09-12 so
    every caller (services/consensus.py's own run_consensus,
    services/genlayer_indexer.py's on-chain view-sync, both call sites
    below) can publish a fresh escrow snapshot after its own commit (see
    routers/escrows.py::_publish_escrow_snapshot) without each one
    re-deriving which escrow this verdict actually touched."""
    if subject_type == ConsensusSubjectType.MILESTONE:
        result = await db.execute(
            select(Milestone)
            .where(Milestone.id == subject_id)
            .options(selectinload(Milestone.escrow).selectinload(Escrow.milestones))
        )
        milestone = result.scalar_one_or_none()
        if milestone is None:
            return None

        milestone.reasoning = verdict_reasoning

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

        return milestone.escrow.id if milestone.escrow else None

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
            return None

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

        return escrow.id if escrow else None

    return None
