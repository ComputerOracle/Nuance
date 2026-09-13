"""Auto-deploys a real NuanceEscrow or NuancePredictionMarket instance for
a new escrow/market — the last piece Part 2 needed. Closes the gap
scripts/deploy.ts's own header called out from the start: bootstrap
deployments prove the contracts work, but "a new escrow between two real
users still needs its own fresh deployment with their real data, called
from the app itself once that wiring exists (a Step 4/backend-integration
concern)" — the exact same reasoning applies to prediction markets.

Three layers, same split as genlayer_rpc.py/genlayer_indexer.py:
  - deploy_contract(): a pure subprocess bridge to scripts/genlayer-deploy.ts
    (no DB access) — mirrors genlayer_rpc.read_and_check's shape exactly.
  - deploy_escrow_contract(): the DB-aware orchestration routers/escrows.py
    queues as a background task right after a new escrow is created.
  - deploy_prediction_contract(): the equivalent for a new market,
    invoked from services/market_generator.py's _process_events for every
    market it auto-publishes.

Deliberately server-side, not wallet-signed from the browser like
submitDeliverableOnChain/fileDisputeOnChain/betOnChain (components/app/
genlayer-write-client.ts) are: deploying needs the contract source's raw
bytes, which a browser bundle has no reason to ship, and
GENLAYER_PRIVATE_KEY was never meant to reach client-side JS — the exact
same key scripts/deploy.ts's bootstrap deployments already use, loaded the
exact same way (from backend/.env).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.enums import StatusKey
from app.models import Asset, Escrow, Prediction
from app.services.genlayer_rpc import _repo_root

logger = logging.getLogger(__name__)

# GEN has 18 decimals — same fact components/app/genlayer-chain.ts's
# WEI_PER_GEN is pulled from (GENLAYER_BRADBURY.nativeCurrency.decimals).
_WEI_PER_GEN_EXPONENT = 18

# retry_undeployed_escrows's cooldown before treating an unfinished deploy
# attempt as safe to retry — comfortably longer than _DEPLOY_TIMEOUT_SECONDS
# below (deploy_contract's own hard subprocess timeout), so this never
# double-submits a real, testnet-GEN-costing deploy transaction while a
# previous attempt could plausibly still be in flight. See Escrow.
# deploy_attempted_at's own docstring for the full account of the gap this
# closes.
_DEPLOY_RETRY_COOLDOWN = timedelta(minutes=10)


def _gen_to_wei(amount: Decimal) -> int:
    """Exact Decimal GEN -> integer wei conversion, done off the Decimal's
    own digit tuple rather than `int(amount * 10**18)` — same string-safe
    reasoning genlayer-chain.ts's parseGenToWei documents (never floating
    point, and immune to Decimal's ambient context precision, which a
    naive multiply-then-round could clip for a large-enough amount).
    Replaces this file's old `escrow.total * 100` cents-style encoding —
    stale leftover from before the dollar-removal pass, and on a
    completely different scale than fund_escrow's real wei `value`, which
    made release_milestone's `milestone.amount > self.funded_amount` check
    compare numbers that were never on the same footing to begin with."""
    sign, digits, exponent = amount.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError(f"Cannot convert non-finite Decimal {amount!r} to wei.")
    unscaled = int("".join(map(str, digits)))
    if sign:
        unscaled = -unscaled
    # amount == unscaled * 10**exponent; wei = amount * 10**18
    return unscaled * (10 ** (_WEI_PER_GEN_EXPONENT + exponent))


def _bigint_arg(value: int) -> dict:
    """Wraps a large integer constructor/call arg so it survives the JSON
    round-trip to scripts/genlayer-deploy.ts intact.

    Real bug this avoids: json.dumps(value) for a plain Python int emits a
    bare JSON number literal, and JS's JSON.parse turns any such literal
    into a `number` — an IEEE-754 double, exact only up to 2**53. A wei
    amount at GEN's 18-decimal scale (order 10**18-10**21 here) is always
    past that, so it would silently round to the nearest representable
    double before genlayer-js's own calldata encoder ever sees it (its
    encoder's `case "bigint"` branch IS exact — see node_modules/
    genlayer-js/dist/index.js's encodeImpl — but only if what reaches it
    is already a real JS BigInt, not a `number` that's already lossy).
    This `{"__bigint__": "<digits>"}` shape is what genlayer-deploy.ts's
    JSON.parse reviver looks for and converts back into a true BigInt
    before it ever becomes a `number` — the string in between carries
    arbitrary digit counts exactly, the same reasoning safeStringify
    (scripts/genlayer-deploy-core.ts) already applies in the opposite
    direction for BigInt fields coming back out."""
    return {"__bigint__": str(value)}

_SCRIPT_PATH = _repo_root() / "scripts" / "genlayer-deploy.ts"

# A deploy can take up to ~3 minutes (scripts/genlayer-deploy-core.ts's own
# 60-retry, 3s-interval receipt wait) — this is a belt-and-suspenders cap
# well above that, not a tight timeout; the underlying engine's own bounded
# retries are what actually end the subprocess in the normal case.
_DEPLOY_TIMEOUT_SECONDS = 360


async def deploy_contract(file: str, args: list) -> str | None:
    """Deploys contracts/<file> with `args` via scripts/genlayer-deploy.ts
    and returns the deployed address, or None if the deploy failed —
    logged, never raised. Callers treat None exactly like any other
    pre-cutover row: stay on the legacy off-chain path, no special error
    handling needed at the call site.
    """
    payload = json.dumps({"file": file, "args": args}).encode("utf-8")

    try:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "tsx",
            str(_SCRIPT_PATH),
            cwd=str(_repo_root()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        logger.error("genlayer-deploy subprocess failed to start: %s", exc)
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(payload), timeout=_DEPLOY_TIMEOUT_SECONDS
        )
    except asyncio.CancelledError:
        # Same reasoning as genlayer_rpc.read_and_check's own handling:
        # cancellation (e.g. server shutdown mid-deploy) must not orphan
        # the child process.
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning("genlayer-deploy subprocess (pid=%s) didn't exit after kill()", proc.pid)
        raise
    except (TimeoutError, asyncio.TimeoutError):
        logger.error(
            "genlayer-deploy for %s exceeded %ss — killing it. This should only "
            "happen if the underlying deploy engine's own bounded retries somehow "
            "didn't (see genlayer-deploy-core.ts).",
            file,
            _DEPLOY_TIMEOUT_SECONDS,
        )
        proc.kill()
        return None

    if proc.returncode != 0:
        logger.error(
            "genlayer-deploy exited %s: %s", proc.returncode, stderr.decode("utf-8", "replace")[-2000:]
        )
        return None

    try:
        parsed = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error("genlayer-deploy produced non-JSON stdout: %r", stdout[:2000])
        return None

    if not parsed.get("ok"):
        logger.error("Contract deploy failed for %s: %s", file, parsed.get("error"))
        return None

    return parsed.get("address")


async def deploy_escrow_contract(escrow_id: int) -> None:
    """Background task routers/escrows.py::create_escrow queues right
    after a new escrow is committed. Deploys a fresh NuanceEscrow instance
    with that escrow's real counterparty/milestone data and links it
    (Escrow.contract_address + the milestone's on_chain_index) — from this
    point on, components/app/nuance-app.tsx's submitDeliverable/
    escalateToDisputeCourt see a real linked contract and route through
    the on-chain path automatically, no --link-demo needed.

    Runs its own DB session — same reasoning services/consensus.py's
    run_consensus module docstring gives: this executes after the request
    that queued it has already returned, on its own timeline (up to a few
    minutes). A failed or still-in-flight deploy simply leaves the escrow
    off-chain, same as any pre-cutover row — never a user-facing error.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Escrow)
            .where(Escrow.id == escrow_id)
            .options(selectinload(Escrow.milestones), selectinload(Escrow.asset))
        )
        escrow = result.scalar_one_or_none()
        if escrow is None:
            logger.warning("deploy_escrow_contract: escrow id=%s no longer exists.", escrow_id)
            return
        if escrow.contract_address is not None:
            return  # already linked — a duplicate/retry queue, not an error

        # FOUND 2026-09-10 (integration audit) — this function had no idea
        # ROADMAP.md Part 4 6.2's Asset model existed at all: it always
        # ran _gen_to_wei (a fixed 18-decimal GEN conversion) on the
        # milestone amount and deployed a contract whose fund_escrow only
        # ever accepts native currency (gl.message.value — see contracts/
        # nuance_escrow.py; there is no ERC-20 transfer path anywhere in
        # this contract or components/app/genlayer-write-client.ts). A
        # non-native escrow (e.g. the seeded testnet USDC, 6 decimals) —
        # not creatable from the UI yet, but very much creatable today via
        # a direct POST /escrows call or the SDK (EscrowCreate.asset_
        # symbol) — would have been deployed with an amount that's wrong
        # by 12 orders of magnitude and no real way to ever fund it in the
        # asset it's actually denominated in. Skip auto-deploy entirely
        # for a non-native asset; it stays on the (asset-agnostic —
        # release_milestone does no unit conversion at all) legacy
        # off-chain path until this contract actually supports a second
        # settlement asset.
        if not escrow.asset.is_native:
            logger.info(
                "deploy_escrow_contract: escrow id=%s is denominated in %s, not native GEN — "
                "NuanceEscrow only supports native-currency funding today, staying off-chain.",
                escrow_id,
                escrow.asset.symbol,
            )
            return

        milestone = min(escrow.milestones, key=lambda m: m.order_index, default=None)
        if milestone is None:
            logger.warning(
                "deploy_escrow_contract: escrow id=%s has no milestone to deploy against.",
                escrow_id,
            )
            return

        # Set BEFORE the actual (slow, up to _DEPLOY_TIMEOUT_SECONDS) deploy
        # call below, and committed immediately — this is the guard
        # retry_undeployed_escrows reads to avoid double-submitting a real
        # deploy transaction while this exact attempt could still be in
        # flight (see Escrow.deploy_attempted_at's own docstring). Not
        # rolled back on failure further down: a failed attempt still
        # counts as "attempted," subject to the same cooldown as any other
        # attempt before being retried again.
        escrow.deploy_attempted_at = datetime.now(timezone.utc)
        await db.commit()

        # NuanceEscrow's milestone_amount is a u256, real wei — matching
        # exactly what components/app/genlayer-write-client.ts's
        # fundEscrowOnChain sends as fund_escrow's payable value (via
        # parseGenToWei), and what release_milestone's own
        # `milestone.amount > self.funded_amount` check compares it
        # against. Both sides of that comparison have to be on the same
        # footing — see _gen_to_wei's own docstring for the stale "cents"
        # encoding this replaces, which wasn't.
        amount_wei = _gen_to_wei(milestone.amount)

        address = await deploy_contract(
            "nuance_escrow.py",
            [
                escrow.creator_address,
                escrow.counterparty_address,
                milestone.name,
                _bigint_arg(amount_wei),
                milestone.criteria,
            ],
        )
        if address is None:
            logger.error(
                "Auto-deploy failed for escrow id=%s — staying on the legacy off-chain path "
                "for now; retry_undeployed_escrows will try again once %s has passed.",
                escrow_id,
                _DEPLOY_RETRY_COOLDOWN,
            )
            return

        escrow.contract_address = address
        milestone.on_chain_index = 0
        await db.commit()
        logger.info("Auto-deployed NuanceEscrow for escrow id=%s -> %s", escrow_id, address)

        # FIXED 2026-09-12 — a real gap found live: an already-open escrow
        # detail view had no way to learn a background deploy had just
        # finished short of a manual page reload. Inline import — see
        # app.services.genlayer_indexer's own copy of this exact import
        # for why it's safe (routers/escrows.py doesn't import this
        # module, so no cycle), done inline here specifically because
        # this module (genlayer_deploy) is itself imported *by*
        # routers/escrows.py — a top-level import back would be circular.
        from app.routers.escrows import _publish_escrow_snapshot

        await _publish_escrow_snapshot(escrow_id)


