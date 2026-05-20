from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    tenant_id: str
    task_id: str
    details: dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JsonlAuditLogger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, event: AuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n")


class AuditLogger(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Record one audit event."""
