"""Nuance's own off-chain prediction-market resolution service.

Resolves prediction markets by querying our own backend's 3-persona Gemini
ensemble directly (asking the same model three times with three different
personas, then majority-voting the results in this file's own Python) and
calculates deterministic pari-mutuel payouts. Despite the persona wording
used to exist here, this is NOT GenLayer's real on-chain Intelligent
Oracle / GenVM validator consensus — no blockchain, no independent
validator nodes, nothing decentralized about it. A market only gets that
real thing once it's linked to a deployed NuancePredictionMarket contract
(contract_address set) — see services/genlayer_indexer.py's
trigger_pending_market_resolutions, the actual on-chain equivalent this
file's off-chain path exists as a fallback/legacy alternative to. Fixed
2026-09-08 after this distinction was found to be dangerously blurred:
the system prompt below used to instruct the model to literally roleplay
as "an independent validator node of the GenLayer Intelligent Oracle
consensus network," and the reasoning text shown to users echoed that
fiction back verbatim — indistinguishable from a real on-chain result.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models import Prediction
from app.services.payout import calculate_prediction_payouts
from app.services.prompt_safety import PROMPT_INJECTION_DEFENSE, fence_user_content, scan_for_injection

logger = logging.getLogger(__name__)
settings = get_settings()

VALIDATOR_NAMES = ("Validator-Alpha", "Validator-Beta", "Validator-Gamma")
MODEL = "gemini-2.5-flash"


class OracleUnavailableError(RuntimeError):
    """Raised instead of ever fabricating a resolution — see
    resolve_prediction_market's api_key check. routers/predictions.py
    maps this to a 503, distinct from the existing ValueError->404
    mapping (not found / too early to resolve), since this is neither:
    the market is real and resolvable, the oracle just isn't reachable
    right now."""

_RETRYABLE_ERRORS = (
    errors.APIError,
    errors.ServerError,
    errors.ClientError,
    TimeoutError,
    asyncio.TimeoutError,
)


class OracleValidatorVerdict(BaseModel):
    outcome: Literal["YES", "NO"] = Field(
        description="The resolved outcome: 'YES' if criteria are met, 'NO' otherwise."
    )
    confidence: int = Field(
        ge=0, le=100, description="Confidence score from 0 to 100."
    )
    reasoning: str = Field(
        description="Structured rationale explaining why this market resolves to YES or NO."
    )


def _oracle_system_prompt(name: str) -> str:
    # Factual about what this actually is — see this module's own
    # docstring for why: {name} is one of three roles this app's own
    # backend asks the same underlying model to play, majority-voted in
    # Python right here, not a real GenLayer/GenVM validator node. Telling
    # the model to roleplay as literal on-chain infrastructure it isn't
    # is exactly the fiction that made a fallback-mode failure (see
    # resolve_prediction_market's api_key check) look like a real result.
    return (
        f"You are {name}, one of three independent AI reviewers Nuance's own backend "
        "consults directly to help resolve a prediction market. You are not part of "
        "GenLayer's on-chain validator network — this is an off-chain judgment call, not a "
        "blockchain consensus result. Analyze the prediction market question and its "
        "resolution criteria against public records and metrics. "
        "Provide your independent judgment as structured JSON with outcome ('YES' or 'NO'), confidence (0-100), and reasoning. "
        f"{PROMPT_INJECTION_DEFENSE}"
    )


def _oracle_user_prompt(prediction: Prediction) -> str:
    # Fenced (app/services/prompt_safety.py) — a market's title/description
    # is not wallet-submitted the way a deliverable/dispute evidence is,
    # but it can originate from scraped, adversarial internet content via
    # services/market_generator.py (a tweet, an RSS item, a scraped page),
    # which makes it at least as untrusted as user input. This decides a
    # real payout, so it gets the same treatment as consensus.py's prompts,
    # not less.
    market_details = (
        f"Prediction Market Title: {prediction.title}\n"
        f"Category: {prediction.category}\n"
        f"Resolution Criteria / Details:\n{prediction.description}\n"
        f"Target Resolution Date: {prediction.resolution_date.isoformat()}"
    )
    return (
        f"{fence_user_content('market details', market_details)}\n\n"
        "Evaluate the resolution criteria against verifiable ground truth. "
        "Decide whether the market resolves to YES or NO with supporting reasoning and confidence."
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.5, max=4),
    reraise=True,
)
async def _call_oracle_validator(
    client: genai.Client,
    name: str,
    prediction: Prediction,
) -> dict:
    config = types.GenerateContentConfig(
        system_instruction=_oracle_system_prompt(name),
        response_mime_type="application/json",
        response_schema=OracleValidatorVerdict,
        temperature=0.4,
    )
    prompt = _oracle_user_prompt(prediction)

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=config,
    )

    if response.parsed and isinstance(response.parsed, OracleValidatorVerdict):
        return {
            "name": name,
            "outcome": response.parsed.outcome.upper(),
            "confidence": int(response.parsed.confidence),
            "reasoning": response.parsed.reasoning,
        }

    if response.text:
        data = json.loads(response.text)
        outcome = data.get("outcome", "NO").upper()
        if outcome not in ("YES", "NO"):
            outcome = "NO"
        return {
            "name": name,
            "outcome": outcome,
            "confidence": int(data.get("confidence", 0)),
            "reasoning": data.get("reasoning", ""),
        }

    return {
        "name": name,
        "outcome": "NO",
        "confidence": 0,
        "reasoning": "Empty response received.",
    }


async def _run_single_oracle_validator(
    client: genai.Client,
    name: str,
    prediction: Prediction,
) -> dict:
    try:
        return await _call_oracle_validator(client, name, prediction)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Oracle validator %s failed: %s", name, exc)
        return {
            "name": name,
            "outcome": "NO",
            "confidence": 0,
            "reasoning": f"Validator failed to reach consensus: {exc}",
        }


async def resolve_prediction_market(
    prediction_id: int,
    db: AsyncSession,
) -> Prediction:
    # Row-locked (ROADMAP.md Part 3 5.4) — without this, two concurrent
    # resolve calls (or a resolve racing a bet in routers/predictions.py::
    # place_bet, which takes the same lock) can both pass the "not yet
    # resolved" check below before either commits, both burn a real
    # Gemini call, and both attempt to write a (possibly conflicting)
    # outcome/payout. A no-op on SQLite, a real lock on Postgres — see
    # routers/predictions.py's _get_prediction_for_update_or_404 for the
    # matching half of this on the betting side.
    result = await db.execute(
        select(Prediction)
        .where(Prediction.id == prediction_id)
        .options(selectinload(Prediction.positions))
        .with_for_update()
    )
    prediction = result.scalar_one_or_none()
    if prediction is None:
        raise ValueError(f"Prediction market {prediction_id} not found.")

    if prediction.status_key.upper() == "RESOLVED":
        return prediction

    flags = scan_for_injection(f"{prediction.title}\n{prediction.description}")
    if flags:
        # Not a rejection (see prompt_safety.py's own docstring) — a
        # grep-able signal for review; the fencing in _oracle_user_prompt
        # is what actually defends the prompt regardless of whether this
        # fired. Extra-worth logging here specifically since, unlike a
        # wallet's own deliverable/evidence submission, this text may
        # have come from an ingested tweet/webpage nobody at Nuance wrote
        # or reviewed (services/market_generator.py).
        logger.warning(
            "Possible prompt injection in prediction market %s title/description: %s",
            prediction_id, flags,
        )

    now = datetime.now(timezone.utc)
    res_date = (
        prediction.resolution_date
        if prediction.resolution_date.tzinfo is not None
        else prediction.resolution_date.replace(tzinfo=timezone.utc)
    )
    if now < res_date:
        raise ValueError(
            f"Market cannot be resolved before its resolution date: {prediction.resolution_date.isoformat()}"
        )


    api_key = settings.gemini_api_key
    if not api_key:
        # FIXED 2026-09-08 — this used to silently resolve every market to
        # a hardcoded YES ("Standard simulated ground-truth verification
        # succeeded") regardless of the actual question, whenever the
        # Gemini key was unset. That's a real-money-affecting landmine,
        # not a graceful degrade: pari-mutuel payouts (calculate_
        # prediction_payouts below) would pay out real bets on a made-up
        # answer with no basis in the market's actual criteria. Raising
        # here instead leaves the market's status untouched (still
        # whatever it was — "open," not some new terminal-looking value)
        # so it can simply be retried once the oracle is actually
        # reachable; the row lock this function already holds rolls back
        # with the transaction, same as the "too early" ValueError path
        # above already does.
        logger.error(
            "GEMINI_API_KEY not set — cannot resolve prediction %s; oracle unavailable.",
            prediction_id,
        )
        raise OracleUnavailableError(
            "The prediction-market oracle is not configured (missing GEMINI_API_KEY). "
            "This market has not been resolved — try again once it's configured."
        )
    client = genai.Client(api_key=api_key)
    validator_results = await asyncio.gather(
        *[
            _run_single_oracle_validator(client, name, prediction)
            for name in VALIDATOR_NAMES
        ]
    )

    # 2-of-3 majority calculation
    yes_votes = [r for r in validator_results if r["outcome"] == "YES"]
    no_votes = [r for r in validator_results if r["outcome"] == "NO"]

    if len(yes_votes) >= len(no_votes):
        final_outcome = "YES"
        majority_votes = yes_votes
    else:
        final_outcome = "NO"
        majority_votes = no_votes

    avg_confidence = (
        round(sum(v["confidence"] for v in majority_votes) / len(majority_votes))
        if majority_votes
        else 0
    )
    reasons = [f"[{v['name']}]: {v['reasoning']}" for v in majority_votes]
    # Factual, not "GenLayer Intelligent Oracle" — this text is shown to
    # users verbatim as the market's resolution reasoning; claiming
    # GenLayer/on-chain involvement here would be exactly the fiction
    # this module's own docstring documents fixing. A market resolved via
    # the REAL on-chain oracle never reaches this function at all — see
    # services/genlayer_indexer.py's own resolution path instead.
    consensus_reasoning = (
        f"Nuance off-chain AI review, 2-of-3 agreement ({final_outcome}, {avg_confidence}% confidence). "
        + " ".join(reasons)
    )

    # Apply outcome and calculate payouts
    prediction.status_key = "RESOLVED"
    prediction.outcome = final_outcome
    prediction.resolution_reasoning = consensus_reasoning
    prediction.resolved_at = datetime.now(timezone.utc)

    calculate_prediction_payouts(prediction)

    await db.commit()
    db.expire_all()

    # Re-fetch with fresh relationships
    reloaded = await db.execute(
        select(Prediction)
        .where(Prediction.id == prediction_id)
        .options(selectinload(Prediction.positions))
    )
    return reloaded.scalar_one()
