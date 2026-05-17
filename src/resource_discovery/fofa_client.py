from __future__ import annotations

import base64
import json
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen


class FofaApiError(RuntimeError):
    """Raised when FOFA returns an API-level error."""


class FofaApiClient:
    def __init__(
        self,
        email: str,
        key: str,
        base_url: str = "https://fofa.info/api/v1/search/all",
        opener: Callable | None = None,
        timeout: int = 30,
    ) -> None:
        self.email = email
        self.key = key
        self.base_url = base_url
        self.opener = opener or urlopen
        self.timeout = timeout

    def build_search_url(
        self,
        source_query: str,
        fields: list[str],
        page: int = 1,
        size: int = 100,
    ) -> str:
        qbase64 = base64.b64encode(source_query.encode("utf-8")).decode("ascii")
        params = {
            "email": self.email,
            "key": self.key,
            "qbase64": qbase64,
            "fields": ",".join(fields),
            "page": str(page),
            "size": str(size),
        }
        return f"{self.base_url}?{urlencode(params)}"

    def search(
        self,
        source_query: str,
        fields: list[str],
        page: int = 1,
        size: int = 100,
    ) -> list[dict]:
        url = self.build_search_url(source_query, fields=fields, page=page, size=size)
        with self.opener(url, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("error"):
            raise FofaApiError(payload.get("errmsg") or "FOFA API returned an error")
        return [dict(zip(fields, row)) for row in payload.get("results", [])]
