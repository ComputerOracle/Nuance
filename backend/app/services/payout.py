"""Deterministic Pari-Mutuel Payout Engine.

Calculates payouts according to:
    User Payout = (User Stake on Winning Side / Total Stake on Winning Side) * Total Pool Volume
"""

from __future__ import annotations

from app.models import Prediction


def calculate_prediction_payouts(prediction: Prediction) -> None:
    if not prediction.outcome:
        return

    winning_side = prediction.outcome.strip().upper()
    if winning_side not in ("YES", "NO"):
        return

    positions = prediction.positions or []
    if not positions:
        return

    # Total volume in pool
    total_volume = sum(p.amount for p in positions)
    if total_volume == 0:
        total_volume = prediction.volume or 0

    # Total stake on winning side
    winning_volume = sum(
        p.amount for p in positions if p.side.strip().upper() == winning_side
    )

    for pos in positions:
        pos_side = pos.side.strip().upper()
        if pos_side == winning_side:
            if winning_volume > 0:
                pos.payout = round((pos.amount / winning_volume) * total_volume, 2)
            else:
                pos.payout = float(pos.amount)
            pos.status = "WON"
        else:
            pos.payout = 0.0
            pos.status = "LOST"
