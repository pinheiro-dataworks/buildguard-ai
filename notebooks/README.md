# Notebooks

Exploration, EDA, and research only — per the notebook policy
(`BUILDGUARD_AI_PROJECT_SCOPE.md` Section 34): notebooks must run
top-to-bottom with deterministic seeds, avoid hidden state, import functions
from `src/buildguard/` rather than redefining logic inline, carry written
conclusions, and avoid dumping massive raw output. Once a method is
accepted, it moves into `src/buildguard/` and the notebook is updated to
call it.

- `02_eda.ipynb`: portfolio composition, budget/EVM-ratio distributions,
  and realized cost-overrun/schedule-delay rates -- run top-to-bottom,
  written conclusions included, figures saved to `reports/figures/`.

Not built: `01_data_understanding.ipynb` (its ground largely overlaps
`02_eda.ipynb` once that one existed), `03_feature_research.ipynb`,
`04_model_research.ipynb` -- the feature and model research those two
would have captured happened directly in `src/buildguard/features/`,
`src/buildguard/models/`, and the ADRs (`docs/adr/0005`-`0010`) instead.
