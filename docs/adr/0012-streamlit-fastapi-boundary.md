# ADR-0012: Streamlit/FastAPI Boundary and UI Architecture

**Status:** Accepted

## Context

BuildGuard needs a FastAPI inference service (`GET /health`, `GET
/version`, `POST /predict/cost-risk`, `POST /predict/schedule-risk`,
`POST /predict/final-cost`) that stays independently runnable, and a
six-page Streamlit app (Executive Overview, Project Diagnostic, Scenario
Simulator, Model Performance, Model Health, About/Governance) where every
page needs real predictions. Both, plus any batch-scoring path, must share
one feature pipeline -- two implementations is how train/serve skew starts.
The app is deployed on Streamlit Community Cloud at zero cost
([ADR-0013](0013-zero-cost-deployment.md)) and follows the sidebar and
branding layout in [`docs/design/UI_DESIGN.md`](../design/UI_DESIGN.md).

## Decision

**One prediction code path, called two ways.** `src/buildguard/api/app.py`'s
three `POST /predict/*` functions are plain, dependency-injected Python
functions (`request: PredictionRequest, state: ServiceState`) -- FastAPI
wraps them for HTTP, and `app/data_access.py`'s `predict_all()` calls the
*exact same functions* directly, in-process, for the Streamlit UI. There
is no second "UI prediction" implementation to drift out of sync with the
API.

**Request schema mirrors the raw table shapes**
(`ProjectInput`/`SnapshotInput`/`ChangeOrderInput`), not a bespoke
"prediction request": each endpoint rebuilds the caller's project through
`buildguard.features.pipeline.build_feature_table` -- the identical
function training uses -- so a caller sends a project's real snapshot
*history*, not just its latest state (trend/streak features need it). The
request is validated twice: once by Pydantic (types, ranges, enum
membership -- an unseen category fails safely as a 422 automatically),
once by `buildguard.data.contracts` (cross-field/dataframe checks like
`completion_after_start` that Pydantic's per-field validation can't
express) -- reusing the same contracts already enforced at ingestion, not
a third validation layer.

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
`st.sidebar` calls sit in the script, so the logo and project name could
not be placed above it. A plain `st.sidebar.button()` per page -- styled
via CSS (`type="primary"` for the active page) and tracked in
`st.session_state` -- gives full control over both the sidebar's order
(logo -> title -> nav -> footer) and the bordered-button look.

**Page content lives in `app/page_modules/`, not the conventional
`pages/`.** A directory literally named `pages` next to the entrypoint
script triggers Streamlit's legacy filename-based auto-discovery
*regardless* of navigation approach -- confirmed empirically twice (once
with the custom router, once with an explicit `st.navigation()` call): it
produced a second, unstyled navigation list stacked on top of the intended
one, with page content not rendering at all in the `st.navigation()` case.
Renaming the directory is the reliable fix; each page still lives in its
own file, exposing one `render()` function.

**Verification: a real headless browser pass, not just `import` smoke
tests.** With trained and calibrated artifacts in place, the FastAPI
service was exercised through 15 `fastapi.testclient.TestClient` contract
tests, and the Streamlit app was launched for real and driven with
Playwright across all six pages, screenshotted, and checked for
console/server errors -- catching two real bugs neither `ruff` nor `mypy`
could: `DataQualityReport.is_clean` being a computed property (not a JSON
field, so `report["data_quality"][name]["is_clean"]` raised `KeyError`
from real `monitoring_report.json` data), and a
duplicate-`approved_budget`-column merge in the portfolio batch-scorer.

## Alternatives Considered

- **`st.navigation()` + `st.Page(callable, ...)`** -- Streamlit's modern,
  supported multi-page API; rejected only for the fixed-position sidebar
  nav issue above, not for any other reason. Worth reconsidering if a
  future Streamlit version supports repositioning it, since it also
  offers real per-page URLs and browser back-button support that the
  custom router doesn't.
- **A second, "UI-only" prediction function bypassing `PredictionRequest`
  validation for speed** -- rejected: a second feature/prediction
  implementation is exactly the train/serve skew this design avoids, and
  the validation overhead is negligible next to model inference time
  (measured p95 latencies: 37.2ms/11.3ms/0.06ms, ADR-0011).
- **Calling the HTTP API from Streamlit instead of in-process** --
  rejected: an HTTP round trip to a co-located process adds latency and a
  second process to keep alive, for zero benefit in a single-host,
  zero-cost deployment.
- **Four risk bands (low/medium/high/critical)** -- rejected;
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
- `app/page_modules/` (not `pages/`) is deliberate -- anyone extending the
  app should keep using this directory, not recreate a `pages/` folder
  next to `Home.py`.
- The app needs the champion artifacts on disk before it can predict. If
  they are missing, `get_service_state()` raises a clean
  `FileNotFoundError`, surfaced as a 503 by the API rather than a crash.
  The deployed app avoids this by committing the artifacts
  ([ADR-0013](0013-zero-cost-deployment.md)).
