"""Fallback Claim Relayer Service.

Implements Section 2.2 and Milestone M5 of the Master Build Plan:
Monitors and resolves stuck payouts/refunds caused by the GenLayer platform-level
execution bug (genlayerlabs/genvm-manager#20). When emit_transfer logs but fails
to dispatch native GEN, this relayer verifies on-chain contract balance and
provides automated or on-demand faucet disbursement to the user wallet.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx
from app.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

_RPC_URL = "https://rpc-bradbury.genlayer.com"


async def check_onchain_balance(address: str) -> int:
    """Queries real on-chain balance via eth_getBalance."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _RPC_URL,
            json={"jsonrpc": "2.0", "method": "eth_getBalance", "params": [address, "latest"], "id": 1},
        )
        data = resp.json()
        raw_hex = data.get("result", "0x0")
        return int(raw_hex, 16)


async def check_claim_status(
    contract_address: str,
    recipient_address: str,
    expected_amount_wei: int = 0,
) -> dict[str, Any]:
    """Inspects whether an escrow or prediction market payout is stuck on-chain.

    Returns status details including contract balance, whether funds are stuck,
    and rescue eligibility.
    """
    contract_bal = await check_onchain_balance(contract_address)
    recipient_bal = await check_onchain_balance(recipient_address)

    is_stuck = contract_bal > 0
    return {
        "contract_address": contract_address,
        "recipient_address": recipient_address,
        "contract_balance_wei": contract_bal,
        "recipient_balance_wei": recipient_bal,
        "is_stuck": is_stuck,
        "eligible_for_relayer": is_stuck,
        "message": (
            "Funds are stuck at the contract address due to GenLayer genvm-manager#20. "
            "Relayer rescue is available."
            if is_stuck
            else "No stuck funds detected on-chain."
        ),
    }


async def trigger_contract_sweep(contract_address: str) -> None:
    """Spawns scripts/sweep-and-finalize.ts to sweep stuck funds back to Master Treasury."""
    import asyncio
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    cmd = ["npx", "tsx", "scripts/sweep-and-finalize.ts", contract_address]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("Sweep script succeeded for %s: %s", contract_address, stdout.decode())
        else:
            logger.warning("Sweep script failed for %s: %s", contract_address, stderr.decode())
    except Exception as exc:
        logger.error("Failed to trigger sweep script: %s", exc)

