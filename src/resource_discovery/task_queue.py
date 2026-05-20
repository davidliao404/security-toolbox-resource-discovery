from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskWorkItem:
    tenant_id: str
    task_id: str


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._items: deque[TaskWorkItem] = deque()

    def enqueue(self, item: TaskWorkItem) -> None:
        self._items.append(item)

    def dequeue(self) -> TaskWorkItem | None:
        if not self._items:
            return None
        return self._items.popleft()

    def __len__(self) -> int:
        return len(self._items)
