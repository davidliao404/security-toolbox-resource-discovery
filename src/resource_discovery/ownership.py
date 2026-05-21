from __future__ import annotations


def score_ownership(row: dict, authorized_scope: dict[str, list[str]] | None = None) -> float:
    scope = authorized_scope or {}
    host = _lower(row.get("host") or row.get("domain") or "")
    domain = _lower(row.get("domain") or "")
    org = _lower(row.get("org") or "")
    root_domains = [_lower(item) for item in scope.get("root_domains", [])]
    org_names = [_lower(item) for item in scope.get("org_names", [])]

    if any(domain == root or host == root or host.endswith(f".{root}") for root in root_domains):
        return 0.95
    if org and org in org_names:
        return 0.7
    return 0.3


def _lower(value: object) -> str:
    return str(value or "").strip().lower().rstrip(".")
