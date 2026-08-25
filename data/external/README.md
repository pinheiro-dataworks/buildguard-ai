# External Reference Data (local-only, not redistributed)

This folder holds third-party datasets used **only** as a local reference for
calibrating the realism of BuildGuard AI's synthetic demo portfolio (see
[`docs/DATA_PRIVACY.md`](../../docs/DATA_PRIVACY.md) and
[`src/buildguard/data/synthetic.py`](../../src/buildguard/data/synthetic.py)).

Everything under `data/external/` (except this file) is excluded from
version control via `.gitignore`. It is never shipped in the public repo,
never loaded by the deployed app, and never used as a training or evaluation
dataset for the shipped models.

## `nista_uk_gmpp/`

- **Source:** UK National Infrastructure and Service Transformation Authority
  (NISTA) / Infrastructure and Projects Authority (IPA) — *Annual Report on
  Major Projects*, government major projects portfolio (GMPP) data
  (GOV.UK, published by the UK Cabinet Office).
- **Contents:** `NISTA_Major_Projects_Annual_Report_2025-2026_Data.csv`,
  `nista_annual_report_data_2425.csv` — portfolio-level annual figures per
  major project (Delivery Confidence Assessment rating, whole-life cost,
  financial-year baseline/forecast/variance, schedule narrative, benefits).
- **Purpose here:** informal, non-authoritative reference for realism checks
  only — e.g. plausible ranges/shapes for delivery-confidence rating
  distributions, cost variance magnitudes, and schedule narrative patterns
  when designing the synthetic generator. It is **not** row-level project
  time-series data (no `PV`/`EV`/`AC` snapshots), so it cannot and does not
  drive the BuildGuard data model directly (see Section 8.4 of
  `BUILDGUARD_AI_PROJECT_SCOPE.md`).
- **License status:** UK Government data of this kind is typically published
  under the Open Government Licence v3.0. This has **not** been independently
  re-verified for these specific files, so they are kept local-only and
  excluded from Git history rather than redistributed. If OGL terms are
  confirmed in the future and redistribution becomes desirable, revisit this
  decision explicitly (record it as an ADR) before committing the files.
- **Never used for:** synthetic data generation logic at runtime, model
  training, model evaluation, or any code path reachable by the deployed
  application. Any inspiration drawn from it flows through human judgment
  into the synthetic generator's *parameters*, not through data loading.
