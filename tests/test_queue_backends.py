from resource_discovery.queue_backends import SQLiteTaskQueue, TaskQueueStatus
from resource_discovery.queue_backends import RedisTaskQueue as LegacyRedisTaskQueue
from resource_discovery.sqlite_store import initialize_sqlite
from resource_discovery.task_queue import TaskWorkItem


def test_sqlite_task_queue_dequeues_fifo(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)

    queue.enqueue(TaskWorkItem("tenant_a", "task_1"))
    queue.enqueue(TaskWorkItem("tenant_a", "task_2"))

    assert queue.dequeue() == TaskWorkItem("tenant_a", "task_1")
    assert queue.dequeue() == TaskWorkItem("tenant_a", "task_2")
    assert queue.dequeue() is None


def test_sqlite_task_queue_records_attempts(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    queue.enqueue(TaskWorkItem("tenant_a", "task_1"))

    item = queue.dequeue()
    assert item == TaskWorkItem("tenant_a", "task_1")
    queue.mark_retry(item, "provider_timeout")
    status = queue.status("tenant_a", "task_1")

    assert status == TaskQueueStatus(state="queued", attempts=1, last_error="provider_timeout")


def test_sqlite_task_queue_delays_retry_until_available(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    queue.enqueue(TaskWorkItem("tenant_a", "task_1"))

    item = queue.dequeue()
    assert item == TaskWorkItem("tenant_a", "task_1")
    queue.mark_retry(item, "provider_timeout", delay_seconds=60)

    assert queue.status("tenant_a", "task_1") == TaskQueueStatus(
        state="queued",
        attempts=1,
        last_error="provider_timeout",
    )
    assert queue.dequeue() is None


def test_sqlite_task_queue_marks_done(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    item = TaskWorkItem("tenant_a", "task_1")

    queue.enqueue(item)
    queue.dequeue()
    queue.mark_done(item)

    assert queue.status("tenant_a", "task_1").state == "done"


class LegacyFakeRedisClient:
    def __init__(self):
        self.items = []

    def rpush(self, key, value):
        self.items.append(value)

    def lpop(self, key):
        return self.items.pop(0) if self.items else None


def test_legacy_redis_task_queue_dequeues_and_retries(monkeypatch):
    client = LegacyFakeRedisClient()
    monkeypatch.setattr(
        "redis.Redis.from_url",
        lambda *args, **kwargs: client,
    )
    queue = LegacyRedisTaskQueue("redis://example")
    item = TaskWorkItem("tenant_a", "task_1")

    queue.enqueue(item)
    assert queue.dequeue() == item
    assert queue.dequeue() is None
    queue.mark_retry(item, "provider_timeout")
    assert queue.dequeue() == item
    assert queue.mark_done(item) is None
    assert queue.mark_failed(item, "provider_timeout") is None
