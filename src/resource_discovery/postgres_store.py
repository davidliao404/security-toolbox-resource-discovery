from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, create_engine, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .client_secrets import ClientSecretRecord
from .db import (
    audit_events,
    client_secrets as client_secrets_table,
    rate_limit_buckets,
    request_nonces,
    retention_policies,
    scope_profiles,
    task_results,
    tasks,
)
from .repositories import _parse_cursor
from .request_auth import AuthError
from .scope_guard import TenantScopeProfile


def create_postgres_engine(database_url: str) -> Engine:
    if not database_url:
        raise ValueError("RESOURCE_DISCOVERY_DATABASE_URL is required for postgres storage")
    return create_engine(database_url, pool_pre_ping=True, future=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresTaskRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, payload: dict[str, Any]) -> None:
        self.update(payload)

    def update(self, payload: dict[str, Any]) -> None:
        task = payload["task"]
        now = _utcnow()
        stmt = pg_insert(tasks).values(
            tenant_id=task["tenant_id"],
            task_id=task["task_id"],
            client_id=payload.get("client_id", ""),
            status=str(task["status"]),
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[tasks.c.tenant_id, tasks.c.task_id],
            set_={
                "client_id": stmt.excluded.client_id,
                "status": stmt.excluded.status,
                "payload": stmt.excluded.payload,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def load(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(tasks.c.payload).where(tasks.c.tenant_id == tenant_id, tasks.c.task_id == task_id)
            ).first()
        if row is None:
            raise FileNotFoundError(f"Task not found: {tenant_id}/{task_id}")
        return row.payload

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(tasks.c.task_id, tasks.c.status, tasks.c.updated_at)
            .where(tasks.c.tenant_id == tenant_id)
            .order_by(tasks.c.updated_at.desc())
        )
        with self.engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(row) for row in rows]


class PostgresResultRepository:
    def __init__(self, engine: Engine, max_page_limit: int = 500) -> None:
        self.engine = engine
        self.max_page_limit = max_page_limit

    def save_results(self, tenant_id: str, task_id: str, payload: dict[str, Any]) -> None:
        now = _utcnow()
        with self.engine.begin() as conn:
            conn.execute(delete(task_results).where(task_results.c.tenant_id == tenant_id, task_results.c.task_id == task_id))
            rows = []
            for result_type in ("assets", "services", "source_evidence"):
                for position, item in enumerate(payload.get(result_type, [])):
                    rows.append(
                        {
                            "tenant_id": tenant_id,
                            "task_id": task_id,
                            "result_type": result_type,
                            "position": position,
                            "payload": item,
                            "created_at": now,
                        }
                    )
            if rows:
                conn.execute(insert(task_results), rows)

    def load_results(
        self,
        tenant_id: str,
        task_id: str,
        cursor: str | None,
        limit: int,
        result_type: str = "assets",
    ) -> dict[str, Any]:
        if result_type not in {"assets", "services", "source_evidence"}:
            raise ValueError(f"Unsupported result_type: {result_type}")
        start = _parse_cursor(cursor)
        effective_limit = max(1, min(limit, self.max_page_limit))
        stmt = (
            select(task_results.c.payload)
            .where(
                task_results.c.tenant_id == tenant_id,
                task_results.c.task_id == task_id,
                task_results.c.result_type == result_type,
            )
            .order_by(task_results.c.position)
            .limit(effective_limit + 1)
            .offset(start)
        )
        with self.engine.begin() as conn:
            rows = conn.execute(stmt).all()
        visible = rows[:effective_limit]
        items = [row.payload for row in visible]
        next_cursor = str(start + effective_limit) if len(rows) > effective_limit else None
        return {
            "task_id": task_id,
            "assets": items if result_type == "assets" else [],
            "services": items if result_type == "services" else [],
            "source_evidence": items if result_type == "source_evidence" else [],
            "page": {"next_cursor": next_cursor, "limit": effective_limit, "type": result_type},
        }


class PostgresScopeProfileRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save(self, profile: TenantScopeProfile) -> None:
        now = _utcnow()
        payload = profile.__dict__
        stmt = pg_insert(scope_profiles).values(
            tenant_id=profile.tenant_id,
            profile_id=profile.profile_id,
            status=profile.status,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[scope_profiles.c.tenant_id, scope_profiles.c.profile_id],
            set_={"status": stmt.excluded.status, "payload": stmt.excluded.payload, "updated_at": stmt.excluded.updated_at},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def load_active(self, tenant_id: str, profile_id: str) -> TenantScopeProfile:
        with self.engine.begin() as conn:
            row = conn.execute(
                select(scope_profiles.c.payload).where(
                    scope_profiles.c.tenant_id == tenant_id,
                    scope_profiles.c.profile_id == profile_id,
                )
            ).first()
        if row is None:
            raise FileNotFoundError(f"Scope profile not found: {tenant_id}/{profile_id}")
        profile = TenantScopeProfile(**row.payload)
        if profile.status != "active":
            raise ValueError(f"Scope profile is not active: {profile_id}")
        return profile


class PostgresNonceRepository:
    def __init__(self, engine: Engine, window_seconds: int = 300) -> None:
        self.engine = engine
        self.window_seconds = window_seconds

    def remember_once(self, nonce: str, timestamp: datetime) -> bool:
        request_time = timestamp.astimezone(timezone.utc)
        expires_at = request_time + timedelta(seconds=self.window_seconds)
        with self.engine.begin() as conn:
            conn.execute(delete(request_nonces).where(request_nonces.c.expires_at < request_time))
            result = conn.execute(
                pg_insert(request_nonces)
                .values(nonce=nonce, timestamp=request_time, expires_at=expires_at)
                .on_conflict_do_nothing(index_elements=[request_nonces.c.nonce])
                .returning(request_nonces.c.nonce)
            )
        return result.scalar_one_or_none() is not None


class PostgresAuditRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def record_event(self, tenant_id: str, task_id: str, event_type: str, details: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(audit_events).values(
                    tenant_id=tenant_id,
                    task_id=task_id,
                    event_type=event_type,
                    details=details,
                    created_at=_utcnow(),
                )
            )

    def list_events(self, tenant_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(
                audit_events.c.tenant_id,
                audit_events.c.task_id,
                audit_events.c.event_type,
                audit_events.c.details,
                audit_events.c.created_at,
            )
            .where(audit_events.c.tenant_id == tenant_id)
            .order_by(audit_events.c.id)
        )
        with self.engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(row) for row in rows]

    def search_events(
        self,
        tenant_id: str,
        event_type: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = [audit_events.c.tenant_id == tenant_id]
        if event_type:
            conditions.append(audit_events.c.event_type == event_type)
        if task_id:
            conditions.append(audit_events.c.task_id == task_id)
        stmt = (
            select(
                audit_events.c.tenant_id,
                audit_events.c.task_id,
                audit_events.c.event_type,
                audit_events.c.details,
                audit_events.c.created_at,
            )
            .where(*conditions)
            .order_by(audit_events.c.id.desc())
            .limit(max(1, min(limit, 500)))
        )
        with self.engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(row) for row in rows]


class PostgresClientSecretRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def upsert(self, record: ClientSecretRecord) -> None:
        stmt = pg_insert(client_secrets_table).values(
            tenant_id=record.tenant_id,
            client_id=record.client_id,
            secret_ref=record.secret_ref,
            active=record.active,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[client_secrets_table.c.tenant_id, client_secrets_table.c.client_id],
            set_={
                "secret_ref": stmt.excluded.secret_ref,
                "active": stmt.excluded.active,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def load_active(self, tenant_id: str, client_id: str) -> ClientSecretRecord:
        stmt = select(
            client_secrets_table.c.tenant_id,
            client_secrets_table.c.client_id,
            client_secrets_table.c.secret_ref,
            client_secrets_table.c.active,
            client_secrets_table.c.created_at,
            client_secrets_table.c.updated_at,
        ).where(
            client_secrets_table.c.tenant_id == tenant_id,
            client_secrets_table.c.client_id == client_id,
            client_secrets_table.c.active.is_(True),
        )
        with self.engine.begin() as conn:
            row = conn.execute(stmt).first()
        if row is None:
            raise AuthError("Unknown client credentials", code="unknown_client")
        return ClientSecretRecord(
            tenant_id=row.tenant_id,
            client_id=row.client_id,
            secret_ref=row.secret_ref,
            active=row.active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class PostgresRateLimitBucketRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_used(self, tenant_id: str, bucket_name: str, window_start: datetime) -> int:
        stmt = select(rate_limit_buckets.c.used).where(
            rate_limit_buckets.c.tenant_id == tenant_id,
            rate_limit_buckets.c.bucket_name == bucket_name,
            rate_limit_buckets.c.window_start == window_start,
        )
        with self.engine.begin() as conn:
            row = conn.execute(stmt).first()
        return int(row.used) if row is not None else 0

    def increment(self, tenant_id: str, bucket_name: str, window_start: datetime, amount: int, limit_value: int) -> int:
        stmt = pg_insert(rate_limit_buckets).values(
            tenant_id=tenant_id,
            bucket_name=bucket_name,
            window_start=window_start,
            used=amount,
            limit_value=limit_value,
            updated_at=_utcnow(),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_rate_limit_bucket",
            set_={
                "used": rate_limit_buckets.c.used + amount,
                "limit_value": limit_value,
                "updated_at": stmt.excluded.updated_at,
            },
        ).returning(rate_limit_buckets.c.used)
        with self.engine.begin() as conn:
            return int(conn.execute(stmt).scalar_one())


class PostgresRetentionRepository:
    DEFAULT_POLICY = {"task_days": 180, "result_days": 90, "audit_days": 365, "nonce_days": 1}

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def load_policy(self, tenant_id: str) -> dict[str, int]:
        stmt = select(
            retention_policies.c.task_days,
            retention_policies.c.result_days,
            retention_policies.c.audit_days,
            retention_policies.c.nonce_days,
        ).where(retention_policies.c.tenant_id == tenant_id)
        with self.engine.begin() as conn:
            row = conn.execute(stmt).first()
        if row is None:
            return dict(self.DEFAULT_POLICY)
        return {
            "task_days": int(row.task_days),
            "result_days": int(row.result_days),
            "audit_days": int(row.audit_days),
            "nonce_days": int(row.nonce_days),
        }

    def cleanup_expired_rows(self, tenant_id: str, now: datetime) -> dict[str, int]:
        policy = self.load_policy(tenant_id)
        result_cutoff = now - timedelta(days=policy["result_days"])
        task_cutoff = now - timedelta(days=policy["task_days"])
        audit_cutoff = now - timedelta(days=policy["audit_days"])
        nonce_cutoff = now - timedelta(days=policy["nonce_days"])
        with self.engine.begin() as conn:
            deleted_results = conn.execute(
                delete(task_results).where(
                    task_results.c.tenant_id == tenant_id,
                    task_results.c.created_at < result_cutoff,
                )
            ).rowcount
            deleted_tasks = conn.execute(
                delete(tasks).where(
                    tasks.c.tenant_id == tenant_id,
                    tasks.c.updated_at < task_cutoff,
                )
            ).rowcount
            deleted_audit = conn.execute(
                delete(audit_events).where(
                    audit_events.c.tenant_id == tenant_id,
                    audit_events.c.created_at < audit_cutoff,
                )
            ).rowcount
            deleted_nonces = conn.execute(delete(request_nonces).where(request_nonces.c.expires_at < nonce_cutoff)).rowcount
        return {
            "results": int(deleted_results or 0),
            "tasks": int(deleted_tasks or 0),
            "audit_events": int(deleted_audit or 0),
            "request_nonces": int(deleted_nonces or 0),
        }
