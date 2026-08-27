# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Repository foundation: full project layout, `pyproject.toml` (uv-managed,
  Ruff + Mypy strict + Pytest configured), `Makefile`, governance files
  (`LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`),
  GitHub issue/PR templates, `.pre-commit-config.yaml`.
- Project scope and engineering charter
  (`BUILDGUARD_AI_PROJECT_SCOPE.md`).
- Data privacy policy (`docs/DATA_PRIVACY.md`) and the first two ADRs
  (`docs/adr/0001-project-architecture.md`,
  `docs/adr/0002-data-privacy-strategy.md`).
- UI design spec capturing the sidebar/branding direction for Phase 8
  (`docs/design/UI_DESIGN_SPEC.md`), without implementing any UI yet.
- Typed configuration loading (`src/buildguard/config.py`) over
  `configs/base.yaml` and `configs/business.yaml`.
- Core data contracts (`src/buildguard/data/contracts.py`,
  `src/buildguard/data/enums.py`): Pandera schemas for Projects, Project
  Snapshots, Work Packages, Change Orders, Suppliers, and the Economic
  Index, enforcing the Section 8.5 minimum checks plus a cross-table
  chronological-consistency check.
- Earned Value Management formula engine (`src/buildguard/features/evm.py`):
  CV, SV, CPI, SPI, two independent EAC baselines (CPI-based and
  schedule-adjusted composite), ETC, VAC — each documented with its
  business interpretation and safe division-by-zero handling (Section 9).
- Deterministic synthetic portfolio generator
  (`src/buildguard/data/synthetic.py`): all six core tables (Projects,
  Project Snapshots, Work Packages, Change Orders, Suppliers, Economic
  Index) generated from one seeded RNG, correlated through a per-project
  latent risk profile so the required realism relationships (Section 8.2)
  hold by construction. Design rationale, a caught progress-accumulation
  bug, and the validated nominal-vs-inflation-adjusted overrun-rate finding
  are recorded in `docs/adr/0004-synthetic-data-design.md`.
- `scripts/generate_data.py` (`make data`): writes the full dataset to
  `data/processed/` (gitignored) and a small 20-project sample to
  `data/sample/` (committed) from the same run.
- `docs/DATA_DICTIONARY.md`: column-level reference for all six tables.
- `EconomicIndexProvider` interface (`src/buildguard/data/economic_index.py`,
  Section 8.3): `DemoIndexProvider` (deterministic illustrative index, used
  by the generator and, by default, everywhere else) and an intentionally
  unimplemented `ExternalLicensedProvider` placeholder. The synthetic
  generator was refactored to consume this instead of its own private copy
  of the same logic.
- Inflation-adjusted cost normalization
  (`src/buildguard/features/inflation.py`, Section 10): decomposes nominal
  cost variance into an operational (execution) component and an inflation
  component, with the identity `nominal = operational + inflation` tested
  directly against `evm.cost_variance` and validated against real generated
  data (exact decomposition, zero error).
- Temporal / lifecycle features (`src/buildguard/features/temporal.py`):
  lifecycle position/stage and trend/persistence signals (e.g. consecutive
  months of SPI decline) — captures "persistent deterioration" (Section
  8.2) that a single snapshot's ratios can't express alone.
- `docs/ARCHITECTURE.md`: system overview, package layout, EVM and
  inflation-normalization methodology.
- Ground-truth label derivation (`src/buildguard/data/labels.py`, Section
  6/11): `cost_overrun`/`schedule_delay` resolved from the snapshot
  history against the **inflation-adjusted (real)** final cost, per the
  open question recorded in ADR-0004. In-flight projects get `pd.NA`, never
  a coerced negative.
- Chronological, project-grouped train/calibration/test split
  (`src/buildguard/data/split.py`, Section 12): whole projects, ordered by
  `planned_start_date`, assigned to exactly one split — no project's
  history can appear in more than one. Rationale in
  `docs/adr/0003-temporal-validation.md`.
- Leakage-safe feature pipeline (`src/buildguard/features/pipeline.py`,
  Section 11/28): the single function assembling EVM, inflation, temporal,
  and leakage-safe cumulative change-order features (via
  `pandas.merge_asof(..., direction="backward")`) into one model-ready
  table. Work Packages and Suppliers are deliberately excluded (documented
  limitation: neither table carries a per-row date).
- `docs/LEAKAGE_POLICY.md`: prediction timestamp, feature-availability
  timestamps, label creation, forbidden features, and the automated tests
  that enforce them.
- `tests/leakage/test_pipeline_leakage.py`: the Section 11-mandated
  automated leakage tests — a future-dated change order injected into the
  test fixtures never contributes to an earlier snapshot's features,
  verified directly rather than assumed.
- 99% test coverage on everything shipped so far (`tests/unit/`,
  `tests/contracts/`, `tests/leakage/`); Ruff, Ruff format, and Mypy
  (`--strict`) all clean.
