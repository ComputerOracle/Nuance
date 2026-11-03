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


import httpx

_RPC_URL = "https://rpc-bradbury.genlayer.com"


async def _fetch_native_balance(client: httpx.AsyncClient, address: str) -> str:
    """Queries eth_getBalance directly from Bradbury JSON-RPC via Python httpx."""
    try:
        resp = await client.post(
            _RPC_URL,
            json={"jsonrpc": "2.0", "method": "eth_getBalance", "params": [address, "latest"], "id": 1},
        )
        data = resp.json()
        raw_hex = data.get("result", "0x0")
        return str(int(raw_hex, 16))
    except Exception as exc:
        logger.warning("Direct RPC eth_getBalance failed for %s: %s", address, exc)
        raise


async def read_and_check(
    reads: list[ReadRequest], transaction_hashes: list[str]
) -> tuple[dict[str, ReadResult], dict[str, TransactionResult]]:
    """Optimized round-trip: resolves __native_balance__ reads directly via
    Python httpx JSON-RPC (0 subprocess overhead). Only delegates complex
    calldata view calls and transaction status checks to genlayer-read.ts
    when strictly necessary."""
    if not reads and not transaction_hashes:
        return {}, {}

    direct_reads: dict[str, ReadResult] = {}
    subproc_reads: list[ReadRequest] = []

    # Fast-path native balance queries via direct Python httpx
    native_balance_items = [r for r in reads if r.get("functionName") == "__native_balance__"]
    other_reads = [r for r in reads if r.get("functionName") != "__native_balance__"]

    if native_balance_items:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            tasks = [
                _fetch_native_balance(http_client, r["address"])
                for r in native_balance_items
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r, res in zip(native_balance_items, results):
                if isinstance(res, Exception):
                    # Fallback to subprocess if direct HTTP call fails
                    subproc_reads.append(r)
                else:
                    direct_reads[r["id"]] = {"ok": True, "result": res}

    subproc_reads.extend(other_reads)

    # If no subprocess calls required, return early!
    if not subproc_reads and not transaction_hashes:
        return direct_reads, {}

    payload = json.dumps({"reads": subproc_reads, "transactions": transaction_hashes}).encode("utf-8")

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

    all_reads = {**direct_reads, **parsed.get("reads", {})}
    return all_reads, parsed.get("transactions", {})
