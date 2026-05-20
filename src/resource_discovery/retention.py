from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RetentionPolicy:
    task_metadata_days: int
    result_snapshot_days: int
    audit_log_days: int

    @classmethod
    def gateway_default(cls) -> "RetentionPolicy":
        return cls(task_metadata_days=180, result_snapshot_days=90, audit_log_days=365)


def is_expired(
    path: str | Path,
    *,
    now: datetime | None = None,
    retention_days: int,
    modified_at: datetime | None = None,
) -> bool:
    current_time = now or datetime.now(timezone.utc)
    file_path = Path(path)
    file_modified_at = modified_at or datetime.fromtimestamp(file_path.stat().st_mtime, timezone.utc)
    age_seconds = (current_time - file_modified_at).total_seconds()
    return age_seconds > retention_days * 24 * 60 * 60


def cleanup_expired_files(
    base_dir: str | Path,
    *,
    retention_days: int,
    now: datetime | None = None,
    patterns: tuple[str, ...] = ("*.json", "*.jsonl"),
    modified_at_by_path: dict[Path, datetime] | None = None,
) -> list[Path]:
    root = Path(base_dir)
    if not root.exists():
        return []
    deleted: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            modified_at = (modified_at_by_path or {}).get(path)
            if not is_expired(path, now=now, retention_days=retention_days, modified_at=modified_at):
                continue
            path.unlink()
            deleted.append(path)
    return deleted
