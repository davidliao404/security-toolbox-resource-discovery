from __future__ import annotations

from dataclasses import dataclass

from .models import DiscoverySeed, SourceQueryPlan
from .query_planner import plan_fofa_queries


@dataclass(frozen=True)
class DiscoveryWorkflowConfig:
    strategy: str = "baseline"
    max_query_plans: int = 30
    page_limit: int = 10
    result_limit: int = 1000


def build_query_plans(
    task_id: str,
    seeds: list[DiscoverySeed],
    config: DiscoveryWorkflowConfig,
) -> list[SourceQueryPlan]:
    plans = plan_fofa_queries(
        task_id,
        seeds,
        page_limit=config.page_limit,
        result_limit=config.result_limit,
        strategy=config.strategy,
    )
    if len(plans) > config.max_query_plans:
        raise ValueError(
            f"Generated {len(plans)} query plans, "
            f"exceeding query plan budget {config.max_query_plans}"
        )
    return plans
