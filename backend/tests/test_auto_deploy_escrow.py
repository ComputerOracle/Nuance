"""Tests for services/genlayer_deploy.py — the actual Part 2 finish line:
a real NuanceEscrow instance deployed automatically for every new escrow,
not just ones manually linked via `genlayer_indexer.py --link-demo`.

Mocks app.services.genlayer_deploy.deploy_contract entirely (no
subprocess, no real network, no real testnet GEN spent) and covers:
  1. deploy_escrow_contract links a real escrow correctly — contract_address
     and the milestone's on_chain_index — and passes the right constructor
     args (creator, counterparty, milestone name/criteria, amount converted
     to real wei — see genlayer_deploy.py's _gen_to_wei/_bigint_arg for why
     it's wrapped rather than a bare int).
  2. A failed deploy (deploy_contract returns None) leaves the escrow
     unlinked, same as any pre-cutover row — no exception, no partial state.
  3. An already-linked escrow is left alone — deploy_contract is never
     even called (idempotency guard against a duplicate/retry queue).
  4. End-to-end: POST /escrows (with auto_deploy_escrow_contracts turned
     on for this test only, overriding conftest.py's safe default) really
     queues the background task, which really links the escrow by the
     time the test's own follow-up GET runs — same reliance on
     TestClient's background-task-completes-before-return behavior the
     rest of this suite already depends on (see test_consensus.py).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

_TMP_DIR = tempfile.mkdtemp(prefix="nuance-auto-deploy-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DIR}/test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32bytes+")

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

import app.services.genlayer_deploy as genlayer_deploy  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.enums import StatusKey  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Escrow, Milestone, User  # noqa: E402

_FAKE_ADDRESS = "0xF00Dbabe00000000000000000000000000000042"


@pytest.fixture(scope="module", autouse=True)
def _init_schema():
    with TestClient(app):
        yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _get_token(client: TestClient, wallet: Account) -> str:
    message = client.post("/auth/nonce", json={"wallet_address": wallet.address}).json()["message"]
    signed = wallet.sign_message(encode_defunct(text=message))
    resp = client.post(
        "/auth/verify",
        json={"wallet_address": wallet.address, "message": message, "signature": signed.signature.hex()},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _create_escrow_row(
    creator: str,
    counterparty: str,
    total: str,
    criteria: str,
    contract_address: str | None = None,
    asset_id: int = 1,
    status_key: StatusKey = StatusKey.IN_PROGRESS,
    deploy_attempted_at: datetime | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        for addr in (creator, counterparty):
            if await db.get(User, addr) is None:
                db.add(User(wallet_address=addr))
        escrow = Escrow(
            creator_address=creator,
            counterparty_address=counterparty,
            title="Auto-deploy test escrow",
            total=Decimal(total),
            asset_id=asset_id,
            status_key=status_key,
            contract_address=contract_address,
            deploy_attempted_at=deploy_attempted_at,
        )
        escrow.milestones.append(
            Milestone(
                name="Milestone 1",
                amount=Decimal(total),
                status_key=StatusKey.PENDING,
                criteria=criteria,
                order_index=0,
            )
        )
        db.add(escrow)
        await db.commit()
        await db.refresh(escrow)
        return escrow.id


async def _get_escrow(escrow_id: int) -> Escrow:
    async with AsyncSessionLocal() as db:
        return await db.get(Escrow, escrow_id)


async def _get_milestone(escrow_id: int) -> Milestone:
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Milestone).where(Milestone.escrow_id == escrow_id))
        return result.scalars().one()


def test_deploy_escrow_contract_links_correctly(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
            "500.00",
            "Ship the thing.",
        )
    )

    captured = {}

    async def _fake_deploy_contract(file, args):
        captured["file"] = file
        captured["args"] = args
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.deploy_escrow_contract(escrow_id))

    escrow = asyncio.run(_get_escrow(escrow_id))
    milestone = asyncio.run(_get_milestone(escrow_id))
    assert escrow.contract_address == _FAKE_ADDRESS
    assert milestone.on_chain_index == 0
    assert escrow.deploy_attempted_at is not None

    assert captured["file"] == "nuance_escrow.py"
    creator, counterparty, milestone_name, amount_arg, criteria = captured["args"]
    assert creator == "0x1111111111111111111111111111111111111111"
    assert counterparty == "0x2222222222222222222222222222222222222222"
    assert milestone_name == "Milestone 1"
    # Wrapped via _bigint_arg — see that function's own docstring for why
    # a bare Python int can't safely cross the JSON bridge to
    # scripts/genlayer-deploy.ts at this magnitude.
    assert amount_arg == {"__bigint__": str(500 * 10**18)}  # 500.00 GEN -> wei
    assert criteria == "Ship the thing."


def test_deploy_escrow_contract_skips_non_native_asset(monkeypatch):
    """Regression test for a real fund-safety bug found 2026-09-10
    (integration audit): this function used to have no idea ROADMAP.md
    Part 4 6.2's Asset model existed — it would deploy a real on-chain
    NuanceEscrow for a non-native-asset escrow (e.g. the seeded testnet
    USDC, asset_id=2) using _gen_to_wei's fixed 18-decimal GEN
    conversion, and NuanceEscrow.fund_escrow only ever accepts native
    currency (gl.message.value) — there's no ERC-20 transfer path
    anywhere in the contract or components/app/genlayer-write-client.ts.
    Must stay off-chain (deploy_contract never even called) until this
    contract actually supports a second settlement asset."""
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x3333333333333333333333333333333333333333",
            "0x4444444444444444444444444444444444444444",
            "9000.00",
            "Pay in USDC.",
            asset_id=2,  # seeded testnet USDC — see app/db.py::_seed_assets
        )
    )

    called = {"deploy_contract": False}

    async def _fake_deploy_contract(file, args):
        called["deploy_contract"] = True
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.deploy_escrow_contract(escrow_id))

    assert called["deploy_contract"] is False
    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address is None


def test_deploy_escrow_contract_failed_deploy_leaves_it_unlinked(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x3333333333333333333333333333333333333333",
            "0x4444444444444444444444444444444444444444",
            "10.00",
            "Whatever.",
        )
    )

    async def _fake_deploy_contract(file, args):
        return None  # simulates a real deploy failure

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.deploy_escrow_contract(escrow_id))

    escrow = asyncio.run(_get_escrow(escrow_id))
    milestone = asyncio.run(_get_milestone(escrow_id))
    assert escrow.contract_address is None
    assert milestone.on_chain_index is None
    # FIXED 2026-09-12 — a failed attempt still counts as "attempted," so
    # retry_undeployed_escrows knows not to immediately re-fire it (see
    # that function's own cooldown reasoning).
    assert escrow.deploy_attempted_at is not None


def test_deploy_escrow_contract_skips_already_linked(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x5555555555555555555555555555555555555555",
            "0x6666666666666666666666666666666666666666",
            "25.00",
            "Already linked.",
            contract_address="0xAlreadyLinked000000000000000000000001",
        )
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called for an already-linked escrow")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.deploy_escrow_contract(escrow_id))  # must not raise

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address == "0xAlreadyLinked000000000000000000000001"


def test_create_escrow_endpoint_queues_and_completes_deploy(client: TestClient, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_deploy_escrow_contracts", True)

    async def _fake_deploy_contract(file, args):
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    creator = Account.create()
    token = _get_token(client, creator)

    resp = client.post(
        "/escrows",
        json={
            "title": "Real end-to-end auto-deploy test",
            "counterparty_address": "0x" + "7" * 40,
            "total": 100,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    escrow_id = resp.json()["id"]

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address == _FAKE_ADDRESS


# --- retry_undeployed_escrows ---------------------------------------------
#
# FIXED 2026-09-12 — a real gap found live: deploy_escrow_contract was a
# pure one-shot fire-and-forget background task queued exactly once, at
# creation. A failed or interrupted attempt left an escrow off-chain (no
# real GEN custody, ever) PERMANENTLY, with no way for this app to ever
# try again. See Escrow.deploy_attempted_at's own docstring for the full
# account.


def test_retry_undeployed_escrows_retries_a_never_attempted_escrow(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x8888888888888888888888888888888888888888",
            "0x9999999999999999999999999999999999999999",
            "12.00",
            "Never attempted yet.",
        )
    )

    async def _fake_deploy_contract(file, args):
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.retry_undeployed_escrows())

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address == _FAKE_ADDRESS


def test_retry_undeployed_escrows_retries_a_stale_failed_attempt(monkeypatch):
    stale = datetime.now(timezone.utc) - genlayer_deploy._DEPLOY_RETRY_COOLDOWN - timedelta(minutes=1)
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "12.00",
            "Failed a while ago.",
            deploy_attempted_at=stale,
        )
    )

    async def _fake_deploy_contract(file, args):
        return _FAKE_ADDRESS

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fake_deploy_contract)

    asyncio.run(genlayer_deploy.retry_undeployed_escrows())

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address == _FAKE_ADDRESS


def test_retry_undeployed_escrows_skips_a_recent_attempt_in_cooldown(monkeypatch):
    """The core safety property: an attempt from 1 minute ago could
    plausibly still be running (deploy_contract's own subprocess timeout
    is measured in minutes) — retrying it now would risk double-submitting
    a real, testnet-GEN-costing deploy transaction."""
    recent = datetime.now(timezone.utc) - timedelta(minutes=1)
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0xcccccccccccccccccccccccccccccccccccccccc",
            "0xdddddddddddddddddddddddddddddddddddddddd",
            "12.00",
            "Attempted very recently.",
            deploy_attempted_at=recent,
        )
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should not be called for an attempt still in cooldown")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_escrows())  # must not raise

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address is None


def test_retry_undeployed_escrows_skips_cancelled_escrows(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            "0xffffffffffffffffffffffffffffffffffffffff",
            "12.00",
            "Cancelled before ever deploying.",
            status_key=StatusKey.CANCELLED,
        )
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called for a cancelled escrow")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_escrows())  # must not raise

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address is None


def test_retry_undeployed_escrows_skips_non_native_asset(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x1010101010101010101010101010101010101010",
            "0x2020202020202020202020202020202020202020",
            "12.00",
            "USDC-denominated, never eligible.",
            asset_id=2,  # seeded testnet USDC
        )
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called for a non-native asset")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_escrows())  # must not raise

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address is None


def test_retry_undeployed_escrows_skips_already_linked(monkeypatch):
    escrow_id = asyncio.run(
        _create_escrow_row(
            "0x3030303030303030303030303030303030303030",
            "0x4040404040404040404040404040404040404040",
            "12.00",
            "Already linked.",
            contract_address="0xAlreadyLinked000000000000000000000002",
        )
    )

    def _fail_if_called(file, args):
        raise AssertionError("deploy_contract should never be called for an already-linked escrow")

    monkeypatch.setattr(genlayer_deploy, "deploy_contract", _fail_if_called)

    asyncio.run(genlayer_deploy.retry_undeployed_escrows())  # must not raise

    escrow = asyncio.run(_get_escrow(escrow_id))
    assert escrow.contract_address == "0xAlreadyLinked000000000000000000000002"


class _FlakyCommitDb:
    """Duck-typed stand-in for the one thing genlayer_deploy._commit_or_
    raise_loudly actually calls (db.commit()/db.rollback()) — deliberately
    NOT a real AsyncSession, since patching every SQLAlchemy session's
    commit() globally would also break the unrelated deploy_attempted_at
    commit earlier in deploy_escrow_contract (by design not wrapped in
    retry logic — see that function's own comment on why losing it is
    cheap). This isolates the one commit this test suite actually needs
    to make flaky."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self):
        self.commit_calls += 1
        if self.commit_calls <= self.fail_times:
            raise OperationalError("UPDATE escrows ...", {}, Exception("database is locked"))

    async def rollback(self):
        self.rollback_calls += 1


