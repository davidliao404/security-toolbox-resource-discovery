from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .scope_guard import TenantScopeProfile
from .task_store import FileTaskStore, _safe_id


class TaskRepository(Protocol):
    def create(self, payload: dict[str, Any]) -> None:
        """Create a task snapshot."""

    def update(self, payload: dict[str, Any]) -> None:
        """Replace a task snapshot."""

    def load(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        """Load a task snapshot."""

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        """List task summaries for a tenant."""


class ResultRepository(Protocol):
    def save_results(self, tenant_id: str, task_id: str, payload: dict[str, Any]) -> None:
        """Persist discovery results separately from task metadata."""

    def load_results(
        self,
        tenant_id: str,
        task_id: str,
        cursor: str | None,
        limit: int,
        result_type: str = "assets",
    ) -> dict[str, Any]:
        """Load a paginated result payload."""


class ScopeProfileRepository(Protocol):
    def load_active(self, tenant_id: str, profile_id: str) -> TenantScopeProfile:
        """Load an active tenant scope profile."""


class FileTaskRepository:
    def __init__(self, base_dir: str | Path) -> None:
        self.store = FileTaskStore(base_dir)

    def create(self, payload: dict[str, Any]) -> None:
        self.store.save(payload)

    def update(self, payload: dict[str, Any]) -> None:
        self.store.save(payload)

    def load(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        return self.store.load(tenant_id, task_id)

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        return self.store.list(tenant_id)


class FileResultRepository:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def save_results(self, tenant_id: str, task_id: str, payload: dict[str, Any]) -> None:
        path = self._result_path(tenant_id, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        result_payload = {
            "task_id": task_id,
            "assets": payload.get("assets", []),
            "services": payload.get("services", []),
            "source_evidence": payload.get("source_evidence", []),
        }
        path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_results(
        self,
        tenant_id: str,
        task_id: str,
        cursor: str | None,
        limit: int,
        result_type: str = "assets",
    ) -> dict[str, Any]:
        path = self._result_path(tenant_id, task_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if result_type not in {"assets", "services", "source_evidence"}:
            raise ValueError(f"Unsupported result_type: {result_type}")
        start = int(cursor or 0)
        end = start + limit
        items = payload.get(result_type, [])
        next_cursor = str(end) if end < len(items) else None
        return {
            "task_id": task_id,
            "assets": items[start:end] if result_type == "assets" else [],
            "services": items[start:end] if result_type == "services" else [],
            "source_evidence": items[start:end] if result_type == "source_evidence" else [],
            "page": {"next_cursor": next_cursor, "limit": limit, "type": result_type},
        }

    def _result_path(self, tenant_id: str, task_id: str) -> Path:
        return self.base_dir / _safe_id(tenant_id, "tenant_id") / f"{_safe_id(task_id, 'task_id')}.json"


class FileScopeProfileRepository:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def load_active(self, tenant_id: str, profile_id: str) -> TenantScopeProfile:
        path = self.base_dir / f"{_safe_id(tenant_id, 'tenant_id')}.{_safe_id(profile_id, 'profile_id')}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = TenantScopeProfile(**payload)
        if profile.status != "active":
            raise ValueError(f"Scope profile is not active: {profile_id}")
        return profile
