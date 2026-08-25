# ADR-0002: Data Privacy Strategy — Synthetic-First, No Real Project Data

**Status:** Accepted

## Context

BuildGuard AI's legacy baseline (GETEC Analytics) worked against real,
confidential construction-portfolio data. A public portfolio repository
cannot publish anything resembling that data — commercially sensitive
budgets, supplier terms, and client exposure — without violating
confidentiality obligations that outlive any single employer relationship.
At the same time, the project's credibility depends on the data *behaving*
like real construction data (realistic EVM dynamics, overrun/delay base
rates, subgroup heterogeneity).

Two local UK NISTA/IPA major-projects annual-report CSVs were made
available during scoping as a possible real-data source, but they are
portfolio-level annual figures, not row-level project time series — they
don't match the data model in Section 8.4 (no `PV`/`EV`/`AC` snapshots), and
their redistribution license has not been independently verified.

## Decision

1. The entire public-facing pipeline — data generation, features, training,
   evaluation, and the deployed app — runs exclusively on a **deterministic
   synthetic portfolio** (`src/buildguard/data/synthetic.py`), seeded and
   reproducible via `make data`.
2. The NISTA/IPA CSVs are kept **local-only**, excluded from Git via
   `.gitignore`, and used — if at all — purely as an informal human
   reference when tuning synthetic-generator parameters (e.g., plausible
   delivery-confidence rating distributions). No code path loads them.
   Documented in `data/external/README.md` and `docs/DATA_PRIVACY.md`.
3. Public economic indicators (e.g., an INCC-style construction inflation
   index) are accessed only through the `EconomicIndexProvider` interface,
   defaulting to `DemoIndexProvider`; any real external index requires a
   documented, verified license before it can back `ExternalLicensedProvider`.

## Alternatives Considered

- **Anonymize and ship a real dataset** — rejected: true anonymization of
  granular financial time series is hard to guarantee, and no explicit
  permission exists for any real project's data.
- **Redistribute the NISTA/IPA CSVs as-is (likely OGL-licensed)** —
  rejected for now: the license has not been independently confirmed for
  these specific files, and the data doesn't fit the project's schema
  anyway. Revisit explicitly (new ADR) if redistribution becomes useful.
- **Skip a synthetic generator and hand-write a small fixture dataset** —
  rejected: too small to support the target scale (100-500 projects,
  Section 8.2) or meaningful slice analysis (Section 18).

## Consequences

- Every model result in this repository is provably free of confidentiality
  risk, which is a precondition for the whole project being publishable.
- The synthetic generator itself becomes a first-class, carefully designed
  component (not a throwaway script) — its realism *is* the project's
  credibility, which is why it gets its own dedicated module, seed
  discipline, and documented relationships (Section 8.2).
- Any future move to real data (e.g., a licensed dataset) requires a new ADR
  and a fresh privacy review — it does not happen by default.
