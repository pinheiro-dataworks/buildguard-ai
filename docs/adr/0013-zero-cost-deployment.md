# ADR-0013: Zero-Cost Deployment Architecture

**Status:** Accepted

## Context

"Custo deve ser zero" (cost must be zero) was a hard constraint stated at
project kickoff, before any code existed, and it has shaped nearly every
other decision in this project: local SQLite MLflow instead of a hosted
tracking server ([ADR-0006](0006-model-selection.md)'s mention), synthetic
data instead of a paid dataset license, in-process Streamlit/FastAPI
calls instead of two hosted services ([ADR-0012](0012-streamlit-fastapi-boundary.md)).
Section 31 names the mandatory public path explicitly; Section 52
requires any enterprise-scale reference architecture to be clearly
labeled as **not** what's actually deployed. This ADR is the one place
that decision gets written down formally, with alternatives, rather than
only implied by the rest of the codebase.

## Decision

**The mandatory public path, end to end:**

```
GitHub (public repo) -> GitHub Actions (lint/test/type-check) -> Streamlit Community Cloud
                                                                    +-- BuildGuard UI
                                                                    +-- packaged models (models/*.joblib)
                                                                    +-- in-process prediction service (Section 29)
                                                                    +-- synthetic demo dataset
```

- **CI/CD: GitHub Actions**, free and unlimited for public repositories
  -- no cost regardless of how often the pipeline runs
  ([`ci.yml`](../../.github/workflows/ci.yml), [`security.yml`](../../.github/workflows/security.yml)).
- **Hosting: Streamlit Community Cloud**, free tier, serving the app
  directly from the GitHub repo -- no separate deploy step or paid
  compute.
- **Experiment tracking: local, file-based MLflow** (SQLite backend,
  `sqlite:///mlruns/mlflow.db`) -- a single file, not a hosted tracking
  server.
- **Model serving: in-process, not a hosted model endpoint.** The
  FastAPI service and the Streamlit app both run the champion models
  directly in the same process/container that serves the UI -- no
  SageMaker/Vertex/managed-endpoint equivalent.
- **No paid database.** All state is either a committed artifact
  (`reports/experiments/*.json`, `models/*.joblib`) or regenerated
  deterministically from a fixed seed.
- **No LLM, no monitoring SaaS.** `scripts/monitor.py` is plain Python
  against the real portfolio and champions -- not Datadog/New Relic/an
  LLM-based analysis layer.

**Section 52's enterprise reference architecture is a separate,
clearly-labeled document, never this one.** If a `docs/architecture/aws-reference.md`
is ever written, it must carry the header "REFERENCE ARCHITECTURE -- NOT
THE PUBLIC DEMO" and must never be described as deployed unless it
actually is -- and if ever demoed, torn down immediately with budget
alerts in place (Section 31).

## Alternatives Considered

- **A paid always-on host (Render/Railway/Fly.io paid tier, a small
  cloud VM)** -- rejected outright by the zero-cost constraint; none of
  these are needed given Streamlit Community Cloud's free tier already
  satisfies Section 31's public-path requirement.
- **A hosted MLflow tracking server** (Databricks-managed, or a
  self-hosted server on a paid VM) -- rejected for the same reason;
  local SQLite gives identical tracking guarantees (run_id, params,
  metrics, git SHA -- Section 25) for a single-maintainer project with
  no concurrent-writer requirement.
- **A separately hosted FastAPI deployment** (its own free-tier
  container, e.g. Render's free web service) reached over HTTP from
  Streamlit -- rejected per Section 29's own guidance and
  [ADR-0012](0012-streamlit-fastapi-boundary.md): an HTTP round trip to
  a service that could just as well run in-process adds latency and a
  second process to keep alive for no benefit in a single-host
  deployment; the FastAPI app remains independently runnable
  (`make api`) for anyone who does want it separately hosted later.
- **GitHub Actions self-hosted runners** -- unnecessary; hosted runners
  are free and sufficient for this project's CI workload (Section 59:
  "GitHub Actions standard hosted runners for public repos" is
  explicitly the compatible baseline as of writing).

## Consequences

- Every architectural choice in this project is implicitly bounded by
  "would this survive on Streamlit Community Cloud's free tier" --
  model artifact size (Section 49's <100MB target), no background
  workers beyond what Streamlit itself manages, no persistent database
  connections.
- Free-tier policies change over time; Section 59 explicitly requires
  re-verifying current limits immediately before the actual Session O
  deployment, not trusting this ADR's description as permanently
  accurate.
- Because there is no hosted database, every piece of "state" this
  project has (calibration decisions, evaluation results, monitoring
  reports) is either a committed JSON artifact or deterministically
  regenerable -- which is also why reproducibility (Section 26) and
  zero-cost hosting end up being the same design decision in practice,
  not two independent ones.
- If a future need genuinely requires a paid service, that is a decision
  to make explicitly and document in a new ADR -- not a silent drift away
  from this one.
