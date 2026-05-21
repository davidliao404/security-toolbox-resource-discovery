from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .fofa_client import FofaApiClient
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


class FofaSourceClient:
    DEFAULT_FIELDS = [
        "host",
        "ip",
        "port",
        "protocol",
        "domain",
        "title",
        "product",
        "version",
        "server",
        "link",
        "asn",
        "org",
        "country",
        "country_name",
        "header_hash",
        "banner_hash",
        "cname",
        "lastupdatetime",
    ]

    def __init__(self, api_client: FofaApiClient, fields: list[str] | None = None) -> None:
        self.api_client = api_client
        self.fields = fields or self.DEFAULT_FIELDS

    def fetch(self, plan: SourceQueryPlan) -> list[dict]:
        rows: list[dict] = []
        for page in range(1, plan.page_limit + 1):
            page_rows = self.api_client.search(
                plan.source_query,
                fields=self.fields,
                page=page,
                size=min(plan.result_limit, 100),
            )
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(rows) >= plan.result_limit:
                break
        return rows[: plan.result_limit]
