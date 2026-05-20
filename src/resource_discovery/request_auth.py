from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


class AuthError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class NonceStore(Protocol):
    def remember_once(self, nonce: str, timestamp: datetime) -> bool:
        """Return False when the nonce was already seen."""


@dataclass
class InMemoryNonceStore:
    seen: set[str] | None = None

    def __post_init__(self) -> None:
        if self.seen is None:
            self.seen = set()

    def remember_once(self, nonce: str, timestamp: datetime) -> bool:
        assert self.seen is not None
        if nonce in self.seen:
            return False
        self.seen.add(nonce)
        return True


def build_signature(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    canonical = _canonical_request(method=method, path=path, timestamp=timestamp, nonce=nonce, body=body)
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
    now: datetime | None = None,
    allowed_skew_seconds: int = 300,
    nonce_store: NonceStore | None = None,
) -> bool:
    request_time = _parse_timestamp(timestamp)
    current_time = now or datetime.now(timezone.utc)
    if abs((current_time - request_time).total_seconds()) > allowed_skew_seconds:
        raise AuthError("Request timestamp is outside the allowed window", code="timestamp_out_of_window")

    expected = build_signature(
        secret=secret,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    if not hmac.compare_digest(expected, signature):
        raise AuthError("Invalid request signature", code="invalid_signature")

    if nonce_store is not None and not nonce_store.remember_once(nonce, request_time):
        raise AuthError("Request nonce has already been used", code="replay_detected")
    return True


def _canonical_request(*, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return "\n".join([method.upper(), path, timestamp, nonce, body_hash])


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AuthError("Invalid request timestamp", code="invalid_timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
