# Models

The three champion artifacts produced by `make train` and `make calibrate`:

| File | Task | Contents |
|---|---|---|
| `cost_overrun_champion.joblib` | Cost-overrun risk | Random Forest pipeline wrapped with isotonic calibration |
| `schedule_delay_champion.joblib` | Schedule-delay risk | LightGBM pipeline wrapped with isotonic calibration |
| `final_cost_champion.joblib` | Final cost | Deterministic EVM estimate at completion (`BAC / CPI`), no learned parameters |

They are committed (about 6 MB in total) because Streamlit Community Cloud
deploys straight from the repository with no build or training step
([ADR-0013](../docs/adr/0013-zero-cost-deployment.md)). They are fully
reproducible: `make train && make calibrate` regenerates them from the
fixed seed in `configs/base.yaml`.

`make package` bundles them with a `MANIFEST.json` carrying each model's
version metadata (`model_name`, `semantic_version`, `training_date`,
`data_version`, `git_sha`, `metrics`, `threshold`,
`calibration_method`) into `dist/` for distribution as a release asset.

Run `make calibrate` only on a freshly trained artifact: calibrating an
already-calibrated model silently double-calibrates it (see
[`docs/RUNBOOK.md`](../docs/RUNBOOK.md)).