async def retry_undeployed_escrows() -> None:
    """Called once per services/genlayer_indexer.py poll cycle (gated by
    the same settings.auto_deploy_escrow_contracts flag as the initial
    deploy) — the fix for a real gap: deploy_escrow_contract used to be a
    pure one-shot fire-and-forget background task queued exactly once, at
    creation. If it failed for ANY reason (a transient Bradbury RPC
    hiccup, the backend restarting mid-deploy), that escrow stayed on the
    legacy off-chain path — no real GEN custody, ever — PERMANENTLY, with
    no way for this app to ever try again and no visibility that it had
    even happened.

    Finds every native-GEN, not-yet-deployed, not-cancelled escrow whose
    last attempt (if any) is old enough that it can't plausibly still be
    running (see _DEPLOY_RETRY_COOLDOWN), and just calls
    deploy_escrow_contract again — that function's own idempotency guards
    (contract_address is None, asset.is_native, a real milestone to deploy
    against) are exactly what a safe retry needs, so this doesn't
    duplicate any of that logic, only decides *when* to call it again.
    """
    cutoff = datetime.now(timezone.utc) - _DEPLOY_RETRY_COOLDOWN
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Escrow.id)
            .join(Asset, Escrow.asset_id == Asset.id)
            .where(
                Escrow.contract_address.is_(None),
                Escrow.status_key != StatusKey.CANCELLED,
                Asset.is_native.is_(True),
                (Escrow.deploy_attempted_at.is_(None)) | (Escrow.deploy_attempted_at < cutoff),
            )
        )
        escrow_ids = [row[0] for row in result.all()]

    for escrow_id in escrow_ids:
        await deploy_escrow_contract(escrow_id)


