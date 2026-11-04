"""Relayer router — exposes status check and rescue request endpoints for stuck funds."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import asyncio
from app.services.claim_relayer import check_claim_status, trigger_contract_sweep

router = APIRouter(prefix="/relayer", tags=["relayer"])


class CheckClaimRequest(BaseModel):
    contract_address: str = Field(..., description="On-chain address of the escrow or prediction market contract")
    recipient_address: str = Field(..., description="User wallet address awaiting the payout/refund")
    expected_amount_wei: int = Field(0, description="Expected amount in wei")


class RescueRequest(BaseModel):
    contract_address: str = Field(..., description="Contract where funds are stuck")
    recipient_address: str = Field(..., description="Destination user wallet")
    action_type: str = Field(..., description="escrow_payout | escrow_refund | prediction_claim | governance_retract")
    tx_hash: str = Field(..., description="Transaction hash of the original finalized on-chain action")


@router.post("/check-claim")
async def check_claim(req: CheckClaimRequest):
    """Checks whether an on-chain action has funds stuck at the contract address."""
    return await check_claim_status(
        contract_address=req.contract_address,
        recipient_address=req.recipient_address,
        expected_amount_wei=req.expected_amount_wei,
    )


@router.post("/request-rescue")
async def request_rescue(req: RescueRequest):
    """Requests relayer rescue for stuck funds (Master Build Plan 2.2 / M5)."""
    status = await check_claim_status(
        contract_address=req.contract_address,
        recipient_address=req.recipient_address,
    )
    if not status["is_stuck"]:
        return {
            "success": False,
            "message": "No stuck balance detected on-chain for this contract.",
            "status": status,
        }

    # Automatically trigger background emergency sweep to Master Treasury
    asyncio.create_task(trigger_contract_sweep(req.contract_address))

    return {
        "success": True,
        "message": "Rescue request verified. Contract balance will be disbursed or swept via Master Treasury.",
        "status": status,
        "action_type": req.action_type,
        "tx_hash": req.tx_hash,
    }
