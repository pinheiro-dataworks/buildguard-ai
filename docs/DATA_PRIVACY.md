# Data Privacy & Confidentiality Policy

## 1. Hard rule

No confidential employer, client, contractor, supplier, or employee data —
and no real, identifiable construction project — ever enters this public
repository, in code, data files, notebooks, screenshots, or Git history.
This applies to every commit, forever (a later deletion does not remove it
from history).

## 2. What data BuildGuard AI actually uses

| Source | Status | Used by the deployed app? |
|---|---|---|
| Synthetic construction portfolio (`src/buildguard/data/synthetic.py`) | Generated deterministically from a fixed seed (`configs/base.yaml: seed`) | **Yes** — this is the only dataset the public app and shipped models ever see |
| Demo economic index (`DemoIndexProvider`) | Synthetic/illustrative inflation series | **Yes** |
| External licensed economic index (`ExternalLicensedProvider`) | Optional adapter, not implemented by default | No — the public app must run without it |
| `data/external/nista_uk_gmpp/` (UK NISTA/IPA major-projects annual report) | Local-only reference data, excluded from Git (`.gitignore`) | **No** — never loaded by app or training code; see [`data/external/README.md`](../data/external/README.md) |

## 3. Why synthetic data

Real construction cost and schedule data is commercially sensitive by
nature (it reveals contract terms, supplier performance, and client
financial exposure). A public portfolio project cannot ethically or legally
publish that data, so BuildGuard AI's entire public-facing pipeline — data
generation, feature engineering, training, evaluation, and the live demo —
runs on a synthetic portfolio designed to reproduce the *statistical
relationships* construction cost control depends on (e.g., poor CPI →
overrun risk, SPI deterioration → delay risk) without corresponding to any
real project, company, or person.

## 4. Generation guarantees

- **Deterministic:** a fixed seed produces byte-identical output, so the
  dataset is fully reproducible from `make data` — no external download, no
  hidden state.
- **No real entities:** project names, cities, supplier names, and IDs are
  synthesized; any resemblance to a real project or company is coincidental
  and not sourced from any real record.
- **No PII:** the data model (Section 8.4 of `BUILDGUARD_AI_PROJECT_SCOPE.md`)
  contains no personal data fields at all — no names, contacts, or employee
  identifiers.

## 5. External reference data

`data/external/` may contain third-party datasets used purely as a local,
informal reference when calibrating synthetic-data realism (see
[`data/external/README.md`](../data/external/README.md) for current
contents and their license status). These files are excluded from version
control and from every code path reachable by training, inference, or the
deployed app. If a dataset's redistribution license is explicitly verified
in the future, promoting it out of `data/external/` is a deliberate decision
recorded as an ADR — not a default.

## 6. Public economic indicators

Where a real public index (e.g., INCC-style construction inflation index) is
referenced for realism or as an optional adapter, its source and license are
documented before any redistribution, and the public demo path always
defaults to `DemoIndexProvider` so it never depends on unverified
third-party licensing.

## 7. If this policy is ever violated

Any commit found to contain confidential or real project data must be
reported and treated as a security incident: the data is removed, history is
rewritten to purge it, and the incident is documented. As of this writing,
no such incident has occurred.