async def deploy_prediction_contract(prediction_id: int) -> None:
    """Two callers, two different "pending_review" meanings:

    - services/market_generator.py's _process_events, for every market it
      auto-publishes (auto_publish=True, immediately "open" — a
      "pending_review" DRAFT from that pipeline is never passed here at
      all; it might still be discarded/edited before a human makes it
      live, and spending real testnet GEN deploying a contract for a
      market that may never launch isn't worth it). Retired 2026-09-12 in
      favor of the path below, but left in place rather than deleted.
    - routers/predictions.py's create_prediction (2026-09-12 rebrand: a
      real person authoring a real market, replacing the pipeline above).
      Every market from there STARTS "pending_review" on purpose — see
      that endpoint's own docstring — specifically so this function can
      deploy it: on success, this flips it to "open" (the case handled
      right below), which is what actually makes it visible/bettable.
      Before this fix, only market_generator's callers ever set
      contract_address; a create_prediction market that deployed
      successfully would have stayed invisible forever with a real
      contract nobody could reach.

    Either way: deploys a fresh NuancePredictionMarket instance with that
    market's real question/resolution data and links it (Prediction.
    contract_address) — from this point on, components/app/nuance-app.tsx's
    placeBet/resolveMarket see a real linked contract and route through
    the on-chain path automatically.

    Skips (logs, doesn't fail) a market with no resolution_source_url —
    NuancePredictionMarket.resolve_market's whole judgment depends on
    fetching that URL (gl.nondet.web.get(), see that contract's own fix
    note), and a market with nothing to check against can't meaningfully
    resolve on-chain at all. create_prediction's own schema (PredictionCreate)
    already requires this field, so this branch is dead for that caller —
    kept for market_generator's, whose Prediction rows predate the
    requirement. Runs its own DB session — same reasoning
    deploy_escrow_contract gives.
    """
    async with AsyncSessionLocal() as db:
        prediction = await db.get(Prediction, prediction_id)
        if prediction is None:
            logger.warning("deploy_prediction_contract: prediction id=%s no longer exists.", prediction_id)
            return
        if prediction.contract_address is not None:
            return  # already linked — a duplicate/retry queue, not an error

        if not prediction.resolution_source_url:
            logger.info(
                "Skipping auto-deploy for prediction id=%s — no resolution_source_url to "
                "resolve against; staying on the legacy off-chain path.",
                prediction_id,
            )
            return

        # Set BEFORE the actual (slow) deploy call below, and committed
        # immediately — see Escrow.deploy_attempted_at's own docstring for
        # the identical reasoning (deploy_escrow_contract does the exact
        # same thing right before its own deploy_contract call). This is
        # the guard retry_undeployed_predictions reads to avoid double-
        # submitting a real deploy transaction while this exact attempt
        # could still be in flight. Not rolled back on failure further
        # down: a failed attempt still counts as "attempted," subject to
        # the same cooldown as any other attempt before being retried.
        prediction.deploy_attempted_at = datetime.now(timezone.utc)
        await db.commit()

        address = await deploy_contract(
            "nuance_prediction_market.py",
            [
                prediction.title,
                prediction.resolution_source_url,
                prediction.description,
                prediction.resolution_date.isoformat(),
            ],
        )
        if address is None:
            logger.error(
                "Auto-deploy failed for prediction id=%s — it stays on the legacy "
                "off-chain path.",
                prediction_id,
            )
            return

        prediction.contract_address = address
        # See this function's own docstring — the actual create_prediction
        # activation step. Only ever flips pending_review->open, so this
        # is a no-op for market_generator's already-"open" auto-published
        # rows (harmless either way, checked explicitly rather than
        # unconditionally overwriting status_key so this function never
        # clobbers some other state a market might be in by the time its
        # background deploy finally lands).
        if prediction.status_key == "pending_review":
            prediction.status_key = "open"
        await db.commit()
        logger.info("Deployed NuancePredictionMarket for prediction id=%s -> %s", prediction_id, address)


