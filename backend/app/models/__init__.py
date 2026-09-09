"""SQLAlchemy async models, as a package.

Split from a single models.py once governance.py needed its own module —
every class is re-exported here so `from app.models import Escrow, Proposal`
(and `from app import models` in main.py, which just needs every table
imported somewhere so it registers on Base.metadata) keep working exactly
as before the split.
"""

from __future__ import annotations

from app.models.core import (
    ApiKey,
    Asset,
    ConsensusJob,
    DeliverableSubmission,
    Dispute,
    DisputeEvidence,
    DisputeMessage,
    Escrow,
    IdempotencyRecord,
    MarketEventLog,
    Milestone,
    Prediction,
    PredictionPosition,
    User,
    UserSettings,
    Webhook,
)
from app.models.governance import Proposal, Vote

__all__ = [
    "ApiKey",
    "Asset",
    "ConsensusJob",
    "DeliverableSubmission",
    "Dispute",
    "DisputeEvidence",
    "DisputeMessage",
    "Escrow",
    "IdempotencyRecord",
    "MarketEventLog",
    "Milestone",
    "Prediction",
    "PredictionPosition",
    "Proposal",
    "User",
    "UserSettings",
    "Vote",
    "Webhook",
]
