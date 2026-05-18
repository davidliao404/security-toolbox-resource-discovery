from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class SnapshotStoreError(RuntimeError):
    """Raised when a task snapshot cannot be stored or read safely."""


class FileTaskStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def save(self, payload: dict[str, Any]) -> Path:
        task = payload.get("task") or {}
        tenant_id = _safe_id(task.get("tenant_id"), "tenant_id")
        task_id = _safe_id(task.get("task_id"), "task_id")
        path = self._snapshot_path(tenant_id, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def load(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        path = self._snapshot_path(
            _safe_id(tenant_id, "tenant_id"),
            _safe_id(task_id, "task_id"),
        )
        if not path.exists():
            raise SnapshotStoreError(f"Snapshot not found: {tenant_id}/{task_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        safe_tenant_id = _safe_id(tenant_id, "tenant_id")
        tenant_dir = self.base_dir / safe_tenant_id
        if not tenant_dir.exists():
            return []
        summaries: list[dict[str, Any]] = []
        for path in sorted(tenant_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            task = payload.get("task") or {}
            summary = (payload.get("snapshot") or {}).get("summary") or {}
            summaries.append(
                {
                    "tenant_id": task.get("tenant_id"),
                    "task_id": task.get("task_id"),
                    "status": task.get("status"),
                    "asset_count": summary.get("asset_count", 0),
                    "service_count": summary.get("service_count", 0),
                    "risk_hint_count": summary.get("risk_hint_count", 0),
                }
            )
        return summaries

    def _snapshot_path(self, tenant_id: str, task_id: str) -> Path:
        return self.base_dir / tenant_id / f"{task_id}.json"


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not SAFE_ID_RE.match(value):
        raise SnapshotStoreError(f"Unsafe {label}: {value!r}")
    return value
