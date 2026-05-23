import os
import time

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
