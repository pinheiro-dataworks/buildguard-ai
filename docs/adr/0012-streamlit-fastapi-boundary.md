# ADR-0012: Streamlit/FastAPI Boundary and UI Architecture

**Status:** Accepted

## Context

Section 29 requires a FastAPI inference service (`GET /health`, `GET
/version`, `POST /predict/cost-risk`, `POST /predict/schedule-risk`,
`POST /predict/final-cost`) that "must remain independently runnable,"
while also saying the Streamlit app "may call it in-process (zero cost)."
Section 30 requires six pages (Executive Overview, Project Diagnostic,
Scenario Simulator, Model Performance, Model Health, About/Governance),
each needing real predictions, and Section 28 requires the API and any
batch-scoring path to share one feature pipeline, never two. Section 33's
suggested layout is `app/ Home.py, pages/` -- a real, deployable multi-page
app on Streamlit Community Cloud, following `docs/design/UI_DESIGN_SPEC.md`'s
exact sidebar/branding direction.

## Decision

**One prediction code path, called two ways.** `src/buildguard/api/app.py`'s
three `POST /predict/*` functions are plain, dependency-injected Python
functions (`request: PredictionRequest, state: ServiceState`) -- FastAPI
wraps them for HTTP, and `app/data_access.py`'s `predict_all()` calls the
*exact same functions* directly, in-process, for the Streamlit UI. There
is no second "UI prediction" implementation to drift out of sync with the
API (Section 28).

**Request schema mirrors the raw table shapes**
(`ProjectInput`/`SnapshotInput`/`ChangeOrderInput`), not a bespoke
"prediction request": each endpoint rebuilds the caller's project through
`buildguard.features.pipeline.build_feature_table` -- the identical
function training uses -- so a caller sends a project's real snapshot
*history*, not just its latest state (trend/streak features need it). The
request is validated twice: once by Pydantic (types, ranges, enum
membership -- Section 48's "unseen categories" fails safely as a 422
automatically), once by `buildguard.data.contracts` (cross-field/dataframe
checks like `completion_after_start` that Pydantic's per-field validation
can't express) -- reusing the same contracts already enforced at ingestion
(Section 8.5), not a third validation layer.

**Portfolio-wide views batch-score instead of calling the single-prediction
path 400 times.** The Executive Overview page scores every project's
latest snapshot in one vectorized pass through `build_feature_table` +
`model.predict_proba`, the same pattern `scripts/evaluate.py`/`monitor.py`
already use -- a legitimate different access pattern (batch vs.
single-prediction) sharing the same feature pipeline and champion
artifacts, not a second inference path.

**A custom sidebar router, not `st.navigation()`.** Tried first, and
rejected after empirical testing: `st.navigation()`'s sidebar nav widget
always renders at a fixed position regardless of where surrounding
`st.sidebar` calls sit in the script, so the logo/project-name could not
be placed above it as `UI_DESIGN_SPEC.md` requires. A plain
`st.sidebar.button()` per page -- styled via CSS (`type="primary"` for the
active page) and tracked in `st.session_state` -- gives full control over
both the sidebar's order (logo -> title -> nav -> footer) and the
bordered-rectangle button look the spec calls for.

**Page content lives in `app/page_modules/`, not Section 33's suggested
`pages/`.** A directory literally named `pages` next to the entrypoint
script triggers Streamlit's legacy filename-based auto-discovery
*regardless* of navigation approach -- confirmed empirically twice (once
with the custom router, once with an explicit `st.navigation()` call): it
produced a second, unstyled navigation list stacked on top of the intended
one, with page content not rendering at all in the `st.navigation()` case.
Renaming the directory is the reliable fix; each page still lives in its
own file, exposing one `render()` function, so the one-file-per-page
structure Section 33 intends is otherwise unchanged.

**Verification: a real headless browser pass, not just `import` smoke
tests.** `make train && make calibrate` were already run (their artifacts
are committed); the FastAPI service was exercised through 15
`fastapi.testclient.TestClient` contract tests, and the Streamlit app was
launched for real and driven with Playwright across all six pages,
screenshotted, and checked for console/server errors -- catching two real
bugs neither `ruff` nor `mypy` could: `DataQualityReport.is_clean` being a
computed property (not a JSON field, so `report["data_quality"][name]["is_clean"]`
raised `KeyError` from real `monitoring_report.json` data), and a
duplicate-`approved_budget`-column merge in the portfolio batch-scorer.

## Alternatives Considered

- **`st.navigation()` + `st.Page(callable, ...)`** -- Streamlit's modern,
  supported multi-page API; rejected only for the fixed-position sidebar
  nav issue above, not for any other reason. Worth reconsidering if a
  future Streamlit version supports repositioning it, since it also
  offers real per-page URLs and browser back-button support that the
  custom router doesn't.
- **A second, "UI-only" prediction function bypassing `PredictionRequest`
  validation for speed** -- rejected: Section 28 forbids a second feature/
  prediction implementation, and the validation overhead is negligible
  next to model inference time (Section 23's own measured latencies:
  20.8ms/5.6ms/0.03ms p95).
- **Calling the deployed HTTP API from Streamlit instead of in-process**
  -- rejected per Section 29's explicit guidance; an HTTP round trip to a
  co-located process adds latency and a second process to keep alive for
  zero benefit in the zero-cost single-host deployment (Section 31).
- **Four risk bands (low/medium/high/critical), matching
  `docs/design/prototype-inspiration.html`'s own palette** -- rejected;
  `models.thresholds.risk_band()` (ADR-0011) only ever produces three
  bands, and inventing a fourth for the UI alone would mean the UI
  claiming a distinction the underlying model doesn't make.

## Consequences

- Any future change to `PredictionRequest`/`build_feature_table` changes
  behavior identically for the API and the UI -- there's only one place to
  update, and no risk of the two drifting apart the way train/serve skew
  usually happens.
- The custom sidebar router means giving up `st.navigation()`'s per-page
  URLs; deep-linking to a specific page (e.g. from README screenshots or
  an external link) is not supported today -- worth revisiting if that
  becomes a real need.
- `app/page_modules/` (not `pages/`) is a deliberate, documented deviation
  from Section 33's suggested name -- anyone extending the app should keep
  using this directory, not recreate a `pages/` folder next to `Home.py`.
- Deployment to Streamlit Community Cloud (Session O) must run
  `make train && make calibrate` (or ship their outputs) before the app
  can start -- `get_service_state()` raises a clean `FileNotFoundError` ->
  503 otherwise, per ADR-0012's own error-handling design, not a crash.
