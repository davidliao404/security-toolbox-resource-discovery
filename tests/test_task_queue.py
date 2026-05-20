from resource_discovery.task_queue import InMemoryTaskQueue, TaskWorkItem


def test_in_memory_task_queue_dequeues_fifo():
    queue = InMemoryTaskQueue()
    queue.enqueue(TaskWorkItem(tenant_id="tenant_poc", task_id="task_001"))
    queue.enqueue(TaskWorkItem(tenant_id="tenant_poc", task_id="task_002"))

    assert queue.dequeue() == TaskWorkItem(tenant_id="tenant_poc", task_id="task_001")
    assert queue.dequeue() == TaskWorkItem(tenant_id="tenant_poc", task_id="task_002")
    assert queue.dequeue() is None


def test_in_memory_task_queue_reports_length():
    queue = InMemoryTaskQueue()

    assert len(queue) == 0
    queue.enqueue(TaskWorkItem(tenant_id="tenant_poc", task_id="task_001"))

    assert len(queue) == 1
