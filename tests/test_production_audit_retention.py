from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from resource_discovery.postgres_store import PostgresAuditRepository, PostgresRetentionRepository


class FakeRowsResult:
    def __init__(self, *, rows=None, first=None, rowcount=0):
        self._rows = rows or []
        self._first = first
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self._rows

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


def test_postgres_audit_search_filters_by_tenant_event_type_and_task():
    rows = [
        {
            "tenant_id": "tenant_a",
            "task_id": "task_1",
            "event_type": "discovery_task_completed",
            "details": {"ok": True},
            "created_at": datetime(2026, 5, 25, tzinfo=timezone.utc),
        }
    ]
    repo = PostgresAuditRepository(FakeEngine([FakeRowsResult(rows=rows)]))

    events = repo.search_events("tenant_a", event_type="discovery_task_completed", task_id="task_1", limit=10)

    assert events == rows
    compiled = str(repo.engine.connection.statements[0])
    assert "tenant_id" in compiled
    assert "event_type" in compiled
    assert "task_id" in compiled


def test_postgres_retention_policy_defaults_when_missing():
    repo = PostgresRetentionRepository(FakeEngine([FakeRowsResult(first=None)]))

    policy = repo.load_policy("tenant_a")

    assert policy == {"task_days": 180, "result_days": 90, "audit_days": 365, "nonce_days": 1}


def test_postgres_retention_cleanup_scopes_customer_rows_by_tenant():
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)
    policy = SimpleNamespace(task_days=180, result_days=90, audit_days=365, nonce_days=1)
    repo = PostgresRetentionRepository(
        FakeEngine(
            [
                FakeRowsResult(first=policy),
                FakeRowsResult(rowcount=2),
                FakeRowsResult(rowcount=3),
                FakeRowsResult(rowcount=1),
                FakeRowsResult(rowcount=4),
            ]
        )
    )

    deleted = repo.cleanup_expired_rows("tenant_a", now=now)

    assert deleted == {"results": 2, "tasks": 3, "audit_events": 1, "request_nonces": 4}
    statements = "\n".join(str(statement) for statement in repo.engine.connection.statements)
    assert "tenant_id" in statements
    assert str(now - timedelta(days=180)).split("+")[0][:10] not in statements
