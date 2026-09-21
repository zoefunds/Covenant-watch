"""
SIWE-style wallet auth: nonce issuance + signature verification + signed
session cookie issuance. A connected wallet address alone is NEVER treated
as authenticated -- every protected route depends on `require_session`
(app/api/deps.py) resolving a valid, unexpired, unrevoked Session row whose
address matches.
"""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

from eth_account import Account
from eth_account.messages import encode_defunct
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.nonce import Nonce
from app.models.session import Session as SessionModel

log = get_logger(__name__)
settings = get_settings()

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="covenant-watch-session")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def issue_nonce(db: DBSession, address: str) -> Nonce:
    nonce_value = secrets.token_hex(16)
    expires_at = _utcnow() + dt.timedelta(seconds=settings.NONCE_TTL_SECONDS)
    row = Nonce(address=address, nonce=nonce_value, expires_at=expires_at)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def build_siwe_message(address: str, nonce: str, expires_at: dt.datetime) -> str:
    return (
        "Covenant Watch wants you to sign in with your wallet.\n\n"
        f"Address: {address}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {_utcnow().isoformat()}\n"
        f"Expires At: {expires_at.isoformat()}\n"
        "This signature does not authorize any transaction, spending, or "
        "on-chain action. It only proves control of this address to "
        "Covenant Watch's backend."
    )


class AuthError(Exception):
    pass


def verify_and_consume_nonce(db: DBSession, address: str, message: str, signature: str) -> None:
    """Recovers the signer from (message, signature) and checks it matches
    `address`, then looks up an unused, unexpired nonce embedded in the
    message and marks it used. Raises AuthError on any failure."""

    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception as e:  # noqa: BLE001
        raise AuthError(f"could not recover signer: {e}") from e

    if recovered.lower() != address.lower():
        raise AuthError("signature does not match claimed address")

    nonce_value = None
    for line in message.splitlines():
        if line.startswith("Nonce:"):
            nonce_value = line.split("Nonce:", 1)[1].strip()
            break
    if not nonce_value:
        raise AuthError("message missing nonce")

    row = (
        db.query(Nonce)
        .filter(Nonce.address == address, Nonce.nonce == nonce_value)
        .order_by(Nonce.id.desc())
        .first()
    )
    if row is None:
        raise AuthError("unknown nonce")
    if row.used_at is not None:
        raise AuthError("nonce already used")
    if row.expires_at.replace(tzinfo=dt.timezone.utc) < _utcnow():
        raise AuthError("nonce expired")

    row.used_at = _utcnow()
    db.add(row)
    db.commit()


def create_session(db: DBSession, address: str) -> tuple[str, dt.datetime]:
    """Creates a Session row and returns (signed_cookie_value, expires_at)."""
    session_id = uuid.uuid4().hex
    expires_at = _utcnow() + dt.timedelta(seconds=settings.SESSION_TTL_SECONDS)
    row = SessionModel(id=session_id, address=address, expires_at=expires_at)
    db.add(row)
    db.commit()

    token = _serializer.dumps({"sid": session_id, "addr": address})
    return token, expires_at


def resolve_session(db: DBSession, cookie_value: str) -> SessionModel | None:
    try:
        data = _serializer.loads(cookie_value, max_age=settings.SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None

    sid = data.get("sid")
    if not sid:
        return None

    row = db.get(SessionModel, sid)
    if row is None:
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at.replace(tzinfo=dt.timezone.utc) < _utcnow():
        return None
    if row.address.lower() != str(data.get("addr", "")).lower():
        return None
    return row


def revoke_session(db: DBSession, session_row: SessionModel) -> None:
    session_row.revoked_at = _utcnow()
    db.add(session_row)
    db.commit()
