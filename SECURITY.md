# Security Policy

## Reporting a Vulnerability

If you discover a security issue in BuildGuard AI, please report it
privately via GitHub's "Report a vulnerability" flow on this repository
(Security tab) rather than opening a public issue. Do not include exploit
details in a public channel until a fix has been released.

## Scope & Data

- This repository contains **no proprietary, confidential, or personally
  identifiable data**. All demo data is synthetically generated
  (`src/buildguard/data/synthetic.py`). See
  [`docs/DATA_PRIVACY.md`](docs/DATA_PRIVACY.md).
- No secrets, API keys, or cloud credentials are ever committed. Local
  configuration lives in `.env` (gitignored); `.env.example` documents the
  expected variables with no real values.
- The public deployment (Streamlit Community Cloud) serves only the
  synthetic demo dataset and packaged demo model — never real project data.

## Practices

- Dependencies are pinned via `uv.lock` and installed from PyPI only.
- CI includes lint (Ruff), type-checking (Mypy), and automated tests before
  any merge; dependency and static security scanning (`pip-audit`, Bandit)
  are part of the CI pipeline (see `.github/workflows/`).
- API payloads are validated with Pydantic schemas; file uploads (if any) are
  restricted by type and size.
- No arbitrary code execution paths are exposed to user input.
