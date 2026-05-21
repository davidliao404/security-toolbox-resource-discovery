from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sqlite_store import _connect, _utcnow
from .task_queue import TaskWorkItem


@dataclass(frozen=True)
class TaskQueueStatus:
    state: str
    attempts: int
    last_error: str


class SQLiteTaskQueue:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def enqueue(self, item: TaskWorkItem) -> None:
        now = _utcnow()
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into queue_jobs (tenant_id, task_id, state, attempts, last_error, available_at, created_at, updated_at)
                values (?, ?, 'queued', 0, '', ?, ?, ?)
                on conflict(tenant_id, task_id) do update set
                    state='queued',
                    available_at=excluded.available_at,
                    updated_at=excluded.updated_at
                """,
                (item.tenant_id, item.task_id, now, now, now),
            )

    def dequeue(self) -> TaskWorkItem | None:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """
                select tenant_id, task_id from queue_jobs
                where state='queued'
                order by created_at
                limit 1
                """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "update queue_jobs set state='running', updated_at=? where tenant_id=? and task_id=?",
                (_utcnow(), row["tenant_id"], row["task_id"]),
            )
        return TaskWorkItem(row["tenant_id"], row["task_id"])

    def mark_retry(self, item: TaskWorkItem, reason: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                update queue_jobs
                set state='queued', attempts=attempts + 1, last_error=?, updated_at=?
                where tenant_id=? and task_id=?
                """,
                (reason, _utcnow(), item.tenant_id, item.task_id),
            )

    def mark_done(self, item: TaskWorkItem) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "update queue_jobs set state='done', updated_at=? where tenant_id=? and task_id=?",
                (_utcnow(), item.tenant_id, item.task_id),
            )

    def mark_failed(self, item: TaskWorkItem, reason: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                update queue_jobs
                set state='failed', last_error=?, updated_at=?
                where tenant_id=? and task_id=?
                """,
                (reason, _utcnow(), item.tenant_id, item.task_id),
            )

    def status(self, tenant_id: str, task_id: str) -> TaskQueueStatus:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "select state, attempts, last_error from queue_jobs where tenant_id=? and task_id=?",
                (tenant_id, task_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Queue job not found: {tenant_id}/{task_id}")
        return TaskQueueStatus(state=row["state"], attempts=row["attempts"], last_error=row["last_error"])


class RedisTaskQueue:
    def __init__(self, redis_url: str, queue_name: str = "resource_discovery:tasks") -> None:
        import redis

        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name

    def enqueue(self, item: TaskWorkItem) -> None:
        self.client.rpush(self.queue_name, f"{item.tenant_id}:{item.task_id}")

    def dequeue(self) -> TaskWorkItem | None:
        value = self.client.lpop(self.queue_name)
        if value is None:
            return None
        tenant_id, task_id = value.split(":", 1)
        return TaskWorkItem(tenant_id, task_id)

    def mark_retry(self, item: TaskWorkItem, reason: str) -> None:
        self.enqueue(item)

    def mark_done(self, item: TaskWorkItem) -> None:
        return None

    def mark_failed(self, item: TaskWorkItem, reason: str) -> None:
        return None
