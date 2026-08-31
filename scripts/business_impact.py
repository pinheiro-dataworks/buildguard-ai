#!/usr/bin/env python
"""Business impact scenario computation (Section 21).

Usage::

    uv run python scripts/business_impact.py
    make business-impact

Requires `make evaluate` to have run first (reads its
`reports/experiments/test_set_metrics.json` for the real held-out
cost-overrun recall). Combines that, the real portfolio composition
(which projects are still active/unresolved), and the explicit
assumption in `configs/business.yaml` into one number -- written to
`reports/experiments/business_impact.json`, always labeled
"Scenario-based estimated impact" wherever it is shown (never a claimed
realized ROI, per Section 21).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from _common import load_training_dataset
from buildguard.config import PROJECT_ROOT, load_base_config, load_business_config
from buildguard.evaluation.business_impact import compute_business_impact
from buildguard.models.tracking import configure_tracking, get_git_sha, log_model_run

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = load_base_config()
    business_cfg = load_business_config()
    dataset = load_training_dataset(cfg)

    reports_dir = PROJECT_ROOT / cfg.paths.reports_dir
    experiments_dir = reports_dir / "experiments"
    test_metrics = json.loads(
        (experiments_dir / "test_set_metrics.json").read_text(encoding="utf-8")
    )
    recall = test_metrics["tasks"]["cost_overrun"]["test_metrics"]["recall"]

    result = compute_business_impact(
        projects=dataset.raw.projects,
        outcomes=dataset.outcomes,
        model_recall=recall,
        avoidable_impact_assumption=business_cfg.business_impact.avoidable_impact_assumption,
    )

    data_version = get_git_sha()
    report = {"git_sha": data_version, **asdict(result)}
    out_path = experiments_dir / "business_impact.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("Active (unresolved) projects: %d", result.active_projects)
    logger.info("Avg financial exposure: $%.2fM", result.avg_financial_exposure / 1e6)
    logger.info("Overrun prevalence (resolved population): %.1f%%", result.overrun_prevalence * 100)
    logger.info("Cost-overrun model recall (held-out test): %.1f%%", result.model_recall * 100)
    logger.info("Avoidable-impact assumption: %.0f%%", result.avoidable_impact_assumption * 100)
    logger.info("%s: $%.2fM", result.label, result.estimated_decision_support_value / 1e6)
    logger.info("Written to %s", out_path)

    configure_tracking(cfg.paths.mlflow_tracking_uri, cfg.training.mlflow_experiment_name)
    log_model_run(
        run_name="business-impact-run",
        params={"data_version": data_version},
        metrics={
            "estimated_decision_support_value": result.estimated_decision_support_value,
            "active_projects": float(result.active_projects),
        },
        tags={"stage": "business_impact"},
    )


if __name__ == "__main__":
    main()
