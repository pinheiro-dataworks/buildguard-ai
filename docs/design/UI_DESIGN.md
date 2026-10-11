# UI Design

Visual design of the Streamlit app (`app/`). Tokens live in `app/theme.py`;
the sidebar is built in `app/Home.py`.

## Brand reference

[`renan-standard.png`](renan-standard.png) is the visual standard: colors,
the dark sidebar, and the personal-brand elements below all come from it.
The logo is `assets/brand/logo_renan_ds.png`.

## Sidebar

Fixed, dark, in this order from top to bottom:

1. **Logo**, centered. Rendered as a plain `<img>` rather than
   `st.image()`, which would add a hover-to-fullscreen control.
2. **Project name**, "BuildGuard AI", in the light sidebar text color.
3. **Navigation**: one bordered, full-width button per page (Executive
   Overview, Project Diagnostic, Scenario Simulator, Model Performance,
   Model Health, About / Governance). Hover and the active page use the
   warm accent.
4. **Footer**: author name, the package version (`buildguard.__version__`),
   and a link to the GitHub repository.

This exact order is why the app uses a custom `st.session_state` router
instead of `st.navigation()`, which always renders its navigation at a
fixed position above any other sidebar content
([ADR-0012](../adr/0012-streamlit-fastapi-boundary.md)).

## Color tokens

| Token (`app/theme.py`) | Value | Usage |
|---|---|---|
| `SIDEBAR_BG` | `#141414` | Sidebar background |
| `SIDEBAR_TEXT` | `#E9E5D8` | Sidebar labels, project title |
| `SIDEBAR_TEXT_DIM` | `#8A8676` | Footer text |
| `SIDEBAR_BORDER` | `#C9C4B0` | Navigation button borders |
| `CANVAS_BG` | `#F5F3EA` | Main content background |
| `SURFACE` | `#FFFFFF` | Cards, panels, chart backgrounds |
| `INK` | `#16171A` | Primary text on light surfaces |
| `ACCENT_WARM` | `#E8531F` | Active navigation, highlights (logo's orange-red band) |
| `ACCENT_COOL` | `#2F8FE0` | Secondary accents (logo's blue band) |

## Risk bands

Three bands, matching `buildguard.models.thresholds.risk_band` (the
optimized thresholds never produce a fourth "critical" band). Each band
pairs a text color with a soft background so the label never relies on
color alone:

| Band | Text | Background |
|---|---|---|
| Low | `#25794F` | `#E3F3EA` |
| Medium | `#A9700A` | `#FBF0DA` |
| High | `#B14A1E` | `#FBE7DC` |

## Copy rules

- Risk is shown as a probability or estimate for a human reviewer, never
  as a verdict such as "the project will overrun"
  (`theme.DECISION_SUPPORT_DISCLAIMER`).
- Every SHAP surface shows the causality disclaimer
  (`CAUSALITY_DISCLAIMER`, same wording in `app/theme.py` and
  `buildguard.explainability.shap`).
- The Scenario Simulator states that it is a what-if tool, not a causal
  model.
- Business impact is labeled "scenario-based estimated impact", with every
  factor shown.
