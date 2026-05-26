import pytest

from resource_discovery.task_operations import TaskOperationError, cancel_task, list_dead_letters


class MemoryTaskRepository:
    def __init__(self, status="queued"):
        self.payload = {"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": status}}
        self.updated = []

    def load(self, tenant_id, task_id):
        return self.payload

    def update(self, payload):
        self.payload = payload
        self.updated.append(payload)


class DeadLetterQueue:
    def dead_letter_items(self):
        return [
            {
                "tenant_id": "tenant_a",
                "task_id": "task_1",
                "attempts": "3",
                "last_error": "provider_timeout",
                "updated_at": "2026-05-25T10:00:00+08:00",
            }
        ]


@pytest.mark.parametrize("status", ["queued", "retrying", "running"])
def test_cancel_task_marks_active_task_cancelled(status):
    repo = MemoryTaskRepository(status)

    result = cancel_task(repo, "tenant_a", "task_1", actor="ops-user")

    assert result["status"] == "cancelled"
    assert repo.payload["task"]["status"] == "cancelled"
    assert repo.payload["task"]["cancelled_by"] == "ops-user"
    assert "cancelled_at" in repo.payload["task"]


@pytest.mark.parametrize("status", ["success", "partial_success", "failed", "cancelled"])
def test_cancel_task_rejects_terminal_task(status):
    repo = MemoryTaskRepository(status)

    with pytest.raises(TaskOperationError) as exc:
        cancel_task(repo, "tenant_a", "task_1", actor="ops-user")

    assert exc.value.code == "task_not_cancellable"
    assert repo.updated == []


def test_list_dead_letters_normalizes_queue_items():
    assert list_dead_letters(DeadLetterQueue()) == [
        {
            "tenant_id": "tenant_a",
            "task_id": "task_1",
            "attempts": 3,
            "last_error": "provider_timeout",
            "updated_at": "2026-05-25T10:00:00+08:00",
        }
    ]
