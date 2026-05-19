import base64
import json
from urllib.parse import parse_qs, urlparse

import pytest

from resource_discovery.fofa_client import FofaApiClient, FofaApiError


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_builds_search_url_with_qbase64_and_fields():
    client = FofaApiClient(email="user@example.org", key="secret")

    url = client.build_search_url('domain="example.org"', fields=["host", "ip", "port"], page=2, size=50)
    query = parse_qs(urlparse(url).query)

    decoded_query = base64.b64decode(query["qbase64"][0]).decode("utf-8")
    assert decoded_query == 'domain="example.org"'
    assert query["email"] == ["user@example.org"]
    assert query["key"] == ["secret"]
    assert query["fields"] == ["host,ip,port"]
    assert query["page"] == ["2"]
    assert query["size"] == ["50"]


def test_builds_key_only_search_url_for_relay():
    client = FofaApiClient(key="secret", base_url="http://fofa.icu/api/v1/search/all")

    url = client.build_search_url('domain="example.org"', fields=["host"], page=1, size=10)
    query = parse_qs(urlparse(url).query)

    assert query["key"] == ["secret"]
    assert "email" not in query
    assert url.startswith("http://fofa.icu/api/v1/search/all?")


def test_rejects_missing_key_before_any_network_use():
    with pytest.raises(ValueError, match="FOFA key"):
        FofaApiClient(email="", key="")


def test_fetch_search_maps_results_to_field_names():
    captured_urls = []

    def fake_urlopen(url, timeout):
        captured_urls.append(url)
        return FakeResponse(
            {
                "error": False,
                "results": [
                    ["vpn.example.org", "203.0.113.10", 443],
                    ["admin.example.org", "203.0.113.20", 8443],
                ],
            }
        )

    client = FofaApiClient(email="user@example.org", key="secret", opener=fake_urlopen)

    rows = client.search('domain="example.org"', fields=["host", "ip", "port"])

    assert rows == [
        {"host": "vpn.example.org", "ip": "203.0.113.10", "port": 443},
        {"host": "admin.example.org", "ip": "203.0.113.20", "port": 8443},
    ]
    assert captured_urls


def test_fetch_search_raises_provider_error():
    def fake_urlopen(url, timeout):
        return FakeResponse({"error": True, "errmsg": "invalid key"})

    client = FofaApiClient(email="user@example.org", key="bad", opener=fake_urlopen)

    with pytest.raises(FofaApiError, match="invalid key"):
        client.search('domain="example.org"', fields=["host"])
