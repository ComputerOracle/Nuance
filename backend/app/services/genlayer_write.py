"""Backend-signed plain write calls — the trigger for
NuanceDisputeCourt.adjudicate_dispute, closing the gap flagged repeatedly
elsewhere in this codebase: filing a dispute on-chain (routers/escrows.py's
raise_dispute_on_chain) never got it a verdict, because nothing called
adjudicate_dispute. That function has no sender restriction at all (see
contracts/nuance_dispute_court.py) — GenVM's validator network does the
actual judging regardless of which address sends the call, so the backend
triggering it automatically (with the same GENLAYER_PRIVATE_KEY
scripts/deploy.ts already uses) isn't a meaningfully different trust
boundary than any other address doing so.

Deliberately narrow, same reasoning as scripts/genlayer-write.ts's own
header: write_contract() is a thin bridge with no caller-supplied
functionName from outside this package — services/genlayer_indexer.py's
trigger_pending_adjudications is the only real caller, and it always
passes "adjudicate_dispute" itself, never anything dynamic.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.services.genlayer_rpc import _repo_root

logger = logging.getLogger(__name__)

_SCRIPT_PATH = _repo_root() / "scripts" / "genlayer-write.ts"
# A plain write has no receipt wait built in (unlike a deploy) — its own
# bounded rate-limit retries (see genlayer-deploy-core.ts's
# withRateLimitRetry) are what normally ends the subprocess quickly. This
# is a belt-and-suspenders cap, not a tight timeout.
_WRITE_TIMEOUT_SECONDS = 60


async def write_contract(address: str, function_name: str, args: list) -> str | None:
    """Signs and sends one write call via scripts/genlayer-write.ts using
    the backend's own key, and returns the transaction hash — or None if
    the call failed to even send (logged, never raised). Does NOT wait for
    the transaction to be accepted; services/genlayer_indexer.py's normal
    poll cycle discovers the result afterward via its existing get_dispute
    view-sync, same as any other on-chain write this app tracks.
    """
    payload = json.dumps(
        {"address": address, "functionName": function_name, "args": args}
    ).encode("utf-8")

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
        logger.error("genlayer-write subprocess failed to start: %s", exc)
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(payload), timeout=_WRITE_TIMEOUT_SECONDS
        )
    except asyncio.CancelledError:
        # Same reasoning as genlayer_rpc.read_and_check / genlayer_deploy.
        # deploy_contract's own handling: cancellation must not orphan the
        # child process.
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning("genlayer-write subprocess (pid=%s) didn't exit after kill()", proc.pid)
        raise
    except (TimeoutError, asyncio.TimeoutError):
        logger.error(
            "genlayer-write for %s.%s exceeded %ss — killing it.",
            address,
            function_name,
            _WRITE_TIMEOUT_SECONDS,
        )
        proc.kill()
        return None

    if proc.returncode != 0:
        logger.error(
            "genlayer-write exited %s: %s", proc.returncode, stderr.decode("utf-8", "replace")[-2000:]
        )
        return None

    try:
        parsed = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error("genlayer-write produced non-JSON stdout: %r", stdout[:2000])
        return None

    if not parsed.get("ok"):
        logger.error("write_contract failed for %s.%s: %s", address, function_name, parsed.get("error"))
        return None

    return parsed.get("txHash")
