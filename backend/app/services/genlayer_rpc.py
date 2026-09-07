"""Bridge to scripts/genlayer-read.ts — the verified, read-only GenLayer
RPC client services/genlayer_indexer.py relies on.

Why a subprocess instead of a Python GenLayer client: this repo has no
verified Python GenLayer SDK. `genlayer_py`/`genlayer` aren't installed
(checked directly — `pip show` finds neither), and scripts/deploy.ts's own
header documents at length why guessing at an unverified SDK's call shape
from docs.genlayer.com alone repeatedly broke against real Bradbury
deploys. genlayer-js, by contrast, is already installed *and* already
verified in this exact repo (scripts/deploy.ts's deployContract/
waitForTransactionReceipt, lib/chain-status.ts's status-bucketing) — live
read-call verification for this file specifically (get_escrow/
get_milestone/get_dispute_count/get_market against the real deployed
bootstrap contracts) was run 2026-09-07 before this module was written.
Rather than re-derive raw JSON-RPC calls in Python from scratch — the
exact kind of unverified guess this codebase's own commit history shows
is expensive to get wrong — the indexer shells out to
scripts/genlayer-read.ts for the RPC leg only, and does every database
write itself via SQLAlchemy (see genlayer_indexer.py) — still exactly one
process ever writing to nuance.db, no dual-writer risk from a second
runtime touching the same sqlite file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class ReadRequest(TypedDict):
    id: str
    address: str
    functionName: str
    args: list[Any]


class ReadResult(TypedDict, total=False):
    ok: bool
    result: Any
    error: str


class TransactionResult(TypedDict, total=False):
    ok: bool
    rawStatusName: str | None
    bucket: str
    success: bool | None
    raw: Any
    error: str


def _repo_root() -> Path:
    """Walk up from this file until a package.json turns up — the repo
    root, wherever this package ends up nested (mirrors what scripts/
    deploy.ts does with `resolve(__dirname, "..")`, just without assuming
    a fixed nesting depth from this file's own location)."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "package.json").exists():
            return candidate
    # Fallback if package.json ever moves: backend/app/services/ -> repo
    # root is 3 levels up (services -> app -> backend -> root).
    return here.parents[3]


_SCRIPT_PATH = _repo_root() / "scripts" / "genlayer-read.ts"


async def read_and_check(
    reads: list[ReadRequest], transaction_hashes: list[str]
) -> tuple[dict[str, ReadResult], dict[str, TransactionResult]]:
    """One batched round-trip to scripts/genlayer-read.ts: `reads` (contract
    view calls) plus `transaction_hashes` (status checks) in a single
    subprocess call. Every item is independently ok/error inside the
    response (see that script's own header) — a bad address or a
    momentary chain hiccup on one item never loses the rest of the batch.

    Returns ({}, {}) rather than raising if the subprocess itself can't
    even run (missing `npx`/`tsx`, e.g.) — genlayer_indexer.py treats that
    as "nothing synced this cycle" and logs it, rather than crashing the
    whole poll loop over one bad cycle.
    """
    if not reads and not transaction_hashes:
        return {}, {}

    payload = json.dumps({"reads": reads, "transactions": transaction_hashes}).encode("utf-8")

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
        logger.error("genlayer-read subprocess failed to start: %s", exc)
        return {}, {}

    try:
        stdout, stderr = await proc.communicate(payload)
    except asyncio.CancelledError:
        # Reached when genlayer_indexer.run_forever's task is cancelled
        # (main.py's lifespan, on shutdown) while a poll cycle is
        # mid-subprocess — communicate() being cancelled does NOT kill the
        # child on its own, it just stops awaiting it, which is exactly
        # the "orphan subprocess" a clean shutdown has to avoid. kill()
        # + a short wait() reaps it properly before the cancellation
        # propagates up.
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning("genlayer-read subprocess (pid=%s) didn't exit after kill()", proc.pid)
        raise

    if proc.returncode != 0:
        # genlayer-js logs a verbose per-call error dump to stderr even
        # for calls it recovers from internally (confirmed live,
        # 2026-09-07, against a deliberately invalid address) — only a
        # non-zero *exit code* (that script's own top-level .catch) means
        # stdout has no usable JSON at all.
        logger.error(
            "genlayer-read exited %s: %s",
            proc.returncode,
            stderr.decode("utf-8", "replace")[-2000:],
        )
        return {}, {}

    try:
        parsed = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error("genlayer-read produced non-JSON stdout: %r", stdout[:2000])
        return {}, {}

    return parsed.get("reads", {}), parsed.get("transactions", {})
