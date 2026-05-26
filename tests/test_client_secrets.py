from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from resource_discovery.client_secrets import (
    ClientSecretRecord,
    ClientSecretRotationService,
    StaticSecretMaterialResolver,
)
from resource_discovery.postgres_store import PostgresClientSecretRepository
from resource_discovery.request_auth import AuthError


class MemoryClientSecretRepository:
    def __init__(self):
        self.records = {}

    def upsert(self, record):
        self.records[(record.tenant_id, record.client_id)] = record

    def load_active(self, tenant_id, client_id):
        record = self.records.get((tenant_id, client_id))
        if record is None or not record.active:
            raise AuthError("Unknown client credentials", code="unknown_client")
        return record

    def deactivate(self, tenant_id, client_id):
        record = self.records[(tenant_id, client_id)]
        self.records[(tenant_id, client_id)] = ClientSecretRecord(
            tenant_id=record.tenant_id,
            client_id=record.client_id,
            secret_ref=record.secret_ref,
            active=False,
            created_at=record.created_at,
            updated_at=datetime.now(timezone.utc),
        )


class FakeRowsResult:
    def __init__(self, *, first=None):
        self._first = first

    def first(self):
        return self._first


class FakeConnection:
    def __init__(self, results=None):
        self.results = results or []
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        if self.results:
            return self.results.pop(0)
        return FakeRowsResult()


class FakeBegin:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self, results=None):
        self.connection = FakeConnection(results)

    def begin(self):
        return FakeBegin(self.connection)


def test_rotation_service_resolves_active_secret_ref():
    repo = MemoryClientSecretRepository()
    material = StaticSecretMaterialResolver({"vault://tenant_a/toolbox/current": "secret-v2"})
    service = ClientSecretRotationService(repo, material)

    service.activate("tenant_a", "toolbox", "vault://tenant_a/toolbox/current")

    assert service.resolve("tenant_a", "toolbox") == "secret-v2"


def test_rotation_service_rejects_inactive_secret():
    repo = MemoryClientSecretRepository()
    material = StaticSecretMaterialResolver({"vault://tenant_a/toolbox/current": "secret-v2"})
    service = ClientSecretRotationService(repo, material)

    service.activate("tenant_a", "toolbox", "vault://tenant_a/toolbox/current")
    repo.deactivate("tenant_a", "toolbox")

    with pytest.raises(AuthError) as exc:
        service.resolve("tenant_a", "toolbox")
    assert exc.value.code == "unknown_client"


def test_static_secret_material_resolver_rejects_unknown_ref():
    resolver = StaticSecretMaterialResolver({})

    with pytest.raises(AuthError) as exc:
        resolver.resolve_material("vault://missing")

    assert exc.value.code == "unknown_client"


def test_postgres_client_secret_repository_loads_active_record():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        tenant_id="tenant_a",
        client_id="toolbox",
        secret_ref="vault://tenant_a/toolbox/current",
        active=True,
        created_at=now,
        updated_at=now,
    )
    repo = PostgresClientSecretRepository(FakeEngine([FakeRowsResult(first=row)]))

    record = repo.load_active("tenant_a", "toolbox")

    assert record.secret_ref == "vault://tenant_a/toolbox/current"
    assert record.active is True


def test_postgres_client_secret_repository_upserts_record():
    now = datetime.now(timezone.utc)
    engine = FakeEngine()
    repo = PostgresClientSecretRepository(engine)

    repo.upsert(
        ClientSecretRecord(
            tenant_id="tenant_a",
            client_id="toolbox",
            secret_ref="vault://tenant_a/toolbox/current",
            active=True,
            created_at=now,
            updated_at=now,
        )
    )

    assert len(engine.connection.statements) == 1


def test_postgres_client_secret_repository_rejects_missing_record():
    repo = PostgresClientSecretRepository(FakeEngine([FakeRowsResult(first=None)]))

    with pytest.raises(AuthError) as exc:
        repo.load_active("tenant_a", "missing")

    assert exc.value.code == "unknown_client"
