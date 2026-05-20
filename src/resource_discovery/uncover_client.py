from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import SourceQueryPlan


class UncoverExecutionError(RuntimeError):
    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


@dataclass(frozen=True)
class UncoverParseResult:
    rows: list[dict[str, Any]]
    parse_error_count: int = 0


def parse_uncover_jsonl(text: str) -> list[dict[str, Any]]:
    return parse_uncover_jsonl_with_stats(text).rows


def parse_uncover_jsonl_with_stats(text: str) -> UncoverParseResult:
    rows: list[dict[str, Any]] = []
    parse_error_count = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            parse_error_count += 1
            continue
        rows.append(_normalize_uncover_item(item))
    return UncoverParseResult(rows=rows, parse_error_count=parse_error_count)


class FixtureUncoverSourceClient:
    def __init__(self, jsonl_path: str | Path) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.rows = parse_uncover_jsonl(self.jsonl_path.read_text(encoding="utf-8"))

    def fetch(self, plan: SourceQueryPlan) -> list[dict[str, Any]]:
        matched_rows: list[dict[str, Any]] = []
        for row in self.rows:
            matched_query_types = row.get("matched_query_types", [])
            if not matched_query_types or plan.query_type in matched_query_types:
                matched_rows.append(dict(row))
        return matched_rows[: plan.result_limit]


class UncoverCommandSourceClient:
    def __init__(
        self,
        provider_config_path: str | Path,
        binary: str = "uncover",
        runner: Callable[[list[str]], str] | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.provider_config_path = str(provider_config_path)
        self.binary = binary
        self.runner = runner or _run_command
        self.timeout_seconds = timeout_seconds

    def fetch(self, plan: SourceQueryPlan) -> list[dict[str, Any]]:
        command = [
            self.binary,
            "-ff",
            plan.source_query,
            "-e",
            "fofa",
            "-j",
            "-silent",
            "-l",
            str(plan.result_limit),
            "-provider",
            self.provider_config_path,
        ]
        try:
            if self.runner is _run_command:
                output = self.runner(command, self.timeout_seconds)
            else:
                output = self.runner(command)
        except subprocess.TimeoutExpired as exc:
            raise UncoverExecutionError(f"uncover command timed out after {exc.timeout} seconds") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "").strip()
            suffix = f": {message}" if message else ""
            raise UncoverExecutionError(f"uncover command failed with exit code {exc.returncode}{suffix}") from exc
        return parse_uncover_jsonl(output)


def _normalize_uncover_item(item: dict[str, Any]) -> dict[str, Any]:
    port = item.get("port")
    normalized = {
        "ip": item.get("ip"),
        "port": int(port) if port not in (None, "") else 0,
        "host": item.get("host") or item.get("domain"),
        "source": item.get("source", "fofa"),
        "lastupdatetime": item.get("lastupdatetime") or item.get("timestamp"),
        "protocol": (item.get("protocol") or "unknown").lower(),
        "service": (item.get("service") or item.get("product") or "unknown").lower(),
    }
    for optional in ["title", "product", "url", "link", "matched_query_types"]:
        if item.get(optional) not in (None, ""):
            normalized[optional] = item[optional]
    return normalized


def _run_command(command: list[str], timeout_seconds: int = 30) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
    )
    return completed.stdout
