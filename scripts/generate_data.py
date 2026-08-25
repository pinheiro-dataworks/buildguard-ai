#!/usr/bin/env python
"""Generate the synthetic BuildGuard AI portfolio (`make data`).

Writes two outputs from the same deterministic generation run:

- ``configs/base.yaml: paths.data_processed`` -- the full dataset, at the
  scale configured under ``synthetic_data`` (gitignored, regenerated on
  demand; never redistributed in the public repo as raw files).
- ``configs/base.yaml: paths.data_sample`` -- a small, fixed-size subset of
  the same run, committed to the repo so notebooks and the app can load a
  quick sample without a generation step.
"""

from __future__ import annotations

import logging
from pathlib import Path

from buildguard.config import PROJECT_ROOT, load_base_config
from buildguard.data.synthetic import PortfolioDataset, generate_portfolio

logger = logging.getLogger(__name__)

_SAMPLE_N_PROJECTS = 20


def _write_dataset(dataset: PortfolioDataset, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset.projects.to_csv(out_dir / "projects.csv", index=False)
    dataset.snapshots.to_csv(out_dir / "project_snapshots.csv", index=False)
    dataset.work_packages.to_csv(out_dir / "work_packages.csv", index=False)
    dataset.change_orders.to_csv(out_dir / "change_orders.csv", index=False)
    dataset.suppliers.to_csv(out_dir / "suppliers.csv", index=False)
    dataset.economic_index.to_csv(out_dir / "economic_index.csv", index=False)


def _subset_for_sample(dataset: PortfolioDataset, n_projects: int) -> PortfolioDataset:
    sample_ids = set(dataset.projects["project_id"].head(n_projects))

    return PortfolioDataset(
        projects=dataset.projects[dataset.projects["project_id"].isin(sample_ids)].reset_index(
            drop=True
        ),
        snapshots=dataset.snapshots[dataset.snapshots["project_id"].isin(sample_ids)].reset_index(
            drop=True
        ),
        work_packages=dataset.work_packages[
            dataset.work_packages["project_id"].isin(sample_ids)
        ].reset_index(drop=True),
        change_orders=dataset.change_orders[
            dataset.change_orders["project_id"].isin(sample_ids)
        ].reset_index(drop=True),
        suppliers=dataset.suppliers[dataset.suppliers["project_id"].isin(sample_ids)].reset_index(
            drop=True
        ),
        economic_index=dataset.economic_index,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_base_config()

    logger.info(
        "Generating synthetic portfolio (seed=%s, n_projects=%s)",
        config.seed,
        config.synthetic_data.n_projects,
    )
    dataset = generate_portfolio(config)

    processed_dir = PROJECT_ROOT / config.paths.data_processed
    _write_dataset(dataset, processed_dir)
    logger.info(
        "Full dataset written to %s (%d projects, %d snapshots)",
        processed_dir,
        len(dataset.projects),
        len(dataset.snapshots),
    )

    sample = _subset_for_sample(dataset, n_projects=_SAMPLE_N_PROJECTS)
    sample_dir = PROJECT_ROOT / config.paths.data_sample
    _write_dataset(sample, sample_dir)
    logger.info(
        "Sample dataset written to %s (%d projects, %d snapshots)",
        sample_dir,
        len(sample.projects),
        len(sample.snapshots),
    )


if __name__ == "__main__":
    main()
