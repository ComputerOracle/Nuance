"""JWT session tokens + personal_sign (EIP-191) signature recovery.

Pure helpers with no DB/FastAPI dependency — app/dependencies.py and
app/routers/auth.py compose these into the actual request flow.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct

from app.config import get_settings

settings = get_settings()

JWT_ALGORITHM = "HS256"

# How long a server-issued nonce stays valid for signing, independent of
# the JWT's own expiry (jwt_expires_minutes) issued once it's redeemed.
NONCE_TTL_MINUTES = 10


class InvalidSignatureError(Exception):
    """A (message, signature) pair didn't recover to a valid address."""


class TokenError(Exception):
    """A bearer token was missing, malformed, expired, or mis-signed."""


def generate_nonce() -> str:
    return secrets.token_hex(16)


def build_signin_message(wallet_address: str, nonce: str, issued_at: datetime) -> str:
    """The exact human-readable string the wallet is asked to sign.
    `/auth/verify` only requires that `nonce` appear somewhere in the
    message it's given (see verify_nonce_membership) — this is the message
    /auth/nonce hands back for the client to sign as-is.
    """
    return (
        "Sign in to Nuance\n\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at.isoformat()}"
    )


def nonce_is_expired(nonce_issued_at: datetime | None) -> bool:
    if nonce_issued_at is None:
        return True
    issued = nonce_issued_at
    if issued.tzinfo is None:
        # SQLite round-trips datetimes as naive; treat naive as UTC since
        # that's what we always write (datetime.now(timezone.utc)).
        issued = issued.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - issued > timedelta(minutes=NONCE_TTL_MINUTES)


def recover_signer(message: str, signature: str) -> str:
    """Recovers the checksummed address that produced `signature` over
    `message` via personal_sign. Normalizes every failure mode (bad hex,
    wrong length, malformed v/r/s) to one InvalidSignatureError so callers
    don't need to know eth_account's internal exception types."""
    try:
        signable = encode_defunct(text=message)
        return Account.recover_message(signable, signature=signature)
    except Exception as exc:  # noqa: BLE001 — collapse all recovery failures to one type
        raise InvalidSignatureError(str(exc)) from exc


def create_access_token(wallet_address: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": wallet_address,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the wallet_address (`sub` claim) of a valid, unexpired token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    wallet_address = payload.get("sub")
    if not wallet_address:
        raise TokenError("Token missing 'sub' claim.")
    return wallet_address
