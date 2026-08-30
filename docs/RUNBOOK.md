# Runbook

Operational procedures for running, deploying, and maintaining BuildGuard
AI. Not a description of a live deployment — see
[`BUILDGUARD_AI_COMMIT_PLAN.md`](../BUILDGUARD_AI_COMMIT_PLAN.md) for
current deployment status (Session O, not yet done).

## 1. Local setup and full pipeline

```bash
make setup     # uv-managed environment (core deps + dev extra)
make data      # generate the synthetic demo dataset
make train     # train and select the three core champion models (~6-7 min)
make calibrate # calibrate probabilities, optimize thresholds, quantify uncertainty
make evaluate  # final held-out test evaluation, explainability, failure analysis
make monitor   # data quality, drift, and performance monitoring
make test      # unit, integration, leakage, contract tests (coverage gate 85%)
```

**Order matters and is enforced by what each script reads, not just by
convention:** `calibrate` loads `train`'s saved artifacts;
`evaluate`/`monitor` read `calibrate`'s `reports/experiments/calibration_summary.json`.
Running any step out of order fails loudly (a missing file), not
silently.

**`make calibrate` is not idempotent** — running it twice in a row against
an already-calibrated champion artifact silently double-calibrates and
produces wrong comparison numbers (discovered and documented in
`scripts/calibrate.py`'s own docstring while building Session K). Always
run `make train` immediately before `make calibrate`, never `make
calibrate` alone a second time.

## 2. Running the app and API locally

```bash
make api  # FastAPI on http://127.0.0.1:8000, docs at /docs
make app  # Streamlit on http://localhost:8501
```

Both require `make train && make calibrate` to have already produced
`models/*.joblib` and `reports/experiments/calibration_summary.json` —
otherwise every prediction endpoint/page returns a clean 503 /
`FileNotFoundError` rather than crashing (`buildguard.api.dependencies.get_service_state`).

## 3. Deployment (Streamlit Community Cloud — Section 31)

Not yet done (Session O) — this is a manual step; Streamlit Community
Cloud deployment requires a GitHub-authenticated dashboard session,
which nothing running in this repo's automation has access to.

**Why this works with no build step:** Streamlit Community Cloud clones
the repo and runs `app/Home.py` directly — it does not run `make train`/
`make calibrate` first. `models/*.joblib` and
`reports/experiments/calibration_summary.json` are therefore committed
to the repo (deliberately, ~6MB total, Section 49's <100MB target) —
without them, every prediction page would 503 on first load. A locked
`requirements.txt` (`uv export --format requirements.txt --no-dev
--no-hashes --no-emit-project`) is committed alongside `pyproject.toml`/
`uv.lock` for platforms that don't resolve `uv.lock` natively.

**Real incident, first deploy attempt:** the app failed at import with
`ModuleNotFoundError: No module named 'fastapi'`. Root cause: Streamlit
Cloud can install from `pyproject.toml` instead of `requirements.txt`,
and a plain `pip install .` only pulls `[project.dependencies]`, never
optional extras — `fastapi`/`streamlit`/`scikit-learn`/etc. were all
sitting in `ml`/`api`/`app` optional groups at the time. Fixed by
collapsing those groups into `dependencies` directly (every one of them
is genuinely required to run `app/Home.py` now that the API/app both
exist, so the "optional per phase" split no longer reflected reality)
and by having `Home.py` add `src/` to `sys.path` explicitly rather than
assuming `buildguard` itself ends up importable. See Section 6 below.

**Steps:**

1. Push `main` with `models/*.joblib` and `requirements.txt` present
   (already true as of this commit).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   the GitHub account that owns this repo.
3. "New app" → repository `pinheiro-dataworks/buildguard-ai`, branch
   `main`, main file path `app/Home.py`.
4. Deploy. First boot installs ~150 packages from `requirements.txt` —
   expect a few minutes, not instant.
5. Once live, open the app and click through all six pages once —
   Executive Overview's portfolio batch-scoring is the slowest first
   load (regenerates the demo portfolio in memory, `st.cache_data`
   caches it after that).
6. Confirm the Model Health and Model Performance pages render real
   numbers (not a 503/`FileNotFoundError`) before sharing the link.
7. Never upgrade to a paid tier or point at an external database/model
   endpoint — the zero-cost path (Section 31,
   [ADR-0013](adr/0013-zero-cost-deployment.md)) is mandatory for the
   public demo.

**Smoke test after deploying:** re-run the same Playwright check used to
verify the app locally in Session L, pointed at the live URL instead of
`localhost:8501`, checking each page loads and the console has no errors.

## 4. Responding to a monitoring alert

`make monitor`'s `retraining_triggers` (see [`MONITORING.md`](MONITORING.md))
can fire without meaning "retrain now." Follow Section 24's sequence:

1. **Detect** — a trigger fires in `reports/monitoring/monitoring_report.json`.
2. **Investigate** — read the relevant ADR-0011 context first: is this a
   known, expected pattern (e.g. chronological-split feature drift) or a
   genuine new finding? Check `reports/error_analysis/` for the affected
   task.
3. **Validate data** — confirm the input data quality checks are clean
   (`monitoring_report.json: data_quality`) before assuming a model
   problem.
4. **Retrain candidate** — `make train` on updated data if warranted.
5. **Compare vs. champion** — the new candidate must beat the current
   champion on the calibration split before replacing it (same logic
   `scripts/train.py` already applies to every candidate).
6. **Approve** — a human decision, not automatic.
7. **Release** — `make calibrate && make evaluate && make monitor` against
   the new champion, then redeploy.

**Never skip straight to retraining because a trigger fired** — this is
enforced structurally (`scripts/monitor.py` never calls `scripts/train.py`),
not just by this procedure.

## 5. Rollback

Champion artifacts (`models/*.joblib`) and their calibration/evaluation
summaries (`reports/experiments/*.json`) are regenerated by
`train`/`calibrate`/`evaluate` from a fixed seed against a specific git
SHA (recorded in each summary's `git_sha` field). To roll back:

1. `git checkout <previous-good-sha>` for the code.
2. Re-run `make train && make calibrate` to regenerate that commit's
   champions (deterministic given the same seed and code).
3. Redeploy.

There is no separate model registry to roll back independently of code
in this zero-cost design — model and code versions are tied together by
construction.

## 6. Known troubleshooting

- **Deployed app fails with `ModuleNotFoundError` on a package that's
  installed locally.** Streamlit Cloud may have installed from
  `pyproject.toml`'s core `dependencies` only, skipping something that
  used to live in an optional extra. All runtime dependencies now live
  in `dependencies` directly for exactly this reason — if a new one is
  ever added back as an "optional" extra, expect this failure mode to
  return for whichever page imports it first.
- **Streamlit shows a duplicate, unstyled navigation list.** Caused by a
  directory literally named `pages/` next to `app/Home.py` — Streamlit
  auto-discovers it regardless of navigation approach. Page content
  lives in `app/page_modules/` specifically to avoid this
  ([ADR-0012](adr/0012-streamlit-fastapi-boundary.md)); never rename it
  back to `pages/`.
- **`mypy` fails on a new third-party import in `src/`.** Add it to
  `pyproject.toml`'s `[[tool.mypy.overrides]]` `ignore_missing_imports`
  list rather than adding inline `# type: ignore` comments throughout.
- **A CI security-scan failure on a dependency you can't upgrade.** Check
  whether the fix is blocked by another dependency's own version pin
  (`uv lock --upgrade-package <name> --verbose` shows the real
  constraint chain) before assuming it's fixable — see
  `.github/workflows/security.yml`'s documented `cryptography` exception
  for a worked example.
