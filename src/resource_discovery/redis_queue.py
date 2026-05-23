from __future__ import annotations

import json
import time
from dataclasses import asdict

from .queue_backends import TaskQueueStatus
from .task_queue import TaskWorkItem


class RedisTaskQueue:
    def __init__(
        self,
        redis_url: str,
        queue_name: str = "resource_discovery:tasks",
        visibility_timeout_seconds: float = 60.0,
    ) -> None:
        import redis

        self.redis_url = redis_url
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name
        self.visibility_timeout_seconds = visibility_timeout_seconds
        self.ready_key = f"{queue_name}:ready"
        self.running_key = f"{queue_name}:running"
        self.job_key_prefix = f"{queue_name}:job"
        self.dlq_key = f"{queue_name}:dlq"

    def enqueue(self, item: TaskWorkItem) -> None:
        job_key = self._job_key(item)
        now = time.time()
        self.client.hset(
            job_key,
            mapping={
                "tenant_id": item.tenant_id,
                "task_id": item.task_id,
                "state": "queued",
                "attempts": self.client.hget(job_key, "attempts") or "0",
                "last_error": self.client.hget(job_key, "last_error") or "",
                "created_at": self.client.hget(job_key, "created_at") or str(now),
                "updated_at": str(now),
            },
        )
        self.client.rpush(self.ready_key, self._encode(item))

    def dequeue(self) -> TaskWorkItem | None:
        self._requeue_expired()
        encoded = self.client.lpop(self.ready_key)
        if encoded is None:
            return None
        item = self._decode(encoded)
        visible_at = time.time() + self.visibility_timeout_seconds
        self.client.zadd(self.running_key, {encoded: visible_at})
        self.client.hset(self._job_key(item), mapping={"state": "running", "updated_at": str(time.time())})
        return item

    def mark_retry(self, item: TaskWorkItem, reason: str, delay_seconds: float = 0.0) -> None:
        encoded = self._encode(item)
        job_key = self._job_key(item)
        attempts = int(self.client.hget(job_key, "attempts") or 0) + 1
        self.client.zrem(self.running_key, encoded)
        self.client.hset(
            job_key,
            mapping={"state": "queued", "attempts": str(attempts), "last_error": reason, "updated_at": str(time.time())},
        )
        if delay_seconds <= 0:
            self.client.rpush(self.ready_key, encoded)
        else:
            self.client.zadd(self.running_key, {encoded: time.time() + delay_seconds})

    def mark_done(self, item: TaskWorkItem) -> None:
        encoded = self._encode(item)
        self.client.zrem(self.running_key, encoded)
        self.client.hset(self._job_key(item), mapping={"state": "done", "updated_at": str(time.time())})

    def mark_failed(self, item: TaskWorkItem, reason: str) -> None:
        encoded = self._encode(item)
        job_key = self._job_key(item)
        self.client.zrem(self.running_key, encoded)
        self.client.hset(job_key, mapping={"state": "failed", "last_error": reason, "updated_at": str(time.time())})
        self.client.rpush(self.dlq_key, json.dumps({"tenant_id": item.tenant_id, "task_id": item.task_id, "last_error": reason}))

    def status(self, tenant_id: str, task_id: str) -> TaskQueueStatus:
        item = TaskWorkItem(tenant_id, task_id)
        payload = self.client.hgetall(self._job_key(item))
        if not payload:
            raise FileNotFoundError(f"Queue job not found: {tenant_id}/{task_id}")
        return TaskQueueStatus(
            state=payload.get("state", ""),
            attempts=int(payload.get("attempts") or 0),
            last_error=payload.get("last_error", ""),
        )

    def dead_letter_items(self) -> list[dict[str, str]]:
        return [json.loads(value) for value in self.client.lrange(self.dlq_key, 0, -1)]

    def depth(self) -> int:
        return int(self.client.llen(self.ready_key))

    def clear(self) -> None:
        pattern = f"{self.queue_name}:*"
        keys = list(self.client.scan_iter(match=pattern))
        if keys:
            self.client.delete(*keys)

    def _requeue_expired(self) -> None:
        now = time.time()
        expired = self.client.zrangebyscore(self.running_key, 0, now)
        for encoded in expired:
            self.client.zrem(self.running_key, encoded)
            self.client.rpush(self.ready_key, encoded)
            item = self._decode(encoded)
            self.client.hset(self._job_key(item), mapping={"state": "queued", "updated_at": str(now)})

    def _job_key(self, item: TaskWorkItem) -> str:
        return f"{self.job_key_prefix}:{item.tenant_id}:{item.task_id}"

    @staticmethod
    def _encode(item: TaskWorkItem) -> str:
        return json.dumps(asdict(item), separators=(",", ":"))

    @staticmethod
    def _decode(value: str) -> TaskWorkItem:
        payload = json.loads(value)
        return TaskWorkItem(payload["tenant_id"], payload["task_id"])
