from __future__ import annotations

import argparse
import json
from pathlib import Path

from .deduplicator import deduplicate_assets, deduplicate_services
from .models import DiscoverySeed
from .normalizer import normalize_fofa_results
from .query_planner import plan_fofa_queries
from .report_builder import build_exposure_report
from .risk_hints import generate_risk_hints
from .source_client import FixtureSourceClient


def run_fixture_demo(seeds_path: str | Path, fixture_path: str | Path) -> dict:
    payload = json.loads(Path(seeds_path).read_text(encoding="utf-8"))
    task_id = payload.get("task_id", "dt_poc_001")
    tenant_id = payload.get("tenant_id", "tenant_poc")
    seeds = [DiscoverySeed(**seed) for seed in payload["seeds"]]
    plans = plan_fofa_queries(task_id, seeds)
    client = FixtureSourceClient(fixture_path)

    assets = []
    services = []
    evidences = []
    for plan in plans:
        batch = normalize_fofa_results(task_id, plan, client.fetch(plan))
        assets.extend(batch.assets)
        services.extend(batch.services)
        evidences.extend(batch.evidences)

    deduped_assets = deduplicate_assets(assets)
    deduped_services = deduplicate_services(services)
    risk_hints = generate_risk_hints(task_id, deduped_services)
    report = build_exposure_report(task_id, tenant_id, deduped_assets, deduped_services, risk_hints)

    return {
        "report": report.to_dict(),
        "assets": [asset.to_dict() for asset in deduped_assets],
        "services": [service.to_dict() for service in deduped_services],
        "risk_hints": [risk.to_dict() for risk in risk_hints],
        "source_evidence": [evidence.to_dict() for evidence in evidences],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline FOFA resource discovery PoC.")
    parser.add_argument("--seeds", required=True, help="Path to seeds JSON file.")
    parser.add_argument("--fixture", required=True, help="Path to FOFA-like fixture JSON file.")
    args = parser.parse_args()
    print(json.dumps(run_fixture_demo(args.seeds, args.fixture), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
