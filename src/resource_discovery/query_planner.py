from __future__ import annotations

from .models import DiscoverySeed, SourceQueryPlan


SUPPORTED_SEED_TYPES = {"root_domain", "organization_name", "ip_cidr"}


def _escape_fofa(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _query_for_seed(seed: DiscoverySeed) -> tuple[str, str]:
    value = _escape_fofa(seed.value.strip())
    if not value:
        raise ValueError(f"Seed {seed.seed_id} value is empty")
    if seed.type == "root_domain":
        return f'domain="{value}"', "domain"
    if seed.type == "organization_name":
        return f'cert.subject.org="{value}" || title="{value}"', "organization"
    if seed.type == "ip_cidr":
        return f'ip="{value}"', "ip_range"
    raise ValueError(f"Unsupported seed type: {seed.type}")


def plan_fofa_queries(
    task_id: str,
    seeds: list[DiscoverySeed],
    page_limit: int = 10,
    result_limit: int = 1000,
) -> list[SourceQueryPlan]:
    plans: list[SourceQueryPlan] = []
    for index, seed in enumerate(seeds, start=1):
        source_query, query_type = _query_for_seed(seed)
        plans.append(
            SourceQueryPlan(
                plan_id=f"plan_{index:03d}",
                task_id=task_id,
                source="fofa",
                seed_id=seed.seed_id,
                source_query=source_query,
                query_type=query_type,
                page_limit=page_limit,
                result_limit=result_limit,
            )
        )
    return plans
