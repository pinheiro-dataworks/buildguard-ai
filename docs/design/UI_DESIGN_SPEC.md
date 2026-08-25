# UI Design Spec — Streamlit App (Phase 8)

Not implemented yet — the roadmap (`BUILDGUARD_AI_PROJECT_SCOPE.md`,
Section 45) explicitly puts UI after the ML evaluation design is stable.
This document captures the visual direction agreed during project kickoff so
it isn't lost between now and Phase 8 (Productization).

## Two references, two different jobs

- **`docs/design/prototype-inspiration.html`** — layout/content inspiration
  only: page structure, information density, component types (topbar,
  KPI cards, risk pills, tables). Its blue color system is **not** used.
- **`docs/design/renan-standard.png`** — the authoritative visual/brand
  standard. All colors, the sidebar treatment, and the personal-brand
  elements below come from this reference, not from the prototype HTML.

## Sidebar (fixed, dark)

1. **Top:** `assets/brand/logo_renan_ds.png` (the "renan DS" mark).
2. **Directly below the logo:** the project name, "BuildGuard AI", set in a
   light/cream color against the dark sidebar.
3. **Nav section:** page links as bordered rectangular buttons (thin
   light/cream border, transparent/dark fill, active state gets a filled or
   highlighted border) — one per app page (Executive Overview, Project
   Diagnostic, Scenario Simulator, Model Performance, Model Health, About /
   Governance).
4. **Bottom of sidebar (footer):**
   - App/model **version** string (e.g. `v0.1.0`).
   - A link to the maintainer's **GitHub** — URL to be confirmed by the
     project owner before this ships (do not fabricate a GitHub URL).

## Color tokens (sampled from `renan-standard.png`; refine against the
actual file with a color picker when implementing — these are close
approximations, not final)

| Token | Approx. value | Usage |
|---|---|---|
| `--sidebar-bg` | `#141414` | Sidebar background (near-black) |
| `--sidebar-text` | `#E9E5D8` | Sidebar labels, project title |
| `--sidebar-text-dim` | `#8A8676` | Footer version/GitHub text |
| `--sidebar-border` | `#C9C4B0` | Nav button borders |
| `--canvas-bg` | `#F5F3EA` | Main content background (warm off-white) |
| `--surface` | `#FFFFFF` | Cards/panels |
| `--ink` | `#16171A` | Primary text on light surfaces |
| `--accent-warm` | `#E8531F` | Primary actions / highlights (from the logo's orange-red band) |
| `--accent-cool` | `#2F8FE0` | Secondary / informational accents (from the logo's blue band) |

Risk-band colors (low/medium/high/critical) still need their own
accessible, colorblind-safe palette — to be defined against these base
tokens when the Model Performance / risk-band UI is actually built (see the
`dataviz` design skill for the palette methodology).

## Explicit non-goals for now

- No Streamlit code should be written until the three core ML tasks
  (Section 6) have a stable evaluation design — per the roadmap's
  "do not build the UI before the ML evaluation design is stable" rule.
- Do not hardcode a GitHub URL anywhere (sidebar footer, README badges)
  until the project owner confirms it explicitly.