async def retry_undeployed_predictions() -> None:
    """The predictions equivalent of retry_undeployed_escrows above — same
    gap, same fix. Reported live (2026-09-13): a user asked that every bet
    on a prediction market use real GEN, "like a real Prediction Markets."
    Checked the actual database rather than assuming the on-chain betting
    path (already built — routers/predictions.py's place_bet refuses a
    contract-linked market's off-chain endpoint outright) covered
    everything: it found 8 markets already `status_key == "open"` —
    genuinely accepting real bets right now — with `contract_address`
    still null, most from services/market_generator.py's now-retired
    auto-publish pipeline (see deploy_prediction_contract's own docstring)
    predating deploy_prediction_contract's per-market background task, a
    couple more from a create_prediction deploy that simply never got
    retried after failing once. Every bet placed against any of them goes
    through the plain off-chain POST /predictions/{id}/bet — notional
    PredictionPosition bookkeeping with no real GEN behind it at all,
    exactly the gap being asked about.

    Deliberately scoped to `status_key == "open"` only, NOT
    "pending_review" — a pending_review row from market_generator's
    pipeline is an unreviewed draft nobody chose to publish (see that
    function's own docstring on why deploying a real contract for one
    isn't worth the real testnet GEN); this only targets markets ALREADY
    live and ALREADY accepting bets, which is the actual gap. A
    create_prediction row past its own initial deploy attempt reaches
    "open" only on success, so by definition never needs retrying via
    this path — this exists for the failure case of that same flow, same
    as retry_undeployed_escrows exists for deploy_escrow_contract's.

    Same idempotency reasoning as retry_undeployed_escrows: deploy_
    prediction_contract's own guards (contract_address is None,
    resolution_source_url set) are exactly what a safe retry needs, so
    this only decides *when* to call it again, same cooldown constant.
    Once a market like this gets linked, routers/predictions.py's
    place_bet's existing contract_address check starts refusing new
    off-chain bets on it automatically — no change needed there at all.
    """
    cutoff = datetime.now(timezone.utc) - _DEPLOY_RETRY_COOLDOWN
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Prediction.id).where(
                Prediction.contract_address.is_(None),
                Prediction.status_key == "open",
                Prediction.resolution_source_url.isnot(None),
                (Prediction.deploy_attempted_at.is_(None)) | (Prediction.deploy_attempted_at < cutoff),
            )
        )
        prediction_ids = [row[0] for row in result.all()]

    for prediction_id in prediction_ids:
        await deploy_prediction_contract(prediction_id)
