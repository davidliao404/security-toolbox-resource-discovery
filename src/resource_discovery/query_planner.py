from __future__ import annotations

from .models import DiscoverySeed, SourceQueryPlan


SUPPORTED_SEED_TYPES = {"root_domain", "organization_name", "ip_cidr"}
SUPPORTED_STRATEGIES = {"baseline", "easm"}


def _escape_fofa(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _baseline_templates(seed: DiscoverySeed) -> list[tuple[str, str, str]]:
    value = _escape_fofa(seed.value.strip())
    if not value:
        raise ValueError(f"Seed {seed.seed_id} value is empty")
    if seed.type == "root_domain":
        return [(f'domain="{value}"', "domain", "root_domain_match")]
    if seed.type == "organization_name":
        return [
            (
                f'cert.subject.org="{value}" || title="{value}"',
                "organization",
                "organization_match",
            )
        ]
    if seed.type == "ip_cidr":
        return [(f'ip="{value}"', "ip_range", "ip_range_match")]
    raise ValueError(f"Unsupported seed type: {seed.type}")


def _easm_templates(seed: DiscoverySeed) -> list[tuple[str, str, str]]:
    value = _escape_fofa(seed.value.strip())
    if not value:
        raise ValueError(f"Seed {seed.seed_id} value is empty")
    if seed.type == "root_domain":
        return [
            (f'domain="{value}"', "domain", "root_domain_match"),
            (f'host=".{value}"', "domain", "host_suffix_match"),
            (f'cert.domain="{value}"', "certificate", "certificate_domain_match"),
        ]
    if seed.type == "organization_name":
        return [
            (
                f'cert.subject.org="{value}"',
                "organization",
                "organization_certificate_match",
            ),
            (f'title="{value}"', "organization", "organization_title_match"),
            (f'org="{value}"', "organization", "asn_organization_match"),
        ]
    if seed.type == "ip_cidr":
        return [(f'ip="{value}"', "ip_range", "ip_range_match")]
    raise ValueError(f"Unsupported seed type: {seed.type}")


def plan_fofa_queries(
    task_id: str,
    seeds: list[DiscoverySeed],
    page_limit: int = 10,
    result_limit: int = 1000,
    strategy: str = "baseline",
) -> list[SourceQueryPlan]:
    if strategy not in SUPPORTED_STRATEGIES:
        raise ValueError(f"Unsupported discovery strategy: {strategy}")
    templates = _baseline_templates if strategy == "baseline" else _easm_templates
    plans: list[SourceQueryPlan] = []
    for seed in seeds:
        for source_query, query_type, query_intent in templates(seed):
            plans.append(
                SourceQueryPlan(
                    plan_id=f"plan_{len(plans) + 1:03d}",
                    task_id=task_id,
                    source="fofa",
                    seed_id=seed.seed_id,
                    source_query=source_query,
                    query_type=query_type,
                    page_limit=page_limit,
                    result_limit=result_limit,
                    stage="seed",
                    query_intent=query_intent,
                    derived_from=[seed.seed_id],
                )
            )
    return plans
