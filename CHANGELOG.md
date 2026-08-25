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
- 98% test coverage on everything shipped so far (`tests/unit/`,
  `tests/contracts/`); Ruff, Ruff format, and Mypy (`--strict`) all clean.
