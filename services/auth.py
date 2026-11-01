"""
Password hashing and signed session tokens (standard library only).

Passwords: scrypt with a per-user random salt, stored as ``scrypt$<salt>$<hash>``.
Tokens:    ``<base64url payload>.<hmac-sha256>`` signed with SECRET_KEY, 12 h lifetime.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from config import settings

TOKEN_TTL_SECONDS = 12 * 3600
_PREFIX = "scrypt$"


def _secret() -> bytes:
    key = settings.SECRET_KEY
    if not key:
        if settings.APP_ENV == "production":
            raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
        key = "dev-only-insecure-key"  # local development only
    return key.encode()


def ensure_configured() -> None:
    """Call at startup so a missing SECRET_KEY in production fails the deploy, not the first login."""
    _secret()


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{_PREFIX}{salt.hex()}${_scrypt(password, salt).hex()}"


def is_hashed(stored: str) -> bool:
    return stored.startswith(_PREFIX)


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. Unknown users (stored=None) still cost one hash."""
    if stored is None:
        _scrypt(password, bytes(16))  # spend comparable time so unknown usernames aren't distinguishable
        return False
    if not is_hashed(stored):
        # Legacy row saved before hashing existed: it holds the plaintext password.
        return hmac.compare_digest(password.encode(), stored.encode())
    _, salt_hex, hash_hex = stored.split("$")
    return hmac.compare_digest(_scrypt(password, bytes.fromhex(salt_hex)), bytes.fromhex(hash_hex))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(username: str) -> str:
    payload = _b64(json.dumps({"u": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode())
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str | None) -> str | None:
    """Return the username a valid, unexpired token was issued to, else None."""
    try:
        payload, sig = (token or "").split(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return data["u"] if data["exp"] > time.time() else None
    except (ValueError, KeyError, TypeError):
        return None
