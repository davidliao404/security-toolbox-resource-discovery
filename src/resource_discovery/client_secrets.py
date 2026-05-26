from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .request_auth import AuthError


@dataclass(frozen=True)
class ClientSecretRecord:
    tenant_id: str
    client_id: str
    secret_ref: str
    active: bool
    created_at: datetime
    updated_at: datetime


class ClientSecretRepository(Protocol):
    def upsert(self, record: ClientSecretRecord) -> None:
        """Create or replace the active secret reference."""

    def load_active(self, tenant_id: str, client_id: str) -> ClientSecretRecord:
        """Load the active secret reference for a tenant/client pair."""


class SecretMaterialResolver(Protocol):
    def resolve_material(self, secret_ref: str) -> str:
        """Resolve the secret material behind a secret reference."""


class StaticSecretMaterialResolver:
    def __init__(self, material_by_ref: dict[str, str]) -> None:
        self.material_by_ref = material_by_ref

    def resolve_material(self, secret_ref: str) -> str:
        try:
            return self.material_by_ref[secret_ref]
        except KeyError:
            raise AuthError("Unknown client credentials", code="unknown_client") from None


class ClientSecretRotationService:
    def __init__(self, repository: ClientSecretRepository, material_resolver: SecretMaterialResolver) -> None:
        self.repository = repository
        self.material_resolver = material_resolver

    def activate(self, tenant_id: str, client_id: str, secret_ref: str) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert(
            ClientSecretRecord(
                tenant_id=tenant_id,
                client_id=client_id,
                secret_ref=secret_ref,
                active=True,
                created_at=now,
                updated_at=now,
            )
        )

    def resolve(self, tenant_id: str, client_id: str) -> str:
        record = self.repository.load_active(tenant_id, client_id)
        if not record.active:
            raise AuthError("Unknown client credentials", code="unknown_client")
        return self.material_resolver.resolve_material(record.secret_ref)
