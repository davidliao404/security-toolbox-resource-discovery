from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .repositories import _parse_cursor
from .scope_guard import TenantScopeProfile


def initialize_sqlite(path: str | Path) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            create table if not exists tasks (
                tenant_id text not null,
                task_id text not null,
                status text not null,
                payload text not null,
                updated_at text not null,
                primary key (tenant_id, task_id)
            );
            create table if not exists results (
                tenant_id text not null,
                task_id text not null,
                result_type text not null,
                position integer not null,
                payload text not null,
                primary key (tenant_id, task_id, result_type, position)
            );
            create table if not exists scope_profiles (
                tenant_id text not null,
                profile_id text not null,
                status text not null,
                payload text not null,
                updated_at text not null,
                primary key (tenant_id, profile_id)
            );
            create table if not exists nonces (
                nonce text primary key,
                timestamp text not null,
                expires_at text not null
            );
            create table if not exists audit_events (
                id integer primary key autoincrement,
                tenant_id text not null,
                task_id text not null,
                event_type text not null,
                details text not null,
                created_at text not null
            );
            create table if not exists queue_jobs (
                tenant_id text not null,
                task_id text not null,
                state text not null,
                attempts integer not null,
                last_error text not null,
                available_at text not null,
                created_at text not null,
                updated_at text not null,
                primary key (tenant_id, task_id)
            );
            """
        )


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path))
    conn.row_factory = sqlite3.Row
    return conn


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteTaskRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def create(self, payload: dict[str, Any]) -> None:
        self.update(payload)

    def update(self, payload: dict[str, Any]) -> None:
        task = payload["task"]
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into tasks (tenant_id, task_id, status, payload, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(tenant_id, task_id) do update set
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    task["tenant_id"],
                    task["task_id"],
                    task["status"],
                    json.dumps(payload, ensure_ascii=False),
                    _utcnow(),
                ),
            )

    def load(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "select payload from tasks where tenant_id=? and task_id=?",
                (tenant_id, task_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Task not found: {tenant_id}/{task_id}")
        return json.loads(row["payload"])

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "select task_id, status, updated_at from tasks where tenant_id=? order by updated_at desc",
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class SQLiteResultRepository:
    def __init__(self, db_path: str | Path, max_page_limit: int = 500) -> None:
        self.db_path = Path(db_path)
        self.max_page_limit = max_page_limit

    def save_results(self, tenant_id: str, task_id: str, payload: dict[str, Any]) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("delete from results where tenant_id=? and task_id=?", (tenant_id, task_id))
            for result_type in ("assets", "services", "source_evidence"):
                for position, item in enumerate(payload.get(result_type, [])):
                    conn.execute(
                        """
                        insert into results (tenant_id, task_id, result_type, position, payload)
                        values (?, ?, ?, ?, ?)
                        """,
                        (tenant_id, task_id, result_type, position, json.dumps(item, ensure_ascii=False)),
                    )

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
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                """
                select payload from results
                where tenant_id=? and task_id=? and result_type=?
                order by position
                limit ? offset ?
                """,
                (tenant_id, task_id, result_type, effective_limit + 1, start),
            ).fetchall()
        visible = rows[:effective_limit]
        next_cursor = str(start + effective_limit) if len(rows) > effective_limit else None
        items = [json.loads(row["payload"]) for row in visible]
        return {
            "task_id": task_id,
            "assets": items if result_type == "assets" else [],
            "services": items if result_type == "services" else [],
            "source_evidence": items if result_type == "source_evidence" else [],
            "page": {"next_cursor": next_cursor, "limit": effective_limit, "type": result_type},
        }


class SQLiteScopeProfileRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def save(self, profile: TenantScopeProfile) -> None:
        payload = profile.__dict__
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into scope_profiles (tenant_id, profile_id, status, payload, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(tenant_id, profile_id) do update set
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    profile.tenant_id,
                    profile.profile_id,
                    profile.status,
                    json.dumps(payload, ensure_ascii=False),
                    _utcnow(),
                ),
            )

    def load_active(self, tenant_id: str, profile_id: str) -> TenantScopeProfile:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "select payload from scope_profiles where tenant_id=? and profile_id=?",
                (tenant_id, profile_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Scope profile not found: {tenant_id}/{profile_id}")
        profile = TenantScopeProfile(**json.loads(row["payload"]))
        if profile.status != "active":
            raise ValueError(f"Scope profile is not active: {profile_id}")
        return profile


class SQLiteNonceRepository:
    def __init__(self, db_path: str | Path, window_seconds: int = 300) -> None:
        self.db_path = Path(db_path)
        self.window_seconds = window_seconds

    def remember_once(self, nonce: str, timestamp: datetime) -> bool:
        expires_at = timestamp.astimezone(timezone.utc) + timedelta(seconds=self.window_seconds)
        with _connect(self.db_path) as conn:
            conn.execute(
                "delete from nonces where expires_at < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )
            try:
                conn.execute(
                    "insert into nonces (nonce, timestamp, expires_at) values (?, ?, ?)",
                    (nonce, timestamp.astimezone(timezone.utc).isoformat(), expires_at.isoformat()),
                )
            except sqlite3.IntegrityError:
                return False
        return True


class SQLiteAuditRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def record_event(self, tenant_id: str, task_id: str, event_type: str, details: dict[str, Any]) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into audit_events (tenant_id, task_id, event_type, details, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (tenant_id, task_id, event_type, json.dumps(details, ensure_ascii=False), _utcnow()),
            )

    def list_events(self, tenant_id: str) -> list[dict[str, Any]]:
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                """
                select tenant_id, task_id, event_type, details, created_at
                from audit_events
                where tenant_id=?
                order by id
                """,
                (tenant_id,),
            ).fetchall()
        return [
            {
                "tenant_id": row["tenant_id"],
                "task_id": row["task_id"],
                "event_type": row["event_type"],
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
