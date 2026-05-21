from resource_discovery.queue_backends import SQLiteTaskQueue, TaskQueueStatus
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


def test_sqlite_task_queue_marks_done(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    item = TaskWorkItem("tenant_a", "task_1")

    queue.enqueue(item)
    queue.dequeue()
    queue.mark_done(item)

    assert queue.status("tenant_a", "task_1").state == "done"
