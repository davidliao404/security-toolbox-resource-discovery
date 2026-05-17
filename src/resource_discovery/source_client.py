from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import SourceQueryPlan


class SourceClient(Protocol):
    def fetch(self, plan: SourceQueryPlan) -> list[dict]:
        """Return provider rows for a query plan."""


class FixtureSourceClient:
    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.rows = payload.get("results", [])

    def fetch(self, plan: SourceQueryPlan) -> list[dict]:
        matched_rows: list[dict] = []
        for row in self.rows:
            matched_query_types = row.get("matched_query_types", [])
            if not matched_query_types or plan.query_type in matched_query_types:
                matched_rows.append(dict(row))
        return matched_rows[: plan.result_limit]
