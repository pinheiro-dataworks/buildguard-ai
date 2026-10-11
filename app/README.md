# App (Streamlit)

The public BuildGuard AI dashboard. `Home.py` is the entry point
(`make app`); it renders a custom sidebar router and one page per module
under `page_modules/`:

| Page | Module |
|---|---|
| Executive Overview | `page_modules/executive_overview.py` |
| Project Diagnostic | `page_modules/project_diagnostic.py` |
| Scenario Simulator | `page_modules/scenario_simulator.py` |
| Model Performance | `page_modules/model_performance.py` |
| Model Health | `page_modules/model_health.py` |
| About / Governance | `page_modules/about_governance.py` |

`data_access.py` loads the committed reports and calls the FastAPI endpoint
functions in-process, so the app and the API share one prediction code
path. `theme.py` holds the color tokens and CSS described in
[`docs/design/UI_DESIGN.md`](../docs/design/UI_DESIGN.md).

Pages live in `page_modules/` rather than `pages/` on purpose: Streamlit
auto-discovers a directory literally named `pages/` and adds its own
navigation list next to the custom one. See
[ADR-0012](../docs/adr/0012-streamlit-fastapi-boundary.md).
