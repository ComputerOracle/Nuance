"""SQLAlchemy 2.0 async models — User, UserSettings, Asset, Escrow,
Milestone, DeliverableSubmission, ConsensusJob, Dispute, DisputeEvidence,
Prediction, PredictionPosition.

Governance's Proposal/Vote live in governance.py instead — see
app/models/__init__.py for the re-export that makes the split invisible
to every other importer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ChainStatus, ConsensusStage, ConsensusSubjectType, StatusKey

# ROADMAP.md Part 4 6.2 — replaces the old `Money = Numeric(12, 2)` (USD-
# shaped, 2 decimal places) that Escrow.total/Milestone.amount used before
# 2026-09-08. 2dp can't hold a native GEN amount (18 decimals) without
# silent truncation — this widens to accommodate any asset up to 18
# decimals (Asset.decimals below) with 20 integer digits of headroom.
# Deliberately still just ONE numeric column, not "store raw base units as
# an integer" (the more common on-chain pattern): every other model in
# this codebase already represents amounts as human-scale Decimal
# ("500.00", not "50000" cents), and asset_id + Asset.decimals is enough
# to interpret/quantize an amount correctly without changing that
# convention for every existing reader.
AssetAmount = Numeric(38, 18)


class Asset(Base):
    """A settlement currency an Escrow's total/milestones are denominated
    in — see Escrow.asset_id. Seeded with native GEN (Bradbury testnet's
    currency; is_native=True, contract_address=None, matching how
    genlayer-js's own native-currency convention works — see contracts/
    nuance_escrow.py's fund_escrow/gl.message.value) and one testnet
    ERC-20 stablecoin, per ROADMAP.md 6.2. `symbol` is unique so
    `POST /escrows` can accept a human-friendly "GEN"/"USDC" instead of
    requiring callers to already know an asset_id.
    """

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(unique=True)
    decimals: Mapped[int]
    # Null for the native asset (GEN) — there's no separate token contract
    # to hold, value moves as a plain payable transfer. Set for any
    # ERC-20-style asset (contracts/nuance_escrow.py doesn't implement
    # ERC-20 transfers itself yet — see ROADMAP.md 6.2's own scoping note
    # on what "support" means today vs. a real on-chain transfer path).
    contract_address: Mapped[str | None] = mapped_column(default=None)
    is_native: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    """Identity = wallet address (lowercased). No password; see the auth prompt
    for the personal_sign + nonce verification flow.
    """

    __tablename__ = "users"

    wallet_address: Mapped[str] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(default=None)
    nonce: Mapped[str | None] = mapped_column(default=None)
    nonce_issued_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    settings: Mapped["UserSettings | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    created_escrows: Mapped[list["Escrow"]] = relationship(
        foreign_keys="[Escrow.creator_address]", back_populates="creator"
    )
    counterparty_escrows: Mapped[list["Escrow"]] = relationship(
        foreign_keys="[Escrow.counterparty_address]", back_populates="counterparty"
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    wallet_address: Mapped[str] = mapped_column(
        ForeignKey("users.wallet_address"), primary_key=True
    )
    notify_on: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_escalate_on: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="settings")


class Escrow(Base):
    __tablename__ = "escrows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    counterparty_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    title: Mapped[str]
    total: Mapped[Decimal] = mapped_column(AssetAmount)
    # ROADMAP.md Part 4 6.2 — which Asset this escrow (and every one of its
    # milestones — see Milestone.amount's own note) is denominated in.
    # server_default keeps every pre-existing row (and any raw INSERT that
    # doesn't know about this column yet) pointed at asset_id=1, the
    # native-GEN row _seed_assets() guarantees exists first — see that
    # function's own docstring on why 1 specifically, not "whichever row
    # is_native happens to be."
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), server_default="1")
    status_key: Mapped[StatusKey] = mapped_column(default=StatusKey.IN_PROGRESS)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Which deployed NuanceEscrow instance (contracts/nuance_escrow.py)
    # backs this escrow — null means this escrow predates/isn't part of
    # the on-chain cutover and stays on the legacy services/consensus.py
    # path (see ROADMAP.md 4.5's migration-path note). One contract
    # instance per escrow, holding all of that escrow's milestones — set
    # automatically by services/genlayer_deploy.py's deploy_escrow_contract
    # right after creation.
    contract_address: Mapped[str | None] = mapped_column(default=None)
    # The tx hash of the creator's NuanceEscrow.fund_escrow call, once
    # sent — a real, payable transaction (components/app/
    # genlayer-write-client.ts's fundEscrowOnChain), not just bookkeeping.
    # Null means either not on-chain yet, or on-chain but not funded yet;
    # the contract's own `funded_amount` (checked by release_milestone
    # before any payout) is the actual source of truth either way — this
    # column only tracks whether this app has sent a fund_escrow call at
    # all, for UI purposes (hide the "Fund Escrow" action once it has).
    funded_tx_hash: Mapped[str | None] = mapped_column(default=None)
    # The tx hash of the creator's NuanceEscrow.cancel_escrow call, once
    # sent — set alongside status_key flipping to StatusKey.CANCELLED in
    # routers/escrows.py's cancel_escrow_on_chain ack. Null means never
    # cancelled on-chain.
    cancelled_tx_hash: Mapped[str | None] = mapped_column(default=None)

    creator: Mapped["User"] = relationship(
        foreign_keys=[creator_address], back_populates="created_escrows"
    )
    counterparty: Mapped["User"] = relationship(
        foreign_keys=[counterparty_address], back_populates="counterparty_escrows"
    )
    asset: Mapped["Asset"] = relationship()
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="escrow",
        order_by="Milestone.order_index",
        cascade="all, delete-orphan",
    )
    disputes: Mapped[list["Dispute"]] = relationship(
        back_populates="escrow",
        cascade="all, delete-orphan",
    )


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrows.id"))
    name: Mapped[str]
    # Denominated in its parent Escrow's asset (Escrow.asset_id) — a
    # milestone has no asset of its own, every milestone in one escrow
    # shares the one currency the escrow itself was created in.
    amount: Mapped[Decimal] = mapped_column(AssetAmount)
    status_key: Mapped[StatusKey] = mapped_column(default=StatusKey.PENDING)
    criteria: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(default=0)
    # This milestone's index inside its escrow's NuanceEscrow contract
    # (the u256 key submit_deliverable/get_milestone take) — distinct from
    # `id`/`order_index`, which are this DB's own. Null until explicitly
    # linked; see Escrow.contract_address's docstring.
    on_chain_index: Mapped[int | None] = mapped_column(default=None)
    # services/genlayer_indexer.py's read-cache columns — see enums.py's
    # ChainStatus docstring for the shared vocabulary with
    # lib/chain-status.ts. chain_status is the UI-facing bucket;
    # on_chain_raw_status is GenVM's actual 14-value TransactionStatus
    # (e.g. "APPEAL_REVEALING"), kept alongside it so an appeal can be
    # detected specifically rather than only as "still decided, not final"
    # (ROADMAP.md 4.5, requirement: flag an appeal, don't just fold it in).
    chain_status: Mapped[ChainStatus] = mapped_column(default=ChainStatus.LEGACY_OFFCHAIN)
    on_chain_raw_status: Mapped[str | None] = mapped_column(default=None)
    # The most recent submit_deliverable/release_milestone tx hash the
    # indexer is (or was) tracking for this milestone.
    on_chain_tx_hash: Mapped[str | None] = mapped_column(default=None)
    # The validator committee's own stated reasoning for approving/disputing
    # this milestone — real GenVM validator text for an on-chain milestone
    # (read back via get_milestone's own `reasoning` field and applied by
    # services/consensus.py's _apply_verdict_to_state), or the off-chain
    # ensemble's text for a legacy milestone. FIXED 2026-09-08: this column
    # didn't exist before — _apply_verdict_to_state received the real
    # reasoning text every time but had nowhere to put it for a Milestone
    # (unlike Dispute.ruling, which always stored it), so it was silently
    # discarded; a user could only find it by reading the raw chain
    # explorer directly, which is exactly what happened during a live test.
    reasoning: Mapped[str | None] = mapped_column(Text, default=None)
    # Set once POST /escrows/{id}/release has actually paid this milestone
    # out — added 2026-09-08, another real gap found live: release_milestone
    # only ever re-set status_key to APPROVED (a no-op re-assignment, since
    # consensus already set it there the moment the verdict landed) with
    # nothing distinguishing "approved, payout pending" from "approved,
    # already paid" — so the "Release Payment" button had no way to know
    # it had already been clicked and kept reappearing indefinitely.
    # Mirrors the on-chain contract's own Milestone.released bool
    # (contracts/nuance_escrow.py), which this off-chain path never had an
    # equivalent for.
    released_at: Mapped[datetime | None] = mapped_column(default=None)

    escrow: Mapped["Escrow"] = relationship(back_populates="milestones")
    submissions: Mapped[list["DeliverableSubmission"]] = relationship(
        back_populates="milestone",
        cascade="all, delete-orphan",
    )


class DeliverableSubmission(Base):
    __tablename__ = "deliverable_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    milestone_id: Mapped[int] = mapped_column(ForeignKey("milestones.id"))
    wallet: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    text: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(server_default=func.now())

    milestone: Mapped["Milestone"] = relationship(back_populates="submissions")


class ConsensusJob(Base):
    """One AI-validator-consensus run against a milestone submission or (once
    the disputes prompt lands) a piece of dispute evidence. `subject_id`
    points at `milestones.id` or `disputes.id` depending on `subject_type` —
    a polymorphic FK, so it's a plain int column rather than a real
    ForeignKey (there's no single table it always references).
    """

    __tablename__ = "consensus_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_type: Mapped[ConsensusSubjectType]
    subject_id: Mapped[int]
    stage: Mapped[int] = mapped_column(default=int(ConsensusStage.IDLE))

    # List of {name, vote, confidence, reasoning} dicts, one per validator
    validator_results: Mapped[list | None] = mapped_column(JSON, default=None)

    verdict_label: Mapped[str | None] = mapped_column(default=None)
    verdict_approved: Mapped[bool | None] = mapped_column(default=None)
    verdict_confidence: Mapped[int | None] = mapped_column(default=None)
    verdict_reasoning: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(default=None)


class Dispute(Base):
    """A claim raised against an escrow (optionally a specific milestone).
    `opened_by_address` is a FK to `users.wallet_address`.
    """

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    escrow_id: Mapped[int] = mapped_column(ForeignKey("escrows.id"))
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id"), default=None)
    opened_by_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    issue: Mapped[str] = mapped_column(Text)
    status_key: Mapped[StatusKey] = mapped_column(default=StatusKey.DISPUTED)

    # Populated by POST /disputes/{id}/enforce.
    ruling: Mapped[str | None] = mapped_column(Text, default=None)
    enforced_by: Mapped[str | None] = mapped_column(ForeignKey("users.wallet_address"), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # This dispute's id inside NuanceDisputeCourt (contracts/
    # nuance_dispute_court.py) — a single SHARED REGISTRY for the whole
    # app (one deployed address, DISPUTE_COURT_CONTRACT_ADDRESS), unlike
    # Escrow/Prediction's per-row contract_address. Null means this
    # dispute predates/isn't part of the on-chain cutover. See
    # Escrow.contract_address's docstring for chain_status/
    # on_chain_raw_status/on_chain_tx_hash below.
    on_chain_dispute_id: Mapped[int | None] = mapped_column(default=None)
    chain_status: Mapped[ChainStatus] = mapped_column(default=ChainStatus.LEGACY_OFFCHAIN)
    on_chain_raw_status: Mapped[str | None] = mapped_column(default=None)
    on_chain_tx_hash: Mapped[str | None] = mapped_column(default=None)
    # The tx hash of the NuanceDisputeCourt.adjudicate_dispute call
    # services/genlayer_indexer.py's trigger_pending_adjudications sent for
    # this dispute, once on_chain_dispute_id is known — a SEPARATE
    # transaction from on_chain_tx_hash above (which tracks file_dispute,
    # not adjudicate_dispute). Set only once a send actually succeeds, so
    # the indexer never re-sends it every poll cycle; a failed *send*
    # (network/rate-limit, no tx hash back) leaves this null and is safe
    # to retry next cycle, since nothing was actually submitted.
    adjudication_tx_hash: Mapped[str | None] = mapped_column(default=None)

    escrow: Mapped["Escrow"] = relationship(back_populates="disputes")
    opener: Mapped["User"] = relationship(foreign_keys=[opened_by_address])
    messages: Mapped[list["DisputeMessage"]] = relationship(
        back_populates="dispute",
        order_by="DisputeMessage.created_at",
        cascade="all, delete-orphan",
    )
    evidence: Mapped[list["DisputeEvidence"]] = relationship(
        back_populates="dispute",
        order_by="DisputeEvidence.created_at",
        cascade="all, delete-orphan",
    )


class DisputeMessage(Base):
    __tablename__ = "dispute_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"))
    sender_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    dispute: Mapped["Dispute"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(foreign_keys=[sender_address])


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(ForeignKey("disputes.id"))
    submitter_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    description: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    dispute: Mapped["Dispute"] = relationship(back_populates="evidence")
    submitter: Mapped["User"] = relationship(foreign_keys=[submitter_address])


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    resolution_date: Mapped[datetime]
    volume: Mapped[int] = mapped_column(default=0)
    status_key: Mapped[str] = mapped_column(default="open")
    outcome: Mapped[str | None] = mapped_column(Text, default=None)
    resolution_reasoning: Mapped[str | None] = mapped_column(Text, default=None)
    # The announcement/tweet a machine-generated market was extracted from —
    # null for hand-created markets. See services/market_generator.py.
    resolution_source_url: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)

    # Which deployed NuancePredictionMarket instance (contracts/
    # nuance_prediction_market.py) backs this market — one instance per
    # market, same reasoning as Escrow.contract_address's docstring; null
    # means this market stays on the legacy off-chain resolution path.
    contract_address: Mapped[str | None] = mapped_column(default=None)
    chain_status: Mapped[ChainStatus] = mapped_column(default=ChainStatus.LEGACY_OFFCHAIN)
    on_chain_raw_status: Mapped[str | None] = mapped_column(default=None)
    on_chain_tx_hash: Mapped[str | None] = mapped_column(default=None)
    # The tx hash of the NuancePredictionMarket.resolve_market call
    # services/genlayer_indexer.py's trigger_pending_market_resolutions
    # sent for this market, once its cutoff has passed — a separate
    # transaction from on_chain_tx_hash above (which has no single canonical
    # meaning for a market anyway, since many different bettors' own
    # transactions could occupy it; resolution is the one transaction this
    # app itself ever tracks for a market as a whole). Set only once a
    # send actually succeeds, so it's never re-sent every poll cycle; a
    # failed *send* (network/rate-limit, no tx hash back) leaves this null
    # and is safe to retry next cycle.
    resolution_trigger_tx_hash: Mapped[str | None] = mapped_column(default=None)

    positions: Mapped[list["PredictionPosition"]] = relationship(
        back_populates="prediction",
        cascade="all, delete-orphan",
        order_by="PredictionPosition.created_at",
    )


class PredictionPosition(Base):
    __tablename__ = "prediction_positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    wallet_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    side: Mapped[str] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(default=0)
    payout: Mapped[float | None] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(Text, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    prediction: Mapped["Prediction"] = relationship(back_populates="positions")
    user: Mapped["User"] = relationship(foreign_keys=[wallet_address])


class MarketEventLog(Base):
    """Dedup ledger for services/market_generator.py — one row per raw
    source event (a tweet id, or a hash of an RSS/webpage entry's URL) it
    has ever looked at, so the exact same announcement is never fed to the
    LLM extractor twice, regardless of whether it produced a market, was
    judged noise, or the extraction call itself failed.
    """

    __tablename__ = "market_event_log"

    source_id: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(default="unknown")  # "twitter" | "rss" | "web"
    source_url: Mapped[str | None] = mapped_column(Text, default=None)
    outcome: Mapped[str] = mapped_column(default="skipped")  # "created" | "skipped" | "error"
    prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("predictions.id"), default=None
    )
    processed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IdempotencyRecord(Base):
    """Cache row backing app/middleware/idempotency.py's dedup + in-flight
    lock guard on financial/state-changing write routes (POST /escrows,
    POST /escrows/{id}/release, POST /disputes/{id}/evidence, POST
    /disputes/{id}/enforce, POST /predictions/{id}/bet, POST /proposals/{id}
    /vote — see app/middleware/write_routes.py for the exact set). Scoped to
    (key, user_address, endpoint) rather than key alone — the same
    Idempotency-Key header value reused by two different wallets, or
    coincidentally on two different endpoints, must not collide with each
    other.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "key", "user_address", "endpoint", name="uq_idempotency_key_user_endpoint"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(Text)
    user_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    endpoint: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    # "in_progress" while the wrapped request is still executing — acts as
    # the in-flight lock (a second request with the same key while this is
    # set gets 409) — "completed" once response_code/response_body are
    # filled in and safe to replay.
    status: Mapped[str] = mapped_column(default="in_progress")
    response_code: Mapped[int | None] = mapped_column(default=None)
    response_body: Mapped[dict | list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(default=None)


class ApiKey(Base):
    """A scoped, non-browser credential for autonomous agents — ROADMAP.md
    Part 4 6.1: "Nuance's own Agent Directory concept implies non-human
    counterparties should be able to act without a browser wallet flow."
    Issued via POST /auth/api-keys (JWT-authed) and authenticated on every
    subsequent request via the X-Api-Key header (see app/dependencies.py's
    get_current_user_or_api_key). Maps back to the same User a browser
    session would — an API key is a second way to *prove you are* a given
    wallet, not a separate identity/permission system, so every existing
    "only the escrow creator can..." check keeps working completely
    unchanged for a key-authenticated request.

    Only `secret_hash` (sha256) is ever stored — the raw secret is
    returned exactly once, in POST /auth/api-keys's own response, the
    same "shown once, never again" convention every comparable platform
    uses (Stripe restricted keys, GitHub PATs, ...): a hash can't be
    reversed to show the original value again later, even to its own
    owner, so losing it means issuing a new key, not "looking it up".
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Public identifier — safe to log, appears in the key itself
    # ("nuance_live_<key_id>_<secret>") so a request's own X-Api-Key header
    # is enough to look up which row to check the secret against, without
    # hashing every stored key to find a match.
    key_id: Mapped[str] = mapped_column(unique=True)
    secret_hash: Mapped[str]
    wallet_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    # e.g. ["escrow:create", "bet:place", "evidence:submit"] — checked by
    # app/dependencies.py's require_scope; not enforced at the DB layer,
    # same "DB stores the shape, the router layer enforces the rule"
    # split every other permission check in this codebase already uses.
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Caller-supplied, purely for the owner's own bookkeeping (GET
    # /auth/api-keys listing "prod bot" vs "test key") — never checked by
    # anything.
    label: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    # Revocation is a soft delete (set this, don't drop the row) — keeps
    # the row around as an audit trail of a key that existed and who it
    # belonged to, same reasoning Dispute/ConsensusJob rows are never
    # deleted either.
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped["User"] = relationship()


class Webhook(Base):
    """A callback URL an agent registers to be notified of consensus/
    dispute/prediction completion events instead of polling GET
    /consensus/{id} (or its WS equivalent) itself — ROADMAP.md Part 4 6.1.
    Delivered by services/webhooks.py at the same points services/
    realtime.py's Redis publish already fires from (consensus DONE,
    dispute enforce, prediction resolve) — a webhook and a live WS
    subscriber both learn about the same event from the same call site,
    just over a different transport.

    `secret` signs each delivery (see services/webhooks.py's
    _sign_payload) so the receiving endpoint can verify a payload
    actually came from Nuance and wasn't forged by a third party who
    guessed/found the callback URL — the same HMAC-signature convention
    Stripe/GitHub webhooks use. Unlike ApiKey.secret_hash, this is stored
    *plain*, not hashed — a webhook secret has to stay usable server-side
    to keep signing every future delivery, whereas an API key secret only
    ever needs to be *compared against*, never reproduced.
    """

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(ForeignKey("users.wallet_address"))
    url: Mapped[str] = mapped_column(Text)
    # e.g. ["consensus.completed", "dispute.resolved", "prediction.resolved"]
    event_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    secret: Mapped[str]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_delivered_at: Mapped[datetime | None] = mapped_column(default=None)
    # The HTTP status the receiving endpoint returned on the most recent
    # delivery attempt, or a small negative sentinel for a failure that
    # never got an HTTP response at all (timeout, DNS, connection refused)
    # — see services/webhooks.py's DELIVERY_TIMEOUT_STATUS/DELIVERY_ERROR_STATUS.
    # Purely observability (GET /webhooks shows "is this callback healthy")
    # — a failing webhook is never retried indefinitely or auto-disabled;
    # see that module's own docstring on why.
    last_delivery_status: Mapped[int | None] = mapped_column(default=None)

    user: Mapped["User"] = relationship()


