# ADR-0001: Project Architecture & Repository Layout

**Status:** Accepted

## Context

BuildGuard AI must read as a small, professionally engineered ML product —
not a notebook collection or a dashboard-only demo — while staying
reproducible on zero recurring cost. That requires a repository structure
that separates concerns the way a production ML system does: data
contracts, feature engineering shared between train and serve, model
training, evaluation, explainability, monitoring, an API layer, and a UI
layer, each independently testable.

## Decision

Adopt the `src/`-layout Python package structure defined in
`BUILDGUARD_AI_PROJECT_SCOPE.md` Section 33:

- `src/buildguard/` — the installable package (`data`, `features`, `models`,
  `evaluation`, `explainability`, `monitoring`, `api`, `utils`), consumed by
  both the FastAPI service and the Streamlit app so feature logic is never
  duplicated between training and inference (Section 28).
- `app/` — Streamlit UI only; no business logic lives here.
- `scripts/` — thin CLI entry points (`generate_data.py`, `train.py`,
  `evaluate.py`, `monitor.py`, `package_model.py`) that call into
  `src/buildguard/`.
- `configs/` — externalized YAML configuration; no scattered magic numbers.
- `tests/` — mirrors the concern split (`unit`, `integration`, `contracts`,
  `leakage`, `monitoring`, `api`) so each testing layer in Section 35 has an
  unambiguous home.
- `notebooks/` — exploration only, per the notebook policy (Section 34);
  accepted logic graduates into `src/buildguard/`.

Package management: [`uv`](https://docs.astral.sh/uv/) with a committed
`uv.lock`, Python 3.11 pinned via `.python-version`. Ruff (lint + format)
and Mypy (`strict = true`) are configured in `pyproject.toml` from the first
commit, rather than retrofitted later.

## Alternatives Considered

- **Flat `buildguard/` package at repo root (no `src/` layout)** — rejected:
  the `src/` layout prevents accidentally importing the package from the
  repo root without installation, which has previously caused
  train/serve import-path bugs in similar projects.
- **Monorepo-style `packages/api`, `packages/app`, `packages/ml`** —
  rejected as over-engineered for a single-package portfolio project; adds
  packaging overhead with no corresponding benefit at this scale.
- **Poetry instead of uv** — rejected: uv is faster, has first-class Python
  version management (`uv python`), and is increasingly the default choice
  for new Python projects as of 2026.

## Consequences

- Every new capability has one obvious home; the mapping from
  `BUILDGUARD_AI_PROJECT_SCOPE.md` sections to folders stays legible to a
  reviewer.
- `mypy --strict` from day one is stricter than most portfolio projects
  attempt — this is intentional signal, and it forward-loads a small amount
  of typing overhead onto every future PR.
- Because `src/buildguard/` is shared by API, app, and scripts, a train/serve
  consistency test (Section 28, Section 35) becomes possible and is required
  before v1.0.0.
