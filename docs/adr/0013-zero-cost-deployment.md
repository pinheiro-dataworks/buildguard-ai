# ADR-0013: Zero-Cost Deployment Architecture

**Status:** Accepted

## Context

Zero recurring cost is a hard constraint of this project, set before any
code existed, and it has shaped nearly every other decision: local SQLite
MLflow instead of a hosted tracking server
([ADR-0006](0006-model-selection.md)'s mention), synthetic data instead of
a paid dataset license, in-process Streamlit/FastAPI calls instead of two
hosted services ([ADR-0012](0012-streamlit-fastapi-boundary.md)). Any
enterprise-scale reference architecture must also be clearly labeled as
**not** what is actually deployed. This ADR is the one place that decision
gets written down formally, with alternatives, rather than only implied by
the rest of the codebase.

## Decision

**The public path, end to end:**

```
GitHub (public repo) -> GitHub Actions (lint/test/type-check) -> Streamlit Community Cloud
                                                                    +-- BuildGuard UI
                                                                    +-- packaged models (models/*.joblib)
                                                                    +-- in-process prediction service
                                                                    +-- synthetic demo dataset
```

- **CI/CD: GitHub Actions**, free for public repositories -- no cost
  regardless of how often the pipeline runs
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

**An enterprise reference architecture, if ever written, is a separate,
clearly labeled document, never this one.** It must carry the header
"REFERENCE ARCHITECTURE -- NOT THE PUBLIC DEMO" and must never be
described as deployed unless it actually is -- and if any part of it is
ever demoed on a paid cloud, it is torn down immediately, with budget
alerts in place.

## Alternatives Considered

- **A paid always-on host (Render/Railway/Fly.io paid tier, a small
  cloud VM)** -- rejected outright by the zero-cost constraint; none of
  these are needed given Streamlit Community Cloud's free tier already
  hosts the full public path.
- **A hosted MLflow tracking server** (Databricks-managed, or a
  self-hosted server on a paid VM) -- rejected for the same reason;
  local SQLite gives identical tracking guarantees (run_id, params,
  metrics, git SHA) for a single-maintainer project with no
  concurrent-writer requirement.
- **A separately hosted FastAPI deployment** (its own free-tier
  container, e.g. Render's free web service) reached over HTTP from
  Streamlit -- rejected per [ADR-0012](0012-streamlit-fastapi-boundary.md):
  an HTTP round trip to a service that could just as well run in-process
  adds latency and a second process to keep alive for no benefit in a
  single-host deployment; the FastAPI app remains independently runnable
  (`make api`) for anyone who does want it separately hosted later.
- **GitHub Actions self-hosted runners** -- unnecessary; GitHub-hosted
  runners are free for public repositories and sufficient for this
  project's CI workload.

## Consequences

- Every architectural choice in this project is implicitly bounded by
  "would this survive on Streamlit Community Cloud's free tier" --
  model artifact size (< 100MB in total), no background workers beyond
  what Streamlit itself manages, no persistent database connections.
- Free-tier policies change over time; current limits have to be
  re-verified before relying on this ADR's description for a new
  deployment.
- Because there is no hosted database, every piece of "state" this
  project has (calibration decisions, evaluation results, monitoring
  reports) is either a committed JSON artifact or deterministically
  regenerable -- which is also why reproducibility and zero-cost hosting
  end up being the same design decision in practice, not two independent
  ones.
- If a future need genuinely requires a paid service, that is a decision
  to make explicitly and document in a new ADR -- not a silent drift away
  from this one.

**Real deployment incident (first live attempt):** the app failed at
import with `ModuleNotFoundError: No module named 'fastapi'`. Streamlit
Community Cloud installs from `pyproject.toml` when it decides to skip
`requirements.txt`, and a plain `pip install .` only pulls
`[project.dependencies]`, never optional extras -- `fastapi`/`streamlit`/
`scikit-learn`/etc. were split into `ml`/`api`/`app` optional groups at
the time (dependencies had been added incrementally as each layer was
built, and the split was never revisited once every layer existed in one
deployed app). Fixed by collapsing all of them into `dependencies`
directly, and by having `app/Home.py` add `src/` to `sys.path` explicitly
rather than assuming `buildguard` ends up importable via whatever install
path Streamlit Cloud happens to choose. The lesson generalizes: a
dependency-group split that made sense for incremental development
stops being safe the moment a single deployed entrypoint needs all of
the groups at once.
