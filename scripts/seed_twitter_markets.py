"""Seed 5 refined, high-signal prediction markets derived directly from the live Twitter feed of @GenLayer.

Each market:
1. Is based on a real, verifiable post retrieved with the active TwitterAPI.io key.
2. Contains objective resolution criteria, unambiguous source URLs, and clear maturity cutoffs.
3. Links to the on-chain NuancePredictionMarket contract instance on Bradbury Testnet.
4. Records deduplication entries in MarketEventLog so the ingestion pipeline stays synchronized.
5. Seeds initial pari-mutuel liquidity positions from the treasury and deployer accounts.
"""

import asyncio
from datetime import datetime, timezone
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.db import AsyncSessionLocal
from app.enums import ChainStatus
from app.models import MarketEventLog, Prediction, PredictionPosition

PREDICTION_MARKET_CONTRACT = "0x08149602c5cAaE87beFb0631B5Cf983a944aD67C"
TREASURY_WALLET = "0x41648de45cc4d0172becd4db0a0a0b459c383705"
DEPLOYER_WALLET = "0xcafc5f0a599475c61f700ff02a11b5647c188fcd"

ITEMS = [
    {
        "source_id": "twitter_2117309553931108493",
        "url": "https://x.com/GenLayer/status/2117309553931108493",
        "category": "STAKING & TOKENOMICS",
        "title": "Will GenLayer Pre-Mainnet Staking distribute staking yield before Mainnet genesis?",
        "description": (
            "Resolves YES if the GenLayer Foundation officially initiates reward accrual and distribution "
            "for participants in the Pre-Mainnet Staking programme before Mainnet genesis, verified by "
            "announcements on genlayer.com, portal.genlayer.foundation, or the official @GenLayer X account. "
            "Resolves NO if the staking programme is postponed until after Mainnet or rewards are distributed "
            "only post-genesis."
        ),
        "resolution_date": datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        "volume": 84500,
        "yes_amount": 52000,
        "no_amount": 32500,
    },
    {
        "source_id": "twitter_2113269144795701558",
        "url": "https://x.com/GenLayer/status/2113269144795701558",
        "category": "PROTOCOL & INFRASTRUCTURE",
        "title": "Will GenLayer deploy its Bradbury adjudication settlement contracts to Arbitrum before 2027?",
        "description": (
            "Resolves YES if GenLayer deploys and verifies its core consensus and adjudication settlement "
            "contracts on Arbitrum infrastructure (Arbitrum One, Arbitrum Nova, or a dedicated Arbitrum Orbit "
            "rollup) on or before December 31, 2026 at 23:59 UTC. Resolves NO if settlement contracts remain "
            "exclusively on legacy testnet infrastructure by that cutoff."
        ),
        "resolution_date": datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        "volume": 128000,
        "yes_amount": 89600,
        "no_amount": 38400,
    },
    {
        "source_id": "twitter_2115039782719864971",
        "url": "https://x.com/GenLayer/status/2115039782719864971",
        "category": "TOKENOMICS",
        "title": "Will the GenLayer Foundation announce the official GEN Token Generation Event (TGE) date before December 15, 2026?",
        "description": (
            "Resolves YES if the GenLayer Foundation or @GenLayer publishes the definitive calendar date "
            "for the GEN public Token Generation Event (TGE) on or before December 15, 2026 at 23:59 UTC. "
            "Resolves NO if no specific calendar date for the TGE has been officially announced by the deadline."
        ),
        "resolution_date": datetime(2026, 12, 15, 23, 59, 59, tzinfo=timezone.utc),
        "volume": 92000,
        "yes_amount": 53360,
        "no_amount": 38640,
    },
    {
        "source_id": "twitter_2115377660151177393",
        "url": "https://x.com/GenLayer/status/2115377660151177393",
        "category": "AI CONSENSUS",
        "title": "Will GenLayer enforce multi-model LLM diversity (>= 3 distinct model providers) per consensus round in Bradbury Phase 2?",
        "description": (
            "Resolves YES if the GenLayer validator protocol requires that validator nodes selected for an "
            "intelligent contract execution round must run at least 3 distinct LLM model families (e.g., Anthropic "
            "Claude, OpenAI GPT, and Meta Llama / Google Gemini) to achieve consensus on Bradbury Testnet before "
            "December 31, 2026. Resolves NO otherwise."
        ),
        "resolution_date": datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        "volume": 65000,
        "yes_amount": 48750,
        "no_amount": 16250,
    },
    {
        "source_id": "twitter_2113699829704516029",
        "url": "https://x.com/GenLayer/status/2113699829704516029",
        "category": "AGENTIC SECURITY",
        "title": "Will GenLayer open-source the 'Greyboxing' specification for autonomous agent wallet protection before year-end 2026?",
        "description": (
            "Resolves YES if GenLayer releases an open-source repository, developer SDK, or technical specification "
            "detailing the 'Greyboxing' runtime sandbox that prevents prompt injection attacks against agentic "
            "wallets on or before December 31, 2026 at 23:59 UTC. Resolves NO otherwise."
        ),
        "resolution_date": datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        "volume": 71500,
        "yes_amount": 34320,
        "no_amount": 37180,
    },
]

async def seed():
    async with AsyncSessionLocal() as session:
        created_predictions = []
        for item in ITEMS:
            pred = Prediction(
                title=item["title"],
                description=item["description"],
                category=item["category"],
                resolution_date=item["resolution_date"],
                volume=item["volume"],
                status_key="open",
                resolution_source_url=item["url"],
                contract_address=PREDICTION_MARKET_CONTRACT,
                chain_status=ChainStatus.FINALIZED,
            )
            session.add(pred)
            await session.flush()  # populate pred.id

            # Seed initial positions
            pos_yes = PredictionPosition(
                prediction_id=pred.id,
                wallet_address=TREASURY_WALLET,
                side="YES",
                amount=item["yes_amount"],
                status="PENDING",
            )
            pos_no = PredictionPosition(
                prediction_id=pred.id,
                wallet_address=DEPLOYER_WALLET,
                side="NO",
                amount=item["no_amount"],
                status="PENDING",
            )
            session.add(pos_yes)
            session.add(pos_no)

            # Record in MarketEventLog
            log = MarketEventLog(
                source_id=item["source_id"],
                source="twitter",
                source_url=item["url"],
                outcome="created",
                prediction_id=pred.id,
            )
            session.add(log)
            created_predictions.append(pred)

        await session.commit()
        print(f"Successfully created {len(created_predictions)} refined prediction markets:")
        for p in created_predictions:
            print(f"  - [{p.id}] {p.title} (Category: {p.category}, Volume: {p.volume / 1000} GEN)")

if __name__ == "__main__":
    asyncio.run(seed())