def test_commit_or_raise_loudly_recovers_from_transient_lock(monkeypatch):
    """FOUND 2026-09-14, live: a real NuanceEscrow deploy (real gas spent)
    got its address commit dropped by a transient 'database is locked' —
    _commit_or_raise_loudly exists so that a passing collision like this
    one doesn't lose a real on-chain fact. No sleep in this test — the
    retry backoff would make this test slow for no reason; the actual
    delay math isn't what's under test here."""
    monkeypatch.setattr(genlayer_deploy.asyncio, "sleep", _instant_sleep)
    db = _FlakyCommitDb(fail_times=2)

    asyncio.run(genlayer_deploy._commit_or_raise_loudly(db, context="test"))

    assert db.commit_calls == 3  # 2 failures + 1 success
    assert db.rollback_calls == 2


def test_commit_or_raise_loudly_raises_after_exhausting_retries(monkeypatch):
    """The other half: if the lock never clears, this must NOT behave
    like an ordinary failed deploy (deploy_contract returning None,
    silently left for the next retry sweep) — that would permanently
    lose track of a contract address real testnet GEN already paid for.
    Raising is what makes retry_undeployed_escrows' own try/except
    (genlayer_deploy.py) — not this function — the one place that
    decides what happens next, and makes deploy_escrow_contract's own
    background-task failure show up as a real traceback instead of a
    quiet, misleading 'deploy failed' log line."""
    monkeypatch.setattr(genlayer_deploy.asyncio, "sleep", _instant_sleep)
    db = _FlakyCommitDb(fail_times=999)

    with pytest.raises(OperationalError):
        asyncio.run(
            genlayer_deploy._commit_or_raise_loudly(db, context="test-always-fails")
        )

    assert db.commit_calls == genlayer_deploy._COMMIT_RETRY_ATTEMPTS
    assert db.rollback_calls == genlayer_deploy._COMMIT_RETRY_ATTEMPTS


async def _instant_sleep(_seconds):
    return None
