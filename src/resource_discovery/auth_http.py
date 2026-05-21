from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol

from .request_auth import AuthError, NonceStore, verify_signature


class ClientSecretResolver(Protocol):
    def resolve(self, tenant_id: str, client_id: str) -> str:
        """Return the shared secret for a tenant/client pair."""


class FileClientSecretResolver:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def resolve(self, tenant_id: str, client_id: str) -> str:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            return payload[tenant_id][client_id]
        except KeyError:
            raise AuthError("Unknown client credentials", code="unknown_client") from None


def authenticate_http_request(
    *,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    resolver: ClientSecretResolver,
    nonce_store: NonceStore,
    now: datetime,
    allowed_skew_seconds: int = 300,
) -> dict[str, str]:
    required = ["X-Tenant-Id", "X-Client-Id", "X-Timestamp", "X-Nonce", "X-Signature"]
    missing = [name for name in required if not headers.get(name)]
    if missing:
        raise AuthError("Missing authentication header", code="missing_auth_header")
    tenant_id = headers["X-Tenant-Id"]
    client_id = headers["X-Client-Id"]
    secret = resolver.resolve(tenant_id, client_id)
    verify_signature(
        secret=secret,
        method=method,
        path=path,
        timestamp=headers["X-Timestamp"],
        nonce=headers["X-Nonce"],
        body=body,
        signature=headers["X-Signature"],
        now=now,
        allowed_skew_seconds=allowed_skew_seconds,
        nonce_store=nonce_store,
    )
    return {"tenant_id": tenant_id, "client_id": client_id}
