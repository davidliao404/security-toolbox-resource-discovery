import os
import sys
import time
from types import SimpleNamespace

import pytest

from resource_discovery.redis_queue import RedisTaskQueue
from resource_discovery.task_queue import TaskWorkItem


@pytest.fixture()
def queue():
    redis_url = os.getenv("RESOURCE_DISCOVERY_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("RESOURCE_DISCOVERY_TEST_REDIS_URL is not set")
    queue = RedisTaskQueue(redis_url, queue_name="resource_discovery:test")
    queue.clear()
    yield queue
    queue.clear()


def test_redis_task_queue_dequeues_fifo(queue):
    queue.enqueue(TaskWorkItem("tenant_a", "task_1"))
    queue.enqueue(TaskWorkItem("tenant_a", "task_2"))

    assert queue.dequeue() == TaskWorkItem("tenant_a", "task_1")
    assert queue.dequeue() == TaskWorkItem("tenant_a", "task_2")


def test_redis_task_queue_retries_and_dead_letters(queue):
    item = TaskWorkItem("tenant_a", "task_1")
    queue.enqueue(item)
    assert queue.dequeue() == item

    queue.mark_retry(item, "provider_timeout", delay_seconds=0)
    assert queue.dequeue() == item
    queue.mark_failed(item, "provider_timeout")

    assert queue.dead_letter_items() == [{"tenant_id": "tenant_a", "task_id": "task_1", "last_error": "provider_timeout"}]


def test_redis_task_queue_requeues_visibility_timeout(queue):
    item = TaskWorkItem("tenant_a", "task_1")
    queue = RedisTaskQueue(queue.redis_url, queue_name=queue.queue_name, visibility_timeout_seconds=0.01)
    queue.clear()
    queue.enqueue(item)

    assert queue.dequeue() == item
    time.sleep(0.02)
    assert queue.dequeue() == item


class FakeRedisClient:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.zsets = {}

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        values = self.lists.setdefault(key, [])
        return values.pop(0) if values else None

    def lrange(self, key, start, end):
        return list(self.lists.get(key, []))

    def llen(self, key):
        return len(self.lists.get(key, []))

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    def zrem(self, key, value):
        self.zsets.setdefault(key, {}).pop(value, None)

    def zrangebyscore(self, key, minimum, maximum):
        return [
            value
            for value, score in self.zsets.get(key, {}).items()
            if minimum <= score <= maximum
        ]

    def scan_iter(self, match):
        prefix = match.removesuffix("*")
        keys = set(self.hashes) | set(self.lists) | set(self.zsets)
        return [key for key in keys if key.startswith(prefix)]

    def delete(self, *keys):
        for key in keys:
            self.hashes.pop(key, None)
            self.lists.pop(key, None)
            self.zsets.pop(key, None)


def test_redis_task_queue_unit_flow_without_external_redis(monkeypatch):
    client = FakeRedisClient()
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *args, **kwargs: client)),
    )
    import resource_discovery.redis_queue as redis_queue_module

    now = {"value": 100.0}
    monkeypatch.setattr(redis_queue_module.time, "time", lambda: now["value"])
    queue = RedisTaskQueue("redis://example", queue_name="resource_discovery:unit", visibility_timeout_seconds=60)
    item = TaskWorkItem("tenant_a", "task_1")

    queue.enqueue(item)
    assert queue.depth() == 1
    assert queue.dequeue() == item
    assert queue.status("tenant_a", "task_1").state == "running"

    queue.mark_retry(item, "provider_timeout", delay_seconds=30)
    assert queue.status("tenant_a", "task_1").attempts == 1
    assert queue.dequeue() is None

    now["value"] = 131.0
    assert queue.dequeue() == item
    queue.mark_failed(item, "provider_timeout")
    assert queue.dead_letter_items() == [
        {"tenant_id": "tenant_a", "task_id": "task_1", "last_error": "provider_timeout"}
    ]

    queue.mark_done(item)
    assert queue.status("tenant_a", "task_1").state == "done"
    queue.clear()
    assert queue.depth() == 0


def test_redis_task_queue_status_raises_for_missing_job(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "redis",
        SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *args, **kwargs: FakeRedisClient())),
    )
    queue = RedisTaskQueue("redis://example", queue_name="resource_discovery:unit")

    with pytest.raises(FileNotFoundError):
        queue.status("tenant_a", "missing")
